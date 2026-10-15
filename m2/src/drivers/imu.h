// Interfaz del IMU. El resto del firmware solo conoce esto: para cambiar de sensor en B2
// (ICM-20948, BNO085) se escribe otro driver que la implemente y se cambia una línea en app.cpp.
// Sin includes de Arduino: el PC también la usa (IMU falso en las pruebas).
#pragma once
#include <cstdint>
#include "../core/vec3.h"

namespace euler {

enum class ImuStatus : uint8_t {
  Ok,
  NoAck,     // el chip no contesta en el bus
  Timeout,   // la lectura no terminó a tiempo
  BadId,     // contesta, pero con un ID que el driver no puede manejar
  BadData,   // datos imposibles (gravedad absurda, todo en cero)
};

struct ImuSample {
  Vec3 accel_g;   // g, en los ejes de la caja (ya con el mapa de ejes aplicado)
  Vec3 gyro_dps;  // °/s, idem
  float temp_c = 0;
};

class IImu {
 public:
  virtual ~IImu() {}
  // Inicializa el chip. NoAck si no contesta.
  virtual ImuStatus begin() = 0;
  virtual ImuStatus read(ImuSample& out) = 0;
  // ID que reportó el chip en begin() (WHO_AM_I), para mostrarlo y registrar clones.
  virtual uint8_t whoAmI() const = 0;
  virtual const char* name() const = 0;
};

}  // namespace euler
