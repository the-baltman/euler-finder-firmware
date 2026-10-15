#include "guide.h"

namespace euler {

GuideOut Guide::update(Pointing now, Pointing ref, Target t) {
  GuideOut o;
  // La marca 1 es el origen: el objetivo está en (ref + offset de la marca).
  o.d_giro_deg = wrap180((ref.az_deg + t.giro_deg) - now.az_deg);
  o.d_alt_deg = (ref.el_deg + t.altura_deg) - now.el_deg;
  o.dist_deg = std::sqrt(o.d_giro_deg * o.d_giro_deg + o.d_alt_deg * o.d_alt_deg);

  // Histéresis: sin ella la pantalla parpadea entre estados en el borde del umbral.
  switch (state_) {
    case GuideState::Far:
      if (o.dist_deg < tun::kFarExitDeg) state_ = GuideState::Near;
      break;
    case GuideState::Near:
      if (o.dist_deg > tun::kFarEnterDeg) state_ = GuideState::Far;
      else if (o.dist_deg < tun::kInViewEnterDeg) state_ = GuideState::InView;
      break;
    case GuideState::InView:
      if (o.dist_deg > tun::kInViewExitDeg) state_ = GuideState::Near;
      break;
  }
  o.state = state_;

  o.arrow_rad = std::atan2(o.d_alt_deg, o.d_giro_deg);
  o.giro_ptr = clampf(o.d_giro_deg / tun::kScaleDeg, -1.0f, 1.0f);
  o.alt_ptr = clampf(o.d_alt_deg / tun::kScaleDeg, -1.0f, 1.0f);

  // Estrella: sale del borde y entra a la mira conforme baja la distancia.
  float r = clampf(o.dist_deg / tun::kScaleDeg, 0.0f, 1.0f) * tun::kStarRimPx;
  float ux = 0, uy = 0;
  if (o.dist_deg > 1e-4f) {
    ux = o.d_giro_deg / o.dist_deg;
    uy = o.d_alt_deg / o.dist_deg;
  }
  o.star_x_px = ux * r;
  o.star_y_px = -uy * r;
  return o;
}

}  // namespace euler
