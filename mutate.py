#!/usr/bin/env python
"""Pruebas de mutacion: rompe el codigo a proposito y exige que las pruebas lo noten.

Uso:  python mutate.py            (todo)
      python mutate.py -k seq     (solo los mutantes cuyo id contiene 'seq')
      python mutate.py -j 4       (procesos en paralelo; por defecto 4)

Cada mutante se aplica a una COPIA temporal de protocolo/, sim/ y pytest.ini (el repo no se toca), se
corre pytest completo (sin -x, para saber QUE pruebas lo atrapan) y se espera al menos un fallo.
Sale con codigo 1 si sobrevive algun mutante, si alguno es invalido o si queda alguna funcion de prueba
que ningun mutante haya hecho fallar (una prueba que nunca falla no demuestra nada).

Las pruebas con sockets reales (-m udp) tardan ~13 s: solo corren para los mutantes marcados udp=True.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

# (id, archivo, texto original, texto mutado, n-esima aparicion (1 = la primera), corre pruebas udp)
M = []


def m(ident, archivo, viejo, nuevo, nth=1, udp=False):
    M.append((ident, archivo, viejo, nuevo, nth, udp))


P = "protocolo/euler_proto.py"
M1 = "sim/euler_sim/m1.py"
M2 = "sim/euler_sim/m2.py"
IM = "sim/euler_sim/impair.py"
CK = "sim/euler_sim/clock.py"
VN = "sim/euler_sim/virtual.py"
UN = "sim/euler_sim/udpnet.py"
SC = "sim/euler_sim/scenarios.py"

# --- Codec ---
m("proto-version", P, "PROTO_VERSION = 1 ", "PROTO_VERSION = 2 ")
m("proto-big-endian", P, '_HB_HEAD = struct.Struct("<BBHHQiiBB")', '_HB_HEAD = struct.Struct(">BBHHQiiBB")')
m("proto-ra-con-signo", P, '_HB_ASG = struct.Struct("<BHIi")', '_HB_ASG = struct.Struct("<BHii")')
m("proto-sin-bytes-de-mas", P, "    if len(data) > size:\n        raise TrailingBytes", "    if False:\n        raise TrailingBytes")
m("proto-truncado-flojo", P, "    if len(data) < size:\n        raise TruncatedPacket", "    if len(data) < size - 1:\n        raise TruncatedPacket")
m("proto-sin-version", P, "if data[1] != PROTO_VERSION:", "if False:")
m("proto-version-despues-del-largo", P, "        if len(data) < 2:\n            raise TruncatedPacket(\"HB sin byte de version\")\n", "")
m("proto-ra-360", P, '_need_int("ra_e7", self.ra_e7, 0, RA_MAX_E7 - 1)', '_need_int("ra_e7", self.ra_e7, 0, RA_MAX_E7)')
m("proto-dec-90", P, '_need_int("dec_e7", self.dec_e7, -DEC_MAX_E7, DEC_MAX_E7)', '_need_int("dec_e7", self.dec_e7, -DEC_MAX_E7, DEC_MAX_E7 + 1)')
m("proto-lat", P, '_need_int("lat_e7", self.lat_e7, -LAT_MAX_E7, LAT_MAX_E7)', '_need_int("lat_e7", self.lat_e7, -LAT_MAX_E7, LAT_MAX_E7 + 1)')
m("proto-lon", P, '_need_int("lon_e7", self.lon_e7, -LON_MAX_E7, LON_MAX_E7)', '_need_int("lon_e7", self.lon_e7, -LON_MAX_E7, LON_MAX_E7 + 1)')
m("proto-nx-cero", P, '_need_int("nx", v, 1, MAX_NX)', '_need_int("nx", v, 0, MAX_NX)')
m("proto-nx-once", P, '_need_int("nx", v, 1, MAX_NX)', '_need_int("nx", v, 1, MAX_NX + 1)')
m("proto-nx-repetido", P, "if len(set(nxs)) != len(nxs):", "if False:")
m("proto-banderas-hb", P, "if self.flags & ~HB_FLAGS_MASK:", "if False:")
m("proto-banderas-ref", P, "if self.flags & ~REF_FLAGS_MASK:", "if False:")
m("proto-norma-cuaternion", P, "if abs(norm - 1.0) > QUAT_NORM_TOL:", "if False:")
m("proto-nan-cuaternion", P, " or not math.isfinite(c)", "")
m("proto-bateria", P, '_need_int("battery_pct", self.battery_pct, 0, BATTERY_MAX)', '_need_int("battery_pct", self.battery_pct, 0, BATTERY_MAX + 1)')
m("proto-estado", P, "M2_STATE_MAX = 6 ", "M2_STATE_MAX = 7 ")
m("proto-calidad", P, "QUALITY_MAX = 100 ", "QUALITY_MAX = 101 ")
m("proto-since-sync", P, '_need_int("since_sync_s", self.since_sync_s, 0, 0xFFFF)', '_need_int("since_sync_s", self.since_sync_s, 0, 0xFFFE)')
m("proto-utc-hb", P, '_need_int("utc_ms", self.utc_ms, 0, 0xFFFFFFFFFFFFFFFF)', '_need_int("utc_ms", self.utc_ms, 0, 0xFFFFFFFFFFFFFFFE)')
m("proto-codigo-ack", P, "    ACK = 4", "    ACK = 7")
m("proto-hb-ignora-n", P, "_exact(data, HB_HEADER_SIZE + HB_ASSIGNMENT_SIZE * n)", "_exact(data, HB_HEADER_SIZE)")
m("proto-seq-borde-ventana", P, "d >= 0x10000 - SEQ_STALE_WINDOW", "d > 0x10000 - SEQ_STALE_WINDOW")
m("proto-seq-duplicado", P, "return d == 0 or d", "return d")
m("proto-seq-ventana-ancha", P, "SEQ_STALE_WINDOW = 8 ", "SEQ_STALE_WINDOW = 9 ")

# --- M1 ---
m("m1-periodo-hb", M1, "self._next_hb += self.cfg.hb_period_s", "self._next_hb += self.cfg.hb_period_s + 0.001")
m("m1-hb-sin-secuencia", M1, "self._hb_seq = (self._hb_seq + 1) & 0xFFFF", "pass")
m("m1-assign-sin-envio", M1, "        self._tx(nx, p.Assign(nx, target_id, ra_e7, dec_e7))", "        pass")
m("m1-req-repetido-vuelve-a-resolver", M1, "if activo and d.seq == req.seq:", "if False:")
m("m1-ref-sin-limite", M1, "if dock.tries >= self.cfg.ref_max_tries:", "if False:")
m("m1-ref-reintento-lento", M1, "dock.next_retx = now + self.cfg.ref_retry_s", "dock.next_retx = now + 2 * self.cfg.ref_retry_s")
m("m1-ack-no-cierra", M1, "if d is not None and d.seq == pkt.seq and d.phase is DockPhase.REF_SENT:", "if False:")
m("m1-ack-ignora-seq", M1, "if d is not None and d.seq == pkt.seq and d.phase is DockPhase.REF_SENT:", "if d is not None and d.phase is DockPhase.REF_SENT:")
m("m1-solves-en-paralelo", M1, "        if self._solving is None and self._queue:\n            self._start_solve(now)", "        if self._queue:\n            self._start_solve(now)")
m("m1-req-viejo-pisa", M1, "if activo and p.seq_delta(req.seq, d.seq) > 0x8000:", "if False:")
m("m1-solve-obsoleto-se-manda", M1, "        if self.docks.get(dock.nx) is not dock:\n            return", "        pass")
m("m1-rafaga-de-hb", M1, "            if self._next_hb <= now:                 # reloj saltado", "            while False:                 # reloj saltado")
m("m1-borrar-asignacion", M1, "self.assignments.pop(nx, None)", "pass")
m("m1-status-no-se-guarda", M1, "self.m2_status[pkt.nx] = pkt", "pass")
m("m1-hb-extra-no-sale", M1, "        if now >= self._extra_hb_at:\n            self._extra_hb_at = math.inf\n            self._send_hb(now)", "        if now >= self._extra_hb_at:\n            self._extra_hb_at = math.inf")
m("m1-req-sin-ack", M1, "        self._queue.append(nd)\n        self._tx(req.nx, p.Ack(req.nx, req.seq))", "        self._queue.append(nd)")
m("m1-hb-sin-asignaciones", M1, "asg = tuple(self.assignments[nx] for nx in sorted(self.assignments))", "asg = ()")

# --- M2 ---
m("m2-watchdog-2-hb", M2, "return self._last_hb_rx + self.cfg.watchdog_hb * self.cfg.hb_period_s", "return self._last_hb_rx + (self.cfg.watchdog_hb - 1) * self.cfg.hb_period_s")
m("m2-watchdog-borde", M2, "return now >= self._watchdog_deadline()", "return now > self._watchdog_deadline()")
m("m2-guia-depende-de-base", M2, "return self.synced and self.target is not None", "return self.synced and self.target is not None and not self._lost_flag")
m("m2-hb-viejo-pisa", M2, "if self._hb_seq is not None and p.seq_is_stale_or_dup(hb.seq, self._hb_seq):", "if False:")
m("m2-hb-no-refresca-watchdog", M2, "        self._last_hb_rx = now\n", "")
m("m2-base-ajena", M2, "        elif hb.base_id != self.base_id:", "        elif False:")
m("m2-base-perdida-no-se-reengancha", M2, "if self.base_id is None or self.base_lost(now):", "if self.base_id is None:")
m("m2-ack-ignora-seq", M2, "elif self.dock_state is DockState.WAIT_ACK and pkt.seq == self._dock_seq:", "elif self.dock_state is DockState.WAIT_ACK:")
m("m2-ref-repetido-no-reconfirma", M2, "elif ref.seq == self._last_done_seq:", "elif False:")
m("m2-ref-tardio-se-aplica", M2, "if waiting and ref.seq == self._dock_seq:", "if ref.seq == self._dock_seq:")
m("m2-sin-solucion-sincroniza", M2, "if ref.stars == 0:", "if False:")
m("m2-dock-sin-limite", M2, "if self._dock_tries >= self.cfg.req_max_tries:", "if False:")
m("m2-reintento-lento", M2, "self._dock_timer = now + self.cfg.req_retry_s", "self._dock_timer = now + 2 * self.cfg.req_retry_s")
m("m2-periodo-status", M2, "self._next_status += self.cfg.status_period_s\n", "self._next_status += self.cfg.status_period_s + 0.5\n")
m("m2-guia-doble", M2, "self.guide_ticks += 1", "self.guide_ticks += 2")
m("m2-assign-ajeno", M2, "            if pkt.nx != self.nx:\n                self._reject(\"misrouted\")\n            else:\n                # Un ASSIGN", "            if False:\n                self._reject(\"misrouted\")\n            else:\n                # Un ASSIGN")
m("m2-apagado-oye", M2, "        if now < self.cfg.start_s:\n            return                                   # apagado", "        if False:\n            return                                   # apagado")
m("m2-reloj-propio", M2, "return utc + int(round((now - t) * 1000.0))", "return utc")
m("m2-calidad", M2, "quality = 100 if self.synced else 0", "quality = 100")
m("m2-desde-sync", M2, "min(0xFFFE, int(now - self.sync_time))", "0")
m("m2-estado-acople", M2, "if self.dock_state in (DockState.WAIT_ACK, DockState.WAIT_REF):\n            state = ST_ACOPLE", "if False:\n            state = ST_ACOPLE")
m("m2-ref-timeout-no-reintenta", M2, "        else:\n            self._send_req(now)\n\n    def _on_ref", "        else:\n            self._dock_timer = math.inf\n\n    def _on_ref")
m("m2-acople-doble", M2, "if self.dock_state in (DockState.WAIT_ACK, DockState.WAIT_REF):\n            return False", "if False:\n            return False")
m("m2-ref-aplica-dos-veces", M2, "            self.ref_applied += 1", "            self.ref_applied += 2")
m("m2-status-sin-base", M2, "            if self.base_id is not None:\n                self._send_status(now)", "            if True:\n                self._send_status(now)")

# --- Red y reloj ---
m("imp-perdida-a-la-mitad", IM, "if rng.random() < self.loss:", "if rng.random() < self.loss / 2:")
m("imp-sin-desorden", IM, "d += rng.uniform(0.0, self.reorder_max_s)", "d += 0.0")
m("imp-sin-duplicados", IM, "if rng.random() < self.dup:", "if False:")
m("imp-sin-validar", IM, "if not 0.0 <= v <= 1.0:", "if False:")
m("imp-sin-validar-tiempos", IM, "if self.latency_s < 0 or self.jitter_s < 0 or self.reorder_max_s < 0:", "if False:")
m("reloj-escala-al-reves", CK, "return (self._time_fn() - self._t0) * self.scale", "return (self._time_fn() - self._t0) / self.scale")
m("reloj-a-pared-al-reves", CK, "return sim_s / self.scale", "return sim_s * self.scale")
m("reloj-sin-validar", CK, "if scale <= 0:", "if False:")
m("reloj-reset", CK, "        self._t0 = self._time_fn()\n\n    def now", "        pass\n\n    def now")
m("virtual-ignora-filtro", VN, "delays = [] if (self.drop_filter and self.drop_filter(self.now, src, dst, pkt)) else self.impair.plan(self.rng)", "delays = self.impair.plan(self.rng)")
m("virtual-m1-muerto-envia", VN, "        if not self.m1_up:\n            return\n        targets", "        targets")
m("virtual-m1-muerto-recibe", VN, "        if self.m1_up:\n            self.m1.on_packet(data, t)", "        self.m1.on_packet(data, t)")
m("virtual-broadcast-a-uno", VN, "targets = sorted(self.m2) if dst == BROADCAST else [dst]", "targets = sorted(self.m2)[:1] if dst == BROADCAST else [dst]")

# --- Escenario / barrido ---
m("barrido-borrado-no-ocurre", SC, "                    net.m1.clear_assignment(1, net.now)", "                    pass")
m("barrido-asentamiento-cero", SC, "s_t = last_bad - te + POLL_S", "s_t = 0.0")
m("barrido-final-ok-siempre", SC, "    final_ok = all(", "    final_ok = True or all(")
m("barrido-acoples-siempre-10", SC, "docks_done = [c for c in net.m2.values() if c.dock_state.name == \"DONE\"]", "docks_done = list(net.m2.values())")

# --- UDP real ---
m("udp-matar-m1-no-mata", UN, "            self._m1_node.alive = False", "            self._m1_node.alive = True", udp=True)
m("udp-envio-retrasado-no-sale", UN, "while self._delayed and self._delayed[0][0] <= now:", "while self._delayed and self._delayed[0][0] <= -1:", udp=True)
m("udp-broadcast-a-uno", UN, "targets = sorted(self._m2_addr) if dst == BROADCAST else [dst]", "targets = sorted(self._m2_addr)[:1] if dst == BROADCAST else [dst]", udp=True)
m("udp-deterioro-ignorado", UN, "for delay in self.net.impair.plan(self.rng):", "for delay in [0.0]:", udp=True)
m("udp-escala-ignorada", UN, "self.clock = ScaledClock(scale)", "self.clock = ScaledClock(1.0 if scale > 30 else scale)", udp=True)
m("udp-recibe-muerto", UN, "            with self.lock:\n                if self.alive:\n                    self.core.on_packet", "            with self.lock:\n                if True:\n                    self.core.on_packet", udp=True)
# --- Segunda ronda: lo que sobrevivio o nadie atrapaba ---
TV = "protocolo/tests/test_codec.py"
m("proto-vacio", P, '    if len(data) < 1:\n        raise TruncatedPacket("datagrama vacio")\n', "")
m("proto-encode-acepta-todo", P, '    raise TypeError(f"no es un paquete del protocolo: {pkt!r}")', "    return b''")
m("proto-ack-con-relleno", P, "return _ACK.pack(PacketType.ACK, pkt.nx, pkt.seq)", "return _ACK.pack(PacketType.ACK, pkt.nx, pkt.seq) + b'\\x00'")
m("proto-hb-asignacion-con-relleno", P, "out += _HB_ASG.pack(a.nx, a.target_id, a.ra_e7, a.dec_e7)", "out += _HB_ASG.pack(a.nx, a.target_id, a.ra_e7, a.dec_e7) + b'\\x00'")
m("proto-max-asignaciones-9", P, "MAX_ASSIGNMENTS = MAX_NX ", "MAX_ASSIGNMENTS = 9 ")
m("proto-assign-ra-con-signo", P, '_ASSIGN = struct.Struct("<BBHIi")', '_ASSIGN = struct.Struct("<BBHii")')
m("proto-seq-delta-mascara", P, "return (new - old) & 0xFFFF", "return (new - old) & 0xFFFFF")
m("vec-sin-status", "protocolo/vectores_dorados.txt", "VALID status ", "#VALID status ")
m("vec-byte-cambiado", "protocolo/vectores_dorados.txt", "VALID ack_minimo 04010000", "VALID ack_minimo 04010001")
m("vec-invalido-aceptable", "protocolo/vectores_dorados.txt", "INVALID tipo_0 00 UnknownType", "INVALID tipo_0 00 TruncatedPacket")
m("test-semillas-pocas", "sim/tests/test_barrido.py", "SEMILLAS = range(24)", "SEMILLAS = range(8)")
m("imp-latencia", IM, "d = self.latency_s + rng.uniform(0.0, self.jitter_s)", "d = self.latency_s + 1.0")
m("imp-sin-semilla", IM, "if rng.random() < self.loss:", "if __import__('random').random() < self.loss:")

# --- Retrabajo gate 1 (R1-R8) ---
# R1 (B1): el M2 reiniciado vuelve a contar desde dock_seq0
m("m1-cerrado-solo-confirma", M1, "if activo and d.seq == req.seq:", "if d is not None and d.seq == req.seq:")
m("m1-viejo-sin-acople-activo", M1, "if activo and p.seq_delta(req.seq, d.seq) > 0x8000:", "if d is not None and p.seq_delta(req.seq, d.seq) > 0x8000:")
# R2 (B2): sin DOCK_REF a ACK + ref_wait_s es error, no reenvio
m("m2-espera-ref-reenvia", M2, "        if self.dock_state is DockState.WAIT_REF:\n            # El M1 confirmo la peticion pero el DOCK_REF no llego en ref_wait_s: error de acople (ESPEC. 5.3).\n            self.dock_state = DockState.FAILED_TIMEOUT\n            self.dock_finished = now\n            self._dock_timer = math.inf\n            return\n", "")
# R3 (B3): regla de objetivo
m("m2-hb-igual-pisa-local", M2, "        elif not self.target_local:\n            self.target = nuevo", "        else:\n            self.target = nuevo")
m("m2-hb-sin-mi-nx-borra-local", M2, "            elif not self.target_local:\n                self.target = None", "            else:\n                self.target = None")
m("m2-assign-no-limpia-local", M2, "dec_e7)\n                self.target_local = False", "dec_e7)")
m("m2-hb-otro-id-respeta-local", M2, "            if nuevo is not None:\n                self.target, self.target_local = nuevo, False", "            if nuevo is not None and not self.target_local:\n                self.target, self.target_local = nuevo, False")
m("m2-hb-compara-por-valor", M2, "if _tid(nuevo) != _tid(self.assigned):", "if nuevo != self.assigned:")
m("m2-hb-no-refresca-ra", M2, "            self.target = nuevo                         # refresca RA/Dec", "            pass                                        # refresca RA/Dec")
m("m2-base-nueva-conserva-asignado", M2, "                self.assigned = None            # base nueva", "                pass                            # base nueva")
m("m2-misma-base-borra-asignado", M2, "            if self.base_id != hb.base_id:\n                self.base_id = hb.base_id\n                self.assigned = None", "            if True:\n                self.base_id = hb.base_id\n                self.assigned = None")
m("m2-select-local-no-marca", M2, "        self.target_local = True\n", "        self.target_local = False\n")
# R4 (H3): HB extra tras asignar o quitar
m("m1-quitar-sin-hb-extra", M1, "        self.assignments.pop(nx, None)\n        self._schedule_extra_hb(now)", "        self.assignments.pop(nx, None)")
m("m1-hb-extra-apagado-por-defecto", M1, "hb_after_assign: bool = True", "hb_after_assign: bool = False")
m("m1-hb-extra-corre-el-periodo", M1, "        if now >= self._extra_hb_at:\n            self._extra_hb_at = math.inf\n            self._send_hb(now)", "        if now >= self._extra_hb_at:\n            self._extra_hb_at = math.inf\n            self._send_hb(now)\n            self._next_hb = now + self.cfg.hb_period_s")
# R5 (H2): sin HB aceptado no hay DOCK_REQ
m("m2-dock-sin-base", M2, "        if self.base_id is None:\n            return False\n", "")
# R7 (C2): n <= 10 antes del largo
m("proto-n-despues-del-largo", P, "        if n > MAX_ASSIGNMENTS:\n            raise InvalidField(f\"{n} asignaciones, maximo {MAX_ASSIGNMENTS}\")\n        _exact(data, HB_HEADER_SIZE + HB_ASSIGNMENT_SIZE * n)\n", "        _exact(data, HB_HEADER_SIZE + HB_ASSIGNMENT_SIZE * n)\n        if n > MAX_ASSIGNMENTS:\n            raise InvalidField(f\"{n} asignaciones, maximo {MAX_ASSIGNMENTS}\")\n")
# R8 (C3): la norma del cuaternion se valida sobre los f32 que viajan
m("proto-max-asignaciones-11", P, "MAX_ASSIGNMENTS = MAX_NX ", "MAX_ASSIGNMENTS = 11 ")
m("proto-cuaternion-overflow-sin-capturar", P, "        except OverflowError:", "        except KeyError:")
m("proto-cuaternion-sin-redondeo-f32", P, "            q = _QUAT_F32.unpack(_QUAT_F32.pack(*(float(c) for c in q)))", "            pass")


M[:] = [x for x in M if x is not None]


def ejecutar(mutante, base: Path):
    ident, archivo, viejo, nuevo, nth, udp = mutante
    with tempfile.TemporaryDirectory(prefix=f"mut-{ident}-") as tmp:
        tmp = Path(tmp)
        for carpeta in ("protocolo", "sim"):
            shutil.copytree(base / carpeta, tmp / carpeta,
                            ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
        shutil.copy(base / "pytest.ini", tmp / "pytest.ini")
        f = tmp / archivo
        texto = f.read_text(encoding="utf-8")
        partes = texto.split(viejo)
        if len(partes) - 1 < nth:
            return ident, "no-aplicable", set(), f"no encontre el texto original (apariciones: {len(partes) - 1})"
        # reemplaza solo la n-esima aparicion
        nuevo_texto = viejo.join(partes[:nth]) + nuevo + viejo.join(partes[nth:])
        f.write_text(nuevo_texto, encoding="utf-8")
        if archivo.endswith(".py"):
            try:
                compile(nuevo_texto, archivo, "exec")
            except SyntaxError as e:
                return ident, "invalido", set(), f"el mutante no compila: {e}"
        args = [sys.executable, "-m", "pytest", "-q", "--tb=no", "-rf", "-p", "no:cacheprovider"]
        args += [] if udp else ["-m", "not udp"]
        if udp:
            args += ["-m", "udp"]
        r = subprocess.run(args, cwd=tmp, capture_output=True, text=True, timeout=600)
        falladas = set(re.findall(r"^FAILED \S*?([\w/\\.]+\.py)::(\w+)", r.stdout, re.M))
        if r.returncode == 1:
            return ident, "muerto", falladas, ""
        if r.returncode == 2 and "error during collection" in r.stdout:
            return ident, "muerto", falladas, "(rompe la coleccion de pruebas: el mutante compila pero ya no importa)"
        if r.returncode == 0:
            return ident, "SOBREVIVIO", set(), ""
        return ident, "invalido", set(), (r.stdout + r.stderr)[-400:]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-k", default="")
    ap.add_argument("-j", type=int, default=4)
    a = ap.parse_args()
    sel = [x for x in M if a.k in x[0]]

    base_run = subprocess.run([sys.executable, "-m", "pytest", "-q", "--tb=short", "-p", "no:cacheprovider"],
                              cwd=RAIZ, capture_output=True, text=True)
    print("Linea base (todo el repo, incluye udp):", base_run.stdout.strip().splitlines()[-1])
    if base_run.returncode != 0:
        print(base_run.stdout[-2000:])
        sys.exit("La linea base ya falla: arregla las pruebas antes de mutar.")

    with ThreadPoolExecutor(max_workers=a.j) as ex:
        resultados = list(ex.map(lambda x: ejecutar(x, RAIZ), sel))

    por_estado = {}
    atrapadas = set()
    for ident, estado, falladas, nota in resultados:
        por_estado.setdefault(estado, []).append(ident)
        atrapadas |= {nombre for _, nombre in falladas}
        marca = "ok " if estado == "muerto" else "!! "
        print(f"{marca}{ident:42s} {estado:12s} {len(falladas):3d} pruebas lo atrapan {nota}")

    print()
    print({k: len(v) for k, v in por_estado.items()}, "de", len(sel))

    # Pruebas que ningun mutante hizo fallar
    listado = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"],
                             cwd=RAIZ, capture_output=True, text=True).stdout
    todas = set(re.findall(r"::(\w+)", listado))
    nunca = sorted(todas - atrapadas)
    if a.k == "":
        print(f"Funciones de prueba: {len(todas)}; atrapadas por algun mutante: {len(todas & atrapadas)}")
        if nunca:
            print("Funciones que NINGUN mutante hizo fallar:")
            for n in nunca:
                print("   ", n)
    malo = por_estado.get("SOBREVIVIO") or por_estado.get("invalido") or por_estado.get("no-aplicable") or (nunca and a.k == "")
    sys.exit(1 if malo else 0)


if __name__ == "__main__":
    main()
