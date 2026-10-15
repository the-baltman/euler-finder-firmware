"""Reloj escalable y deterioro de la red."""
import random

import pytest

from euler_sim.clock import ScaledClock
from euler_sim.impair import Impairment


class RelojFalso:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def test_reloj_escalado_multiplica_el_tiempo_real():
    f = RelojFalso()
    c = ScaledClock(50.0, time_fn=f)
    assert c.now() == 0.0
    f.t += 0.2
    assert c.now() == pytest.approx(10.0)                 # 0.2 s reales = un HB
    assert c.to_wall(10.0) == pytest.approx(0.2)
    c.reset()
    assert c.now() == 0.0


def test_reloj_rechaza_escala_no_positiva():
    with pytest.raises(ValueError):
        ScaledClock(0)
    with pytest.raises(ValueError):
        ScaledClock(-1)


@pytest.mark.parametrize("campo", ["loss", "reorder", "dup"])
@pytest.mark.parametrize("valor", [-0.1, 1.1])
def test_deterioro_rechaza_probabilidades_fuera_de_rango(campo, valor):
    with pytest.raises(ValueError):
        Impairment(**{campo: valor})


def test_deterioro_rechaza_tiempos_negativos():
    with pytest.raises(ValueError):
        Impairment(latency_s=-1)


def test_sin_deterioro_nunca_pierde_y_siempre_entrega_una_copia():
    rng = random.Random(0)
    imp = Impairment()
    for _ in range(1000):
        plan = imp.plan(rng)
        assert len(plan) == 1 and 0.005 <= plan[0] <= 0.007


def test_perdida_total_y_perdida_nula():
    rng = random.Random(0)
    assert all(Impairment(loss=1.0).plan(rng) == [] for _ in range(100))
    assert all(len(Impairment(loss=0.0).plan(rng)) == 1 for _ in range(100))


@pytest.mark.parametrize("p", [0.1, 0.3, 0.5])
def test_la_tasa_de_perdida_medida_coincide_con_la_configurada(p):
    rng = random.Random(7)
    imp = Impairment(loss=p)
    n = 20000
    perdidos = sum(1 for _ in range(n) if not imp.plan(rng))
    assert abs(perdidos / n - p) < 0.015


def test_el_desorden_existe_y_su_tasa_es_la_configurada():
    rng = random.Random(8)
    imp = Impairment(reorder=0.25, reorder_max_s=15.0)
    n = 20000
    tarde = sum(1 for _ in range(n) if imp.plan(rng)[0] > 0.1)
    assert abs(tarde / n - 0.25) < 0.015
    # y con ese retraso dos paquetes consecutivos (10 s de separacion) pueden cruzarse
    cruces = 0
    for _ in range(2000):
        a, b = imp.plan(rng)[0], 10.0 + imp.plan(rng)[0]
        cruces += b < a
    assert cruces > 0


def test_la_tasa_de_duplicados_es_la_configurada():
    rng = random.Random(9)
    imp = Impairment(dup=0.2)
    n = 20000
    dobles = sum(1 for _ in range(n) if len(imp.plan(rng)) == 2)
    assert abs(dobles / n - 0.2) < 0.015


def test_el_plan_es_reproducible_con_la_misma_semilla():
    imp = Impairment(loss=0.3, reorder=0.3, dup=0.3)
    ra, rb, rc = random.Random(5), random.Random(5), random.Random(6)
    sa = [imp.plan(ra) for _ in range(200)]
    sb = [imp.plan(rb) for _ in range(200)]
    sc = [imp.plan(rc) for _ in range(200)]
    assert sa == sb
    assert sa != sc


def test_la_latencia_base_se_respeta():
    rng = random.Random(1)
    imp = Impairment(latency_s=0.05, jitter_s=0.0)
    assert all(imp.plan(rng) == [0.05] for _ in range(50))
