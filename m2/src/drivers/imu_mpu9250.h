// Driver del MPU-9250 (y compatibles/clones con el mismo mapa de registros) por I2C.
// Solo giroscopio y acelerómetro: el magnetómetro (AK8963) queda sin usar a propósito,
// porque en modo BASE el metal del tubo lo estorba (arquitectura 5.1).
#pragma once
#include "imu.h"

namespace euler {

class ImuMpu9250 : public IImu {
 public:
  ImuMpu9250() {}
  ImuStatus begin() override;
  ImuStatus read(ImuSample& out) override;
  uint8_t whoAmI() const override { return who_; }
  const char* name() const override { return "MPU-9250"; }

 private:
  bool readReg(uint8_t reg, uint8_t* buf, uint8_t n);
  bool writeReg(uint8_t reg, uint8_t val);
  uint8_t addr_ = 0x68;  // AD0 a GND
  uint8_t who_ = 0;
};

}  // namespace euler
