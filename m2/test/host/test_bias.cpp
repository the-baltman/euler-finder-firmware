// Sesgo del giroscopio: ventana quieta, reinicio por movimiento, re-estimación. 24 semillas.
#include <random>
#include "check.h"
#include "../../src/core/gyro_bias.h"
#include "../../src/config/tuning.h"

using namespace euler;

constexpr int kSeeds = 24;

struct Src {
  std::mt19937 rng;
  Vec3 bias;
  double sg = 0.1, sa = 0.003;  // [simulado]
  explicit Src(unsigned seed, Vec3 b) : rng(seed), bias(b) {}
  void sample(Vec3* g, Vec3* a, Vec3 extra = {0, 0, 0}) {
    std::normal_distribution<double> n(0, 1);
    *g = {static_cast<float>(bias.x + extra.x + n(rng) * sg), static_cast<float>(bias.y + extra.y + n(rng) * sg),
          static_cast<float>(bias.z + extra.z + n(rng) * sg)};
    *a = {static_cast<float>(0.1 + n(rng) * sa), static_cast<float>(0.2 + n(rng) * sa),
          static_cast<float>(std::sqrt(1 - 0.05) + n(rng) * sa)};
  }
};

static Vec3 randBias(std::mt19937& r) {
  std::uniform_real_distribution<double> u(-3.0, 3.0);
  return {static_cast<float>(u(r)), static_cast<float>(u(r)), static_cast<float>(u(r))};
}

static void testQuietWindowGivesBias() {
  double worst = 0;
  for (int seed = 1; seed <= kSeeds; seed++) {
    std::mt19937 r(seed);
    Vec3 b = randBias(r);
    Src s(seed, b);
    GyroBias gb;
    int done_at = -1;
    for (int i = 1; i <= 400; i++) {
      Vec3 g, a;
      s.sample(&g, &a);
      if (gb.feed(g, a) && done_at < 0) done_at = i;
      if (done_at < 0) CHECK(!gb.valid());
    }
    CHECK(done_at == static_cast<int>(tun::kBiasInitialWindowS * tun::kSampleHz));  // ni antes ni después
    CHECK(gb.valid());
    double e = norm(gb.biasDps() - b);
    if (e > worst) worst = e;
    CHECK(e < 0.05);
    CHECK_NEAR(norm(gb.meanAccelG()), 1.0, 0.01);
  }
  std::printf("  error del sesgo tras 3 s quieto: peor caso %.4f dps (%d semillas) [simulado]\n", worst, kSeeds);
}

static void testMotionRestartsWindow() {
  for (int seed = 1; seed <= kSeeds; seed++) {
    Src s(seed, {1.0f, -0.5f, 0.3f});
    GyroBias gb;
    int done_at = -1;
    for (int i = 1; i <= 700; i++) {
      Vec3 g, a;
      bool kick = (i == 200);  // un golpe de 30 °/s en una muestra
      s.sample(&g, &a, kick ? Vec3{30, 0, 0} : Vec3{0, 0, 0});
      if (gb.feed(g, a) && done_at < 0) done_at = i;
    }
    // El golpe en la muestra 200 obliga a empezar de nuevo desde 201: la ventana termina en 200+300=500.
    CHECK(done_at == 500);
  }
}

static void testConstantRotationIsNotBias() {
  Src s(1, {20.0f, 0, 0});  // girando parejo a 20 °/s: "quieto" respecto a sí mismo, pero no es sesgo
  GyroBias gb;
  for (int i = 0; i < 1000; i++) {
    Vec3 g, a;
    s.sample(&g, &a);
    gb.feed(g, a);
  }
  CHECK(!gb.valid());
}

static void testImplausibleGravityNeverStarts() {
  GyroBias gb;
  for (int i = 0; i < 1000; i++) gb.feed({0, 0, 0}, {0, 0, 2.5f});  // 2.5 g: en caída o golpeado
  CHECK(!gb.valid());
  CHECK_NEAR(gb.progress(), 0.0, 1e-9);
}

static void testRefreshAfterValid() {
  // Un cambio menor que la cota (kBiasMaxStepDps) se sigue en una sola ventana de 2 s.
  double worst = 0;
  for (int seed = 1; seed <= kSeeds; seed++) {
    Src s(seed, {1.0f, 1.0f, 1.0f});
    GyroBias gb;
    for (int i = 0; i < 300; i++) {
      Vec3 g, a;
      s.sample(&g, &a);
      gb.feed(g, a);
    }
    CHECK(gb.valid());
    s.bias = {1.03f, 1.0f, 0.97f};  // el sesgo cambió (temperatura): 0.042 dps, bajo la cota
    int done_at = -1;
    for (int i = 1; i <= 300; i++) {
      Vec3 g, a;
      s.sample(&g, &a);
      if (gb.feed(g, a) && done_at < 0) done_at = i;
    }
    CHECK(done_at == static_cast<int>(tun::kBiasRefreshWindowS * tun::kSampleHz));  // ventana de 2 s
    double e = norm(gb.biasDps() - s.bias);
    if (e > worst) worst = e;
    CHECK_NEAR(gb.biasDps().x, 1.03, 0.03);
    CHECK_NEAR(gb.biasDps().z, 0.97, 0.03);
  }
  std::printf("  re-estimacion tras un cambio de 0.042 dps: peor error %.4f dps (%d semillas) [estimado: simulador]\n", worst, kSeeds);
}

// Un giro lento y parejo en yaw pasa la prueba de quietud; la cota al paso impide que se absorba como sesgo.
static void testSlowPanIsNotAbsorbed() {
  double worst = 0;
  for (int seed = 1; seed <= kSeeds; seed++) {
    for (int k = 1; k <= 17; k++) {
      double pan = 0.5 * k;  // 0.5 .. 8.5 °/s
      std::mt19937 r(seed);
      Vec3 b = randBias(r);
      Src s(seed, b);
      GyroBias gb;
      for (int i = 0; i < 300; i++) {
        Vec3 g, a;
        s.sample(&g, &a);
        gb.feed(g, a);
      }
      CHECK(gb.valid());
      for (int i = 0; i < 300; i++) {
        Vec3 g, a;
        s.sample(&g, &a, {0, 0, static_cast<float>(pan)});
        gb.feed(g, a);
      }
      double e = std::fabs(gb.biasDps().z - b.z);
      if (e > worst) worst = e;
      CHECK(e <= tun::kBiasMaxStepDps + 0.02);
    }
  }
  std::printf("  paneo lento 0.5..8.5 dps durante 3 s: peor error del sesgo %.4f dps (%d semillas x 17 velocidades) [estimado: simulador]\n",
              worst, kSeeds);
}

// La deriva térmica lenta (0.02 dps por ventana, 60 s) sí se sigue.
static void testSlowDriftIsTracked() {
  double worst = 0;
  for (int seed = 1; seed <= kSeeds; seed++) {
    std::mt19937 r(seed);
    Vec3 b0 = randBias(r);
    Src s(seed, b0);
    GyroBias gb;
    for (int i = 0; i < 300; i++) {
      Vec3 g, a;
      s.sample(&g, &a);
      gb.feed(g, a);
    }
    CHECK(gb.valid());
    const double per_sample = 0.02 / (tun::kBiasRefreshWindowS * tun::kSampleHz);  // dps por muestra
    for (int i = 1; i <= 6000; i++) {  // 60 s
      s.bias.z = static_cast<float>(b0.z + per_sample * i);
      Vec3 g, a;
      s.sample(&g, &a);
      if (gb.feed(g, a)) {
        double e = std::fabs(gb.biasDps().z - s.bias.z);
        if (e > worst) worst = e;
        CHECK(e <= 0.05);
      }
    }
  }
  std::printf("  deriva de 0.02 dps por ventana durante 60 s: peor error del sesgo %.4f dps (%d semillas) [estimado: simulador]\n", worst, kSeeds);
}

static void testProgressAndReset() {
  Src s(5, {0.5f, 0, 0});
  GyroBias gb;
  float last = 0;
  for (int i = 0; i < 150; i++) {
    Vec3 g, a;
    s.sample(&g, &a);
    gb.feed(g, a);
    CHECK(gb.progress() >= last);
    last = gb.progress();
  }
  CHECK_NEAR(gb.progress(), 0.5, 0.01);
  gb.reset();
  CHECK(!gb.valid());
  CHECK_NEAR(gb.progress(), 0.0, 1e-9);
}

int main() {
  testQuietWindowGivesBias();
  testMotionRestartsWindow();
  testConstantRotationIsNotBias();
  testImplausibleGravityNeverStarts();
  testRefreshAfterValid();
  testSlowPanIsNotAbsorbed();
  testSlowDriftIsTracked();
  testProgressAndReset();
  return reportAndExit("test_bias");
}
