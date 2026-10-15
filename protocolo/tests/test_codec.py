"""Codec: tamanos, ida y vuelta, bordes y rechazos."""
import math
import random
import struct

import pytest

import euler_proto as p


def hb(n=0, **kw):
    base = dict(base_id=7, seq=5, utc_ms=1_760_000_000_000, lat_e7=199_000_000, lon_e7=-1_011_000_000,
                flags=0x0F, assignments=tuple(p.Assignment(i + 1, 100 + i, i * 1000, -i * 1000) for i in range(n)))
    base.update(kw)
    return p.Heartbeat(**base)


def f32(x):
    return struct.unpack("<f", struct.pack("<f", x))[0]


# --- Tamanos exactos de la tabla de paquetes ---

@pytest.mark.parametrize("n", range(0, 11))
def test_tamano_del_hb_es_24_mas_11_por_asignacion(n):
    assert len(p.encode(hb(n))) == 24 + 11 * n


def test_hb_con_diez_asignaciones_mide_134():
    assert len(p.encode(hb(10))) == 134 == p.HB_MAX_SIZE


def test_tamanos_de_los_paquetes_fijos():
    assert len(p.encode(p.DockReq(1, 0))) == 4
    assert len(p.encode(p.DockRef(1, 0, 0, (1, 0, 0, 0), 5, 0))) == 30
    assert len(p.encode(p.Ack(1, 0))) == 4
    assert len(p.encode(p.Status(1, 50, 5, 0, 0, 0))) == 9
    assert len(p.encode(p.Assign(1, 1, 0, 0))) == 12


def test_el_primer_byte_es_el_tipo_y_hb_lleva_la_version():
    assert p.encode(hb())[0:2] == bytes([p.PacketType.HB, p.PROTO_VERSION])
    assert p.encode(p.DockReq(1, 0))[0] == p.PacketType.DOCK_REQ
    assert [int(t) for t in p.PacketType] == [1, 2, 3, 4, 5, 6]


def test_little_endian_del_campo_seq():
    assert p.encode(hb(seq=0x0102))[4:6] == b"\x02\x01"


# --- Ida y vuelta ---

def test_ida_y_vuelta_aleatoria_de_todos_los_tipos():
    rng = random.Random(1234)
    for _ in range(300):
        n = rng.randint(0, 10)
        nxs = rng.sample(range(1, 11), n)
        asg = tuple(p.Assignment(nx, rng.randint(0, 65535), rng.randint(0, p.RA_MAX_E7 - 1),
                                 rng.randint(-p.DEC_MAX_E7, p.DEC_MAX_E7)) for nx in nxs)
        quat = [f32(rng.uniform(-1, 1)) for _ in range(4)]
        norm = math.sqrt(sum(c * c for c in quat)) or 1.0
        quat = tuple(f32(c / norm) for c in quat)
        pkts = [
            p.Heartbeat(rng.randint(0, 65535), rng.randint(0, 65535), rng.randint(0, 2**64 - 1),
                        rng.randint(-p.LAT_MAX_E7, p.LAT_MAX_E7), rng.randint(-p.LON_MAX_E7, p.LON_MAX_E7),
                        rng.randint(0, p.HB_FLAGS_MASK), asg),
            p.DockReq(rng.randint(1, 10), rng.randint(0, 65535)),
            p.DockRef(rng.randint(1, 10), rng.randint(0, 65535), rng.randint(0, 2**64 - 1), quat,
                      rng.randint(0, 255), rng.randint(0, p.REF_FLAGS_MASK)),
            p.Ack(rng.randint(1, 10), rng.randint(0, 65535)),
            p.Status(rng.randint(1, 10), rng.randint(0, 100), rng.randint(0, p.M2_STATE_MAX),
                     rng.randint(0, 65535), rng.randint(0, 65535), rng.randint(0, p.QUALITY_MAX)),
            p.Assign(rng.randint(1, 10), rng.randint(0, 65535), rng.randint(0, p.RA_MAX_E7 - 1),
                     rng.randint(-p.DEC_MAX_E7, p.DEC_MAX_E7)),
        ]
        for pk in pkts:
            data = p.encode(pk)
            assert p.decode(data) == pk
            assert p.encode(p.decode(data)) == data


# --- Bordes ---

def test_bordes_de_campos_validos():
    for kw in (dict(seq=0), dict(seq=65535), dict(base_id=65535), dict(utc_ms=2**64 - 1), dict(utc_ms=0),
               dict(lat_e7=p.LAT_MAX_E7, lon_e7=p.LON_MAX_E7), dict(lat_e7=-p.LAT_MAX_E7, lon_e7=-p.LON_MAX_E7)):
        pk = hb(**kw)
        assert p.decode(p.encode(pk)) == pk
    for pk in (p.Assign(10, 65535, p.RA_MAX_E7 - 1, p.DEC_MAX_E7), p.Assign(1, 0, 0, -p.DEC_MAX_E7),
               p.Status(10, 100, p.M2_STATE_MAX, 65535, 65535, p.QUALITY_MAX), p.Status(1, 0, 0, 0, 0, 0)):
        assert p.decode(p.encode(pk)) == pk


def test_ra_mayor_a_la_mitad_del_cielo_cabe_en_el_cable():
    # Hallazgo H1: i32 no llega a 360 deg; el cable lleva u32. 300 deg reventaria un i32.
    a = p.Assign(1, 1, 300 * p.E7, 0)
    assert p.decode(p.encode(a)).ra_e7 == 300 * p.E7


CONSTRUCTORES_INVALIDOS = [
    lambda: hb(seq=65536), lambda: hb(seq=-1), lambda: hb(base_id=65536),
    lambda: hb(utc_ms=2**64), lambda: hb(utc_ms=-1),
    lambda: hb(lat_e7=p.LAT_MAX_E7 + 1), lambda: hb(lat_e7=-p.LAT_MAX_E7 - 1),
    lambda: hb(lon_e7=p.LON_MAX_E7 + 1), lambda: hb(lon_e7=-p.LON_MAX_E7 - 1),
    lambda: hb(flags=0x10), lambda: hb(flags=256), lambda: hb(seq=1.5), lambda: hb(seq=True),
    lambda: hb(11),
    lambda: hb(2, assignments=(p.Assignment(1, 1, 0, 0), p.Assignment(1, 2, 0, 0))),
    lambda: p.Assignment(0, 1, 0, 0), lambda: p.Assignment(11, 1, 0, 0),
    lambda: p.Assignment(1, 65536, 0, 0), lambda: p.Assignment(1, 1, p.RA_MAX_E7, 0),
    lambda: p.Assignment(1, 1, -1, 0), lambda: p.Assignment(1, 1, 0, p.DEC_MAX_E7 + 1),
    lambda: p.DockReq(0, 0), lambda: p.DockReq(11, 0), lambda: p.DockReq(1, 65536),
    lambda: p.Ack(0, 0), lambda: p.Ack(1, -1),
    lambda: p.DockRef(1, 0, 0, (0, 0, 0, 0), 1, 0),
    lambda: p.DockRef(1, 0, 0, (float("nan"), 0, 0, 1), 1, 0),
    lambda: p.DockRef(1, 0, 0, (float("inf"), 0, 0, 0), 1, 0),
    lambda: p.DockRef(1, 0, 0, (1, 0, 0), 1, 0),
    lambda: p.DockRef(1, 0, 0, (1.01, 0, 0, 0), 1, 0),
    lambda: p.DockRef(1, 0, 0, (1, 0, 0, 0), 256, 0), lambda: p.DockRef(1, 0, 0, (1, 0, 0, 0), 1, 2),
    lambda: p.Status(1, 101, 0, 0, 0, 0), lambda: p.Status(1, 0, p.M2_STATE_MAX + 1, 0, 0, 0),
    lambda: p.Status(1, 0, 0, 65536, 0, 0), lambda: p.Status(1, 0, 0, 0, 65536, 0),
    lambda: p.Status(1, 0, 0, 0, 0, p.QUALITY_MAX + 1),
    lambda: p.Assign(1, 1, p.RA_MAX_E7, 0),
]


@pytest.mark.parametrize("ctor", CONSTRUCTORES_INVALIDOS, ids=range(len(CONSTRUCTORES_INVALIDOS)))
def test_construir_un_paquete_fuera_de_rango_falla(ctor):
    with pytest.raises(p.InvalidField):
        ctor()


def test_encode_rechaza_lo_que_no_es_paquete():
    with pytest.raises(TypeError):
        p.encode("hola")


# --- Rechazos del decoder ---

def test_datagrama_vacio_es_truncado():
    with pytest.raises(p.TruncatedPacket):
        p.decode(b"")


@pytest.mark.parametrize("tipo", [0, 7, 8, 0x41, 0x80, 0xFF])
def test_tipo_desconocido(tipo):
    with pytest.raises(p.UnknownType):
        p.decode(bytes([tipo]) + bytes(30))


@pytest.mark.parametrize("ver", [0, 2, 255])
def test_version_distinta_del_hb(ver):
    data = bytearray(p.encode(hb(2)))
    data[1] = ver
    with pytest.raises(p.VersionMismatch):
        p.decode(bytes(data))


def test_version_distinta_se_detecta_aunque_el_largo_sea_ajeno():
    # Otra version podria tener otro tamano: la version manda sobre el largo.
    with pytest.raises(p.VersionMismatch):
        p.decode(bytes([p.PacketType.HB, 9]) + bytes(5))


def test_hb_cuyo_n_no_coincide_con_el_largo():
    data = bytearray(p.encode(hb(3)))
    data[23] = 4                       # dice 4, trae 3
    with pytest.raises(p.TruncatedPacket):
        p.decode(bytes(data))
    data[23] = 2                       # dice 2, trae 3
    with pytest.raises(p.TrailingBytes):
        p.decode(bytes(data))


def test_hb_con_n_255_no_desborda():
    # n > 10 se rechaza ANTES de calcular 24 + 11*n: en C++ ese producto desborda un u8 y el bucle escribiria
    # fuera del arreglo de 10 asignaciones (ESPEC. 4, regla 4).
    data = bytearray(p.encode(hb(0)))
    data[23] = 255
    with pytest.raises(p.InvalidField):
        p.decode(bytes(data))


@pytest.mark.parametrize("n", [11, 24, 255])
def test_hb_con_n_mayor_que_10_es_invalido_aunque_el_largo_cuadre(n):
    data = bytearray(p.encode(hb(10))) + bytes(11 * (n - 10))
    data[23] = n
    assert len(data) == 24 + 11 * n
    with pytest.raises(p.InvalidField):
        p.decode(bytes(data))


def test_fuzz_el_decoder_solo_lanza_protocolerror_y_lo_aceptado_es_canonico():
    rng = random.Random(99)
    aceptados = 0
    for _ in range(20000):
        tipo = rng.choice([1, 2, 3, 4, 5, 6, 7, 0])
        n = {1: 24, 2: 4, 3: 30, 4: 4, 5: 9, 6: 12}.get(tipo, rng.randint(1, 20))
        if rng.random() < 0.15:
            n = rng.randint(1, 40)
        data = bytearray(rng.getrandbits(8) for _ in range(n))
        data[0] = tipo
        if tipo == 1 and n >= 24:
            data[1] = 1
            data[23] = (n - 24) // 11 if (n - 24) % 11 == 0 else data[23]
        # Sesgo hacia lo casi valido: campos chicos para que algunos pasen las validaciones.
        if rng.random() < 0.7 and n > 3:
            for k in range(2, n):
                if rng.random() < 0.6:
                    data[k] = rng.choice([0, 1, 2, 5])
        try:
            pk = p.decode(bytes(data))
        except p.ProtocolError:
            continue
        aceptados += 1
        assert p.encode(pk) == bytes(data)
    assert aceptados > 50, aceptados


# --- Aritmetica de secuencia ---

def test_seq_delta_con_vuelta():
    assert p.seq_delta(0, 65535) == 1
    assert p.seq_delta(5, 3) == 2
    assert p.seq_delta(3, 5) == 65534


def test_seq_estancado_o_duplicado():
    assert p.seq_is_stale_or_dup(100, 100)              # duplicado
    assert p.seq_is_stale_or_dup(99, 100)               # uno atrasado
    assert p.seq_is_stale_or_dup(100 - p.SEQ_STALE_WINDOW, 100)
    assert not p.seq_is_stale_or_dup(101, 100)          # adelantado
    assert not p.seq_is_stale_or_dup(100 - p.SEQ_STALE_WINDOW - 1, 100)  # fuera de ventana: M1 reiniciado
    assert not p.seq_is_stale_or_dup(0, 500)            # contador reiniciado a 0
    assert p.seq_is_stale_or_dup(65535, 0)              # atraso a traves de la vuelta
    assert not p.seq_is_stale_or_dup(1, 65535)          # adelantado a traves de la vuelta


def test_la_ventana_de_atraso_es_de_8_hb_segun_la_especificacion():
    assert p.SEQ_STALE_WINDOW == 8
    assert p.seq_is_stale_or_dup(92, 100)        # 8 atras: atrasado
    assert not p.seq_is_stale_or_dup(91, 100)    # 9 atras: se toma como M1 reiniciado


# --- C3: el codificador no acepta lo que el decodificador rechaza (norma sobre los f32 que viajan) ---

def test_todo_dock_ref_construible_sobrevive_a_ida_y_vuelta_junto_a_la_tolerancia():
    construidos = rechazados = 0
    for k in range(20_000):
        w = 1.0 + p.QUAT_NORM_TOL - k * 1e-11            # pegado al borde de la tolerancia de norma
        try:
            r = p.DockRef(1, 0, 0, (w, 0.0, 0.0, 0.0), 5, 0)
        except p.InvalidField:
            rechazados += 1
            continue
        construidos += 1
        assert p.decode(p.encode(r)) == r
    assert construidos > 0 and rechazados > 0            # la prueba cruza el borde: no es vacua


def test_cuaternion_fuera_del_rango_de_f32_es_invalid_field_no_overflow():
    with pytest.raises(p.InvalidField):
        p.DockRef(1, 0, 0, (1e39, 0.0, 0.0, 0.0), 5, 0)
