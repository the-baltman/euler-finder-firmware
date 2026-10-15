#include "ui.h"
#include <Fonts/FreeSans9pt7b.h>
#include <Fonts/FreeSansBold12pt7b.h>
#include <Fonts/FreeSansBold18pt7b.h>
#include <math.h>
#include "../config/marcas.h"
#include "../config/tuning.h"

namespace euler {

namespace {

constexpr int kC = 120;  // centro de la pantalla, px

constexpr uint16_t rgb(uint8_t r, uint8_t g, uint8_t b) {
  return static_cast<uint16_t>(((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3));
}

struct Palette {
  uint16_t bg, fg, dim, star, crit;
};
// Día: tinta de fondo, papel de trazo. dim = papel al ~40 % sobre la tinta.
constexpr Palette kDay = {rgb(0x0F, 0x12, 0x18), rgb(0xF3, 0xF1, 0xEC), rgb(0x6A, 0x6C, 0x6E),
                          rgb(0xE8, 0x48, 0x3A), rgb(0xE8, 0x48, 0x3A)};
// Noche: fondo negro y todo en tonos de rojo (sin blanco ni azul que arruinen la visión nocturna).
constexpr Palette kNight = {rgb(0, 0, 0), rgb(0xB8, 0x32, 0x28), rgb(0x4A, 0x16, 0x10),
                            rgb(0xE8, 0x48, 0x3A), rgb(0xE8, 0x48, 0x3A)};

GFXcanvas16* g_c = nullptr;
Palette g_p = kDay;

float rad(float deg) { return deg * kDeg2Rad; }

void centerText(const char* s, int y, const GFXfont* font, uint16_t color) {
  g_c->setFont(font);
  g_c->setTextColor(color);
  int16_t x1, y1;
  uint16_t w, h;
  g_c->getTextBounds(s, 0, 0, &x1, &y1, &w, &h);
  g_c->setCursor(kC - static_cast<int>(w) / 2 - x1, y);
  g_c->print(s);
}

// Anillo grueso entre dos ángulos (grados, 0 = arriba, horario). Se arma con cuadriláteros.
void arc(int r_out, int r_in, float a0, float a1, uint16_t color) {
  const float step = 3.0f;
  for (float a = a0; a < a1; a += step) {
    float b = a + step < a1 ? a + step : a1;
    float s0 = sinf(rad(a)), c0 = cosf(rad(a)), s1 = sinf(rad(b)), c1 = cosf(rad(b));
    int ox0 = kC + static_cast<int>(roundf(r_out * s0)), oy0 = kC - static_cast<int>(roundf(r_out * c0));
    int ix0 = kC + static_cast<int>(roundf(r_in * s0)), iy0 = kC - static_cast<int>(roundf(r_in * c0));
    int ox1 = kC + static_cast<int>(roundf(r_out * s1)), oy1 = kC - static_cast<int>(roundf(r_out * c1));
    int ix1 = kC + static_cast<int>(roundf(r_in * s1)), iy1 = kC - static_cast<int>(roundf(r_in * c1));
    g_c->fillTriangle(ox0, oy0, ix0, iy0, ox1, oy1, color);
    g_c->fillTriangle(ix0, iy0, ix1, iy1, ox1, oy1, color);
  }
}

void progressRing(float p) {
  arc(116, 108, 0, 360, g_p.dim);
  if (p > 0.0f) arc(116, 108, 0, 360.0f * (p > 1.0f ? 1.0f : p), g_p.fg);
}

// Línea gruesa de (x0,y0) a (x1,y1).
void thickLine(float x0, float y0, float x1, float y1, float w, uint16_t color) {
  float dx = x1 - x0, dy = y1 - y0;
  float len = sqrtf(dx * dx + dy * dy);
  if (len < 0.5f) return;
  float nx = -dy / len * w * 0.5f, ny = dx / len * w * 0.5f;
  g_c->fillTriangle(x0 + nx, y0 + ny, x0 - nx, y0 - ny, x1 + nx, y1 + ny, color);
  g_c->fillTriangle(x0 - nx, y0 - ny, x1 - nx, y1 - ny, x1 + nx, y1 + ny, color);
}

// Estrella de 4 puntas (símbolo del proyecto, simplificado).
void star(int cx, int cy, int r, uint16_t color) {
  int in = r / 3;
  g_c->fillTriangle(cx, cy - r, cx - in, cy, cx + in, cy, color);
  g_c->fillTriangle(cx, cy + r, cx - in, cy, cx + in, cy, color);
  g_c->fillTriangle(cx - r, cy, cx, cy - in, cx, cy + in, color);
  g_c->fillTriangle(cx + r, cy, cx, cy - in, cx, cy + in, color);
}

// Mira: círculo con cuatro marcas hacia afuera.
void reticle(int r, uint16_t color, bool thick) {
  g_c->drawCircle(kC, kC, r, color);
  if (thick) {
    g_c->drawCircle(kC, kC, r - 1, color);
    g_c->drawCircle(kC, kC, r + 1, color);
  }
  g_c->drawFastHLine(kC - r - 10, kC, 10, color);
  g_c->drawFastHLine(kC + r, kC, 10, color);
  g_c->drawFastVLine(kC, kC - r - 10, 10, color);
  g_c->drawFastVLine(kC, kC + r, 10, color);
}

void drawLogo() {
  // E redonda abierta (la mira que es órbita) con la estrella roja en la abertura.
  const float gap_center = 70.0f;  // grados desde arriba, horario: abertura hacia la derecha
  arc(58, 48, gap_center + 22.0f, gap_center + 338.0f, g_p.fg);
  g_c->fillRect(kC - 4, kC - 3, 38, 7, g_p.fg);  // trazo central que apunta a la abertura
  float sx = kC + 54.0f * sinf(rad(gap_center)), sy = kC - 54.0f * cosf(rad(gap_center));
  star(static_cast<int>(sx), static_cast<int>(sy), 11, g_p.star);
  centerText("EULER", 205, &FreeSansBold18pt7b, g_p.fg);
}

void drawSelfTest(const UiModel& m) {
  centerText("Autoprueba", 62, &FreeSansBold12pt7b, g_p.fg);
  char line[40];
  if (!m.selftest_done) {
    centerText("IMU ...", 112, &FreeSans9pt7b, g_p.fg);
  } else if (m.selftest_ok) {
    centerText("IMU  OK", 112, &FreeSans9pt7b, g_p.fg);
    if (!m.selftest_id_known) {
      snprintf(line, sizeof(line), "Posible clon (ID %02X)", m.who_am_i);
      centerText(line, 140, &FreeSans9pt7b, g_p.dim);
    }
  }
  centerText("Pantalla OK", 168, &FreeSans9pt7b, g_p.fg);
}

void drawFatal(const UiModel& m) {
  // Ícono crítico: el rojo sí va aquí (y solo aquí), nunca en el texto.
  g_c->fillCircle(kC, 62, 26, g_p.crit);
  thickLine(kC - 12, 50, kC + 12, 74, 7, g_p.bg);
  thickLine(kC + 12, 50, kC - 12, 74, 7, g_p.bg);
  const char* l1 = "IMU no responde";
  const char* l2 = "Revisa SDA y SCL";
  if (m.fatal == FatalReason::ImuBadData) {
    l1 = "IMU con datos raros";
    l2 = "Puede ser clon malo";
  } else if (m.fatal == FatalReason::ImuLost) {
    l1 = "IMU se desconecto";
    l2 = "Revisa los cables";
  }
  centerText(l1, 125, &FreeSansBold12pt7b, g_p.fg);
  centerText(l2, 153, &FreeSans9pt7b, g_p.fg);
  centerText("Pulsa A o B", 190, &FreeSans9pt7b, g_p.dim);
  centerText("para reintentar", 210, &FreeSans9pt7b, g_p.dim);
}

void drawBias(const UiModel& m) {
  progressRing(m.bias_progress);
  centerText("Midiendo", 98, &FreeSansBold12pt7b, g_p.fg);
  centerText("No muevas el equipo", 130, &FreeSans9pt7b, g_p.fg);
  if (m.phase_ms > 8000 && m.bias_progress < 0.05f) {
    centerText("Apoyalo quieto", 158, &FreeSans9pt7b, g_p.dim);
  }
}

void markLabel(const UiModel& m, int y) {
  const Marca& k = MARCAS[m.mark_idx < kNumMarcas ? m.mark_idx : 0];
  char buf[32];
  snprintf(buf, sizeof(buf), k.ejemplo ? "%s ej." : "%s", k.nombre);
  centerText(buf, y, &FreeSans9pt7b, g_p.fg);
}

void drawWaitSync(const UiModel& m) {
  progressRing(m.ring_progress);
  centerText("Marca 1", 58, &FreeSansBold12pt7b, g_p.fg);
  reticle(30, g_p.fg, false);
  centerText(m.ring_progress > 0 ? "Sincronizando" : "Apunta y sujeta B", 195, &FreeSans9pt7b, g_p.fg);
}

void drawGuide(const UiModel& m) {
  const GuideOut& g = m.guide;
  if (m.ring_progress > 0) progressRing(m.ring_progress);
  else arc(117, 115, 0, 360, g_p.dim);

  markLabel(m, 36);

  if (g.state == GuideState::Far) {
    // Lejos: flecha desde el centro hacia donde hay que mover; la estrella espera en el borde.
    float dx = cosf(g.arrow_rad), dy = -sinf(g.arrow_rad);
    float x0 = kC + dx * 18, y0 = kC + dy * 18;
    float x1 = kC + dx * 56, y1 = kC + dy * 56;
    float hx = kC + dx * 78, hy = kC + dy * 78;
    thickLine(x0, y0, x1, y1, 10, g_p.fg);
    float px = -dy, py = dx;
    g_c->fillTriangle(hx, hy, x1 + px * 17, y1 + py * 17, x1 - px * 17, y1 - py * 17, g_p.fg);
  } else {
    // Cerca / en mira: mandan las escalas. Giro abajo, altura a la derecha; la marca central larga es el cero.
    g_c->drawFastHLine(55, 205, 130, g_p.dim);
    g_c->drawFastVLine(55, 199, 12, g_p.dim);
    g_c->drawFastVLine(185, 199, 12, g_p.dim);
    g_c->drawFastVLine(kC, 195, 20, g_p.fg);
    g_c->drawFastVLine(205, 55, 130, g_p.dim);
    g_c->drawFastHLine(199, 55, 12, g_p.dim);
    g_c->drawFastHLine(199, 185, 12, g_p.dim);
    g_c->drawFastHLine(195, kC, 20, g_p.fg);
    int gx = kC + static_cast<int>(g.giro_ptr * 65.0f);
    g_c->fillTriangle(gx - 8, 188, gx + 8, 188, gx, 202, g_p.fg);   // apunta a la escala de giro
    int ay = kC - static_cast<int>(g.alt_ptr * 65.0f);
    g_c->fillTriangle(188, ay - 8, 188, ay + 8, 202, ay, g_p.fg);   // apunta a la escala de altura
    reticle(34, g_p.fg, g.state == GuideState::InView);
  }

  // Estrella (única pieza roja de la guía).
  int sx = kC + static_cast<int>(roundf(g.star_x_px));
  int sy = kC + static_cast<int>(roundf(g.star_y_px));
  star(sx, sy, g.state == GuideState::InView ? 14 : 11, g_p.star);

  if (g.state == GuideState::InView) {
    centerText("EN MIRA", 92, &FreeSansBold12pt7b, g_p.fg);
  } else if (m.sync_toast) {
    centerText("Sync listo", 92, &FreeSans9pt7b, g_p.fg);
  }
}

}  // namespace

void uiRender(Display& d, const UiModel& m) {
  g_c = &d.canvas();
  g_p = m.night ? kNight : kDay;
  d.setContentRotation(m.phase == Phase::WaitSync || m.phase == Phase::Guide || m.phase == Phase::Bias
                           ? m.mount.screen_rotation_deg
                           : 0);
  g_c->fillScreen(g_p.bg);
  switch (m.phase) {
    case Phase::Logo: drawLogo(); break;
    case Phase::SelfTest: drawSelfTest(m); break;
    case Phase::Fatal: drawFatal(m); break;
    case Phase::Bias: drawBias(m); break;
    case Phase::WaitSync: drawWaitSync(m); break;
    case Phase::Guide: drawGuide(m); break;
  }
}

}  // namespace euler
