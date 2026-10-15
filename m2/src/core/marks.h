// Objetivo efectivo de una marca: giro y altura relativos a la marca 1, con la
// corrección opcional de paralaje (el pivote del nivelador no coincide con su línea de mira).
#pragma once
#include "../config/marcas.h"
#include "guide.h"

namespace euler {

// off_lat_m / off_vert_m: desplazamiento de la mira respecto al pivote (+ derecha / + arriba).
// Si el desplazamiento es 0, o a una de las dos marcas le falta la distancia, no se corrige.
Target marcaEfectiva(const Marca& k, const Marca& m1, float off_lat_m, float off_vert_m);

// Atajo con las constantes de marcas.h.
Target objetivoDeMarca(int idx);

}  // namespace euler
