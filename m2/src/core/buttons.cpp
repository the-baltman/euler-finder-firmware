#include "buttons.h"
#include "../config/tuning.h"

namespace euler {

void ButtonPair::debounce(One& b, uint32_t now, bool raw) {
  if (raw != b.raw) {
    b.raw = raw;
    b.raw_since = now;
  }
  // El cambio se acepta cuando el nivel crudo lleva estable kDebounceMs.
  if (b.raw != b.down && static_cast<uint32_t>(now - b.raw_since) >= tun::kDebounceMs) {
    b.down = b.raw;
    if (b.down) {
      b.t_down = now;
      b.involved = false;
      b.long_fired = false;
    }
  }
}

BtnOut ButtonPair::update(uint32_t now, bool raw_a, bool raw_b) {
  BtnOut o;
  if (!started_) {  // un botón ya pulsado al arrancar (atascado) se ignora hasta que se suelte
    started_ = true;
    a_.ignore = raw_a;
    b_.ignore = raw_b;
    a_.raw_since = b_.raw_since = now;
  }
  if (a_.ignore) { if (!raw_a) a_.ignore = false; raw_a = false; }
  if (b_.ignore) { if (!raw_b) b_.ignore = false; raw_b = false; }
  bool a_prev = a_.down, b_prev = b_.down;
  debounce(a_, now, raw_a);
  debounce(b_, now, raw_b);

  // Si el otro botón está (o estuvo) pulsado, esta pulsación ya no es corta ni larga.
  if (a_.down && b_.down) {
    a_.involved = true;
    b_.involved = true;
  }

  // Liberaciones -> pulsación corta.
  if (a_prev && !a_.down && !a_.involved && !a_.long_fired) o.a_short = true;
  if (b_prev && !b_.down && !b_.involved && !b_.long_fired) o.b_short = true;

  // Pulsaciones largas, una sola vez por pulsación.
  if (a_.down && !a_.involved && !a_.long_fired) {
    uint32_t held = now - a_.t_down;
    o.a_progress = static_cast<float>(held) / tun::kLongPressMs;
    if (held >= tun::kLongPressMs) {
      a_.long_fired = true;
      o.a_long = true;
      o.a_progress = 1.0f;
    }
  }
  if (b_.down && !b_.involved && !b_.long_fired) {
    uint32_t held = now - b_.t_down;
    o.b_progress = static_cast<float>(held) / tun::kLongPressMs;
    if (held >= tun::kLongPressMs) {
      b_.long_fired = true;
      o.b_long = true;
      o.b_progress = 1.0f;
    }
  }
  if (o.a_progress > 1.0f) o.a_progress = 1.0f;
  if (o.b_progress > 1.0f) o.b_progress = 1.0f;

  // A+B: se cuenta desde que el segundo botón quedó abajo.
  if (a_.down && b_.down) {
    uint32_t start = (static_cast<int32_t>(a_.t_down - b_.t_down) > 0) ? a_.t_down : b_.t_down;
    combo_start_ = start;
    uint32_t held = now - combo_start_;
    o.combo_progress = static_cast<float>(held) / tun::kComboMs;
    if (o.combo_progress > 1.0f) o.combo_progress = 1.0f;
    if (!combo_fired_ && held >= tun::kComboMs) {
      combo_fired_ = true;
      o.combo = true;
    }
  } else {
    combo_fired_ = false;
  }
  o.a_down = a_.down;
  o.b_down = b_.down;
  return o;
}

}  // namespace euler
