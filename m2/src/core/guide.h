// Guía hacia la marca elegida: giro y altura que faltan, estado lejos/cerca/en mira
// (con histéresis) y la geometría que la pantalla dibuja. Lógica pura.
#pragma once
#include <cstdint>
#include "../config/tuning.h"
#include "fusion.h"

namespace euler {

enum class GuideState : uint8_t { Far, Near, InView };

struct Target {
  float giro_deg;    // respecto a la marca 1, + = a la derecha
  float altura_deg;  // respecto a la marca 1, + = arriba
};

struct GuideOut {
  float d_giro_deg = 0;  // lo que falta girar (+ = hay que girar a la derecha)
  float d_alt_deg = 0;   // lo que falta subir (+ = hay que subir)
  float dist_deg = 0;
  GuideState state = GuideState::Far;
  float arrow_rad = 0;   // dirección a moverse en pantalla, 0 = derecha, +pi/2 = arriba
  float giro_ptr = 0;    // -1..1, posición del puntero de giro (solo dibujo, sin números)
  float alt_ptr = 0;     // -1..1, posición del puntero de altura
  float star_x_px = 0;   // desplazamiento de la estrella respecto al centro, + = derecha
  float star_y_px = 0;   // + = abajo (coordenadas de pantalla)
};

class Guide {
 public:
  void reset() { state_ = GuideState::Far; }
  GuideOut update(Pointing now, Pointing sync_ref, Target target);

 private:
  GuideState state_ = GuideState::Far;
};

}  // namespace euler
