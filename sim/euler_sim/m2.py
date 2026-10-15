"""M2 falso (un nivelador, modo BASE): recibe HB y ASSIGN, hace el acople, manda STATUS y vigila la base.

Maquina de estado pura, igual que el M1: bytes y tiempo entran, bytes salen por el callback.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Dict, List, Optional, Tuple

import euler_proto as p


@dataclass
class M2Config:
    nx: int
    start_s: float = 0.0                 # instante en que enciende
    status_offset_s: float = 0.0         # desfase del primer STATUS (cada M2 enciende a su hora)
    hb_period_s: float = p.HB_PERIOD_S
    watchdog_hb: int = p.WATCHDOG_HB_COUNT
    status_period_s: float = p.STATUS_PERIOD_S
    # [estimado: parametros del simulador] los valores reales los fija el firmware del M2.
    req_retry_s: float = 1.0             # espera entre reintentos de DOCK_REQ
    req_max_tries: int = 8               # DOCK_REQ enviados antes de rendirse
    ref_wait_s: float = 60.0             # espera del DOCK_REF tras el ACK; debe cubrir la cola de solves de los demas M2
    guide_period_s: float = 1.0          # paso del "guiado" abstracto del simulador
    dock_seq0: int = 0


class DockState(Enum):
    IDLE = "sin acople"
    WAIT_ACK = "esperando ACK del M1"
    WAIT_REF = "esperando DOCK_REF"
    DONE = "acople completo"
    FAILED_TIMEOUT = "acople fallido: el M1 no responde"
    FAILED_NO_SOLUTION = "acople fallido: el M1 no resolvio el cielo"


class Level(Enum):
    LEVE = "leve"


# Codigos de estado de STATUS (ver euler_proto.M2_STATE_MAX): el simulador usa estos.
ST_ELEGIR_BASE, ST_ACOPLE, ST_MONTAJE, ST_SYNC, ST_GUIA = 1, 2, 3, 4, 5
SINCE_SYNC_NEVER = 0xFFFF               # "nunca": el campo es u16 y satura


def _tid(a: Optional[p.Assignment]) -> Optional[int]:
    return None if a is None else a.target_id


class M2Core:
    def __init__(self, cfg: M2Config, send: Callable[[bytes], None]):
        if not 1 <= cfg.nx <= p.MAX_NX:
            raise ValueError("nx fuera de 1..10")
        self.cfg = cfg
        self.nx = cfg.nx
        self._send = send
        # base
        self.base_id: Optional[int] = None
        self._hb_seq: Optional[int] = None
        self._last_hb_rx = cfg.start_s            # el reloj del watchdog parte del encendido
        self._lost_flag = False
        self.base_lost_events = 0
        self.last_hb: Optional[p.Heartbeat] = None
        # tiempo propio: referencia (utc_ms, instante local) del ultimo HB
        self._time_ref: Optional[Tuple[int, float]] = None
        # guiado
        self.target: Optional[p.Assignment] = None
        self.assigned: Optional[p.Assignment] = None   # lo ultimo que dijo el M1 para mi Nx
        self.target_local = False                      # el objetivo lo eligio el usuario con los botones
        self.synced = False
        self.sync_time: Optional[float] = None
        self.ref: Optional[p.DockRef] = None
        self.ref_applied = 0
        self.guide_ticks = 0
        self._next_guide = cfg.start_s + cfg.guide_period_s
        self._next_status = cfg.start_s + cfg.status_offset_s
        # acople
        self.dock_state = DockState.IDLE
        self._dock_seq = cfg.dock_seq0 & 0xFFFF
        self._dock_tries = 0
        self._dock_timer = math.inf
        self.dock_started: Optional[float] = None
        self.dock_finished: Optional[float] = None
        self._last_done_seq: Optional[int] = None
        # contadores
        self.tx: Dict[str, int] = {}
        self.rx: Dict[str, int] = {}
        self.rejected: Dict[str, int] = {}
        self.stale_hb = 0
        self.foreign_hb = 0

    # --- Consultas ---

    def _watchdog_deadline(self) -> float:
        return self._last_hb_rx + self.cfg.watchdog_hb * self.cfg.hb_period_s

    def base_lost(self, now: float) -> bool:
        """Perdieron 3 HB (30 s) desde el ultimo aceptado (o desde el encendido si nunca llego uno)."""
        return now >= self._watchdog_deadline()

    def errors(self, now: float) -> List[Tuple[Level, str]]:
        return [(Level.LEVE, "sin_base")] if self.base_lost(now) else []

    def guiding(self) -> bool:
        """Guia mientras haya sync y objetivo. Deliberadamente NO depende de que haya base."""
        return self.synced and self.target is not None

    def utc_ms_estimate(self, now: float) -> Optional[int]:
        if self._time_ref is None:
            return None
        utc, t = self._time_ref
        return utc + int(round((now - t) * 1000.0))

    # --- Manejo por el exterior ---

    def next_deadline(self) -> float:
        d = min(self._next_guide, self._next_status, self._dock_timer)
        if not self._lost_flag:
            d = min(d, self._watchdog_deadline())
        return d

    def tick(self, now: float) -> None:
        if now < self.cfg.start_s:
            return
        if not self._lost_flag and self.base_lost(now):
            self._lost_flag = True
            self.base_lost_events += 1
        if now >= self._next_guide:
            if self.guiding():
                self.guide_ticks += 1
            self._next_guide += self.cfg.guide_period_s
            if self._next_guide <= now:
                self._next_guide = now + self.cfg.guide_period_s
        if now >= self._next_status:
            if self.base_id is not None:
                self._send_status(now)
            self._next_status += self.cfg.status_period_s
            if self._next_status <= now:
                self._next_status = now + self.cfg.status_period_s
        if now >= self._dock_timer:
            self._dock_timeout(now)

    def request_dock(self, now: float) -> bool:
        """Boton de acople. False si ya hay uno en curso o si aun no se acepto ningun HB (ESPEC. 1, regla H2)."""
        if self.base_id is None:
            return False
        if self.dock_state in (DockState.WAIT_ACK, DockState.WAIT_REF):
            return False
        self._dock_seq = (self._dock_seq + 1) & 0xFFFF
        self._dock_tries = 0
        self.dock_started, self.dock_finished = now, None
        self._send_req(now)
        return True

    def on_packet(self, data: bytes, now: float) -> None:
        if now < self.cfg.start_s:
            return                                   # apagado: no oye nada
        try:
            pkt = p.decode(data)
        except p.ProtocolError as e:
            self.rejected[type(e).__name__] = self.rejected.get(type(e).__name__, 0) + 1
            return
        name = type(pkt).__name__
        self.rx[name] = self.rx.get(name, 0) + 1
        if isinstance(pkt, p.Heartbeat):
            self._on_hb(pkt, now)
        elif isinstance(pkt, p.Assign):
            if pkt.nx != self.nx:
                self._reject("misrouted")
            else:
                # Un ASSIGN siempre se aplica y reemplaza incluso una eleccion local.
                self.assigned = self.target = p.Assignment(pkt.nx, pkt.target_id, pkt.ra_e7, pkt.dec_e7)
                self.target_local = False
        elif isinstance(pkt, p.Ack):
            if pkt.nx != self.nx:
                self._reject("misrouted")
            elif self.dock_state is DockState.WAIT_ACK and pkt.seq == self._dock_seq:
                self.dock_state = DockState.WAIT_REF
                self._dock_timer = now + self.cfg.ref_wait_s
        elif isinstance(pkt, p.DockRef):
            if pkt.nx != self.nx:
                self._reject("misrouted")
            else:
                self._on_ref(pkt, now)
        else:
            self._reject("unexpected_" + name)

    # --- Internos ---

    def _reject(self, why: str) -> None:
        self.rejected[why] = self.rejected.get(why, 0) + 1

    def _tx(self, pkt) -> None:
        name = type(pkt).__name__
        self.tx[name] = self.tx.get(name, 0) + 1
        self._send(p.encode(pkt))

    def _on_hb(self, hb: p.Heartbeat, now: float) -> None:
        if self.base_id is None or self.base_lost(now):
            # Primera base, o la anterior se perdio: se acepta la que hable (puede ser otra o un M1 reiniciado).
            if self.base_id != hb.base_id:
                self.base_id = hb.base_id
                self.assigned = None            # base nueva: lo que dijo la anterior ya no cuenta
            self._hb_seq = None
        elif hb.base_id != self.base_id:
            self.foreign_hb += 1
            return
        if self._hb_seq is not None and p.seq_is_stale_or_dup(hb.seq, self._hb_seq):
            self.stale_hb += 1
            return
        self._hb_seq = hb.seq
        self._last_hb_rx = now
        self._lost_flag = False
        self.last_hb = hb
        self._time_ref = (hb.utc_ms, now)
        self._apply_hb_assignment(next((a for a in hb.assignments if a.nx == self.nx), None))

    def _apply_hb_assignment(self, nuevo: Optional[p.Assignment]) -> None:
        """Regla de objetivo (ESPEC. 5.1): el HB manda por flanco, comparando target_id, no por valor."""
        if _tid(nuevo) != _tid(self.assigned):          # aparecer o desaparecer tambien es cambio
            self.assigned = nuevo
            if nuevo is not None:
                self.target, self.target_local = nuevo, False
            elif not self.target_local:
                self.target = None
        elif not self.target_local:
            self.target = nuevo                         # refresca RA/Dec: el M1 recalcula la Luna y los planetas

    def select_local(self, target_id: int, ra_e7: int, dec_e7: int) -> None:
        """Eleccion con los botones del M2: local en v1 (STATUS no lleva objetivo, el M1 no se entera)."""
        self.target = p.Assignment(self.nx, target_id, ra_e7, dec_e7)
        self.target_local = True

    def _send_status(self, now: float) -> None:
        if self.dock_state in (DockState.WAIT_ACK, DockState.WAIT_REF):
            state = ST_ACOPLE
        elif self.base_id is None:
            state = ST_ELEGIR_BASE
        elif not self.synced:
            state = ST_MONTAJE
        elif self.target is None:
            state = ST_SYNC
        else:
            state = ST_GUIA
        since = SINCE_SYNC_NEVER if self.sync_time is None else min(0xFFFE, int(now - self.sync_time))
        battery = max(0, 100 - int(now // 600.0))     # curva falsa del simulador
        quality = 100 if self.synced else 0
        self._tx(p.Status(self.nx, battery, state, since, 0, quality))

    def _send_req(self, now: float) -> None:
        self._dock_tries += 1
        self.dock_state = DockState.WAIT_ACK
        self._dock_timer = now + self.cfg.req_retry_s
        self._tx(p.DockReq(self.nx, self._dock_seq))

    def _dock_timeout(self, now: float) -> None:
        if self.dock_state is DockState.WAIT_REF:
            # El M1 confirmo la peticion pero el DOCK_REF no llego en ref_wait_s: error de acople (ESPEC. 5.3).
            self.dock_state = DockState.FAILED_TIMEOUT
            self.dock_finished = now
            self._dock_timer = math.inf
            return
        if self.dock_state not in (DockState.WAIT_ACK, DockState.WAIT_REF):
            self._dock_timer = math.inf
            return
        if self._dock_tries >= self.cfg.req_max_tries:
            self.dock_state = DockState.FAILED_TIMEOUT
            self.dock_finished = now
            self._dock_timer = math.inf
        else:
            self._send_req(now)

    def _on_ref(self, ref: p.DockRef, now: float) -> None:
        waiting = self.dock_state in (DockState.WAIT_ACK, DockState.WAIT_REF)
        if waiting and ref.seq == self._dock_seq:
            self._tx(p.Ack(self.nx, ref.seq))
            self._last_done_seq = ref.seq
            self._dock_timer = math.inf
            self.dock_finished = now
            if ref.stars == 0:
                self.dock_state = DockState.FAILED_NO_SOLUTION   # stars=0: sin solucion valida
                return
            self.dock_state = DockState.DONE
            self.ref = ref
            self.ref_applied += 1
            self.synced = True
            self.sync_time = now
        elif ref.seq == self._last_done_seq:
            # El M1 no recibio mi ACK y reenvio la referencia: se confirma otra vez, sin reaplicarla.
            self._tx(p.Ack(self.nx, ref.seq))
        else:
            self._reject("stale_ref")
