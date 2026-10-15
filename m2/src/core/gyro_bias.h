// Sesgo del giroscopio: se mide con el equipo quieto y se re-estima cada vez que
// vuelve a quedar quieto (arquitectura 5.2).
#pragma once
#include "vec3.h"

namespace euler {

class GyroBias {
 public:
  void reset();  // olvida todo (vuelve a medir con la ventana inicial)
  // Una muestra por tick. gyro en °/s, accel en g. Devuelve true si esta muestra completó una ventana quieta.
  bool feed(Vec3 gyro_dps, Vec3 accel_g);
  bool valid() const { return valid_; }
  Vec3 biasDps() const { return bias_; }
  Vec3 meanAccelG() const { return mean_accel_; }  // media de la última ventana aceptada
  float progress() const;                          // 0..1 de la ventana en curso

 private:
  int windowSamples() const;
  void restartWindow();
  bool valid_ = false;
  Vec3 bias_{};
  Vec3 mean_accel_{};
  Vec3 sum_g_{}, sum_a_{}, ref_g_{}, ref_a_{};
  int n_ = 0;
};

}  // namespace euler
