// Sync: fija la referencia "aquí está la marca 1". Guarda las últimas muestras de
// apuntado y, al confirmar, usa su promedio (el botón mueve un poco el equipo).
#pragma once
#include "../config/tuning.h"
#include "fusion.h"

namespace euler {

class Sync {
 public:
  void clear();                // olvida la referencia y las muestras
  void push(Pointing p);       // una por tick
  bool commit();               // false si aún no hay muestras suficientes
  bool valid() const { return valid_; }
  Pointing ref() const { return ref_; }

 private:
  Pointing buf_[tun::kSyncAvgSamples];
  int count_ = 0;  // muestras válidas (<= kSyncAvgSamples)
  int head_ = 0;   // siguiente posición a escribir
  bool valid_ = false;
  Pointing ref_{};
};

}  // namespace euler
