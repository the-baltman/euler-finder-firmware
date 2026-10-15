"""Escenarios del simulador sobre la red virtual (deterministas, sin dormir)."""
import math

import pytest

import euler_proto as p
from euler_sim.impair import Impairment
from euler_sim.m1 import DockPhase, M1Config
from euler_sim.m2 import DockState, Level, M2Config, M2Core
from euler_sim.virtual import VirtualNet

RA, DEC = 250 * p.E7, -30 * p.E7      # RA > 214.7 deg a proposito (hallazgo H1)


def red(n=1, seed=1, impair=None, m1_cfg=None, **m2_kw):
    net = VirtualNet(seed=seed, impair=impair, m1_cfg=m1_cfg)
    for nx in range(1, n + 1):
        net.add_m2(nx, **m2_kw)
    return net


def kinds(net, nx=1, desde=0.0):
    """Paquetes de acople del M2 nx en orden de envio: [(origen, tipo)]."""
    return [(r.src, r.kind) for r in net.log
            if r.kind in ("DockReq", "Ack", "DockRef") and r.t_send >= desde
            and (r.src == f"M2-{nx}" or r.dst == f"M2-{nx}")]


# --- Heartbeat ---

def test_hb_sale_cada_10_s_exactos():
    net = red()
    net.run_until(100.0)
    t = [r.t_send for r in net.sent("Heartbeat")]
    assert len(t) == 11
    assert t[0] == 0.0
    assert all(b - a == 10.0 for a, b in zip(t, t[1:]))


def test_hb_lleva_hora_ubicacion_banderas_y_secuencia():
    net = red()
    net.run_until(25.0)
    hb = net.m2[1].last_hb
    assert hb.seq == 2                                   # HB de t=0, 10, 20
    assert (hb.base_id, hb.lat_e7, hb.lon_e7) == (1, 197_000_000, -1_012_000_000)
    assert hb.flags == p.HB_FLAG_SOLVE_OK | p.HB_FLAG_TIME_VALID | p.HB_FLAG_LOCATION_VALID
    est = net.m2[1].utc_ms_estimate(25.0)
    assert abs(est - (net.m1.cfg.utc0_ms + 25_000)) <= 10      # solo el retraso de red


def test_hb_se_difunde_a_todos_los_m2():
    net = red(n=10)
    net.run_until(10.5)
    assert all(c.rx["Heartbeat"] == 2 for c in net.m2.values())


def test_hb_con_diez_asignaciones_mide_134_bytes_en_el_cable():
    net = red(n=10)
    net.run_until(1.0)
    for nx in range(1, 11):
        net.m1.assign(nx, nx, RA, DEC, net.now)
    net.run_until(10.5)
    tamanos = {r.size for r in net.sent("Heartbeat")}
    assert max(tamanos) == 134
    assert all(len(c.last_hb.assignments) == 10 for c in net.m2.values())


# --- ASSIGN ---

def test_assign_llega_de_inmediato_sin_esperar_el_siguiente_hb():
    net = red()
    net.run_until(3.3)
    net.m1.assign(1, 77, RA, DEC, net.now)
    net.run_until(3.3 + 0.05)
    assert net.m2[1].target == p.Assignment(1, 77, RA, DEC)
    assert net.m2[1].last_hb.assignments == ()           # el HB de t=0 no la traia: llego por ASSIGN


def test_asignacion_solo_para_su_m2():
    net = red(n=3)
    net.run_until(3.0)
    net.m1.assign(2, 5, RA, DEC, net.now)
    net.run_until(3.1)
    assert net.m2[2].target is not None
    assert net.m2[1].target is None and net.m2[3].target is None


def test_el_hb_es_la_verdad_si_ya_no_me_nombra_pierdo_el_objetivo():
    net = red()
    net.run_until(3.0)
    net.m1.assign(1, 5, RA, DEC, net.now)
    net.run_until(12.0)
    assert net.m2[1].target is not None
    net.m1.clear_assignment(1)
    net.run_until(12.5)
    assert net.m2[1].target is not None                  # no hay ASSIGN de borrado: espera al HB
    net.run_until(20.1)
    assert net.m2[1].target is None


def test_h3_a_nivel_de_m2_un_hb_sin_la_asignacion_pisa_al_assign_y_el_siguiente_la_restituye():
    enviados = []
    m2 = M2Core(M2Config(nx=1), enviados.append)
    a = p.Assignment(1, 9, RA, DEC)

    def hb(seq, asg):
        return p.encode(p.Heartbeat(1, seq, 1000 * seq, 0, 0, 0, tuple(asg)))

    m2.on_packet(hb(10, []), 1.0)
    m2.on_packet(p.encode(p.Assign(1, 9, RA, DEC)), 2.0)
    assert m2.target == a
    m2.on_packet(hb(11, []), 2.001)                      # HB armado antes del ASSIGN
    assert m2.target is None                             # <- el defecto H3
    m2.on_packet(hb(12, [a]), 3.0)
    assert m2.target == a


def test_variante_hb_after_assign_junta_la_rafaga_en_un_solo_hb_extra():
    net = red(n=10, m1_cfg=M1Config(hb_after_assign=True))
    net.run_until(1.0)
    antes = len(net.sent("Heartbeat", dst="M2-1"))
    for nx in range(1, 11):
        net.m1.assign(nx, nx, RA, DEC, net.now)
    net.run_until(1.2)
    extra = net.sent("Heartbeat", dst="M2-1")[antes:]
    assert len(extra) == 1
    assert extra[0].size == 134
    assert abs(extra[0].t_send - 1.05) < 1e-9


# --- Acople ---

def test_acople_limpio_orden_tamanos_y_contenido():
    net = red(m1_cfg=M1Config(solve_time_s=2.0))
    net.run_until(1.0)
    assert net.m2[1].request_dock(net.now)
    net.run_until(5.0)
    assert kinds(net, desde=1.0) == [("M2-1", "DockReq"), ("M1", "Ack"), ("M1", "DockRef"), ("M2-1", "Ack")]
    sizes = [r.size for r in net.log if r.kind in ("DockReq", "Ack", "DockRef")]
    assert sizes == [4, 4, 30, 4]
    c = net.m2[1]
    assert c.dock_state is DockState.DONE and c.synced
    assert c.ref.flags & p.REF_FLAG_SAMPLE_IMAGE
    assert c.ref.stars == 12
    assert abs(math.sqrt(sum(x * x for x in c.ref.quat)) - 1.0) < 1e-6
    assert net.m1.dock_phase(1) is DockPhase.DONE
    assert net.m1.solves == 1
    assert 2.0 <= c.dock_finished - c.dock_started < 2.05    # el solve manda, la red casi no pesa


def test_el_solve_es_de_un_solo_acople_a_la_vez():
    net = red(n=10)
    net.run_until(1.0)
    for c in net.m2.values():
        c.request_dock(net.now)
    net.run_until(40.0)
    fin = sorted(c.dock_finished for c in net.m2.values())
    assert all(c.dock_state is DockState.DONE for c in net.m2.values())
    assert net.m1.solves == 10
    assert all(b - a >= 2.0 - 0.005 for a, b in zip(fin, fin[1:]))   # una camara: en fila
    assert fin[-1] - 1.0 >= 20.0


def _drop_nth(net, pred, n=1):
    """Descarta la n-esima copia que cumple pred(src, dst, pkt)."""
    visto = [0]

    def f(t, src, dst, pkt):
        if pkt is not None and pred(src, dst, pkt):
            visto[0] += 1
            return visto[0] == n
        return False
    net.drop_filter = f


def test_req_perdido_se_reintenta_con_la_misma_secuencia_y_se_resuelve_una_vez():
    net = red()
    net.run_until(1.0)
    _drop_nth(net, lambda s, d, k: isinstance(k, p.DockReq))
    net.m2[1].request_dock(net.now)
    net.run_until(10.0)
    reqs = net.sent("DockReq")
    assert len(reqs) == 2 and not reqs[0].delivered and reqs[1].delivered
    assert abs((reqs[1].t_send - reqs[0].t_send) - 1.0) < 1e-9
    assert net.m2[1].dock_state is DockState.DONE
    assert net.m1.solves == 1


def test_ack_del_req_perdido_el_m2_reintenta_el_m1_reconfirma_sin_resolver_otra_vez():
    net = red()
    net.run_until(1.0)
    _drop_nth(net, lambda s, d, k: s == "M1" and isinstance(k, p.Ack))
    net.m2[1].request_dock(net.now)
    net.run_until(10.0)
    assert net.m1.rx["DockReq"] == 2
    assert net.m1.solves == 1
    assert len(net.sent("Ack", src="M1")) == 2
    assert net.m2[1].dock_state is DockState.DONE


def test_dock_ref_perdido_el_m1_lo_reenvia():
    net = red()
    net.run_until(1.0)
    _drop_nth(net, lambda s, d, k: isinstance(k, p.DockRef))
    net.m2[1].request_dock(net.now)
    net.run_until(10.0)
    refs = net.sent("DockRef")
    assert len(refs) == 2 and abs((refs[1].t_send - refs[0].t_send) - 1.0) < 1e-9
    assert net.m1.ref_resends == 1
    assert net.m2[1].dock_state is DockState.DONE and net.m2[1].ref_applied == 1
    assert net.m1.solves == 1


def test_ack_del_ref_perdido_el_m1_reenvia_y_el_m2_reconfirma_sin_reaplicar():
    net = red()
    net.run_until(1.0)
    _drop_nth(net, lambda s, d, k: s == "M2-1" and isinstance(k, p.Ack))
    net.m2[1].request_dock(net.now)
    net.run_until(10.0)
    assert len(net.sent("DockRef")) == 2
    assert len(net.sent("Ack", src="M2-1")) == 2
    assert net.m2[1].ref_applied == 1                    # la referencia se aplica una sola vez
    assert net.m1.dock_phase(1) is DockPhase.DONE


def test_el_m1_deja_de_reenviar_tras_sus_reintentos():
    net = red(m1_cfg=M1Config(ref_max_tries=3))
    net.run_until(1.0)
    net.drop_filter = lambda t, s, d, k: s == "M2-1" and isinstance(k, p.Ack)   # el M1 jamas recibe el ACK
    net.m2[1].request_dock(net.now)
    net.run_until(30.0)
    assert len(net.sent("DockRef")) == 3
    assert net.m1.dock_phase(1) is DockPhase.FAILED


def test_m1_muerto_el_m2_se_rinde_en_tiempo_acotado_y_luego_puede_reintentar():
    net = red()
    net.run_until(1.0)
    net.kill_m1()
    t0 = net.now
    net.m2[1].request_dock(t0)
    net.run_until(t0 + 7.9)
    assert net.m2[1].dock_state is DockState.WAIT_ACK
    net.run_until(t0 + 8.0)
    assert net.m2[1].dock_state is DockState.FAILED_TIMEOUT
    assert len(net.sent("DockReq")) == 8
    net.run_until(t0 + 30.0)
    assert len(net.sent("DockReq")) == 8                 # no sigue hablando
    net.revive_m1()
    assert net.m2[1].request_dock(net.now)
    net.run_until(net.now + 6.0)
    assert net.m2[1].dock_state is DockState.DONE


def test_un_dock_ref_tardio_despues_de_fallar_se_ignora():
    # El M1 tarda 12 s; sus ACK se pierden y el M2 se rinde a los 8 s. La referencia llega a destiempo.
    net = red(m1_cfg=M1Config(solve_time_s=12.0))
    net.run_until(1.0)
    net.drop_filter = lambda t, s, d, k: s == "M1" and isinstance(k, p.Ack)
    net.m2[1].request_dock(net.now)
    net.run_until(30.0)
    c = net.m2[1]
    assert c.dock_state is DockState.FAILED_TIMEOUT
    assert not c.synced and c.ref_applied == 0 and c.ref is None
    assert c.rejected.get("stale_ref", 0) >= 1


def test_sin_solucion_el_m2_no_queda_sincronizado():
    net = red(m1_cfg=M1Config(stars_matched=0))
    net.run_until(1.0)
    net.m2[1].request_dock(net.now)
    net.run_until(8.0)
    c = net.m2[1]
    assert c.dock_state is DockState.FAILED_NO_SOLUTION
    assert not c.synced and c.ref is None
    assert net.m1.dock_phase(1) is DockPhase.DONE        # el M1 recibio el ACK y dejo de reenviar


def test_segundo_acople_usa_secuencia_nueva_y_reaplica():
    net = red()
    net.run_until(1.0)
    net.m2[1].request_dock(net.now)
    net.run_until(6.0)
    s1 = net.m2[1].ref.seq
    assert net.m2[1].request_dock(net.now)
    net.run_until(12.0)
    assert net.m2[1].ref.seq == (s1 + 1) & 0xFFFF
    assert net.m2[1].ref_applied == 2 and net.m1.solves == 2


def test_no_se_puede_pedir_acople_con_otro_en_curso():
    net = red()
    net.run_until(1.0)
    assert net.m2[1].request_dock(net.now)
    assert not net.m2[1].request_dock(net.now)
    assert len(net.sent("DockReq")) == 1


def test_con_todo_duplicado_el_acople_sigue_siendo_idempotente():
    net = red(impair=Impairment(dup=1.0, reorder_max_s=0.5))
    net.run_until(1.0)
    net.m2[1].request_dock(net.now)
    net.run_until(12.0)
    assert net.m1.solves == 1
    assert net.m2[1].ref_applied == 1
    assert net.m2[1].dock_state is DockState.DONE
    assert net.m2[1].stale_hb >= 1                       # los HB repetidos se descartan


# --- STATUS ---

def test_status_cada_10_s_y_con_el_estado_correcto():
    net2 = VirtualNet(seed=3)
    net2.add_m2(1, status_offset_s=3.0)
    net2.add_m2(2, status_offset_s=7.0)
    net2.run_until(4.0)
    net2.m2[1].request_dock(net2.now)
    net2.m1.assign(1, 1, RA, DEC, net2.now)
    net2.run_until(100.0)
    for nx, off in ((1, 3.0), (2, 7.0)):
        t = [r.t_send for r in net2.sent("Status", src=f"M2-{nx}")]
        assert t[0] == off and all(abs(b - a - 10.0) < 1e-9 for a, b in zip(t, t[1:]))
        assert len(t) == int((100.0 - off) // 10) + 1
    s1, s2 = net2.m1.m2_status[1], net2.m1.m2_status[2]
    assert s1.state == 5 and s1.quality == 100 and 0 < s1.since_sync_s < 100
    assert s2.state == 3 and s2.quality == 0 and s2.since_sync_s == 0xFFFF
    assert net2.m1.m2_seen[1] > 90.0


# --- Watchdog ---

def _red_guiando():
    net = red()
    net.run_until(1.0)
    net.m2[1].request_dock(net.now)
    net.m1.assign(1, 5, RA, DEC, net.now)
    net.run_until(34.0)                                  # el HB de t=30 ya llego
    return net


def test_watchdog_exacto_a_30_s_del_ultimo_hb_y_es_error_leve():
    net = _red_guiando()
    c = net.m2[1]
    t_rx = c._last_hb_rx
    assert 30.0 < t_rx < 30.02
    net.kill_m1()
    assert not c.base_lost(t_rx + 29.999) and c.errors(t_rx + 29.999) == []
    assert c.base_lost(t_rx + 30.0)
    assert c.errors(t_rx + 30.0) == [(Level.LEVE, "sin_base")]
    net.run_until(t_rx + 30.5)
    assert c.base_lost_events == 1


def test_sin_base_el_m2_sigue_guiando_con_su_propio_reloj_y_se_recupera():
    net = _red_guiando()
    c = net.m2[1]
    net.kill_m1()
    net.run_until(60.0)
    ticks_60 = c.guide_ticks
    objetivo = c.target
    net.run_until(100.0)
    assert c.base_lost(100.0) and c.guiding()
    assert c.guide_ticks - ticks_60 == 40                # sigue guiando 1 paso/s
    assert c.target == objetivo
    assert abs(c.utc_ms_estimate(100.0) - (net.m1.cfg.utc0_ms + 100_000)) <= 20
    net.revive_m1()
    net.run_until(100.1)
    assert not c.base_lost(100.1)
    assert c.base_lost_events == 1


def test_m2_que_enciende_sin_base_declara_sin_base_a_los_30_s_de_encendido():
    net = red(start_s=5.0)
    net.kill_m1()
    net.run_until(34.99)
    assert not net.m2[1].base_lost(34.99)
    net.run_until(35.0)
    assert net.m2[1].base_lost(35.0) and net.m2[1].base_lost_events == 1


def test_dos_hb_perdidos_no_disparan_el_watchdog_tres_si():
    net = red()
    net.drop_filter = lambda t, s, d, k: isinstance(k, p.Heartbeat) and 10.0 <= t <= 20.0   # se pierden t=10 y t=20
    net.run_until(30.5)
    assert net.m2[1].base_lost_events == 0
    net.drop_filter = lambda t, s, d, k: isinstance(k, p.Heartbeat) and 10.0 <= t <= 30.0   # t=10, 20 y 30
    net2 = red()
    net2.drop_filter = net.drop_filter
    net2.run_until(60.0)
    assert net2.m2[1].base_lost_events == 1


# --- Recepcion de HB: orden, duplicados, base ajena ---

def _m2_directo():
    enviados = []
    return M2Core(M2Config(nx=1), enviados.append), enviados


def _hb(seq, base=1, asg=()):
    return p.encode(p.Heartbeat(base, seq, 1000 * seq, 0, 0, 0, tuple(asg)))


def test_hb_atrasado_o_repetido_no_pisa_al_mas_nuevo():
    m2, _ = _m2_directo()
    a, b = p.Assignment(1, 1, 0, 0), p.Assignment(1, 2, 0, 0)
    m2.on_packet(_hb(5, asg=[a]), 1.0)
    m2.on_packet(_hb(6, asg=[b]), 2.0)
    m2.on_packet(_hb(5, asg=[a]), 3.0)                   # llega tarde
    m2.on_packet(_hb(6, asg=[a]), 3.0)                   # repetido
    assert m2.target == b and m2.stale_hb == 2


def test_hb_atrasado_no_reinicia_el_watchdog():
    m2, _ = _m2_directo()
    m2.on_packet(_hb(5), 1.0)
    m2.on_packet(_hb(4), 25.0)
    assert m2.base_lost(31.0)


def test_secuencia_con_vuelta_de_65535_a_0():
    m2, _ = _m2_directo()
    m2.on_packet(_hb(65535, asg=[p.Assignment(1, 1, 0, 0)]), 1.0)
    m2.on_packet(_hb(0, asg=[p.Assignment(1, 2, 0, 0)]), 2.0)
    assert m2.target.target_id == 2 and m2.stale_hb == 0


def test_m1_reiniciado_con_secuencia_en_cero_se_acepta():
    m2, _ = _m2_directo()
    m2.on_packet(_hb(500), 1.0)
    m2.on_packet(_hb(0, asg=[p.Assignment(1, 7, 0, 0)]), 11.0)
    assert m2.target.target_id == 7 and m2.stale_hb == 0


def test_hb_de_otra_base_se_ignora_mientras_la_actual_viva_y_se_acepta_si_se_perdio():
    m2, _ = _m2_directo()
    m2.on_packet(_hb(1, base=1), 1.0)
    m2.on_packet(_hb(1, base=2, asg=[p.Assignment(1, 9, 0, 0)]), 5.0)
    assert m2.foreign_hb == 1 and m2.target is None and m2.base_id == 1
    m2.on_packet(_hb(1, base=2, asg=[p.Assignment(1, 9, 0, 0)]), 40.0)   # la base 1 callo hace 39 s
    assert m2.base_id == 2 and m2.target.target_id == 9


def test_m2_apagado_no_oye_antes_de_encender():
    m2 = M2Core(M2Config(nx=1, start_s=10.0), lambda b: None)
    m2.on_packet(_hb(1), 5.0)
    assert m2.last_hb is None
    m2.on_packet(_hb(1), 10.0)
    assert m2.last_hb is not None


# --- Paquetes corruptos ---

@pytest.mark.parametrize("basura,clase", [
    (b"", "TruncatedPacket"),
    (b"\x07\x01\x00\x00", "UnknownType"),
    (bytes([1, 9]) + bytes(22), "VersionMismatch"),
    (p.encode(p.Ack(1, 1)) + b"\x00", "TrailingBytes"),
    (bytes([3, 1]) + bytes(28), "InvalidField"),        # DOCK_REF con cuaternion nulo
])
def test_paquetes_invalidos_se_cuentan_y_no_cambian_el_estado(basura, clase):
    net = red()
    net.run_until(1.0)
    estado_m2 = (net.m2[1].target, net.m2[1].synced, net.m2[1].dock_state)
    net.inject(1, basura)
    net.inject(None, basura)
    net.run_until(2.0)
    assert net.m2[1].rejected.get(clase) == 1
    assert net.m1.rejected.get(clase) == 1
    assert (net.m2[1].target, net.m2[1].synced, net.m2[1].dock_state) == estado_m2
    assert net.m1.docks == {} and net.m1.solves == 0


def test_hb_de_otra_version_no_cambia_la_base_del_m2():
    net = red()
    malo = bytearray(_hb(3))
    malo[1] = 2
    net.inject(1, bytes(malo))
    net.run_until(0.0001)
    assert net.m2[1].last_hb is None and net.m2[1].base_id is None
    assert net.m2[1].rejected["VersionMismatch"] == 1


def test_paquete_en_la_direccion_equivocada_se_rechaza():
    net = red()
    net.run_until(1.0)
    net.inject(None, _hb(1))                             # un HB al M1
    net.inject(1, p.encode(p.DockReq(1, 1)))             # un DOCK_REQ a un M2
    net.inject(1, p.encode(p.Assign(2, 1, 0, 0)))        # ASSIGN de otro M2
    net.run_until(2.0)
    assert net.m1.rejected["unexpected_Heartbeat"] == 1
    assert net.m2[1].rejected["unexpected_DockReq"] == 1
    assert net.m2[1].rejected["misrouted"] == 1 and net.m2[1].target is None


# --- Determinismo ---

def _firma(net):
    return [(round(r.t_send, 9), r.src, r.dst, r.kind, r.delivered) for r in net.log]


def _corrida(seed):
    net = red(n=4, seed=seed, impair=Impairment(loss=0.2, reorder=0.3, dup=0.1))
    net.run_until(1.0)
    for c in net.m2.values():
        c.request_dock(net.now)
    net.run_until(60.0)
    return net


def test_misma_semilla_misma_historia_y_otra_semilla_otra():
    assert _firma(_corrida(5)) == _firma(_corrida(5))
    assert _firma(_corrida(5)) != _firma(_corrida(6))


# --- M1 en aislado: casos que la red virtual rara vez provoca ---

class _M1Directo:
    def __init__(self, **cfg):
        from euler_sim.m1 import M1Core
        self.enviados = []
        self.core = M1Core(M1Config(**cfg), lambda dst, data: self.enviados.append((dst, p.decode(data))))

    def tipos(self, cls):
        return [pk for _, pk in self.enviados if isinstance(pk, cls)]


def _req(nx, seq):
    return p.encode(p.DockReq(nx, seq))


def test_dock_req_viejo_que_llega_tarde_no_pisa_al_nuevo():
    m = _M1Directo()
    m.core.tick(0.0)
    m.core.on_packet(_req(1, 5), 0.1)
    m.core.on_packet(_req(1, 6), 0.2)                    # el M2 pidio otro acople
    m.core.on_packet(_req(1, 5), 0.3)                    # el viejo llega tarde
    assert m.core.docks[1].seq == 6
    assert m.core.rejected["old_dock_req"] == 1


def test_resultado_de_un_solve_cuyo_acople_fue_reemplazado_se_descarta():
    m = _M1Directo(solve_time_s=2.0)
    m.core.on_packet(_req(1, 1), 0.0)
    m.core.tick(0.0)                                     # empieza el solve de seq 1
    m.core.on_packet(_req(1, 2), 0.5)                    # el M2 pide otro antes de que termine
    for t in (2.0, 4.0):
        m.core.tick(t)
    assert [r.seq for r in m.tipos(p.DockRef)] == [2]    # jamas se mando la referencia de seq 1
    assert m.core.solves == 2


def test_acople_agotado_se_reinicia_si_el_m2_repite_la_misma_peticion():
    m = _M1Directo(solve_time_s=1.0, ref_max_tries=2, ref_retry_s=1.0)
    m.core.on_packet(_req(1, 9), 0.0)
    for t in (0.0, 1.0, 2.0, 3.0):
        m.core.tick(t)
    assert m.core.dock_phase(1) is DockPhase.FAILED
    n_ref = len(m.tipos(p.DockRef))
    m.core.on_packet(_req(1, 9), 5.0)                    # el M2 sigue esperando: reintenta
    m.core.tick(5.0)
    m.core.tick(6.0)
    assert m.core.dock_phase(1) is DockPhase.REF_SENT
    assert len(m.tipos(p.DockRef)) == n_ref + 1
    assert m.core.solves == 2


def test_reloj_que_salta_no_provoca_una_rafaga_de_hb():
    m = _M1Directo()
    m.core.tick(0.0)
    antes = len(m.tipos(p.Heartbeat))
    m.core.tick(100.0)                                   # el proceso estuvo detenido 100 s
    assert len(m.tipos(p.Heartbeat)) == antes + 1
    assert m.core.next_deadline() == 110.0


def test_m1_guarda_el_status_de_cada_m2():
    m = _M1Directo()
    st = p.Status(3, 80, 5, 12, 0, 100)
    m.core.on_packet(p.encode(st), 7.0)
    assert m.core.m2_status[3] == st and m.core.m2_seen[3] == 7.0


def test_el_m1_ignora_un_ack_de_otra_secuencia():
    m = _M1Directo(solve_time_s=1.0, ref_max_tries=100)
    m.core.on_packet(_req(1, 9), 0.0)
    m.core.tick(0.0)
    m.core.tick(1.0)
    assert m.core.dock_phase(1) is DockPhase.REF_SENT
    m.core.on_packet(p.encode(p.Ack(1, 8)), 1.1)
    assert m.core.dock_phase(1) is DockPhase.REF_SENT
    m.core.on_packet(p.encode(p.Ack(1, 9)), 1.2)
    assert m.core.dock_phase(1) is DockPhase.DONE


def test_el_m2_ignora_un_ack_de_otra_secuencia():
    enviados = []
    m2 = M2Core(M2Config(nx=1, dock_seq0=40), enviados.append)
    m2.request_dock(0.0)
    m2.on_packet(p.encode(p.Ack(1, 99)), 0.1)
    assert m2.dock_state is DockState.WAIT_ACK
    m2.on_packet(p.encode(p.Ack(1, 41)), 0.2)
    assert m2.dock_state is DockState.WAIT_REF


def test_status_durante_el_acople_reporta_estado_acople():
    net = VirtualNet(seed=1)
    net.add_m2(1, status_offset_s=5.0)
    net.run_until(4.5)
    net.m2[1].request_dock(net.now)
    net.run_until(5.1)                                   # el STATUS de t=5 sale con el acople a medias (solve de 2 s)
    assert net.m1.m2_status[1].state == 2
    net.run_until(15.1)
    assert net.m1.m2_status[1].state == 4                # sincronizado y sin objetivo


def test_con_el_m1_apagado_ni_envia_ni_recibe():
    net = red(n=1)
    net.run_until(11.0)
    net.kill_m1()
    rx0, tx0 = dict(net.m1.rx), sum(net.m1.tx.values())
    net.m1.assign(1, 5, RA, DEC, net.now)               # la app insiste mientras esta apagado
    net.run_until(60.0)
    assert net.m1.rx == rx0                              # los STATUS del M2 no llegan a nadie
    assert [r for r in net.log if r.src == "M1" and r.t_send >= 11.0] == []
    assert sum(net.m1.tx.values()) == tx0 + 1            # solo el intento que cuenta el propio M1
