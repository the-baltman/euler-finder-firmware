#include "app.h"
#include <Arduino.h>
#include <esp_timer.h>
#include "config/pins.h"
#include "config/tuning.h"
#include "core/app_fsm.h"
#include "core/buttons.h"
#include "core/fusion.h"
#include "core/gyro_bias.h"
#include "core/selftest.h"
#include "drivers/imu_mpu9250.h"

namespace euler {

namespace {

// Para cambiar de sensor en B2: otro driver que implemente IImu y se instancia aquí.
ImuMpu9250 g_imu;

ButtonPair g_buttons;
Fusion6 g_fusion;
GyroBias g_bias;
AppFsm g_fsm;

UiModel g_published;
portMUX_TYPE g_mux = portMUX_INITIALIZER_UNLOCKED;
volatile uint32_t g_heartbeat = 0;

int g_imu_fail = 0;
int64_t g_last_us = 0;
Phase g_logged_phase = Phase::Logo;
uint32_t g_last_log_ms = 0;

void sleepMs(uint32_t ms) { vTaskDelay(pdMS_TO_TICKS(ms)); }

void tick(TickType_t* last_wake) {
  const uint32_t now = millis();
  BtnOut b = g_buttons.update(now, digitalRead(pins::kBtnA) == LOW, digitalRead(pins::kBtnB) == LOW);

  if (g_fsm.wantsSelfTest()) {
    SelfTestResult r = selfTestImu(g_imu, sleepMs);  // bloquea ~0.4 s; el watchdog de la UI tolera 2 s
    g_fsm.setSelfTest(r, millis());
    Serial.printf("[autoprueba] ok=%d id=0x%02X conocido=%d fatal=%d\n", r.ok, r.who_am_i, r.id_known,
                  static_cast<int>(r.fatal));
    *last_wake = xTaskGetTickCount();  // no recuperar los ticks perdidos en ráfaga
  }
  if (g_fsm.takeBiasRestart()) {
    g_bias.reset();
    g_fusion.reset();
    g_imu_fail = 0;
  }

  Pointing pose{};
  bool pose_valid = false;
  Phase ph = g_fsm.phase();
  if (ph == Phase::Bias || ph == Phase::WaitSync || ph == Phase::Guide) {
    ImuSample s;
    if (g_imu.read(s) == ImuStatus::Ok) {
      g_imu_fail = 0;
      bool window_done = g_bias.feed(s.gyro_dps, s.accel_g);
      if (ph == Phase::Bias) {
        g_fsm.biasProgress(g_bias.progress());
        if (window_done) {
          g_fusion.initFromAccel(g_bias.meanAccelG());
          g_last_us = esp_timer_get_time();
          g_fsm.biasDone(g_bias.meanAccelG(), now);
        }
      } else if (g_fusion.initialized()) {
        // dt medido (con límites) y no el nominal, por si un tick se atrasa.
        int64_t t = esp_timer_get_time();
        float dt = static_cast<float>(t - g_last_us) * 1e-6f;
        g_last_us = t;
        dt = clampf(dt, tun::kDtMinS, tun::kDtMaxS);
        Vec3 w = (s.gyro_dps - g_bias.biasDps()) * kDeg2Rad;
        g_fusion.update(w, s.accel_g, dt);
        pose = g_fusion.pointing(g_fsm.model().mount.pointing_axis);
        pose_valid = true;
      }
    } else if (++g_imu_fail >= tun::kImuFaultReads) {
      g_imu_fail = 0;
      g_fsm.imuFault(now);
    }
  }

  g_fsm.step(now, b, pose_valid, pose);

  const UiModel& m = g_fsm.model();
  if (m.phase != g_logged_phase) {
    g_logged_phase = m.phase;
    Serial.printf("[fase] %d\n", static_cast<int>(m.phase));
  }
  if (pose_valid && now - g_last_log_ms >= 500) {  // ayuda para la prueba de ejes del README
    g_last_log_ms = now;
    Serial.printf("[pose] giro=%.1f altura=%.1f marca=%d estado=%d\n", pose.az_deg, pose.el_deg, m.mark_idx,
                  static_cast<int>(m.guide.state));
  }

  portENTER_CRITICAL(&g_mux);
  g_published = m;
  portEXIT_CRITICAL(&g_mux);
  g_heartbeat = g_heartbeat + 1;
}

void controlTask(void*) {
  TickType_t last = xTaskGetTickCount();
  for (;;) {
    // Periodo fijo guiado por el tick del RTOS (1 ms), no "lo que tarde el lazo".
    vTaskDelayUntil(&last, pdMS_TO_TICKS(1000 / tun::kSampleHz));
    tick(&last);
  }
}

}  // namespace

void appBegin() {
  pinMode(pins::kBtnA, INPUT);  // pull-up externo de 10 kΩ en el hardware
  pinMode(pins::kBtnB, INPUT);
  g_fsm.begin(millis());
  g_published = g_fsm.model();
  // Prioridad mayor que la del loop de Arduino (1): la fusión no se atrasa mientras la UI envía el cuadro por SPI.
  xTaskCreate(controlTask, "control", 4096, nullptr, 2, nullptr);
}

UiModel appSnapshot() {
  UiModel m;
  portENTER_CRITICAL(&g_mux);
  m = g_published;
  portEXIT_CRITICAL(&g_mux);
  return m;
}

uint32_t appHeartbeat() { return g_heartbeat; }

}  // namespace euler
