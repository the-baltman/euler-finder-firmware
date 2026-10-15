// Dos botones con antirrebote y duración: corto, largo (1 s) y A+B (3 s).
// Lógica pura: recibe el nivel crudo y la hora, devuelve eventos. El pin lo lee main/app.
#pragma once
#include <cstdint>

namespace euler {

struct BtnOut {
  bool a_short = false, a_long = false;
  bool b_short = false, b_long = false;
  bool combo = false;       // A+B sostenidos
  float a_progress = 0;     // 0..1 hacia la pulsación larga (solo mientras A está sola)
  float b_progress = 0;     // 0..1, para el anillo que se llena
  float combo_progress = 0; // 0..1 hacia A+B
  bool a_down = false, b_down = false;
};

class ButtonPair {
 public:
  // raw_*: true = pulsado (ya invertido el nivel activo en bajo). now_ms: millis().
  BtnOut update(uint32_t now_ms, bool raw_a, bool raw_b);

 private:
  struct One {
    bool raw = false;
    uint32_t raw_since = 0;
    bool down = false;       // estado con antirrebote
    uint32_t t_down = 0;
    bool involved = false;   // el otro botón estuvo pulsado durante esta pulsación
    bool long_fired = false;
    bool ignore = false;     // venía pulsado al arrancar
  };
  void debounce(One& b, uint32_t now, bool raw);
  One a_, b_;
  bool combo_fired_ = false;
  uint32_t combo_start_ = 0;
  bool started_ = false;
};

}  // namespace euler
