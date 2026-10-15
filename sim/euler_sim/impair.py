"""Deterioro de la red: perdida, desorden y duplicados con tasa configurable."""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List


@dataclass
class Impairment:
    loss: float = 0.0            # probabilidad de perder cada datagrama (por receptor)
    reorder: float = 0.0         # probabilidad de que un datagrama se retrase de mas y llegue desordenado
    reorder_max_s: float = 3.0   # retraso extra maximo, s [estimado]. Para que dos HB se crucen debe pasar de 10 s
    dup: float = 0.0             # probabilidad de que llegue una segunda copia
    latency_s: float = 0.005     # retraso base, s [estimado: parametro del simulador, no medido]
    jitter_s: float = 0.002      # variacion uniforme sobre el retraso base, s [estimado]

    def __post_init__(self):
        for nombre in ("loss", "reorder", "dup"):
            v = getattr(self, nombre)
            if not 0.0 <= v <= 1.0:
                raise ValueError(f"{nombre}={v} fuera de [0, 1]")
        if self.latency_s < 0 or self.jitter_s < 0 or self.reorder_max_s < 0:
            raise ValueError("los tiempos no pueden ser negativos")

    def plan(self, rng: random.Random) -> List[float]:
        """Retrasos (s) con que se entregan las copias del datagrama; lista vacia = perdido."""
        if rng.random() < self.loss:
            return []
        d = self.latency_s + rng.uniform(0.0, self.jitter_s)
        if rng.random() < self.reorder:
            d += rng.uniform(0.0, self.reorder_max_s)
        out = [d]
        if rng.random() < self.dup:
            out.append(self.latency_s + rng.uniform(0.0, self.jitter_s) + rng.uniform(0.0, self.reorder_max_s))
        return out
