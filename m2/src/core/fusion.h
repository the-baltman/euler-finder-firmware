// Fusión de 6 ejes (giroscopio + acelerómetro) tipo Mahony, sin magnetómetro.
// El cabeceo/alabeo salen de la gravedad (absolutos); el giro (yaw) solo de integrar
// el giroscopio, por eso se desvía con el tiempo y se re-referencia con el sync.
#pragma once
#include "vec3.h"

namespace euler {

struct Pointing {
  float az_deg = 0;  // rumbo horario visto desde arriba (+ = a la derecha), referencia arbitraria
  float el_deg = 0;  // altura sobre el horizonte (+ = arriba), absoluta por gravedad
};

class Fusion6 {
 public:
  void reset();
  // Orienta el cuaternión con la gravedad medida; el giro queda en 0.
  bool initFromAccel(Vec3 accel_g);
  // gyro_rps ya sin sesgo, en rad/s; accel_g en g; dt en s.
  void update(Vec3 gyro_rps, Vec3 accel_g, float dt);
  bool initialized() const { return init_; }
  // Rota un vector del cuerpo al mundo (mundo: z = arriba).
  Vec3 toWorld(Vec3 v_body) const;
  // Dirección de "arriba" expresada en el cuerpo.
  Vec3 upInBody() const;
  Pointing pointing(Vec3 axis_body) const;

 private:
  float w_ = 1, x_ = 0, y_ = 0, z_ = 0;  // cuaternión cuerpo -> mundo
  bool init_ = false;
};

}  // namespace euler
