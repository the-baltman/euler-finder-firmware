#include "selftest.h"
#include "../config/tuning.h"

namespace euler {

bool isKnownImuId(uint8_t id) { return id == 0x71 || id == 0x73 || id == 0x70; }

SelfTestResult selfTestImu(IImu& imu, void (*sleep_ms)(uint32_t)) {
  SelfTestResult r;
  ImuStatus st = imu.begin();
  r.who_am_i = imu.whoAmI();
  if (st == ImuStatus::NoAck || st == ImuStatus::Timeout) {
    r.fatal = FatalReason::ImuNoAck;
    return r;
  }
  if (st != ImuStatus::Ok) {  // BadId o BadData reportado por el propio driver
    r.fatal = FatalReason::ImuBadData;
    return r;
  }
  r.id_known = isKnownImuId(r.who_am_i);

  // Datos creíbles: gravedad media cerca de 1 g y el giroscopio no pegado en cero exacto.
  Vec3 sum_a{};
  bool any_gyro_nonzero = false;
  int good = 0;
  for (int i = 0; i < tun::kSelfTestSamples; i++) {
    ImuSample s;
    ImuStatus rs = imu.read(s);
    if (rs == ImuStatus::NoAck || rs == ImuStatus::Timeout) {
      r.fatal = FatalReason::ImuNoAck;
      return r;
    }
    if (rs == ImuStatus::Ok) {
      sum_a = sum_a + s.accel_g;
      if (s.gyro_dps.x != 0 || s.gyro_dps.y != 0 || s.gyro_dps.z != 0) any_gyro_nonzero = true;
      good++;
    }
    if (sleep_ms) sleep_ms(1000 / tun::kSampleHz);
  }
  r.accel_ok_reads = static_cast<uint8_t>(good);
  if (good < tun::kSelfTestSamples / 2) {
    r.fatal = FatalReason::ImuBadData;
    return r;
  }
  float g = norm(sum_a * (1.0f / good));
  if (!(g >= tun::kSelfTestGravMin && g <= tun::kSelfTestGravMax) || !any_gyro_nonzero) {
    r.fatal = FatalReason::ImuBadData;
    return r;
  }
  r.ok = true;
  return r;
}

}  // namespace euler
