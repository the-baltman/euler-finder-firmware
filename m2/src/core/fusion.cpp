#include "fusion.h"
#include "../config/tuning.h"

namespace euler {

void Fusion6::reset() {
  w_ = 1;
  x_ = y_ = z_ = 0;
  init_ = false;
}

bool Fusion6::initFromAccel(Vec3 accel_g) {
  Vec3 u = normalized(accel_g);
  if (norm(u) < 0.5f) return false;
  // Rotación de arco corto que lleva "arriba medido" (en el cuerpo) a +z del mundo.
  Vec3 ez{0, 0, 1};
  Vec3 axis = cross(u, ez);
  float s = norm(axis);
  float c = dot(u, ez);
  if (s < 1e-6f) {
    if (c > 0) {
      w_ = 1;
      x_ = y_ = z_ = 0;
    } else {
      w_ = 0;  // 180° alrededor de x
      x_ = 1;
      y_ = z_ = 0;
    }
  } else {
    float half = std::atan2(s, c) * 0.5f;
    float k = std::sin(half) / s;
    w_ = std::cos(half);
    x_ = axis.x * k;
    y_ = axis.y * k;
    z_ = axis.z * k;
  }
  init_ = true;
  return true;
}

Vec3 Fusion6::toWorld(Vec3 v) const {
  // v' = v + 2*w*(q x v) + 2*(q x (q x v)), con q = (x,y,z)
  Vec3 q{x_, y_, z_};
  Vec3 t = cross(q, v) * 2.0f;
  return v + t * w_ + cross(q, t);
}

Vec3 Fusion6::upInBody() const {
  // R^T * ez: se rota ez con el cuaternión conjugado.
  Vec3 q{-x_, -y_, -z_};
  Vec3 ez{0, 0, 1};
  Vec3 t = cross(q, ez) * 2.0f;
  return ez + t * w_ + cross(q, t);
}

void Fusion6::update(Vec3 g, Vec3 a_g, float dt) {
  if (!init_) return;
  float an = norm(a_g);
  // Con aceleración lineal fuerte (mano moviéndose) la gravedad medida no es confiable.
  if (an > 1e-3f && std::fabs(an - 1.0f) < tun::kAccelGateG) {
    Vec3 a = a_g * (1.0f / an);
    Vec3 up = upInBody();
    // Velocidad angular que acerca "arriba estimado" a "arriba medido": a x up.
    g = g + cross(a, up) * tun::kFusionKp;
  }
  // q <- q * exp(0.5 * g * dt), g expresada en el cuerpo.
  float hw = -0.5f * (x_ * g.x + y_ * g.y + z_ * g.z);
  float hx = 0.5f * (w_ * g.x + y_ * g.z - z_ * g.y);
  float hy = 0.5f * (w_ * g.y + z_ * g.x - x_ * g.z);
  float hz = 0.5f * (w_ * g.z + x_ * g.y - y_ * g.x);
  w_ += hw * dt;
  x_ += hx * dt;
  y_ += hy * dt;
  z_ += hz * dt;
  float n = std::sqrt(w_ * w_ + x_ * x_ + y_ * y_ + z_ * z_);
  if (n < 1e-6f) {  // no debería pasar; se exige re-inicializar
    reset();
    return;
  }
  float inv = 1.0f / n;
  w_ *= inv;
  x_ *= inv;
  y_ *= inv;
  z_ *= inv;
}

Pointing Fusion6::pointing(Vec3 axis_body) const {
  Vec3 p = toWorld(axis_body);
  Pointing out;
  out.az_deg = -std::atan2(p.y, p.x) * kRad2Deg;
  out.el_deg = std::asin(clampf(p.z, -1.0f, 1.0f)) * kRad2Deg;
  return out;
}

}  // namespace euler
