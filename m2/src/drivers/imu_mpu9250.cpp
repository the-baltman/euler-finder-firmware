#include "imu_mpu9250.h"
#include <Arduino.h>
#include <Wire.h>
#include "../config/pins.h"

namespace euler {

namespace {
// Registros (PS-MPU-9250A-01 / mapa de registros; confirmar contra el PDF si algo no responde).
constexpr uint8_t REG_SMPLRT_DIV = 0x19;
constexpr uint8_t REG_CONFIG = 0x1A;
constexpr uint8_t REG_GYRO_CONFIG = 0x1B;
constexpr uint8_t REG_ACCEL_CONFIG = 0x1C;
constexpr uint8_t REG_ACCEL_CONFIG2 = 0x1D;
constexpr uint8_t REG_USER_CTRL = 0x6A;
constexpr uint8_t REG_PWR_MGMT_1 = 0x6B;
constexpr uint8_t REG_ACCEL_XOUT_H = 0x3B;  // 14 bytes: accel(6), temp(2), gyro(6), big endian
constexpr uint8_t REG_WHO_AM_I = 0x75;

constexpr float kAccelLsbPerG = 8192.0f;   // ±4 g
constexpr float kGyroLsbPerDps = 65.5f;    // ±500 °/s (una mano puede girar rápido)
constexpr float kTempLsbPerC = 333.87f;    // MPU-9250: T = raw/333.87 + 21
constexpr float kTempOffsetC = 21.0f;
}  // namespace

bool ImuMpu9250::writeReg(uint8_t reg, uint8_t val) {
  Wire.beginTransmission(addr_);
  Wire.write(reg);
  Wire.write(val);
  return Wire.endTransmission() == 0;
}

bool ImuMpu9250::readReg(uint8_t reg, uint8_t* buf, uint8_t n) {
  Wire.beginTransmission(addr_);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) return false;  // repeated start
  if (Wire.requestFrom(static_cast<int>(addr_), static_cast<int>(n)) != n) return false;
  for (uint8_t i = 0; i < n; i++) {
    if (!Wire.available()) return false;
    buf[i] = static_cast<uint8_t>(Wire.read());
  }
  return true;
}

ImuStatus ImuMpu9250::begin() {
  if (!Wire.begin(pins::kImuSda, pins::kImuScl, hw::kI2cHz)) return ImuStatus::NoAck;
  Wire.setTimeOut(hw::kI2cTimeoutMs);

  // AD0 a GND = 0x68; si el módulo lo trae en alto, 0x69.
  const uint8_t candidates[2] = {0x68, 0x69};
  bool found = false;
  for (uint8_t a : candidates) {
    addr_ = a;
    uint8_t id = 0;
    if (readReg(REG_WHO_AM_I, &id, 1)) {
      who_ = id;
      found = true;
      break;
    }
  }
  if (!found) {
    who_ = 0;
    return ImuStatus::NoAck;
  }
  // 0x00 / 0xFF = bus sin nadie de verdad (línea flotando o atascada).
  if (who_ == 0x00 || who_ == 0xFF) return ImuStatus::BadId;

  // Un ID distinto de 0x71 no se rechaza aquí (clones): la autoprueba juzga con los datos.
  if (!writeReg(REG_PWR_MGMT_1, 0x80)) return ImuStatus::NoAck;  // reset
  delay(100);                                                   // el reset tarda; tiempo holgado
  if (!writeReg(REG_PWR_MGMT_1, 0x01)) return ImuStatus::NoAck;  // despierta, reloj = PLL del giroscopio
  delay(10);
  bool ok = true;
  ok &= writeReg(REG_USER_CTRL, 0x00);        // sin maestro I2C auxiliar
  ok &= writeReg(REG_SMPLRT_DIV, 0x00);       // 1 kHz interno; se lee a 100 Hz por sondeo
  ok &= writeReg(REG_CONFIG, 0x03);           // filtro del giroscopio ~41 Hz
  ok &= writeReg(REG_GYRO_CONFIG, 0x08);      // ±500 °/s, filtro digital activo
  ok &= writeReg(REG_ACCEL_CONFIG, 0x08);     // ±4 g
  ok &= writeReg(REG_ACCEL_CONFIG2, 0x03);    // filtro del acelerómetro ~44.8 Hz
  if (!ok) return ImuStatus::NoAck;
  delay(50);  // deja que arranquen los filtros
  return ImuStatus::Ok;
}

ImuStatus ImuMpu9250::read(ImuSample& out) {
  uint8_t b[14];
  if (!readReg(REG_ACCEL_XOUT_H, b, 14)) return ImuStatus::Timeout;
  auto s16 = [&](int i) { return static_cast<int16_t>((b[i] << 8) | b[i + 1]); };
  float chip_a[3] = {s16(0) / kAccelLsbPerG, s16(2) / kAccelLsbPerG, s16(4) / kAccelLsbPerG};
  float chip_g[3] = {s16(8) / kGyroLsbPerDps, s16(10) / kGyroLsbPerDps, s16(12) / kGyroLsbPerDps};
  float a[3], g[3];
  for (int i = 0; i < 3; i++) {
    a[i] = chip_a[hw::kImuAxisMap.idx[i]] * hw::kImuAxisMap.sign[i];
    g[i] = chip_g[hw::kImuAxisMap.idx[i]] * hw::kImuAxisMap.sign[i];
  }
  out.accel_g = {a[0], a[1], a[2]};
  out.gyro_dps = {g[0], g[1], g[2]};
  out.temp_c = s16(6) / kTempLsbPerC + kTempOffsetC;
  return ImuStatus::Ok;
}

}  // namespace euler
