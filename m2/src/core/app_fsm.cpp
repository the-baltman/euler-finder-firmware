#include "app_fsm.h"
#include "marks.h"

namespace euler {

void AppFsm::begin(uint32_t now) {
  model_ = UiModel{};
  sync_.clear();
  guide_.reset();
  st_done_ = false;
  bias_restart_ = false;
  enter(Phase::Logo, now);
}

void AppFsm::enter(Phase p, uint32_t now) {
  phase_ = p;
  t_enter_ = now;
  model_.phase = p;
  model_.phase_ms = 0;
  model_.ring_progress = 0;
  if (p == Phase::SelfTest) {
    st_done_ = false;
    model_.selftest_done = false;
    model_.fatal = FatalReason::None;
  }
}

void AppFsm::startBias(uint32_t now) {
  sync_.clear();
  guide_.reset();
  model_.synced = false;
  model_.sync_toast = false;
  model_.mark_idx = 0;
  model_.bias_progress = 0;
  bias_restart_ = true;
  enter(Phase::Bias, now);
}

bool AppFsm::takeBiasRestart() {
  bool r = bias_restart_;
  bias_restart_ = false;
  return r;
}

void AppFsm::setSelfTest(const SelfTestResult& r, uint32_t now) {
  (void)now;
  if (phase_ != Phase::SelfTest) return;
  st_ = r;
  st_done_ = true;
  model_.selftest_done = true;
  model_.selftest_ok = r.ok;
  model_.selftest_id_known = r.id_known;
  model_.who_am_i = r.who_am_i;
  model_.fatal = r.fatal;
}

void AppFsm::imuFault(uint32_t now) {
  if (phase_ != Phase::Bias && phase_ != Phase::WaitSync && phase_ != Phase::Guide) return;
  sync_.clear();
  model_.synced = false;
  model_.fatal = FatalReason::ImuLost;
  enter(Phase::Fatal, now);
}

void AppFsm::biasDone(Vec3 up_body, uint32_t now) {
  if (phase_ != Phase::Bias) return;
  model_.mount = detectMount(up_body);
  model_.bias_progress = 1.0f;
  enter(Phase::WaitSync, now);
}

void AppFsm::step(uint32_t now, const BtnOut& b, bool pose_valid, Pointing pose) {
  model_.phase_ms = now - t_enter_;
  model_.ring_progress = 0;

  switch (phase_) {
    case Phase::Logo:
      if (model_.phase_ms >= tun::kLogoMs) enter(Phase::SelfTest, now);
      break;

    case Phase::SelfTest:
      // Se espera el resultado Y un mínimo de tiempo para que se alcance a leer.
      if (st_done_ && model_.phase_ms >= tun::kSelfTestMinMs) {
        if (st_.ok) startBias(now);
        else enter(Phase::Fatal, now);
      }
      break;

    case Phase::Fatal:
      // Salida: cualquier pulsación corta repite la autoprueba (cable suelto, etc.).
      if (b.a_short || b.b_short) enter(Phase::SelfTest, now);
      break;

    case Phase::Bias:
      if (b.a_long) model_.night = !model_.night;
      break;

    case Phase::WaitSync:
    case Phase::Guide: {
      if (b.a_long) model_.night = !model_.night;
      if (b.combo) {  // A+B 3 s: borrar calibración
        startBias(now);
        break;
      }
      if (pose_valid) sync_.push(pose);
      model_.ring_progress = b.b_progress;

      if (b.b_long) {
        if (sync_.commit()) {
          model_.synced = true;
          t_sync_ = now;
          if (phase_ == Phase::WaitSync) {
            model_.mark_idx = kNumMarcas > 1 ? 1 : 0;  // tras el sync se guía hacia la marca 2
            guide_.reset();
            enter(Phase::Guide, now);
          }
        }
      }
      if (phase_ == Phase::Guide) {
        if (b.a_short) {
          model_.mark_idx = (model_.mark_idx + 1) % kNumMarcas;
          guide_.reset();
        }
        if (pose_valid) {
          model_.guide = guide_.update(pose, sync_.ref(), objetivoDeMarca(model_.mark_idx));
        }
        model_.sync_toast = model_.synced && (now - t_sync_) < tun::kSyncToastMs;
      }
      break;
    }
  }
}

}  // namespace euler
