// Máquina de estados: flujo completo, errores y salidas de cada estado.
#include "check.h"
#include "../../src/core/app_fsm.h"
#include "../../src/core/marks.h"

using namespace euler;

struct Rig {
  AppFsm f;
  uint32_t t = 0;
  Pointing pose{0, 0};
  bool pose_ok = true;
  void tick(BtnOut b = {}, uint32_t dt = 10) {
    t += dt;
    f.step(t, b, pose_ok, pose);
  }
  void run(uint32_t ms) {
    for (uint32_t i = 0; i < ms; i += 10) tick();
  }
  void toWaitSync() {
    f.begin(t);
    run(tun::kLogoMs + 20);
    SelfTestResult r; r.ok = true; r.id_known = true; r.who_am_i = 0x71;
    f.setSelfTest(r, t);
    run(tun::kSelfTestMinMs + 20);
    f.biasDone({0, 0.02f, 1.0f}, t);
    tick();
  }
};

static BtnOut ev(bool a_short, bool a_long, bool b_short, bool b_long, bool combo, float bp = 0) {
  BtnOut o;
  o.a_short = a_short; o.a_long = a_long; o.b_short = b_short; o.b_long = b_long; o.combo = combo;
  o.b_progress = bp;
  return o;
}

int main() {
  // --- flujo feliz ---
  {
    Rig r;
    r.f.begin(0);
    CHECK(r.f.phase() == Phase::Logo);
    CHECK(!r.f.model().night);  // el modo noche NO es el predeterminado
    r.run(tun::kLogoMs - 100);
    CHECK(r.f.phase() == Phase::Logo);
    r.run(200);
    CHECK(r.f.phase() == Phase::SelfTest);
    CHECK(r.f.wantsSelfTest());
    // Aunque el resultado llegue pronto, la pantalla espera el mínimo para poder leerse.
    SelfTestResult ok; ok.ok = true; ok.id_known = false; ok.who_am_i = 0x68;
    r.f.setSelfTest(ok, r.t);
    CHECK(!r.f.wantsSelfTest());
    r.tick();
    CHECK(r.f.phase() == Phase::SelfTest);
    CHECK(r.f.model().selftest_done && !r.f.model().selftest_id_known);
    r.run(tun::kSelfTestMinMs);
    CHECK(r.f.phase() == Phase::Bias);
    CHECK(r.f.takeBiasRestart());
    CHECK(!r.f.takeBiasRestart());  // se consume una sola vez
    // El sesgo no avanza de fase por botones.
    r.tick(ev(false, false, false, true, false));
    CHECK(r.f.phase() == Phase::Bias);
    r.f.biasDone({0, 0.02f, 1.0f}, r.t);
    CHECK(r.f.phase() == Phase::WaitSync);
    CHECK(r.f.model().mount.mount == Mount::Flat);

    // B largo sin muestras de pose (fusión sin datos): no confirma.
    r.pose_ok = false;
    r.tick(ev(false, false, false, true, false, 1));
    CHECK(r.f.phase() == Phase::WaitSync && !r.f.model().synced);
    // Con pose: sync -> guía hacia la marca 2
    r.pose_ok = true;
    r.pose = {40, 7};
    for (int i = 0; i < 30; i++) r.tick();
    r.tick(ev(false, false, false, true, false, 1));
    CHECK(r.f.phase() == Phase::Guide);
    CHECK(r.f.model().synced && r.f.model().mark_idx == 1);
    CHECK(r.f.model().sync_toast);
    CHECK_NEAR(r.f.sync().ref().az_deg, 40, 1e-3);
    // Con el equipo sobre la marca 1, la marca 2 está lejos o cerca según el archivo de marcas: el
    // giro que falta es el de la marca 2.
    CHECK_NEAR(r.f.model().guide.d_giro_deg, objetivoDeMarca(1).giro_deg, 1e-3);
    // El aviso de sync dura poco
    r.run(tun::kSyncToastMs + 50);
    CHECK(!r.f.model().sync_toast);

    // A corto cambia de marca y da la vuelta
    int idx = r.f.model().mark_idx;
    for (int i = 0; i < kNumMarcas; i++) {
      r.tick(ev(true, false, false, false, false));
      idx = (idx + 1) % kNumMarcas;
      CHECK(r.f.model().mark_idx == idx);
    }
    // A largo alterna el modo noche
    r.tick(ev(false, true, false, false, false));
    CHECK(r.f.model().night);
    r.tick(ev(false, true, false, false, false));
    CHECK(!r.f.model().night);
  }

  // --- llegar a la marca 2 ---
  {
    Rig r;
    r.toWaitSync();
    r.pose = {10, 3};
    for (int i = 0; i < 30; i++) r.tick();
    r.tick(ev(false, false, false, true, false, 1));
    CHECK(r.f.phase() == Phase::Guide);
    Target t = objetivoDeMarca(r.f.model().mark_idx);
    r.pose = {10 + t.giro_deg, 3 + t.altura_deg};
    r.tick();  // LEJOS -> CERCA
    r.tick();  // CERCA -> EN MIRA
    CHECK(r.f.model().guide.state == GuideState::InView);
    // Re-sync dentro de la guía mantiene la marca elegida
    int idx = r.f.model().mark_idx;
    r.pose = {50, 3};
    for (int i = 0; i < 30; i++) r.tick();
    r.tick(ev(false, false, false, true, false, 1));
    CHECK(r.f.phase() == Phase::Guide && r.f.model().mark_idx == idx);
    CHECK_NEAR(r.f.sync().ref().az_deg, 50, 1e-3);
  }

  // --- A+B borra la calibración y vuelve a medir el sesgo ---
  {
    Rig r;
    r.toWaitSync();
    for (int i = 0; i < 30; i++) r.tick();
    r.tick(ev(false, false, false, true, false, 1));
    CHECK(r.f.phase() == Phase::Guide);
    r.tick(ev(false, false, false, false, true));
    CHECK(r.f.phase() == Phase::Bias);
    CHECK(!r.f.model().synced && !r.f.sync().valid() && r.f.model().mark_idx == 0);
    CHECK(r.f.takeBiasRestart());
    // Y sin un nuevo sync la guía no se alcanza: B largo en Bias no hace nada.
    r.tick(ev(false, false, false, true, false, 1));
    CHECK(r.f.phase() == Phase::Bias);
  }

  // --- falla de autoprueba: error grave y salida por reintento ---
  {
    Rig r;
    r.f.begin(0);
    r.run(tun::kLogoMs + 20);
    SelfTestResult bad; bad.ok = false; bad.fatal = FatalReason::ImuNoAck;
    r.f.setSelfTest(bad, r.t);
    r.run(tun::kSelfTestMinMs + 20);
    CHECK(r.f.phase() == Phase::Fatal);
    CHECK(r.f.model().fatal == FatalReason::ImuNoAck);
    r.run(5000);
    CHECK(r.f.phase() == Phase::Fatal);  // no se sale solo
    r.tick(ev(false, true, false, false, false));  // un largo no reintenta
    CHECK(r.f.phase() == Phase::Fatal);
    r.tick(ev(false, false, true, false, false));  // un corto sí
    CHECK(r.f.phase() == Phase::SelfTest && r.f.wantsSelfTest());
    SelfTestResult ok; ok.ok = true; ok.id_known = true; ok.who_am_i = 0x71;
    r.f.setSelfTest(ok, r.t);
    r.run(tun::kSelfTestMinMs + 20);
    CHECK(r.f.phase() == Phase::Bias);
  }

  // --- IMU que se pierde en plena guía ---
  {
    Rig r;
    r.toWaitSync();
    for (int i = 0; i < 30; i++) r.tick();
    r.tick(ev(false, false, false, true, false, 1));
    CHECK(r.f.phase() == Phase::Guide);
    r.f.imuFault(r.t);
    CHECK(r.f.phase() == Phase::Fatal && r.f.model().fatal == FatalReason::ImuLost);
    CHECK(!r.f.model().synced);
    r.tick(ev(true, false, false, false, false));
    CHECK(r.f.phase() == Phase::SelfTest);
    // Una falla del IMU durante el logo no cambia nada (aún no se usa).
    Rig r2;
    r2.f.begin(0);
    r2.f.imuFault(0);
    CHECK(r2.f.phase() == Phase::Logo);
  }

  // --- resultado de autoprueba fuera de fase se ignora ---
  {
    Rig r;
    r.f.begin(0);
    SelfTestResult bad; bad.ok = false; bad.fatal = FatalReason::ImuBadData;
    r.f.setSelfTest(bad, 0);  // aún en Logo
    r.run(tun::kLogoMs + 20);
    CHECK(r.f.phase() == Phase::SelfTest && r.f.wantsSelfTest());
  }
  return reportAndExit("test_fsm");
}
