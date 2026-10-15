// Nivelador M2 de EULER finder, demo JIJE (carril A). ESP32-C3 SuperMini + MPU-9250 + GC9A01.
// Ver m2/README.md. Regla dura: USB y batería NUNCA a la vez (SW1 en OFF para programar).
#include <Arduino.h>
#include "app.h"
#include "config/pins.h"
#include "drivers/display.h"
#include "ui/ui.h"

using namespace euler;

namespace {
Display g_display;
constexpr uint32_t kFramePeriodMs = 100;      // la UI dibuja a ~10 cuadros por segundo (SPI a 10 MHz)
constexpr uint32_t kHangRestartMs = 3000;     // si la tarea de control no avanza en este tiempo, reinicia
uint32_t g_last_frame_ms = 0;
uint32_t g_hb_last = 0;
uint32_t g_hb_changed_ms = 0;
bool g_night_applied = false;
}  // namespace

void setup() {
  Serial.begin(115200);
  Serial.setTxTimeoutMs(0);  // sin PC conectada no se debe bloquear al imprimir
  enableLoopWDT();           // si el loop de la UI se cuelga, el chip se reinicia solo

  if (!g_display.begin()) {
    Serial.println("[error] sin RAM para el lienzo de la pantalla");
    delay(1000);
    ESP.restart();
  }
  appBegin();
  g_hb_changed_ms = millis();
}

void loop() {
  feedLoopWDT();
  uint32_t now = millis();

  // Vigilancia de la tarea de control: es la única que puede colgarse en el bus I2C.
  uint32_t hb = appHeartbeat();
  if (hb != g_hb_last) {
    g_hb_last = hb;
    g_hb_changed_ms = now;
  } else if (now - g_hb_changed_ms > kHangRestartMs) {
    Serial.println("[error] la tarea de control no responde, reiniciando");
    delay(50);
    ESP.restart();
  }

  if (now - g_last_frame_ms >= kFramePeriodMs) {
    g_last_frame_ms = now;
    UiModel m = appSnapshot();
    if (m.night != g_night_applied) {
      g_night_applied = m.night;
      g_display.setBacklight(m.night ? hw::kBlNightDuty : hw::kBlDayDuty);
    }
    uiRender(g_display, m);
    g_display.push();
  }
  delay(2);  // cede CPU a la tarea de control y a la IDLE
}
