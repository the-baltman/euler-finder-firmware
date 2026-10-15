// Dibujo de todas las pantallas. Solo lee el UiModel; no toma decisiones.
// Reglas de marca: tinta noche #0F1218, papel #F3F1EC; el rojo #E8483A es solo para la
// estrella y lo crítico, nunca en texto. Modo noche: todo rojo (opción, no por defecto).
// Sin cifras de precisión en ninguna pantalla. El texto es ASCII: las fuentes de Adafruit_GFX
// no traen tildes ni ñ.
#pragma once
#include "../core/app_fsm.h"
#include "../drivers/display.h"

namespace euler {

void uiRender(Display& d, const UiModel& m);

}  // namespace euler
