"""Linea de comandos del simulador.

  python -m euler_sim sweep [--seeds 24] [--reorder 0.2] [--reorder-max 3]   barrido de perdida (red virtual)
  python -m euler_sim udp   [--m2 10] [--loss 0.1] [--scale 25] [--duration 120]   10 M2 sobre UDP real
Ejecutar desde sim/ (o con PYTHONPATH=sim).
"""
from __future__ import annotations

import argparse

import euler_proto as p
from .impair import Impairment
from .scenarios import format_sweep, sweep


def _udp(a) -> None:
    from .udpnet import UdpNet

    net = UdpNet(scale=a.scale, seed=a.seed,
                 impair=Impairment(loss=a.loss, reorder=a.reorder, reorder_max_s=a.reorder_max, dup=a.dup))
    for nx in range(1, a.m2 + 1):
        net.add_m2(nx, status_offset_s=nx * 0.7)
    ra, dec = 250 * p.E7, -30 * p.E7
    with net:
        net.run_for(5.0)
        for nx in range(1, a.m2 + 1):
            net.m2_do(nx, lambda c: c.request_dock(net.now()))
        net.run_for(45.0)
        for nx in range(1, a.m2 + 1):
            net.m1_do(lambda m, nx=nx: m.assign(nx, nx, ra, dec, net.now()))
        net.run_until(a.duration)
        ahora = net.now()
        print(f"t_sim={ahora:.1f} s  escala={a.scale}  perdida={a.loss}  desorden={a.reorder}")
        for nx, c in net.m2.items():
            print(f"M2-{nx:<2d} acople={c.dock_state.name:<15s} objetivo={'si' if c.target else 'no':<2s} "
                  f"sin_base={'si' if c.base_lost(ahora) else 'no':<2s} HB_rx={c.rx.get('Heartbeat', 0):<3d} "
                  f"guia_ticks={c.guide_ticks}")
        print("M1: tx", dict(net.m1.tx), "rx", dict(net.m1.rx), "solves", net.m1.solves)


def main() -> None:
    ap = argparse.ArgumentParser(prog="euler_sim")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sweep")
    s.add_argument("--seeds", type=int, default=24)
    s.add_argument("--losses", type=float, nargs="+", default=[0.0, 0.05, 0.1, 0.2, 0.3, 0.5])
    s.add_argument("--reorder", type=float, default=0.2)
    s.add_argument("--reorder-max", type=float, default=3.0)
    s.add_argument("--dup", type=float, default=0.0)
    s.add_argument("--sin-hb-extra", action="store_true", help="referencia: sin el HB extra tras cada cambio (H3)")
    u = sub.add_parser("udp")
    u.add_argument("--m2", type=int, default=10)
    u.add_argument("--loss", type=float, default=0.1)
    u.add_argument("--reorder", type=float, default=0.2)
    u.add_argument("--reorder-max", type=float, default=3.0)
    u.add_argument("--dup", type=float, default=0.0)
    u.add_argument("--scale", type=float, default=25.0)
    u.add_argument("--duration", type=float, default=120.0)
    u.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    if a.cmd == "sweep":
        print(f"{a.seeds} semillas por nivel; reorder={a.reorder} (max {a.reorder_max} s); dup={a.dup}; "
              f"hb_extra={not a.sin_hb_extra}")
        print(format_sweep(sweep(a.losses, range(a.seeds), reorder=a.reorder, dup=a.dup,
                                 reorder_max_s=a.reorder_max, hb_after_assign=not a.sin_hb_extra)))
    else:
        _udp(a)


if __name__ == "__main__":
    main()
