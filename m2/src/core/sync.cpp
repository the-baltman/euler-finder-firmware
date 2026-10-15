#include "sync.h"

namespace euler {

void Sync::clear() {
  count_ = 0;
  head_ = 0;
  valid_ = false;
  ref_ = {};
}

void Sync::push(Pointing p) {
  buf_[head_] = p;
  head_ = (head_ + 1) % tun::kSyncAvgSamples;
  if (count_ < tun::kSyncAvgSamples) count_++;
}

bool Sync::commit() {
  if (count_ < tun::kSyncMinSamples) return false;
  int last = (head_ + tun::kSyncAvgSamples - 1) % tun::kSyncAvgSamples;
  float az0 = buf_[last].az_deg;
  // El rumbo se promedia como diferencias respecto a la última muestra (evita el salto en ±180°).
  float sum_daz = 0, sum_el = 0;
  for (int i = 0; i < count_; i++) {
    sum_daz += wrap180(buf_[i].az_deg - az0);
    sum_el += buf_[i].el_deg;
  }
  ref_.az_deg = wrap180(az0 + sum_daz / count_);
  ref_.el_deg = sum_el / count_;
  valid_ = true;
  return true;
}

}  // namespace euler
