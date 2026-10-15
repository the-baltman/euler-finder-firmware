// Fusión de 6 ejes: signos, convergencia, rechazo de aceleración lineal. Barrido de 24 semillas.
#include "check.h"
#include "sim.h"
#include "../../src/core/fusion.h"
#include "../../src/config/tuning.h"

using namespace euler;

constexpr int kSeeds = 24;
constexpr double kDt = 0.01;

static Vec3 toV(const double v[3]) { return {static_cast<float>(v[0]), static_cast<float>(v[1]), static_cast<float>(v[2])}; }

// Un cuerpo girando limpio alrededor de "arriba" en sentido horario debe SUBIR el rumbo (+).
static void testClockwiseIsPositive() {
  for (int flat = 0; flat < 2; flat++) {
    sim::Mat3 r = sim::attitude(flat, 0, 10, 0);
    Fusion6 f;
    double up_b[3], ez[3] = {0, 0, 1};
    sim::apply(sim::transpose(r), ez, up_b);
    CHECK(f.initFromAccel(toV(up_b)));
    Pointing p0 = f.pointing(sim::pointingAxis(flat));
    // 30° horarios en 3 s, a 10 °/s, sin ruido
    sim::Mat3 prev = r;
    sim::Imu imu(1, {0, 0, 0}, sim::noNoise());
    for (int i = 1; i <= 300; i++) {
      sim::Mat3 now = sim::attitude(flat, 30.0 * i / 300, 10, 0);
      Vec3 g, a;
      imu.sample(prev, now, kDt, false, &g, &a);
      f.update(g * kDeg2Rad, a, kDt);
      prev = now;
    }
    Pointing p1 = f.pointing(sim::pointingAxis(flat));
    CHECK_NEAR(wrap180(p1.az_deg - p0.az_deg), 30.0, 0.2);
    CHECK_NEAR(p1.el_deg, 10.0, 0.2);
  }
}

// Subir el eje de apuntado sube la altura.
static void testElevationUp() {
  for (int flat = 0; flat < 2; flat++) {
    sim::Mat3 prev = sim::attitude(flat, 0, 0, 0);
    Fusion6 f;
    double up_b[3], ez[3] = {0, 0, 1};
    sim::apply(sim::transpose(prev), ez, up_b);
    f.initFromAccel(toV(up_b));
    sim::Imu imu(1, {0, 0, 0}, sim::noNoise());
    for (int i = 1; i <= 200; i++) {
      sim::Mat3 now = sim::attitude(flat, 0, 20.0 * i / 200, 0);
      Vec3 g, a;
      imu.sample(prev, now, kDt, false, &g, &a);
      f.update(g * kDeg2Rad, a, kDt);
      prev = now;
    }
    CHECK_NEAR(f.pointing(sim::pointingAxis(flat)).el_deg, 20.0, 0.2);
  }
}

// Arranca con la gravedad mal estimada (25° de error): la corrección debe llevarla a la real.
static void testConvergenceFromTiltError() {
  double worst = 0;
  for (int seed = 1; seed <= kSeeds; seed++) {
    sim::Mat3 truth = sim::attitude(true, 0, 15, 0);
    sim::Mat3 wrong = sim::attitude(true, 0, 15 + 25, 5);  // otra inclinación
    double up_w[3], ez[3] = {0, 0, 1};
    sim::apply(sim::transpose(wrong), ez, up_w);
    Fusion6 f;
    f.initFromAccel(toV(up_w));
    sim::Imu imu(seed, {0, 0, 0}, {});
    for (int i = 0; i < 1000; i++) {  // 10 s quieto
      Vec3 g, a;
      imu.sample(truth, truth, kDt, false, &g, &a);
      f.update(g * kDeg2Rad, a, kDt);
    }
    double az, el;
    sim::truePointing(truth, true, &az, &el);
    // Compara solo la altura (el rumbo de partida es arbitrario).
    double err = std::fabs(f.pointing({0, 1, 0}).el_deg - el);
    if (err > worst) worst = err;
    CHECK(err < 0.5);
  }
  std::printf("  convergencia desde 25 grados de error: peor caso %.3f grados (%d semillas) [estimado: simulador]\n", worst, kSeeds);
}

// Una ráfaga de aceleración lineal (1.6 g) no debe inclinar la estimación.
static void testLinearAccelGate() {
  sim::Mat3 truth = sim::attitude(true, 0, 15, 0);
  double up_b[3], ez[3] = {0, 0, 1};
  sim::apply(sim::transpose(truth), ez, up_b);
  Fusion6 f;
  f.initFromAccel(toV(up_b));
  double el0 = f.pointing({0, 1, 0}).el_deg;
  for (int i = 0; i < 100; i++) {  // 1 s de "golpe": |a| = 1.6 g en una dirección ajena
    Vec3 bogus{0.0f, -1.6f, 0.0f};
    f.update({0, 0, 0}, bogus, kDt);
  }
  CHECK_NEAR(f.pointing({0, 1, 0}).el_deg, el0, 0.2);
}

// Deriva del rumbo con sesgo ya compensado, trayectoria con movimiento y ruido (24 semillas).
static void testAzimuthTracking() {
  double worst_el = 0, worst_az = 0;
  for (int seed = 1; seed <= kSeeds; seed++) {
    for (int flat = 0; flat < 2; flat++) {
      sim::Imu imu(seed * 7 + flat, {0, 0, 0}, {});
      Vec3 bias_true = imu.randomBias(2.0);
      sim::Imu imu2(seed * 7 + flat, bias_true, {});
      sim::Mat3 prev = sim::attitude(flat, 0, 5, 0);
      Fusion6 f;
      double up_b[3], ez[3] = {0, 0, 1};
      sim::apply(sim::transpose(prev), ez, up_b);
      f.initFromAccel(toV(up_b));
      Pointing p0 = f.pointing(sim::pointingAxis(flat));
      double az_t = 0, el_t = 5;
      for (int i = 1; i <= 2000; i++) {  // 20 s
        double t = i * kDt;
        az_t = 20.0 * std::sin(0.5 * t) + 10.0 * std::sin(1.3 * t + seed);
        el_t = 5 + 8.0 * std::sin(0.7 * t + 1.0);
        double roll = 4.0 * std::sin(0.9 * t);
        sim::Mat3 now = sim::attitude(flat, az_t, el_t, roll);
        Vec3 g, a;
        imu2.sample(prev, now, kDt, true, &g, &a);
        f.update((g - bias_true) * kDeg2Rad, a, kDt);  // sesgo ideal: aísla la fusión
        prev = now;
      }
      Pointing p1 = f.pointing(sim::pointingAxis(flat));
      double e_az = std::fabs(wrap180(static_cast<float>(p1.az_deg - p0.az_deg - az_t)));
      double e_el = std::fabs(p1.el_deg - el_t);
      if (e_az > worst_az) worst_az = e_az;
      if (e_el > worst_el) worst_el = e_el;
      CHECK(e_el < 1.0);
      CHECK(e_az < 2.0);
    }
  }
  std::printf("  seguimiento 20 s con movimiento (sesgo compensado): peor altura %.3f, peor rumbo %.3f grados (%d semillas x 2 montajes) [estimado: simulador]\n",
              worst_el, worst_az, kSeeds);
}

static void testInitRejectsNoGravity() {
  Fusion6 f;
  CHECK(!f.initFromAccel({0, 0, 0}));
  CHECK(!f.initialized());
  // Sin inicializar no integra ni cambia nada.
  Pointing before = f.pointing({0, 1, 0});
  for (int i = 0; i < 100; i++) f.update({1, 1, 1}, {0, 0, 1}, 0.01f);
  CHECK(!f.initialized());
  Pointing after = f.pointing({0, 1, 0});
  CHECK_NEAR(after.az_deg, before.az_deg, 1e-6);
  CHECK_NEAR(after.el_deg, before.el_deg, 1e-6);
}

int main() {
  testClockwiseIsPositive();
  testElevationUp();
  testConvergenceFromTiltError();
  testLinearAccelGate();
  testAzimuthTracking();
  testInitRejectsNoGravity();
  return reportAndExit("test_fusion");
}
