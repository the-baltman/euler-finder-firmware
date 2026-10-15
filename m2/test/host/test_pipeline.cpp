// Integración de punta a punta con IMU simulado: sesgo -> montaje -> fusión -> sync -> guía -> EN MIRA.
// 24 semillas x 2 montajes. Los ruidos y sesgos son supuestos de simulación [estimado: simulador]: las cifras
// que imprime son del simulador, NO del sensor real ni del sistema.
#include <vector>
#include "check.h"
#include "sim.h"
#include "../../src/core/app_fsm.h"
#include "../../src/core/fusion.h"
#include "../../src/core/gyro_bias.h"
#include "../../src/core/marks.h"
#include "../../src/core/mount.h"

using namespace euler;

constexpr int kSeeds = 24;
constexpr double kDt = 0.01;

struct Seg {
  double dur_s;
  double az, el;     // pose verdadera al final del tramo (el tramo llega con smoothstep)
  double wobble;     // temblor de la mano durante el tramo, grados
};

struct Result {
  bool reached_phase_guide = false;
  bool mount_ok = false;
  GuideState final_state = GuideState::Far;
  double pipeline_err_deg = 1e9;  // error del apuntado estimado frente al verdadero, relativo al sync
  double d_giro = 0;              // lo que la pantalla dice que falta al final
};

static Result runScenario(unsigned seed, bool flat, double stop_short_az_deg) {
  Result res;
  sim::NoiseModel nm;
  sim::Imu probe(seed * 131 + (flat ? 0 : 1), {0, 0, 0}, nm);
  Vec3 bias = probe.randomBias(3.0);
  sim::Imu imu(seed * 131 + (flat ? 0 : 1) + 1000, bias, nm);

  std::mt19937 rr(seed);
  std::uniform_real_distribution<double> u(0, 1);
  double az0 = -170 + 340 * u(rr);  // incluye pasar por ±180
  double el0 = 20 * u(rr);
  double az1 = az0 + 30 + 20 * u(rr), el1 = el0 + 3 + 5 * u(rr);  // la marca 1 en el mundo
  Target t2 = objetivoDeMarca(1);
  double az2 = az1 + t2.giro_deg - stop_short_az_deg, el2 = el1 + t2.altura_deg;

  double t_sync_hold = 1.5;
  std::vector<Seg> segs = {
      {4.0, az0, el0, 0.0},     // quieto: mide el sesgo
      {2.0, az1, el1, 0.8},     // lleva el nivelador a la marca 1
      {t_sync_hold, az1, el1, 0.15},  // sostiene y presiona B (temblor de mano)
      {3.0, az2, el2, 0.8},     // va a la marca 2
      {3.0, az2, el2, 0.15},    // sostiene
  };

  AppFsm fsm;
  fsm.begin(0);
  GyroBias gb;
  Fusion6 fu;
  uint32_t now_ms = 0;
  // Se salta logo y autoprueba (ya tienen su prueba): entra directo a medir el sesgo.
  now_ms = tun::kLogoMs + 10;
  fsm.step(now_ms, {}, false, {});
  SelfTestResult st; st.ok = true; st.id_known = true; st.who_am_i = 0x71;
  fsm.setSelfTest(st, now_ms);
  now_ms += tun::kSelfTestMinMs + 10;
  fsm.step(now_ms, {}, false, {});
  fsm.takeBiasRestart();

  sim::Mat3 prev = sim::attitude(flat, az0, el0, 0);
  double t_total = 0, seg_start_az = az0, seg_start_el = el0;
  bool synced_once = false;
  double true_sync_az = 0, true_sync_el = 0;
  double true_az = az0, true_el = el0;
  Pointing last_pose{};
  bool last_pose_ok = false;

  for (size_t si = 0; si < segs.size(); si++) {
    const Seg& sg = segs[si];
    int n = static_cast<int>(sg.dur_s / kDt + 0.5);
    for (int i = 1; i <= n; i++) {
      double f = sim::smoothstep(static_cast<double>(i) / n);
      double az = seg_start_az + (sg.az - seg_start_az) * f;
      double el = seg_start_el + (sg.el - seg_start_el) * f;
      double ph = 2 * sim::kPi * 3.0 * (t_total + i * kDt);
      az += sg.wobble * std::sin(ph) + sg.wobble * 0.5 * std::sin(1.7 * ph + 1);
      el += sg.wobble * std::sin(1.3 * ph + 2) * 0.7;
      double roll = 3.0 * std::sin(0.8 * (t_total + i * kDt)) * (sg.wobble > 0 ? 1 : 0);
      sim::Mat3 now = sim::attitude(flat, az, el, roll);
      bool moving = si == 1 || si == 3;
      Vec3 g, a;
      imu.sample(prev, now, kDt, moving, &g, &a);
      prev = now;
      sim::truePointing(now, flat, &true_az, &true_el);

      now_ms += 10;
      BtnOut btn;
      Pointing pose{};
      bool pose_ok = false;
      Phase ph_now = fsm.phase();
      if (ph_now == Phase::Bias || ph_now == Phase::WaitSync || ph_now == Phase::Guide) {
        bool done = gb.feed(g, a);
        if (ph_now == Phase::Bias) {
          fsm.biasProgress(gb.progress());
          if (done) {
            fu.initFromAccel(gb.meanAccelG());
            fsm.biasDone(gb.meanAccelG(), now_ms);
            res.mount_ok = fsm.model().mount.mount == (flat ? Mount::Flat : Mount::VertUp);
          }
        } else if (fu.initialized()) {
          fu.update((g - gb.biasDps()) * kDeg2Rad, a, static_cast<float>(kDt));
          pose = fu.pointing(fsm.model().mount.pointing_axis);
          pose_ok = true;
        }
      }
      // B largo al final del tramo de sostén en la marca 1
      if (si == 2 && i == n && fsm.phase() == Phase::WaitSync) {
        btn.b_long = true;
        btn.b_progress = 1;
        true_sync_az = true_az;
        true_sync_el = true_el;
        synced_once = true;
      }
      fsm.step(now_ms, btn, pose_ok, pose);
      last_pose = pose;
      last_pose_ok = pose_ok;
    }
    t_total += sg.dur_s;
    seg_start_az = sg.az;
    seg_start_el = sg.el;
  }

  res.reached_phase_guide = fsm.phase() == Phase::Guide && synced_once;
  if (res.reached_phase_guide && last_pose_ok) {
    res.final_state = fsm.model().guide.state;
    res.d_giro = fsm.model().guide.d_giro_deg;
    Pointing ref = fsm.sync().ref();
    double est_daz = wrap180(static_cast<float>(last_pose.az_deg - ref.az_deg));
    double est_del = last_pose.el_deg - ref.el_deg;
    double tru_daz = wrap180(static_cast<float>(true_az - true_sync_az));
    double tru_del = true_el - true_sync_el;
    res.pipeline_err_deg = std::hypot(wrap180(static_cast<float>(est_daz - tru_daz)), est_del - tru_del);
  }
  return res;
}

int main() {
  double worst_err = 0;
  int in_view = 0, total = 0;
  for (int flat = 1; flat >= 0; flat--) {
    for (unsigned seed = 1; seed <= kSeeds; seed++) {
      Result r = runScenario(seed, flat == 1, 0.0);
      total++;
      CHECK(r.reached_phase_guide);
      CHECK(r.mount_ok);
      CHECK(r.pipeline_err_deg < 1.0);  // el apuntado estimado sigue al verdadero (supuestos del simulador)
      if (r.pipeline_err_deg > worst_err) worst_err = r.pipeline_err_deg;
      if (r.final_state == GuideState::InView) in_view++;
      CHECK(r.final_state == GuideState::InView);

      // Si el usuario se detiene 6 grados antes de la marca, NO debe decir EN MIRA y debe pedir ~6 de giro.
      Result s = runScenario(seed, flat == 1, 6.0);
      CHECK(s.final_state == GuideState::Near);
      CHECK(s.d_giro > 4.0 && s.d_giro < 8.0);
    }
  }
  std::printf("  punta a punta (sesgo, montaje, fusion, sync, guia): EN MIRA en %d de %d corridas; peor error del apuntado estimado %.3f grados (%d semillas x 2 montajes) [estimado: simulador, supuestos de ruido y sesgo del simulador]\n",
              in_view, total, worst_err, kSeeds);
  return reportAndExit("test_pipeline");
}
