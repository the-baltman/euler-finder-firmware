"""Escenario completo (10 M2) sobre la red virtual y sus metricas. Lo usan el barrido de pruebas y el CLI.

Cronologia (segundos simulados):
  0-5     los M2 encienden escalonados (hora aleatoria por semilla)
  20      los 10 M2 piden acople a la vez (el M1 los resuelve en fila: tiene una sola camara)
  43.7    el M1 asigna un objetivo a cada M2 (ASSIGN inmediato)
  103.7   reasigna a los pares
  133.7   quita la asignacion del M2 1 (solo el HB se entera)
  T_FIN   fin
"""
from __future__ import annotations

import random
from typing import Dict, List, Optional

import euler_proto as p
from .impair import Impairment
from .m1 import M1Config
from .virtual import VirtualNet

# Fuera de multiplos de 10 s a proposito: un ASSIGN justo al salir un HB cae en la carrera H3 (ver ESPECIFICACION.md).
T_DOCK, T_ASSIGN, T_REASSIGN, T_CLEAR, T_FIN = 20.0, 43.7, 103.7, 133.7, 240.0
POLL_S = 0.25   # resolucion con que se mide cuando converge una asignacion


def _target_for(nx: int, version: int):
    # Objetivo sintetico distinto por M2 y por version. RA > 214.7 deg a proposito (hallazgo H1).
    return 1000 * version + nx, ((nx * 37 + version * 11) % 360) * p.E7, (((nx * 13) % 120) - 60) * p.E7


def run_full(seed: int, loss: float, reorder: float = 0.0, dup: float = 0.0, n_m2: int = 10,
             t_fin: float = T_FIN, reorder_max_s: float = 3.0, hb_after_assign: bool = False) -> Dict[str, object]:
    rng = random.Random(seed * 7919 + 1)
    net = VirtualNet(seed=seed, impair=Impairment(loss=loss, reorder=reorder, dup=dup, reorder_max_s=reorder_max_s),
                     m1_cfg=M1Config(hb_after_assign=hb_after_assign))
    for nx in range(1, n_m2 + 1):
        net.add_m2(nx, start_s=rng.uniform(0.0, 5.0), status_offset_s=rng.uniform(0.0, 10.0),
                   dock_seq0=rng.randint(0, 65535))

    expected: Dict[int, Optional[tuple]] = {nx: None for nx in net.m2}
    events = []                         # (t, nx) cada vez que cambia lo esperado de un M2
    plan = [(T_DOCK, "dock"), (T_ASSIGN, "assign"), (T_REASSIGN, "reassign"), (T_CLEAR, "clear")]
    done = set()
    history: Dict[int, List[tuple]] = {nx: [] for nx in net.m2}   # (t, target) muestreado

    t = 0.0
    while t < t_fin:
        t = round(t + POLL_S, 6)
        net.run_until(t)
        for when, what in plan:
            if what not in done and net.now >= when:
                done.add(what)
                if what == "dock":
                    for core in net.m2.values():
                        core.request_dock(net.now)
                elif what in ("assign", "reassign"):
                    for nx in net.m2:
                        if what == "reassign" and nx % 2:
                            continue
                        tid, ra, dec = _target_for(nx, 1 if what == "assign" else 2)
                        net.m1.assign(nx, tid, ra, dec, net.now)
                        expected[nx] = (tid, ra, dec)
                        events.append((net.now, nx, expected[nx], what))
                elif what == "clear":
                    net.m1.clear_assignment(1)
                    expected[1] = None
                    events.append((net.now, 1, None, what))
        for nx, core in net.m2.items():
            tg = core.target
            history[nx].append((net.now, None if tg is None else (tg.target_id, tg.ra_e7, tg.dec_e7)))

    # Tiempo de asentamiento: desde el evento hasta la ultima muestra con un valor distinto del esperado
    # (dentro de la ventana hasta el siguiente evento del mismo M2), mas un paso.
    settle = {"assign": 0.0, "clear": 0.0}
    unsettled = 0
    by_nx: Dict[int, List[tuple]] = {}
    for (te, nx, exp, what) in events:
        by_nx.setdefault(nx, []).append((te, exp, what))
    for nx, evs in by_nx.items():
        for i, (te, exp, what) in enumerate(evs):
            end = evs[i + 1][0] if i + 1 < len(evs) else t_fin + 1
            last_bad = None
            for (ts, tg) in history[nx]:
                if te <= ts < end and tg != exp:
                    last_bad = ts
            if last_bad is None:
                s_t = 0.0
            elif last_bad >= end - POLL_S * 1.5:
                unsettled += 1
                s_t = end - te
            else:
                s_t = last_bad - te + POLL_S
            kind = "clear" if what == "clear" else "assign"
            settle[kind] = max(settle[kind], s_t)

    docks_done = [c for c in net.m2.values() if c.dock_state.name == "DONE"]
    dock_times = [c.dock_finished - c.dock_started for c in docks_done]
    m1_done = sum(1 for nx in net.m2 if net.m1.dock_phase(nx) is not None and net.m1.dock_phase(nx).name == "DONE")
    final_ok = all(
        (None if c.target is None else (c.target.target_id, c.target.ra_e7, c.target.dec_e7)) == expected[nx]
        for nx, c in net.m2.items())
    return {
        "seed": seed, "n_events": len(events), "loss": loss, "reorder": reorder, "reorder_max_s": reorder_max_s,
        "docks_done": len(docks_done), "n_m2": n_m2,
        "dock_time_max_s": max(dock_times) if dock_times else None,
        "m1_docks_done": m1_done,
        "ref_applied_max": max(c.ref_applied for c in net.m2.values()),
        "settle_assign_max_s": settle["assign"], "settle_clear_max_s": settle["clear"], "unsettled": unsettled, "final_ok": final_ok,
        "base_lost_events": sum(c.base_lost_events for c in net.m2.values()),
        "stale_hb": sum(c.stale_hb for c in net.m2.values()),
        "hb_sent": net.m1.tx.get("Heartbeat", 0),
        "hb_accepted_min": min(c.rx.get("Heartbeat", 0) - c.stale_hb for c in net.m2.values()),
        "net": net,
    }



def sweep(losses, seeds, **kw) -> List[Dict[str, object]]:
    """Corre run_full por cada (perdida, semilla) y resume por perdida. El maximo publicado es el de este barrido."""
    rows = []
    for loss in losses:
        rs = []
        for seed in seeds:
            r = run_full(seed, loss, **kw)
            r.pop("net")
            rs.append(r)
        times = [r["dock_time_max_s"] for r in rs if r["dock_time_max_s"] is not None]
        rows.append({
            "loss": loss, "n_seeds": len(rs),
            "docks_done_min": min(r["docks_done"] for r in rs),
            "docks_done_mean": sum(r["docks_done"] for r in rs) / len(rs),
            "m1_docks_done_min": min(r["m1_docks_done"] for r in rs),
            "m1_done_exceeds_m2": any(r["m1_docks_done"] > r["docks_done"] for r in rs),
            "dock_time_max_s": max(times) if times else None,
            "settle_assign_max_s": max(r["settle_assign_max_s"] for r in rs),
            "settle_clear_max_s": max(r["settle_clear_max_s"] for r in rs),
            "unsettled_total": sum(r["unsettled"] for r in rs),
            "final_ok": sum(1 for r in rs if r["final_ok"]),
            "ref_applied_max": max(r["ref_applied_max"] for r in rs),
            "base_lost_mean": sum(r["base_lost_events"] for r in rs) / len(rs),
        })
    return rows


def format_sweep(rows: List[Dict[str, object]]) -> str:
    head = ("perdida  semillas  acoples_min  acoples_prom  acople_max_s  asignacion_max_s  borrado_max_s  "
            "sin_asentar  final_ok  ref_aplicada_max  sin_base_prom")
    out = [head]
    for r in rows:
        out.append("%7.2f  %8d  %11d  %12.1f  %12s  %16.2f  %13.2f  %11d  %8d  %16d  %13.1f" % (
            r["loss"], r["n_seeds"], r["docks_done_min"], r["docks_done_mean"],
            "-" if r["dock_time_max_s"] is None else "%.1f" % r["dock_time_max_s"],
            r["settle_assign_max_s"], r["settle_clear_max_s"], r["unsettled_total"], r["final_ok"],
            r["ref_applied_max"], r["base_lost_mean"]))
    return "\n".join(out)
