// Máquina de estados de la demo: logo -> autoprueba -> sesgo -> espera de sync -> guía.
// Lógica pura: el hardware (IMU, botones, pantalla) vive en app.cpp / ui.
#pragma once
#include <cstdint>
#include "buttons.h"
#include "guide.h"
#include "mount.h"
#include "selftest.h"
#include "sync.h"

namespace euler {

enum class Phase : uint8_t { Logo, SelfTest, Fatal, Bias, WaitSync, Guide };

// Todo lo que la pantalla necesita para dibujar. La UI solo lee esto.
struct UiModel {
  Phase phase = Phase::Logo;
  FatalReason fatal = FatalReason::None;
  bool selftest_done = false;
  bool selftest_ok = false;
  bool selftest_id_known = true;
  uint8_t who_am_i = 0;
  float bias_progress = 0;     // 0..1
  float ring_progress = 0;     // 0..1, anillo de B (sync) mientras se mantiene pulsado
  bool night = false;
  int mark_idx = 0;
  bool synced = false;
  bool sync_toast = false;     // mostrar "Sync listo" un momento
  GuideOut guide;
  MountInfo mount;
  uint32_t phase_ms = 0;       // ms desde que se entró a la fase
};

class AppFsm {
 public:
  void begin(uint32_t now_ms);

  // --- peticiones al hardware ---
  bool wantsSelfTest() const { return phase_ == Phase::SelfTest && !st_done_; }
  bool takeBiasRestart();  // true una vez si hay que reiniciar sesgo y fusión

  // --- entradas desde el hardware ---
  void setSelfTest(const SelfTestResult& r, uint32_t now_ms);
  void imuFault(uint32_t now_ms);
  void biasProgress(float p) { model_.bias_progress = p; }
  void biasDone(Vec3 up_body, uint32_t now_ms);  // sesgo medido; up_body decide el montaje

  // pose_valid=false mientras la fusión no tenga datos.
  void step(uint32_t now_ms, const BtnOut& btn, bool pose_valid, Pointing pose);

  Phase phase() const { return phase_; }
  const UiModel& model() const { return model_; }
  const Sync& sync() const { return sync_; }

 private:
  void enter(Phase p, uint32_t now);
  void startBias(uint32_t now);
  Phase phase_ = Phase::Logo;
  uint32_t t_enter_ = 0;
  uint32_t t_sync_ = 0;
  bool st_done_ = false;
  SelfTestResult st_{};
  bool bias_restart_ = false;
  Sync sync_;
  Guide guide_;
  UiModel model_;
};

}  // namespace euler
