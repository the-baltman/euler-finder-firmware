// Autoprueba del IMU al arrancar. El MPU-9250 que se vende puede ser un clon, así que:
//   - sin respuesta en el bus  -> error grave
//   - ID conocido y datos creíbles -> bien
//   - ID desconocido pero datos creíbles -> sigue, con aviso ("posible clon")
//   - datos imposibles -> error grave
#pragma once
#include <cstdint>
#include "../drivers/imu.h"

namespace euler {

enum class FatalReason : uint8_t { None, ImuNoAck, ImuBadData, ImuLost };

struct SelfTestResult {
  bool ok = false;
  FatalReason fatal = FatalReason::None;
  uint8_t who_am_i = 0;
  bool id_known = false;   // false = posible clon (solo aviso)
  uint8_t accel_ok_reads = 0;
};

// IDs de WHO_AM_I que el driver sabe manejar: MPU-9250 (0x71), MPU-9255 (0x73), MPU-6500 (0x70).
// Todos comparten el mapa de registros de acelerómetro y giroscopio que usa el driver.
bool isKnownImuId(uint8_t id);

// sleep_ms: espera entre lecturas (en el PC se pasa una función vacía).
SelfTestResult selfTestImu(IImu& imu, void (*sleep_ms)(uint32_t));

}  // namespace euler
