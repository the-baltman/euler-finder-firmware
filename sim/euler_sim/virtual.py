"""Red virtual determinista: reloj virtual, cola de eventos, perdida/desorden con semilla.

Es la red de las pruebas y del barrido de semillas: no duerme, corre cientos de segundos simulados
en milisegundos y repite exactamente con la misma semilla.
"""
from __future__ import annotations

import heapq
import itertools
import math
import random
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

import euler_proto as p
from . import BROADCAST
from .impair import Impairment
from .m1 import M1Config, M1Core
from .m2 import M2Config, M2Core


@dataclass
class WireRecord:
    t_send: float
    src: str            # "M1" o "M2-<nx>"
    dst: str            # "M1", "M2-<nx>"
    kind: str           # nombre de la clase del paquete, o "?" si no decodifica
    size: int
    delivered: bool     # False si se perdio (o lo filtro drop_filter)
    t_deliver: Optional[float]


class VirtualNet:
    def __init__(self, seed: int = 0, impair: Optional[Impairment] = None, m1_cfg: Optional[M1Config] = None,
                 max_events: int = 5_000_000):
        self.now = 0.0
        self.rng = random.Random(seed)
        self.impair = impair or Impairment()
        self.m1_up = True
        self.log: List[WireRecord] = []
        # Filtro de pruebas: drop_filter(t, src, dst, pkt) -> True descarta ese datagrama.
        self.drop_filter: Optional[Callable[[float, str, str, object], bool]] = None
        self._heap: list = []
        self._ids = itertools.count()
        self._max_events = max_events
        self.events = 0
        self.m1 = M1Core(m1_cfg or M1Config(), self._m1_send)
        self.m2: Dict[int, M2Core] = {}

    # --- Armado ---

    def add_m2(self, nx: int, **cfg) -> M2Core:
        core = M2Core(M2Config(nx=nx, **cfg), lambda data, nx=nx: self._m2_send(nx, data))
        self.m2[nx] = core
        return core

    # --- Envio ---

    def _m1_send(self, dst, data: bytes) -> None:
        if not self.m1_up:
            return
        targets = sorted(self.m2) if dst == BROADCAST else [dst]
        for nx in targets:
            self._deliver(data, "M1", f"M2-{nx}", lambda d, t, nx=nx: self.m2[nx].on_packet(d, t))

    def _m2_send(self, nx: int, data: bytes) -> None:
        self._deliver(data, f"M2-{nx}", "M1", self._to_m1)

    def _to_m1(self, data: bytes, t: float) -> None:
        if self.m1_up:
            self.m1.on_packet(data, t)

    def _deliver(self, data: bytes, src: str, dst: str, receiver) -> None:
        try:
            pkt = p.decode(data)
            kind = type(pkt).__name__
        except p.ProtocolError:
            pkt, kind = None, "?"
        delays = [] if (self.drop_filter and self.drop_filter(self.now, src, dst, pkt)) else self.impair.plan(self.rng)
        if not delays:
            self.log.append(WireRecord(self.now, src, dst, kind, len(data), False, None))
            return
        for d in delays:
            t = self.now + d
            self.log.append(WireRecord(self.now, src, dst, kind, len(data), True, t))
            heapq.heappush(self._heap, (t, next(self._ids), receiver, data))

    def inject(self, dst_nx: Optional[int], data: bytes, delay: float = 0.0) -> None:
        """Mete bytes arbitrarios en la red (paquetes corruptos de las pruebas). dst_nx=None va al M1."""
        recv = self._to_m1 if dst_nx is None else (lambda d, t: self.m2[dst_nx].on_packet(d, t))
        heapq.heappush(self._heap, (self.now + delay, next(self._ids), recv, data))

    # --- Motor ---

    def _next_node_deadline(self):
        best, who = math.inf, None
        if self.m1_up:
            d = self.m1.next_deadline()
            if d < best:
                best, who = d, self.m1
        for nx in sorted(self.m2):
            d = self.m2[nx].next_deadline()
            if d < best:
                best, who = d, self.m2[nx]
        return best, who

    def run_until(self, t_end: float) -> None:
        """Avanza el reloj virtual hasta t_end inclusive."""
        while True:
            t_node, who = self._next_node_deadline()
            t_node = max(t_node, self.now)
            t_pkt = self._heap[0][0] if self._heap else math.inf
            if min(t_node, t_pkt) > t_end:
                break
            self.events += 1
            if self.events > self._max_events:
                raise RuntimeError("demasiados eventos: algun nodo no avanza su deadline")
            if t_pkt <= t_node:
                t, _, receiver, data = heapq.heappop(self._heap)
                self.now = max(self.now, t)
                receiver(data, self.now)
            else:
                self.now = t_node
                who.tick(self.now)
        self.now = max(self.now, t_end)

    # --- Fallas para las pruebas ---

    def kill_m1(self) -> None:
        self.m1_up = False

    def revive_m1(self) -> None:
        self.m1_up = True

    # --- Consultas sobre el registro ---

    def sent(self, kind: str, src: Optional[str] = None, dst: Optional[str] = None) -> List[WireRecord]:
        return [r for r in self.log if r.kind == kind and (src is None or r.src == src)
                and (dst is None or r.dst == dst)]
