// Pantalla GC9A01 redonda de 240x240. Se dibuja en un lienzo en RAM y se envía completo
// por SPI: sin parpadeo, a costa de ~115 kB de RAM (el C3 tiene 400 kB).
#pragma once
#include <Adafruit_GFX.h>
#include <stdint.h>

namespace euler {

class Display {
 public:
  static constexpr int kSize = 240;
  bool begin();                         // false si no hubo RAM para el lienzo
  GFXcanvas16& canvas() { return *canvas_; }
  void setContentRotation(int deg);     // 0, 90, 180, 270 horario (montaje vertical)
  void push();                          // envía el lienzo a la pantalla
  void setBacklight(uint8_t duty);      // 0..255
 private:
  GFXcanvas16* canvas_ = nullptr;
};

}  // namespace euler
