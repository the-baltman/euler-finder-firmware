// Botones: antirrebote, corto/largo (1 s), A+B (3 s), botón atascado al arrancar. 24 semillas.
#include <random>
#include "check.h"
#include "../../src/core/buttons.h"
#include "../../src/config/tuning.h"

using namespace euler;

struct Counts {
  int a_short = 0, a_long = 0, b_short = 0, b_long = 0, combo = 0;
  int a_long_ms = -1, b_long_ms = -1, combo_ms = -1;
  float last_b_progress = 0;
  bool progress_monotonic = true;
};

// Reproduce guiones de pulsación: cada botón tiene segmentos [inicio, fin) en ms, con rebote opcional.
struct Script {
  int a_on = -1, a_off = -1, b_on = -1, b_off = -1;
  int bounce_ms = 0;  // ventana de rebote tras cada flanco
};

static bool level(int on, int off, int t, int bounce, std::mt19937& rng) {
  bool state = (on >= 0 && t >= on && (off < 0 || t < off));
  if (bounce > 0) {
    bool near_edge = (on >= 0 && t >= on && t < on + bounce) || (off >= 0 && t >= off && t < off + bounce);
    if (near_edge && (rng() & 1)) return !state;  // chisporroteo
  }
  return state;
}

static Counts run(const Script& s, int total_ms, unsigned seed, int step_ms = 10) {
  std::mt19937 rng(seed);
  ButtonPair bp;
  Counts c;
  float prev_p = 0;
  for (int t = 0; t <= total_ms; t += step_ms) {
    BtnOut o = bp.update(static_cast<uint32_t>(t), level(s.a_on, s.a_off, t, s.bounce_ms, rng),
                         level(s.b_on, s.b_off, t, s.bounce_ms, rng));
    c.a_short += o.a_short;
    c.b_short += o.b_short;
    if (o.a_long) { c.a_long++; c.a_long_ms = t; }
    if (o.b_long) { c.b_long++; c.b_long_ms = t; }
    if (o.combo) { c.combo++; c.combo_ms = t; }
    if (o.b_down && !o.a_down && o.b_progress + 1e-6f < prev_p && o.b_progress > 0) c.progress_monotonic = false;
    prev_p = o.b_progress;
  }
  return c;
}

int main() {
  for (unsigned seed = 1; seed <= 24; seed++) {
    std::mt19937 r(seed * 977u);
    int t0 = 100 + static_cast<int>(r() % 200);

    // Pulsación corta de 80 a 600 ms -> un solo evento corto, sin largo, aun con rebote de 12 ms.
    {
      int dur = 80 + static_cast<int>(r() % 520);
      Script s; s.a_on = t0; s.a_off = t0 + dur; s.bounce_ms = 12;
      Counts c = run(s, t0 + dur + 500, seed);
      CHECK(c.a_short == 1 && c.a_long == 0 && c.b_short == 0 && c.combo == 0);
      Script sb; sb.b_on = t0; sb.b_off = t0 + dur; sb.bounce_ms = 12;
      Counts cb = run(sb, t0 + dur + 500, seed);
      CHECK(cb.b_short == 1 && cb.b_long == 0 && cb.a_short == 0);
    }
    // Pulsación larga: un solo evento largo a ~1 s, y NO se suma un corto al soltar.
    {
      int dur = 1200 + static_cast<int>(r() % 1500);
      Script s; s.b_on = t0; s.b_off = t0 + dur; s.bounce_ms = 12;
      Counts c = run(s, t0 + dur + 500, seed);
      CHECK(c.b_long == 1 && c.b_short == 0);
      CHECK(c.b_long_ms - t0 >= 1000 && c.b_long_ms - t0 <= 1000 + 60);
      CHECK(c.progress_monotonic);
      Script sa; sa.a_on = t0; sa.a_off = t0 + dur; sa.bounce_ms = 12;
      Counts ca = run(sa, t0 + dur + 500, seed);
      CHECK(ca.a_long == 1 && ca.a_short == 0);
    }
    // A+B juntos (segundo botón entra 0..150 ms tarde) 3.4 s: un combo a ~3 s, nada más.
    {
      int late = static_cast<int>(r() % 150);
      Script s; s.a_on = t0; s.a_off = t0 + 3400; s.b_on = t0 + late; s.b_off = t0 + 3400 + static_cast<int>(r() % 100);
      s.bounce_ms = 10;
      Counts c = run(s, t0 + 4200, seed);
      CHECK(c.combo == 1);
      CHECK(c.a_short + c.b_short + c.a_long + c.b_long == 0);
      CHECK(c.combo_ms - (t0 + late) >= 3000 && c.combo_ms - (t0 + late) <= 3000 + 60);
    }
    // A+B soltados a los 2 s: no pasa nada.
    {
      Script s; s.a_on = t0; s.a_off = t0 + 2000; s.b_on = t0 + 30; s.b_off = t0 + 2000;
      Counts c = run(s, t0 + 3000, seed);
      CHECK(c.combo + c.a_short + c.b_short + c.a_long + c.b_long == 0);
    }
    // Un pulso espurio de 6 ms (menor que el antirrebote) no cuenta.
    {
      Script s; s.a_on = t0; s.a_off = t0 + 6;
      Counts c = run(s, t0 + 500, seed);
      CHECK(c.a_short + c.a_long == 0);
    }
  }

  // Rebote real: lectura cada 1 ms con 15 ms de chisporroteo en cada flanco; debe verse UN solo evento.
  for (unsigned seed = 1; seed <= 24; seed++) {
    Script s; s.a_on = 200; s.a_off = 500; s.bounce_ms = 15;
    Counts c = run(s, 900, seed, 1);
    CHECK(c.a_short == 1 && c.a_long == 0);
    Script l; l.b_on = 200; l.b_off = 1700; l.bounce_ms = 15;
    Counts d = run(l, 2200, seed, 1);
    CHECK(d.b_long == 1 && d.b_short == 0);
  }

  // Botón atascado al arrancar: se ignora hasta soltarlo; después funciona normal.
  {
    ButtonPair bp;
    int events = 0;
    for (int t = 0; t < 3000; t += 10) {
      BtnOut o = bp.update(t, true, false);
      events += o.a_short + o.a_long + o.combo;
    }
    CHECK(events == 0);
    BtnOut o{};
    int shorts = 0;
    for (int t = 3000; t < 3600; t += 10) {
      bool press = (t >= 3200 && t < 3350);
      o = bp.update(t, press, false);
      shorts += o.a_short;
    }
    CHECK(shorts == 1);
  }

  // Cambio de signo de millis() (desbordamiento a 32 bits) en mitad de una pulsación larga.
  {
    uint32_t start = 0xFFFFFFFFu - 300u;
    ButtonPair bp2;
    int a_longs = 0;
    uint32_t k_long = 0;
    for (uint32_t k = 0; k < 1500; k += 10) {
      BtnOut o = bp2.update(start + k, k >= 100, false);
      if (o.a_long) { a_longs++; k_long = k; }
    }
    CHECK(a_longs == 1);
    CHECK(k_long >= 1100 && k_long <= 1160);  // 1 s desde la pulsación, aunque el reloj dé la vuelta en medio
  }
  return reportAndExit("test_buttons");
}
