#include "mount.h"
#include "../config/tuning.h"

namespace euler {

MountInfo detectMount(Vec3 up_raw) {
  MountInfo m;
  Vec3 u = normalized(up_raw);
  // Plano: la pantalla mira hacia arriba (o abajo) y se apunta con el borde superior.
  if (std::fabs(u.z) >= tun::kMountFlatMinUp) {
    m.mount = Mount::Flat;
    m.pointing_axis = {0, 1, 0};
    m.screen_rotation_deg = 0;
    return m;
  }
  // Vertical: se apunta con la parte trasera (-z), como la cámara de un celular.
  // La pantalla se gira para que "arriba" del mundo quede arriba en la imagen.
  m.pointing_axis = {0, 0, -1};
  if (std::fabs(u.y) >= std::fabs(u.x)) {
    if (u.y >= 0) { m.mount = Mount::VertUp; m.screen_rotation_deg = 0; }
    else { m.mount = Mount::VertDown; m.screen_rotation_deg = 180; }
  } else {
    // "Arriba" del mundo cae hacia +x (derecha de la pantalla): el contenido gira 90° horario.
    if (u.x > 0) { m.mount = Mount::VertRight; m.screen_rotation_deg = 90; }
    else { m.mount = Mount::VertLeft; m.screen_rotation_deg = 270; }
  }
  return m;
}

}  // namespace euler
