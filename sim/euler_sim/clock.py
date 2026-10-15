"""Reloj escalable: tiempo simulado = tiempo real x escala. Con escala 25, el HB de 10 s sale cada 0.4 s reales."""
from __future__ import annotations

import time
from typing import Callable


class ScaledClock:
    def __init__(self, scale: float = 1.0, time_fn: Callable[[], float] = time.monotonic):
        if scale <= 0:
            raise ValueError("la escala debe ser > 0")
        self.scale = float(scale)
        self._time_fn = time_fn
        self._t0 = time_fn()

    def reset(self) -> None:
        self._t0 = self._time_fn()

    def now(self) -> float:
        """Segundos simulados desde reset()."""
        return (self._time_fn() - self._t0) * self.scale

    def to_wall(self, sim_s: float) -> float:
        """Duracion real (s) de un intervalo simulado."""
        return sim_s / self.scale
