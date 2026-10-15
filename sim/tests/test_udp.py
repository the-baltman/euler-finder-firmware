"""Los mismos nodos sobre sockets UDP reales en localhost, con reloj escalado.

No son deterministas (planificador del SO), asi que los topes son holgados. Escala 25: un HB de 10 s
sale cada 0.4 s reales; 100 s simulados cuestan 4 s.
"""
import time

import pytest

import euler_proto as p
from euler_sim.impair import Impairment
from euler_sim.m1 import DockPhase, M1Config
from euler_sim.m2 import DockState
from euler_sim.udpnet import UdpNet

pytestmark = pytest.mark.udp
ESCALA = 25.0
RA, DEC = 250 * p.E7, -30 * p.E7


def test_el_reloj_escalado_acorta_el_tiempo_real():
    with UdpNet(scale=50.0) as net:
        t0 = time.monotonic()
        net.run_for(100.0)
        real = time.monotonic() - t0
    assert 1.5 < real < 3.5                               # 100 s simulados / 50 = 2 s


def test_hb_assign_y_acople_sobre_udp_real_sin_perdida():
    net = UdpNet(scale=ESCALA, seed=1)
    for nx in (1, 2, 3):
        net.add_m2(nx)
    with net:
        net.run_for(1.0)
        net.m2_do(1, lambda c: c.request_dock(net.now()))
        net.m1_do(lambda m: m.assign(2, 7, RA, DEC, net.now()))
        net.run_for(60.0)
        hbs = [c.rx.get("Heartbeat", 0) for c in net.m2.values()]
    assert all(5 <= n <= 8 for n in hbs), hbs             # 6-7 HB en 60 s
    assert net.m2[1].dock_state is DockState.DONE and net.m2[1].synced
    assert net.m1.dock_phase(1) is DockPhase.DONE
    assert net.m2[2].target == p.Assignment(2, 7, RA, DEC)
    assert all(c.base_lost_events == 0 for c in net.m2.values())


def test_diez_m2_a_la_vez_con_perdida_sobre_udp_real():
    net = UdpNet(scale=ESCALA, seed=3, impair=Impairment(loss=0.1, reorder=0.2))
    for nx in range(1, 11):
        net.add_m2(nx)
    with net:
        net.run_for(5.0)
        for nx in range(1, 11):
            net.m2_do(nx, lambda c: c.request_dock(net.now()))
        net.run_for(45.0)
        for nx in range(1, 11):
            net.m1_do(lambda m, nx=nx: m.assign(nx, nx, RA, DEC, net.now()))
        net.run_for(75.0)                                 # margen para HB perdidos
    assert sum(c.dock_state is DockState.DONE for c in net.m2.values()) >= 9
    assert sum(c.target is not None for c in net.m2.values()) >= 9
    assert all(c.ref_applied <= 1 for c in net.m2.values())
    assert len(net.m1.m2_status) >= 9                    # llegaron STATUS de casi todos


def test_sin_base_sobre_udp_real_sigue_guiando_y_se_recupera():
    net = UdpNet(scale=ESCALA, seed=4)
    net.add_m2(1)
    with net:
        net.run_for(1.0)
        net.m2_do(1, lambda c: c.request_dock(net.now()))
        net.m1_do(lambda m: m.assign(1, 5, RA, DEC, net.now()))
        net.run_for(15.0)
        assert net.m2[1].guiding()
        net.kill_m1()
        net.run_for(45.0)                                 # > 30 s sin HB
        assert net.m2[1].base_lost(net.now())
        assert net.m2[1].guiding()
        ticks = net.m2[1].guide_ticks
        net.run_for(10.0)
        assert net.m2[1].guide_ticks > ticks + 5
        net.revive_m1()
        net.run_for(12.0)
        assert not net.m2[1].base_lost(net.now())
        assert net.m2[1].base_lost_events == 1


def test_con_perdida_total_nada_llega_y_se_declara_sin_base():
    net = UdpNet(scale=ESCALA, seed=5, impair=Impairment(loss=1.0))
    net.add_m2(1)
    with net:
        net.run_for(40.0)
    assert net.m2[1].rx.get("Heartbeat", 0) == 0
    assert net.m2[1].base_lost_events == 1


def test_m1_apagado_sobre_udp_no_procesa_lo_que_le_llega():
    net = UdpNet(scale=ESCALA, seed=6)
    net.add_m2(1, status_offset_s=0.5)
    with net:
        net.run_for(12.0)
        net.kill_m1()
        antes = net.m1.rx.get("Status", 0)
        net.run_for(45.0)                                 # el M2 sigue mandando STATUS cada 10 s
        despues = net.m1.rx.get("Status", 0)
    assert antes >= 1 and despues == antes
