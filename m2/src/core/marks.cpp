#include "marks.h"

namespace euler {

namespace {
// Ángulo (°) que la mira desplazada s queda "antes" de la marca a distancia d: asin(s/d).
// Para apuntar la línea de mira a la marca, el pivote debe girar ese ángulo de menos.
float parallaxDeg(float offset_m, float dist_m) {
  if (offset_m == 0.0f || dist_m <= 0.0f || std::fabs(offset_m) >= dist_m) return 0.0f;
  return std::asin(offset_m / dist_m) * kRad2Deg;
}
}  // namespace

Target marcaEfectiva(const Marca& k, const Marca& m1, float off_lat_m, float off_vert_m) {
  Target t{k.giro_deg, k.altura_deg};
  // Sin distancia en alguna de las dos no hay corrección coherente (se mide contra la marca 1).
  if (k.distancia_m <= 0.0f || m1.distancia_m <= 0.0f) return t;
  t.giro_deg -= parallaxDeg(off_lat_m, k.distancia_m) - parallaxDeg(off_lat_m, m1.distancia_m);
  t.altura_deg -= parallaxDeg(off_vert_m, k.distancia_m) - parallaxDeg(off_vert_m, m1.distancia_m);
  return t;
}

Target objetivoDeMarca(int idx) {
  if (idx < 0 || idx >= kNumMarcas) idx = 0;
  return marcaEfectiva(MARCAS[idx], MARCAS[0], OFFSET_PIVOTE_MIRA_LATERAL_M,
                       OFFSET_PIVOTE_MIRA_VERTICAL_M);
}

}  // namespace euler
