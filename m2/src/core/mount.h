// Montaje detectado con la gravedad: el equipo está plano (pantalla hacia arriba) o
// vertical (como un celular, en 4 giros). Define el eje de apuntado y cómo gira la pantalla.
// Se decide una sola vez, con el equipo quieto en su posición de uso (al terminar la medición
// del sesgo); cambiarlo con el equipo en movimiento rompería el sync.
#pragma once
#include "vec3.h"

namespace euler {

enum class Mount : unsigned char { Flat, VertUp, VertRight, VertDown, VertLeft };

struct MountInfo {
  Mount mount = Mount::Flat;
  Vec3 pointing_axis{0, 1, 0};  // eje del cuerpo que apunta al objetivo
  int screen_rotation_deg = 0;  // giro horario del contenido: 0, 90, 180 o 270
};

// up_body: dirección de "arriba" en el cuerpo (acelerómetro en reposo, no hace falta normalizar).
MountInfo detectMount(Vec3 up_body);

}  // namespace euler
