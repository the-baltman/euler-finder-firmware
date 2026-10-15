// Simulador de un IMU para las pruebas de host. Independiente del código bajo prueba:
// la verdad se genera con matrices de rotación en double; el firmware usa cuaterniones en float.
// Los ruidos y sesgos son SUPUESTOS DE SIMULACIÓN [estimado: simulador], no mediciones del sensor real.
#pragma once
#include <cmath>
#include <random>
#include "../../src/core/vec3.h"

namespace sim {

constexpr double kPi = 3.14159265358979323846;

using euler::Vec3;

struct Mat3 {
  double m[3][3];
};

inline Mat3 ident() { return {{{1, 0, 0}, {0, 1, 0}, {0, 0, 1}}}; }
inline Mat3 mul(const Mat3& a, const Mat3& b) {
  Mat3 r{};
  for (int i = 0; i < 3; i++)
    for (int j = 0; j < 3; j++)
      for (int k = 0; k < 3; k++) r.m[i][j] += a.m[i][k] * b.m[k][j];
  return r;
}
inline Mat3 transpose(const Mat3& a) {
  Mat3 r{};
  for (int i = 0; i < 3; i++)
    for (int j = 0; j < 3; j++) r.m[i][j] = a.m[j][i];
  return r;
}
inline Mat3 rotX(double a) { return {{{1, 0, 0}, {0, std::cos(a), -std::sin(a)}, {0, std::sin(a), std::cos(a)}}}; }
inline Mat3 rotY(double a) { return {{{std::cos(a), 0, std::sin(a)}, {0, 1, 0}, {-std::sin(a), 0, std::cos(a)}}}; }
inline Mat3 rotZ(double a) { return {{{std::cos(a), -std::sin(a), 0}, {std::sin(a), std::cos(a), 0}, {0, 0, 1}}}; }

inline void apply(const Mat3& r, const double v[3], double out[3]) {
  for (int i = 0; i < 3; i++) out[i] = r.m[i][0] * v[0] + r.m[i][1] * v[1] + r.m[i][2] * v[2];
}

// Orientación cuerpo->mundo con el eje de apuntado P en (az horario, el) y alabeo 'roll' sobre P.
// pointing_flat = true  : P = +y del cuerpo, pantalla hacia arriba (montaje plano).
// pointing_flat = false : P = -z del cuerpo, pantalla vertical con +y hacia arriba (montaje vertical).
inline Mat3 attitude(bool pointing_flat, double az_deg, double el_deg, double roll_deg) {
  const double d2r = kPi / 180.0;
  Mat3 r0;
  if (pointing_flat) {
    // x_b -> -y_w, y_b -> +x_w, z_b -> +z_w
    r0 = {{{0, 1, 0}, {-1, 0, 0}, {0, 0, 1}}};
  } else {
    // x_b -> -y_w, y_b -> +z_w, z_b -> -x_w
    r0 = {{{0, 0, -1}, {-1, 0, 0}, {0, 1, 0}}};
  }
  Mat3 pitch = rotX(el_deg * d2r);
  // El alabeo gira alrededor de P (y en plano, z en vertical), no cambia az/el de P.
  Mat3 roll = pointing_flat ? rotY(roll_deg * d2r) : rotZ(roll_deg * d2r);
  return mul(rotZ(-az_deg * d2r), mul(r0, mul(pitch, roll)));
}

inline Vec3 pointingAxis(bool pointing_flat) { return pointing_flat ? Vec3{0, 1, 0} : Vec3{0, 0, -1}; }

// "Verdad" de az/el del eje P para una orientación.
inline void truePointing(const Mat3& r, bool pointing_flat, double* az_deg, double* el_deg) {
  double p_b[3] = {0, pointing_flat ? 1.0 : 0.0, pointing_flat ? 0.0 : -1.0};
  double p_w[3];
  apply(r, p_b, p_w);
  *az_deg = -std::atan2(p_w[1], p_w[0]) * 180.0 / kPi;
  *el_deg = std::asin(p_w[2]) * 180.0 / kPi;
}

struct NoiseModel {
  double gyro_sigma_dps = 0.1;    // [estimado: simulador]
  double accel_sigma_g = 0.003;   // [estimado: simulador]
  double gyro_scale_err = 0.005;  // [estimado: simulador] error de escala del giroscopio (0.5 %)
  double accel_dist_g = 0.05;     // [estimado: simulador] aceleración lineal de la mano mientras se mueve
};

// Genera lecturas de IMU a partir de una secuencia de orientaciones verdaderas.
class Imu {
 public:
  Imu(unsigned seed, Vec3 bias_dps, NoiseModel n) : rng_(seed), bias_(bias_dps), n_(n) {}
  // r_prev -> r_now en dt segundos. 'moving' activa la perturbación lineal del acelerómetro.
  void sample(const Mat3& r_prev, const Mat3& r_now, double dt, bool moving, Vec3* gyro_dps, Vec3* accel_g) {
    Mat3 rel = mul(transpose(r_prev), r_now);
    // vee((R - R^T)/2) / dt: velocidad angular en el cuerpo, exacta a primer orden.
    double w[3] = {(rel.m[2][1] - rel.m[1][2]) / 2 / dt, (rel.m[0][2] - rel.m[2][0]) / 2 / dt,
                   (rel.m[1][0] - rel.m[0][1]) / 2 / dt};
    std::normal_distribution<double> g01(0.0, 1.0);
    const double r2d = 180.0 / kPi;
    gyro_dps->x = static_cast<float>(w[0] * r2d * (1 + n_.gyro_scale_err) + bias_.x + g01(rng_) * n_.gyro_sigma_dps);
    gyro_dps->y = static_cast<float>(w[1] * r2d * (1 + n_.gyro_scale_err) + bias_.y + g01(rng_) * n_.gyro_sigma_dps);
    gyro_dps->z = static_cast<float>(w[2] * r2d * (1 + n_.gyro_scale_err) + bias_.z + g01(rng_) * n_.gyro_sigma_dps);
    double ez[3] = {0, 0, 1}, up_b[3];
    apply(transpose(r_now), ez, up_b);
    double dist = moving ? n_.accel_dist_g : 0.0;
    accel_g->x = static_cast<float>(up_b[0] + g01(rng_) * n_.accel_sigma_g + g01(rng_) * dist);
    accel_g->y = static_cast<float>(up_b[1] + g01(rng_) * n_.accel_sigma_g + g01(rng_) * dist);
    accel_g->z = static_cast<float>(up_b[2] + g01(rng_) * n_.accel_sigma_g + g01(rng_) * dist);
  }
  Vec3 randomBias(double max_dps) {
    std::uniform_real_distribution<double> u(-max_dps, max_dps);
    return {static_cast<float>(u(rng_)), static_cast<float>(u(rng_)), static_cast<float>(u(rng_))};
  }

 private:
  std::mt19937 rng_;
  Vec3 bias_;
  NoiseModel n_;
};

inline NoiseModel noNoise() { return {0, 0, 0, 0}; }

inline double smoothstep(double t) {
  if (t <= 0) return 0;
  if (t >= 1) return 1;
  return t * t * (3 - 2 * t);
}

}  // namespace sim
