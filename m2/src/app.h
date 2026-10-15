// Pegamento entre el hardware y la lógica pura: una tarea de FreeRTOS a 100 Hz fijos lee
// botones e IMU, corre la fusión y la máquina de estados, y publica el UiModel para la pantalla.
#pragma once
#include <stdint.h>
#include "core/app_fsm.h"

namespace euler {

void appBegin();                      // crea la tarea de control (llamar una vez, desde setup)
UiModel appSnapshot();                // copia atómica del modelo para la UI
uint32_t appHeartbeat();              // sube en cada tick; la UI lo vigila para detectar un cuelgue

}  // namespace euler
