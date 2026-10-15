// Vectores 3D y utilidades angulares. Lógica pura: sin Arduino, compila en el PC.
#pragma once
#include <cmath>

namespace euler {

constexpr float kPi = 3.14159265358979f;
constexpr float kDeg2Rad = kPi / 180.0f;
constexpr float kRad2Deg = 180.0f / kPi;

struct Vec3 {
  float x = 0, y = 0, z = 0;
};

inline Vec3 operator+(Vec3 a, Vec3 b) { return {a.x + b.x, a.y + b.y, a.z + b.z}; }
inline Vec3 operator-(Vec3 a, Vec3 b) { return {a.x - b.x, a.y - b.y, a.z - b.z}; }
inline Vec3 operator*(Vec3 a, float s) { return {a.x * s, a.y * s, a.z * s}; }
inline float dot(Vec3 a, Vec3 b) { return a.x * b.x + a.y * b.y + a.z * b.z; }
inline Vec3 cross(Vec3 a, Vec3 b) {
  return {a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x};
}
inline float norm(Vec3 a) { return std::sqrt(dot(a, a)); }

// Devuelve el vector unitario; si la norma es casi cero devuelve {0,0,0}
// para que quien llame decida (nunca divide entre cero).
inline Vec3 normalized(Vec3 a) {
  float n = norm(a);
  if (n < 1e-6f) return {0, 0, 0};
  return a * (1.0f / n);
}

// Envuelve un ángulo a (-180, 180].
inline float wrap180(float deg) {
  while (deg > 180.0f) deg -= 360.0f;
  while (deg <= -180.0f) deg += 360.0f;
  return deg;
}

inline float clampf(float v, float lo, float hi) { return v < lo ? lo : (v > hi ? hi : v); }

}  // namespace euler
