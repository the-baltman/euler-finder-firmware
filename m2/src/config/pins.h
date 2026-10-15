// Pines y ajustes de hardware del nivelador M2 (ESP32-C3 SuperMini).
// Fuente: Electronica/02-Proyectos/EULER-finder/demo-jije.md, sección 2 (pinout de la demo).
// Se usan NÚMEROS DE GPIO, no el orden físico de la placa: compara con la serigrafia de la
// SuperMini recibida antes de cablear.
#pragma once
#include <stdint.h>

namespace euler {
namespace pins {

// --- Pantalla GC9A01 por SPI (modo 0, solo escritura) ---
constexpr int8_t kTftSck = 6;   // GPIO6, SCL del módulo (reloj SPI, no I2C)
constexpr int8_t kTftMosi = 7;  // GPIO7, SDA del módulo (datos SPI)
constexpr int8_t kTftCs = 10;   // GPIO10
constexpr int8_t kTftDc = 4;    // GPIO4
constexpr int8_t kTftRst = 5;   // GPIO5
constexpr int8_t kTftBl = 3;    // GPIO3, luz de fondo con PWM (LEDC)

// --- IMU MPU-9250 por I2C ---
constexpr int8_t kImuSda = 0;   // GPIO0. NO usar el I2C por defecto de Arduino (SDA=8, SCL=9 son strapping)
constexpr int8_t kImuScl = 1;   // GPIO1
// INT del IMU: no cableado (la demo lee por sondeo).

// --- Botones: a GND, con pull-up externo de 10 kΩ a 3V3 (activo en bajo) ---
constexpr int8_t kBtnA = 20;    // GPIO20
constexpr int8_t kBtnB = 21;    // GPIO21

}  // namespace pins

namespace hw {

// SPI: la hoja de datos del GC9A01 da 60 ns de ciclo de escritura (~16 MHz de techo). Se usa 10 MHz.
constexpr uint32_t kTftSpiHz = 10000000;  // Hz

// I2C: el MPU-9250 llega a 400 kHz como máximo.
constexpr uint32_t kI2cHz = 400000;       // Hz
constexpr uint16_t kI2cTimeoutMs = 20;    // ms, para que un bus colgado no congele el firmware

// Luz de fondo (LEDC)
constexpr uint32_t kBlFreqHz = 5000;      // Hz
constexpr uint8_t kBlDayDuty = 255;       // 0..255
constexpr uint8_t kBlNightDuty = 70;      // 0..255, modo noche más tenue [estimado]

// Orientación del módulo IMU dentro de la caja: eje de la caja = signo * eje del chip.
// Caja: x = derecha de la pantalla, y = arriba de la pantalla, z = sale de la pantalla hacia el usuario.
// idx: 0 = x del chip, 1 = y, 2 = z. Ajusta con la prueba de ejes del README (paso 0).
struct AxisMap { int8_t idx[3]; int8_t sign[3]; };
constexpr AxisMap kImuAxisMap = {{0, 1, 2}, {+1, +1, +1}};

}  // namespace hw
}  // namespace euler
