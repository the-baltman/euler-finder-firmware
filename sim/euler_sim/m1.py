"""M1 falso: heartbeat, asignaciones, solve de acople serializado y reintentos de DOCK_REF.

Maquina de estado pura: no abre sockets ni lee relojes. El que lo maneja llama on_packet(datos, ahora)
y tick(ahora), y consulta next_deadline() para saber cuando volver a llamar a tick.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Deque, Dict, Optional

import euler_proto as p
from . import BROADCAST


@dataclass
class M1Config:
    base_id: int = 1
    hb_period_s: float = p.HB_PERIOD_S
    lat_e7: int = 197_000_000         # 19.7 N, Morelia aprox. (valor del simulador)
    lon_e7: int = -1_012_000_000      # -101.2
    utc0_ms: int = 1_792_000_000_000  # hora UTC en t=0 de la simulacion (arbitraria)
    flags: int = p.HB_FLAG_SOLVE_OK | p.HB_FLAG_TIME_VALID | p.HB_FLAG_LOCATION_VALID
    # [estimado: parametro del simulador] el tiempo real del solve en Pi 5 se mide en el Hito 1.
    solve_time_s: float = 2.0
    ref_retry_s: float = 1.0          # [estimado] espera entre reenvios de DOCK_REF
    ref_max_tries: int = 8            # [estimado] envios de DOCK_REF antes de rendirse
    stars_matched: int = 12           # estrellas emparejadas que reporta el solve falso
    ref_flags: int = p.REF_FLAG_SAMPLE_IMAGE   # corrida 1: la referencia sale de una imagen de ejemplo
    # Variante A/B (NO es la especificacion): tras un ASSIGN manda tambien un HB fuera de turno, para que el
    # HB mas nuevo ya traiga la asignacion. Cierra la carrera "HB viejo pisa al ASSIGN" (ESPECIFICACION.md, H3).
    hb_after_assign: bool = False
    hb_extra_delay_s: float = 0.05    # [estimado] espera para juntar varios ASSIGN seguidos en un solo HB extra


class DockPhase(Enum):
    QUEUED = "en cola"
    SOLVING = "resolviendo"
    REF_SENT = "esperando ACK"
    DONE = "completo"
    FAILED = "agoto reintentos"


class _Dock:
    __slots__ = ("nx", "seq", "phase", "tries", "next_retx", "ref_bytes")

    def __init__(self, nx: int, seq: int):
        self.nx, self.seq = nx, seq
        self.phase = DockPhase.QUEUED
        self.tries = 0
        self.next_retx = math.inf
        self.ref_bytes: Optional[bytes] = None


class M1Core:
    def __init__(self, cfg: M1Config, send: Callable[[object, bytes], None], start_s: float = 0.0,
                 seq0: int = 0):
        """send(destino, bytes): destino es BROADCAST o el Nx (int) de un M2."""
        self.cfg = cfg
        self._send = send
        self._hb_seq = seq0 & 0xFFFF
        self._next_hb = start_s
        self._extra_hb_at = math.inf
        self.assignments: Dict[int, p.Assignment] = {}
        self.flags = cfg.flags
        self.docks: Dict[int, _Dock] = {}
        self._queue: Deque[_Dock] = deque()
        self._solving: Optional[_Dock] = None
        self._solve_end = math.inf
        self.m2_status: Dict[int, p.Status] = {}
        self.m2_seen: Dict[int, float] = {}
        self.tx: Dict[str, int] = {}
        self.rx: Dict[str, int] = {}
        self.rejected: Dict[str, int] = {}
        self.solves = 0
        self.ref_resends = 0

    # --- API hacia arriba (la app/BLE de la corrida real) ---

    def assign(self, nx: int, target_id: int, ra_e7: int, dec_e7: int, now: float) -> None:
        """Asigna un objetivo y avisa al M2 de inmediato; el HB lo repite en cada periodo."""
        a = p.Assignment(nx, target_id, ra_e7, dec_e7)
        self.assignments[nx] = a
        self._tx(nx, p.Assign(nx, target_id, ra_e7, dec_e7))
        if self.cfg.hb_after_assign and self._extra_hb_at == math.inf:
            self._extra_hb_at = now + self.cfg.hb_extra_delay_s

    def clear_assignment(self, nx: int) -> None:
        """Quita la asignacion. No existe un ASSIGN de borrado: el M2 se entera con el siguiente HB."""
        self.assignments.pop(nx, None)

    def set_flags(self, flags: int) -> None:
        p.Heartbeat(0, 0, 0, 0, 0, flags)   # valida los bits
        self.flags = flags

    # --- Manejo por el exterior ---

    def next_deadline(self) -> float:
        d = min(self._next_hb, self._solve_end, self._extra_hb_at)
        for dock in self.docks.values():
            if dock.phase is DockPhase.REF_SENT:
                d = min(d, dock.next_retx)
        if self._solving is None and self._queue:
            return -math.inf   # hay trabajo pendiente: que tick arranque el solve ya
        return d

    def tick(self, now: float) -> None:
        if now >= self._next_hb:
            self._send_hb(now)
            self._next_hb += self.cfg.hb_period_s
            if self._next_hb <= now:                 # reloj saltado: no hacer rafagas de HB
                self._next_hb = now + self.cfg.hb_period_s
        if now >= self._extra_hb_at:
            self._extra_hb_at = math.inf
            self._send_hb(now)
        if self._solving is not None and now >= self._solve_end:
            self._finish_solve(now)
        if self._solving is None and self._queue:
            self._start_solve(now)
        for dock in list(self.docks.values()):
            if dock.phase is DockPhase.REF_SENT and now >= dock.next_retx:
                if dock.tries >= self.cfg.ref_max_tries:
                    dock.phase = DockPhase.FAILED
                    dock.next_retx = math.inf
                else:
                    self._resend_ref(dock, now)

    def on_packet(self, data: bytes, now: float) -> None:
        try:
            pkt = p.decode(data)
        except p.ProtocolError as e:
            self.rejected[type(e).__name__] = self.rejected.get(type(e).__name__, 0) + 1
            return
        name = type(pkt).__name__
        self.rx[name] = self.rx.get(name, 0) + 1
        if isinstance(pkt, p.DockReq):
            self._on_dock_req(pkt, now)
        elif isinstance(pkt, p.Ack):
            d = self.docks.get(pkt.nx)
            if d is not None and d.seq == pkt.seq and d.phase is DockPhase.REF_SENT:
                d.phase = DockPhase.DONE
                d.next_retx = math.inf
        elif isinstance(pkt, p.Status):
            self.m2_status[pkt.nx] = pkt
            self.m2_seen[pkt.nx] = now
        else:
            # HB, DOCK_REF y ASSIGN no deben llegarle al M1.
            self.rejected["unexpected_" + name] = self.rejected.get("unexpected_" + name, 0) + 1

    # --- Internos ---

    def _tx(self, dst, pkt) -> None:
        name = type(pkt).__name__
        self.tx[name] = self.tx.get(name, 0) + 1
        self._send(dst, p.encode(pkt))

    def utc_ms(self, now: float) -> int:
        return self.cfg.utc0_ms + int(round(now * 1000.0))

    def _send_hb(self, now: float) -> None:
        asg = tuple(self.assignments[nx] for nx in sorted(self.assignments))
        hb = p.Heartbeat(self.cfg.base_id, self._hb_seq, self.utc_ms(now), self.cfg.lat_e7, self.cfg.lon_e7,
                         self.flags, asg)
        self._hb_seq = (self._hb_seq + 1) & 0xFFFF
        self._tx(BROADCAST, hb)

    def _on_dock_req(self, req: p.DockReq, now: float) -> None:
        d = self.docks.get(req.nx)
        if d is not None and d.seq == req.seq:
            # Reintento del mismo acople: se confirma otra vez, pero NO se vuelve a resolver el cielo.
            self._tx(req.nx, p.Ack(req.nx, req.seq))
            if d.phase is DockPhase.FAILED:
                d.phase, d.tries = DockPhase.QUEUED, 0
                self._queue.append(d)
            return
        if d is not None:
            if p.seq_delta(req.seq, d.seq) > 0x8000:
                self.rejected["old_dock_req"] = self.rejected.get("old_dock_req", 0) + 1
                return                               # DOCK_REQ viejo que llego tarde: ya hay uno mas nuevo
            # Acople nuevo del mismo M2: el anterior se descarta, este donde este.
            if d in self._queue:
                self._queue.remove(d)
        nd = _Dock(req.nx, req.seq)
        self.docks[req.nx] = nd
        self._queue.append(nd)
        self._tx(req.nx, p.Ack(req.nx, req.seq))

    def _start_solve(self, now: float) -> None:
        self._solving = self._queue.popleft()
        self._solving.phase = DockPhase.SOLVING
        self._solve_end = now + self.cfg.solve_time_s

    def _finish_solve(self, now: float) -> None:
        dock, self._solving, self._solve_end = self._solving, None, math.inf
        self.solves += 1
        if self.docks.get(dock.nx) is not dock:
            return                                   # el M2 ya pidio otro acople: este resultado sobra
        # La referencia es la del instante en que termina el solve (modelo: cuaternion que gira lento).
        yaw = (now * 0.01) % (2.0 * math.pi)
        quat = (math.cos(yaw / 2.0), 0.0, 0.0, math.sin(yaw / 2.0))
        ref = p.DockRef(dock.nx, dock.seq, self.utc_ms(now), quat, self.cfg.stars_matched, self.cfg.ref_flags)
        dock.ref_bytes = p.encode(ref)
        dock.phase = DockPhase.REF_SENT
        dock.tries = 0
        self._resend_ref(dock, now, first=True)

    def _resend_ref(self, dock: _Dock, now: float, first: bool = False) -> None:
        dock.tries += 1
        dock.next_retx = now + self.cfg.ref_retry_s
        if not first:
            self.ref_resends += 1
        self.tx["DockRef"] = self.tx.get("DockRef", 0) + 1
        self._send(dock.nx, dock.ref_bytes)

    # --- Consultas para las pruebas ---

    def dock_phase(self, nx: int) -> Optional[DockPhase]:
        d = self.docks.get(nx)
        return d.phase if d else None
