// Autoprueba del IMU con un IMU falso: cada falla posible debe verse como lo que es.
#include "check.h"
#include "../../src/core/selftest.h"

using namespace euler;

struct FakeImu : IImu {
  ImuStatus begin_status = ImuStatus::Ok;
  ImuStatus read_status = ImuStatus::Ok;
  uint8_t id = 0x71;
  Vec3 accel{0.02f, 0.03f, 0.99f};
  Vec3 gyro{0.3f, -0.2f, 0.1f};
  int fail_every = 0;  // cada n lecturas falla (0 = nunca)
  int good_every = 0;  // si >0, solo cada n lecturas sale bien; las demás salen como BadData
  int reads = 0;
  ImuStatus begin() override { return begin_status; }
  ImuStatus read(ImuSample& s) override {
    reads++;
    if (fail_every && reads % fail_every == 0) return ImuStatus::Timeout;
    if (good_every && reads % good_every != 0) return ImuStatus::BadData;
    if (read_status != ImuStatus::Ok) return read_status;
    s.accel_g = accel;
    s.gyro_dps = gyro;
    return ImuStatus::Ok;
  }
  uint8_t whoAmI() const override { return id; }
  const char* name() const override { return "falso"; }
};

static int g_sleeps = 0;
static void fakeSleep(uint32_t) { g_sleeps++; }

int main() {
  {  // MPU-9250 auténtico
    FakeImu f;
    SelfTestResult r = selfTestImu(f, fakeSleep);
    CHECK(r.ok && r.id_known && r.fatal == FatalReason::None && r.who_am_i == 0x71);
    CHECK(g_sleeps > 0);  // espera entre lecturas (no ráfaga)
  }
  {  // clon con otro ID pero datos creíbles: sigue, con aviso
    FakeImu f; f.id = 0x68;
    SelfTestResult r = selfTestImu(f, fakeSleep);
    CHECK(r.ok && !r.id_known && r.who_am_i == 0x68);
  }
  {  // MPU-6500 / 9255 reconocidos
    FakeImu f; f.id = 0x70;
    CHECK(selfTestImu(f, fakeSleep).id_known);
    f.id = 0x73;
    CHECK(selfTestImu(f, fakeSleep).id_known);
  }
  {  // no contesta en el bus: error grave
    FakeImu f; f.begin_status = ImuStatus::NoAck; f.id = 0;
    SelfTestResult r = selfTestImu(f, fakeSleep);
    CHECK(!r.ok && r.fatal == FatalReason::ImuNoAck);
  }
  {  // contesta con ID 0x00/0xFF (bus flotando)
    FakeImu f; f.begin_status = ImuStatus::BadId; f.id = 0xFF;
    SelfTestResult r = selfTestImu(f, fakeSleep);
    CHECK(!r.ok && r.fatal == FatalReason::ImuBadData);
  }
  {  // contesta al ID pero las lecturas expiran
    FakeImu f; f.read_status = ImuStatus::Timeout;
    SelfTestResult r = selfTestImu(f, fakeSleep);
    CHECK(!r.ok && r.fatal == FatalReason::ImuNoAck);
  }
  {  // gravedad absurda (clon que devuelve basura)
    FakeImu f; f.accel = {0, 0, 3.5f};
    SelfTestResult r = selfTestImu(f, fakeSleep);
    CHECK(!r.ok && r.fatal == FatalReason::ImuBadData);
    f.accel = {0, 0, 0.1f};
    r = selfTestImu(f, fakeSleep);
    CHECK(!r.ok && r.fatal == FatalReason::ImuBadData);
  }
  {  // acelerómetro bien pero giroscopio muerto (todo cero exacto)
    FakeImu f; f.gyro = {0, 0, 0};
    SelfTestResult r = selfTestImu(f, fakeSleep);
    CHECK(!r.ok && r.fatal == FatalReason::ImuBadData);
  }
  {  // el chip contesta pero todas las lecturas salen marcadas como datos malos
    FakeImu f; f.read_status = ImuStatus::BadData;
    SelfTestResult r = selfTestImu(f, fakeSleep);
    CHECK(!r.ok && r.fatal == FatalReason::ImuBadData);
  }
  {  // datos plausibles pero solo 1 de cada 4 lecturas es válida: no hay base para fiarse
    FakeImu f; f.good_every = 4;
    SelfTestResult r = selfTestImu(f, fakeSleep);
    CHECK(!r.ok && r.fatal == FatalReason::ImuBadData);
  }
  {  // un bus que falla de vez en cuando también es falla grave: mejor avisar que guiar con datos huecos
    FakeImu f; f.fail_every = 10;
    SelfTestResult r = selfTestImu(f, fakeSleep);
    CHECK(!r.ok && r.fatal == FatalReason::ImuNoAck);
  }
  return reportAndExit("test_selftest");
}
