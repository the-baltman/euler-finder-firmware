"""Codec de referencia del protocolo M1 <-> M2 de EULER finder.

Fuente de los tamanos y campos: arquitectura-operativa.md, seccion 6 (tabla de paquetes).
Todo es little-endian y sin relleno ("<" en struct). La especificacion legible vive en
ESPECIFICACION.md; si este archivo y esa especificacion discrepan, es un error de uno de los dos.

Regla de oro del receptor: un paquete que no cuadra exactamente se RECHAZA (se lanza una
subclase de ProtocolError) y el llamador lo descarta. Nunca se "adivina" un paquete a medias.

Las validaciones de campo (rangos) corren tanto al construir un paquete como al decodificarlo,
asi no se puede codificar algo que el receptor rechazaria.
"""
from __future__ import annotations

import math
import struct
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Tuple, Union

# --- Constantes del protocolo (las referencia el manual: no cambiar sin subir la version) ---

PROTO_VERSION = 1            # byte de version, solo viaja en HB
HB_PERIOD_S = 10.0           # periodo del heartbeat, s (arquitectura, seccion 4)
STATUS_PERIOD_S = 10.0       # periodo del STATUS, s (arquitectura, seccion 6)
WATCHDOG_HB_COUNT = 3        # heartbeats perdidos para declarar "sin base" (30 s)
WATCHDOG_S = WATCHDOG_HB_COUNT * HB_PERIOD_S

MAX_NX = 10                  # IDs fijos N1..N10 grabados en cada M2
MAX_ASSIGNMENTS = MAX_NX     # un objetivo por nivelador como maximo en un HB

HB_HEADER_SIZE = 24          # B
HB_ASSIGNMENT_SIZE = 11      # B por asignacion
HB_MAX_SIZE = HB_HEADER_SIZE + HB_ASSIGNMENT_SIZE * MAX_ASSIGNMENTS  # 134 B

# Unidades de angulo: enteros en 1e-7 grados.
E7 = 10_000_000
LAT_MAX_E7 = 90 * E7
LON_MAX_E7 = 180 * E7
DEC_MAX_E7 = 90 * E7
RA_MAX_E7 = 360 * E7         # exclusivo; u32 en el cable (ESPECIFICACION 7, H1 decidido)

# Tolerancia de norma del cuaternion [estimado: tolerancia propuesta, no medida].
QUAT_NORM_TOL = 1e-3

# Estado del M2 en STATUS [decidido: arbitraje c-morty 2026-10-15], a partir del diagrama de la seccion 5.
M2_STATE_MAX = 6             # 0 AUTOPRUEBA, 1 ELEGIR_BASE, 2 ACOPLE, 3 MONTAJE, 4 SYNC, 5 GUIA, 6 ERROR_GRAVE
QUALITY_MAX = 100            # calidad del sync, 0..100; 0 = sin sync [decidido: arbitraje c-morty 2026-10-15]
BATTERY_MAX = 100            # bateria, %

# Banderas del HB (bits).
HB_FLAG_BASE_MOVED = 0x01
HB_FLAG_SOLVE_OK = 0x02
HB_FLAG_TIME_VALID = 0x04
HB_FLAG_LOCATION_VALID = 0x08
HB_FLAGS_MASK = 0x0F

# Banderas de DOCK_REF (bits) [decidido: arbitraje c-morty 2026-10-15]; la tabla no las define.
REF_FLAG_SAMPLE_IMAGE = 0x01  # la referencia sale de una imagen de ejemplo, no del cielo (corrida 1, sin optica)
REF_FLAGS_MASK = 0x01


class PacketType(IntEnum):
    HB = 1
    DOCK_REQ = 2
    DOCK_REF = 3
    ACK = 4
    STATUS = 5
    ASSIGN = 6


# --- Errores ---

class ProtocolError(ValueError):
    """Paquete invalido: el receptor lo descarta."""


class TruncatedPacket(ProtocolError):
    pass


class UnknownType(ProtocolError):
    pass


class VersionMismatch(ProtocolError):
    pass


class TrailingBytes(ProtocolError):
    pass


class InvalidField(ProtocolError):
    pass


# --- Validadores ---

def _need_int(name: str, v, lo: int, hi: int) -> None:
    if isinstance(v, bool) or not isinstance(v, int):
        raise InvalidField(f"{name} debe ser entero, llego {v!r}")
    if not lo <= v <= hi:
        raise InvalidField(f"{name}={v} fuera de rango [{lo}, {hi}]")


def _need_nx(v) -> None:
    _need_int("nx", v, 1, MAX_NX)


# --- Paquetes ---

@dataclass(frozen=True)
class Assignment:
    nx: int
    target_id: int          # u16
    ra_e7: int              # 0 <= RA < 360 deg, en 1e-7 deg (u32 en el cable)
    dec_e7: int             # -90..+90 deg, en 1e-7 deg (i32)

    def __post_init__(self):
        _need_nx(self.nx)
        _need_int("target_id", self.target_id, 0, 0xFFFF)
        _need_int("ra_e7", self.ra_e7, 0, RA_MAX_E7 - 1)
        _need_int("dec_e7", self.dec_e7, -DEC_MAX_E7, DEC_MAX_E7)


@dataclass(frozen=True)
class Heartbeat:
    base_id: int
    seq: int
    utc_ms: int
    lat_e7: int
    lon_e7: int
    flags: int
    assignments: Tuple[Assignment, ...] = field(default_factory=tuple)

    def __post_init__(self):
        _need_int("base_id", self.base_id, 0, 0xFFFF)
        _need_int("seq", self.seq, 0, 0xFFFF)
        _need_int("utc_ms", self.utc_ms, 0, 0xFFFFFFFFFFFFFFFF)
        _need_int("lat_e7", self.lat_e7, -LAT_MAX_E7, LAT_MAX_E7)
        _need_int("lon_e7", self.lon_e7, -LON_MAX_E7, LON_MAX_E7)
        _need_int("flags", self.flags, 0, 0xFF)
        if self.flags & ~HB_FLAGS_MASK:
            raise InvalidField(f"banderas HB con bits reservados: 0x{self.flags:02X}")
        # Las asignaciones pueden llegar como lista; se normalizan a tupla.
        object.__setattr__(self, "assignments", tuple(self.assignments))
        if len(self.assignments) > MAX_ASSIGNMENTS:
            raise InvalidField(f"{len(self.assignments)} asignaciones, maximo {MAX_ASSIGNMENTS}")
        nxs = [a.nx for a in self.assignments]
        if len(set(nxs)) != len(nxs):
            raise InvalidField("Nx repetido en las asignaciones del HB")


@dataclass(frozen=True)
class DockReq:
    nx: int
    seq: int

    def __post_init__(self):
        _need_nx(self.nx)
        _need_int("seq", self.seq, 0, 0xFFFF)


@dataclass(frozen=True)
class DockRef:
    nx: int
    seq: int
    utc_ms: int
    quat: Tuple[float, float, float, float]   # cuerpo del M2 (cavidad) -> ENU, Hamilton (w, x, y, z) [decidido]; ESPEC. 3.3
    stars: int                                # estrellas emparejadas; 0 = sin solucion valida [decidido]
    flags: int

    def __post_init__(self):
        _need_nx(self.nx)
        _need_int("seq", self.seq, 0, 0xFFFF)
        _need_int("utc_ms", self.utc_ms, 0, 0xFFFFFFFFFFFFFFFF)
        _need_int("stars", self.stars, 0, 0xFF)
        _need_int("flags", self.flags, 0, 0xFF)
        if self.flags & ~REF_FLAGS_MASK:
            raise InvalidField(f"banderas DOCK_REF con bits reservados: 0x{self.flags:02X}")
        q = tuple(self.quat)
        if len(q) != 4:
            raise InvalidField("el cuaternion lleva 4 componentes")
        object.__setattr__(self, "quat", q)
        if any((not isinstance(c, (int, float))) or isinstance(c, bool) or not math.isfinite(c) for c in q):
            raise InvalidField("cuaternion con NaN, infinito o tipo invalido")
        # Se valida lo que viaja: los cuatro valores redondeados a f32 (lo que el receptor va a leer).
        try:
            q = _QUAT_F32.unpack(_QUAT_F32.pack(*(float(c) for c in q)))
        except OverflowError:
            raise InvalidField("cuaternion fuera del rango de f32") from None
        object.__setattr__(self, "quat", q)
        norm = math.sqrt(sum(float(c) * float(c) for c in q))
        if abs(norm - 1.0) > QUAT_NORM_TOL:
            raise InvalidField(f"cuaternion no unitario (norma={norm:.6f})")


@dataclass(frozen=True)
class Ack:
    nx: int
    seq: int

    def __post_init__(self):
        _need_nx(self.nx)
        _need_int("seq", self.seq, 0, 0xFFFF)


@dataclass(frozen=True)
class Status:
    nx: int
    battery_pct: int
    state: int
    since_sync_s: int       # u16, satura en 65535
    correction_cdeg: int    # u16, centesimas de grado
    quality: int

    def __post_init__(self):
        _need_nx(self.nx)
        _need_int("battery_pct", self.battery_pct, 0, BATTERY_MAX)
        _need_int("state", self.state, 0, M2_STATE_MAX)
        _need_int("since_sync_s", self.since_sync_s, 0, 0xFFFF)
        _need_int("correction_cdeg", self.correction_cdeg, 0, 0xFFFF)
        _need_int("quality", self.quality, 0, QUALITY_MAX)


@dataclass(frozen=True)
class Assign:
    nx: int
    target_id: int
    ra_e7: int
    dec_e7: int

    def __post_init__(self):
        # Reusa las reglas de Assignment para que ASSIGN y HB nunca discrepen.
        Assignment(self.nx, self.target_id, self.ra_e7, self.dec_e7)


Packet = Union[Heartbeat, DockReq, DockRef, Ack, Status, Assign]

# --- Formatos de cable ---

_HB_HEAD = struct.Struct("<BBHHQiiBB")
_HB_ASG = struct.Struct("<BHIi")
_DOCK_REQ = struct.Struct("<BBH")
_DOCK_REF = struct.Struct("<BBHQ4fBB")
_QUAT_F32 = struct.Struct("<4f")
_ACK = struct.Struct("<BBH")
_STATUS = struct.Struct("<BBBBHHB")
_ASSIGN = struct.Struct("<BBHIi")

FIXED_SIZES = {
    PacketType.DOCK_REQ: _DOCK_REQ.size,   # 4
    PacketType.DOCK_REF: _DOCK_REF.size,   # 30
    PacketType.ACK: _ACK.size,             # 4
    PacketType.STATUS: _STATUS.size,       # 9
    PacketType.ASSIGN: _ASSIGN.size,       # 12
}

assert _HB_HEAD.size == HB_HEADER_SIZE and _HB_ASG.size == HB_ASSIGNMENT_SIZE
assert FIXED_SIZES == {PacketType.DOCK_REQ: 4, PacketType.DOCK_REF: 30, PacketType.ACK: 4,
                       PacketType.STATUS: 9, PacketType.ASSIGN: 12}


def encode(pkt: Packet) -> bytes:
    if isinstance(pkt, Heartbeat):
        out = bytearray(_HB_HEAD.pack(
            PacketType.HB, PROTO_VERSION, pkt.base_id, pkt.seq, pkt.utc_ms,
            pkt.lat_e7, pkt.lon_e7, pkt.flags, len(pkt.assignments)))
        for a in pkt.assignments:
            out += _HB_ASG.pack(a.nx, a.target_id, a.ra_e7, a.dec_e7)
        return bytes(out)
    if isinstance(pkt, DockReq):
        return _DOCK_REQ.pack(PacketType.DOCK_REQ, pkt.nx, pkt.seq)
    if isinstance(pkt, DockRef):
        return _DOCK_REF.pack(PacketType.DOCK_REF, pkt.nx, pkt.seq, pkt.utc_ms,
                              *pkt.quat, pkt.stars, pkt.flags)
    if isinstance(pkt, Ack):
        return _ACK.pack(PacketType.ACK, pkt.nx, pkt.seq)
    if isinstance(pkt, Status):
        return _STATUS.pack(PacketType.STATUS, pkt.nx, pkt.battery_pct, pkt.state,
                            pkt.since_sync_s, pkt.correction_cdeg, pkt.quality)
    if isinstance(pkt, Assign):
        return _ASSIGN.pack(PacketType.ASSIGN, pkt.nx, pkt.target_id, pkt.ra_e7, pkt.dec_e7)
    raise TypeError(f"no es un paquete del protocolo: {pkt!r}")


def _exact(data: bytes, size: int) -> None:
    if len(data) < size:
        raise TruncatedPacket(f"{len(data)} B, se esperaban {size}")
    if len(data) > size:
        raise TrailingBytes(f"{len(data)} B, se esperaban {size}")


def decode(data: bytes) -> Packet:
    """Decodifica un datagrama completo. Lanza una subclase de ProtocolError si no cuadra."""
    data = bytes(data)
    if len(data) < 1:
        raise TruncatedPacket("datagrama vacio")
    try:
        ptype = PacketType(data[0])
    except ValueError:
        raise UnknownType(f"tipo 0x{data[0]:02X}") from None

    if ptype is PacketType.HB:
        # La version se revisa antes que el largo: otra version puede tener otro tamano.
        if len(data) < 2:
            raise TruncatedPacket("HB sin byte de version")
        if data[1] != PROTO_VERSION:
            raise VersionMismatch(f"version {data[1]}, se habla {PROTO_VERSION}")
        if len(data) < HB_HEADER_SIZE:
            raise TruncatedPacket(f"HB de {len(data)} B, cabecera de {HB_HEADER_SIZE}")
        (_, _, base_id, seq, utc_ms, lat, lon, flags, n) = _HB_HEAD.unpack_from(data, 0)
        if n > MAX_ASSIGNMENTS:
            raise InvalidField(f"{n} asignaciones, maximo {MAX_ASSIGNMENTS}")
        _exact(data, HB_HEADER_SIZE + HB_ASSIGNMENT_SIZE * n)
        asg = []
        for i in range(n):
            nx, tid, ra, dec = _HB_ASG.unpack_from(data, HB_HEADER_SIZE + HB_ASSIGNMENT_SIZE * i)
            asg.append(Assignment(nx, tid, ra, dec))
        return Heartbeat(base_id, seq, utc_ms, lat, lon, flags, tuple(asg))

    _exact(data, FIXED_SIZES[ptype])
    if ptype is PacketType.DOCK_REQ:
        _, nx, seq = _DOCK_REQ.unpack(data)
        return DockReq(nx, seq)
    if ptype is PacketType.DOCK_REF:
        _, nx, seq, utc_ms, w, x, y, z, stars, flags = _DOCK_REF.unpack(data)
        return DockRef(nx, seq, utc_ms, (w, x, y, z), stars, flags)
    if ptype is PacketType.ACK:
        _, nx, seq = _ACK.unpack(data)
        return Ack(nx, seq)
    if ptype is PacketType.STATUS:
        _, nx, bat, state, since, corr, q = _STATUS.unpack(data)
        return Status(nx, bat, state, since, corr, q)
    _, nx, tid, ra, dec = _ASSIGN.unpack(data)
    return Assign(nx, tid, ra, dec)


# --- Aritmetica de secuencia (u16 con vuelta) ---

SEQ_STALE_WINDOW = 8   # cuantos HB "hacia atras" se consideran retrasados y no un M1 reiniciado [decidido: arbitraje c-morty 2026-10-15]


def seq_delta(new: int, old: int) -> int:
    """Distancia de 'old' a 'new' modulo 2^16, en 0..65535."""
    return (new - old) & 0xFFFF


def seq_is_stale_or_dup(new: int, last: int) -> bool:
    """True si 'new' es el mismo HB o uno de los SEQ_STALE_WINDOW anteriores a 'last'.

    Un salto mayor hacia atras se acepta como un M1 que reinicio su contador.
    """
    d = seq_delta(new, last)
    return d == 0 or d >= 0x10000 - SEQ_STALE_WINDOW


def hex_of(data: bytes) -> str:
    return data.hex().upper()
