#include "display.h"
#include <Adafruit_GC9A01A.h>
#include <Arduino.h>
#include <SPI.h>
#include "../config/pins.h"

namespace euler {

namespace {
constexpr uint8_t kBlChannel = 0;
SPIClass g_spi(FSPI);
Adafruit_GC9A01A g_tft(&g_spi, pins::kTftDc, pins::kTftCs, pins::kTftRst);
}  // namespace

bool Display::begin() {
  ledcSetup(kBlChannel, hw::kBlFreqHz, 8);
  ledcAttachPin(pins::kTftBl, kBlChannel);
  ledcWrite(kBlChannel, 0);  // apagada hasta que haya imagen: evita el destello blanco del arranque

  // Los pines SPI se fijan aquí (SCK=6, MOSI=7). SPIClass::begin() ignora una segunda llamada,
  // así que la que hace Adafruit_SPITFT después no pisa estos pines. MISO no se usa (-1).
  g_spi.begin(pins::kTftSck, -1, pins::kTftMosi, -1);

  g_tft.begin(hw::kTftSpiHz);
  g_tft.fillScreen(0);

  canvas_ = new GFXcanvas16(kSize, kSize);
  if (canvas_ == nullptr || canvas_->getBuffer() == nullptr) return false;
  canvas_->fillScreen(0);
  push();
  ledcWrite(kBlChannel, hw::kBlDayDuty);
  return true;
}

void Display::setContentRotation(int deg) {
  if (canvas_) canvas_->setRotation(static_cast<uint8_t>(((deg / 90) % 4 + 4) % 4));
}

void Display::push() {
  if (!canvas_) return;
  g_tft.drawRGBBitmap(0, 0, canvas_->getBuffer(), kSize, kSize);
}

void Display::setBacklight(uint8_t duty) { ledcWrite(kBlChannel, duty); }

}  // namespace euler
