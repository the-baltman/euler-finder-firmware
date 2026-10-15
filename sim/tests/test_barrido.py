"""Barrido de perdida y desorden: 10 M2, 240 s simulados, 24 semillas por nivel.

Las cifras de los topes son [estimado: simulador]; salen de este barrido (maximo observado, redondeado
hacia arriba con margen) y no de mediciones en hardware.
"""
import pytest

from euler_sim.scenarios import POLL_S, sweep

SEMILLAS = range(24)                 # >= 16 semillas por nivel, exigido por el brief
N_SEMILLAS = len(SEMILLAS)


def _fila(rows, loss):
    return next(r for r in rows if r["loss"] == loss)


@pytest.fixture(scope="module")
def sin_perdida():
    return sweep([0.0], SEMILLAS)


@pytest.fixture(scope="module")
def red_tipica():
    # desorden hasta 3 s: entre los paquetes del acople
    return sweep([0.05, 0.1, 0.2, 0.3, 0.5], SEMILLAS, reorder=0.2)


@pytest.fixture(scope="module")
def desorden_extremo():
    # desorden hasta 15 s: dos HB consecutivos pueden cruzarse
    return sweep([0.0, 0.1, 0.2], SEMILLAS, reorder=0.2, reorder_max_s=15.0)


def test_el_barrido_usa_al_menos_16_semillas():
    assert N_SEMILLAS >= 16


def test_sin_perdida_todo_es_exacto(sin_perdida):
    r = _fila(sin_perdida, 0.0)
    assert r["n_seeds"] == N_SEMILLAS
    assert r["docks_done_min"] == 10 and r["m1_docks_done_min"] == 10
    assert 20.0 <= r["dock_time_max_s"] < 21.0           # 10 solves en fila x 2 s
    assert r["settle_assign_max_s"] <= 2 * POLL_S        # ASSIGN inmediato: se mide con paso de 0.25 s
    assert r["settle_clear_max_s"] <= 2 * POLL_S         # sin ASSIGN de borrado, pero el HB extra sale a los 50 ms
    assert r["unsettled_total"] == 0 and r["final_ok"] == N_SEMILLAS
    assert r["base_lost_mean"] == 0.0


@pytest.mark.parametrize("loss", [0.05, 0.1, 0.2, 0.3, 0.5])
def test_invariantes_que_valen_con_cualquier_perdida(red_tipica, desorden_extremo, loss):
    for rows in (red_tipica, desorden_extremo):
        try:
            r = _fila(rows, loss)
        except StopIteration:
            continue
        assert r["ref_applied_max"] <= 1                  # nunca se reaplica una referencia
        assert not r["m1_done_exceeds_m2"]               # el M1 jamas da por hecho un acople que el M2 no vio
        assert r["n_seeds"] == N_SEMILLAS


@pytest.mark.parametrize("loss,acoples_min,dock_max,asig_max,borrado_max", [
    (0.05, 10, 25.0, 6.0, 12.0),       # maximos del barrido de 24 semillas con HB extra: 21.0 / 2.75 / 8.5 s
    (0.1, 10, 26.0, 10.0, 10.0),       # 22.2 / 6.5 / 6.5 s
    (0.2, 10, 28.0, 10.0, 10.0),       # 23.0 / 6.5 / 6.5 s
])
def test_perdida_moderada_todos_acoplan_y_las_asignaciones_convergen(red_tipica, loss, acoples_min, dock_max,
                                                                       asig_max, borrado_max):
    r = _fila(red_tipica, loss)
    assert r["docks_done_min"] >= acoples_min
    assert r["dock_time_max_s"] <= dock_max
    assert r["settle_assign_max_s"] <= asig_max
    assert r["settle_clear_max_s"] <= borrado_max
    assert r["unsettled_total"] == 0
    assert r["final_ok"] == N_SEMILLAS


def test_perdida_alta_degrada_pero_converge(red_tipica):
    r30, r50 = _fila(red_tipica, 0.3), _fila(red_tipica, 0.5)
    assert r30["docks_done_min"] >= 8 and r30["final_ok"] == N_SEMILLAS
    assert r30["unsettled_total"] == 0
    assert r50["docks_done_min"] >= 5                    # con 50 % algunos M2 no alcanzan a acoplar: es lo esperado
    assert r50["final_ok"] >= N_SEMILLAS - 2


def test_la_perdida_se_nota_en_el_watchdog(red_tipica):
    medias = [_fila(red_tipica, l)["base_lost_mean"] for l in (0.05, 0.1, 0.2, 0.3, 0.5)]
    assert medias == sorted(medias) and medias[-1] > medias[0]


@pytest.mark.parametrize("loss", [0.0, 0.1, 0.2])
def test_desorden_extremo_los_hb_cruzados_no_dejan_estado_viejo(desorden_extremo, loss):
    r = _fila(desorden_extremo, loss)
    assert r["final_ok"] == N_SEMILLAS
    assert r["unsettled_total"] == 0
    assert r["docks_done_min"] >= 9


def test_la_perdida_se_ve_en_los_tiempos_de_asentamiento(red_tipica):
    # Cota inferior: evita que una metrica rota (siempre 0) pase las cotas superiores de arriba.
    assert _fila(red_tipica, 0.2)["settle_assign_max_s"] > 5.0
    assert _fila(red_tipica, 0.2)["settle_clear_max_s"] > 5.0
    assert _fila(red_tipica, 0.2)["dock_time_max_s"] > _fila(red_tipica, 0.05)["dock_time_max_s"] - 1e-9


def test_el_instrumento_puede_fallar_con_la_red_muerta():
    # Si todo se pierde, el barrido tiene que decirlo: asi se sabe que final_ok y acoples no son siempre "bien".
    from euler_sim.scenarios import run_full
    r = run_full(0, 1.0)
    assert r["docks_done"] == 0 and r["m1_docks_done"] == 0
    assert r["final_ok"] is False
    assert r["base_lost_events"] == 10                   # cada M2 declara "sin base" una vez
    r0 = run_full(0, 0.0)
    assert r0["n_events"] == 16                          # 10 asignaciones + 5 reasignaciones + 1 borrado
    assert r0["hb_sent"] == 28                           # 25 ordinarios (t=0,10,...,240) + 3 extra (asignar, reasignar, quitar)
    assert run_full(0, 0.0, hb_after_assign=False)["hb_sent"] == 25
