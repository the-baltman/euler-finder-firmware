#include "gyro_bias.h"
#include "../config/tuning.h"

namespace euler {

void GyroBias::reset() {
  valid_ = false;
  bias_ = {};
  mean_accel_ = {};
  restartWindow();
}

void GyroBias::restartWindow() {
  n_ = 0;
  sum_g_ = {};
  sum_a_ = {};
}

int GyroBias::windowSamples() const {
  float s = valid_ ? tun::kBiasRefreshWindowS : tun::kBiasInitialWindowS;
  return static_cast<int>(s * tun::kSampleHz + 0.5f);
}

float GyroBias::progress() const {
  int w = windowSamples();
  return w > 0 ? clampf(static_cast<float>(n_) / w, 0.0f, 1.0f) : 0.0f;
}

bool GyroBias::feed(Vec3 g, Vec3 a) {
  float an = norm(a);
  bool plausible = std::fabs(an - 1.0f) < 0.1f;
  if (n_ > 0) {
    bool still = norm(g - ref_g_) < tun::kBiasQuietGyroDps &&
                 norm(a - ref_a_) < tun::kBiasQuietAccelG && plausible;
    if (!still) restartWindow();
  }
  if (n_ == 0) {
    if (!plausible) return false;
    ref_g_ = g;
    ref_a_ = a;
  }
  sum_g_ = sum_g_ + g;
  sum_a_ = sum_a_ + a;
  n_++;
  if (n_ < windowSamples()) return false;
  Vec3 mean = sum_g_ * (1.0f / n_);
  Vec3 mean_a = sum_a_ * (1.0f / n_);
  restartWindow();
  if (norm(mean) > tun::kBiasMaxDps) return false;  // giraba a velocidad constante: no es sesgo
  if (valid_) {
    // Un giro lento y parejo (base giratoria) pasa la prueba de quietud y no se distingue del sesgo.
    // El sesgo real deriva despacio (temperatura): se acepta el cambio, acotado por ventana.
    Vec3 step = mean - bias_;
    float sn = norm(step);
    if (sn > tun::kBiasMaxStepDps) mean = bias_ + step * (tun::kBiasMaxStepDps / sn);
  }
  bias_ = mean;
  mean_accel_ = mean_a;
  valid_ = true;
  return true;
}

}  // namespace euler
