#!/usr/bin/env python3
"""Pruebas de mutación: rompe la lógica a propósito y exige que alguna prueba falle.

Para cada mutante: copia src/ y test/host/ a una carpeta temporal, cambia UNA cosa en el
código (el texto original debe aparecer exactamente una vez), compila y corre las pruebas
asignadas. El mutante está "muerto" (bien) si alguna prueba falla; "sobrevive" (mal) si todas
pasan; "inválido" si no compila o el texto original no está.

Uso: python test/host/mutate.py        (sale con código 1 si algún mutante sobrevive)
"""
import concurrent.futures as cf
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from run_host_tests import build_and_run, M2  # noqa: E402

# (nombre, archivo en src/, texto original, texto mutado, pruebas que deben detectarlo)
MUTANTS = [
    # --- fusión ---
    ("fusion: signo de la corrección por gravedad", "core/fusion.cpp",
     "g = g + cross(a, up) * tun::kFusionKp;", "g = g + cross(up, a) * tun::kFusionKp;", ["fusion", "pipeline"]),
    ("fusion: signo del rumbo (horario -> antihorario)", "core/fusion.cpp",
     "out.az_deg = -std::atan2(p.y, p.x) * kRad2Deg;", "out.az_deg = std::atan2(p.y, p.x) * kRad2Deg;", ["fusion", "pipeline"]),
    ("fusion: sin rechazo de aceleración lineal", "core/fusion.cpp",
     "if (an > 1e-3f && std::fabs(an - 1.0f) < tun::kAccelGateG) {", "if (an > 1e-3f) {", ["fusion"]),
    ("fusion: integración del eje z con signo mal", "core/fusion.cpp",
     "float hz = 0.5f * (w_ * g.z + x_ * g.y - y_ * g.x);", "float hz = 0.5f * (w_ * g.z + x_ * g.y + y_ * g.x);", ["fusion", "pipeline"]),
    ("fusion: signo de la altura", "core/fusion.cpp",
     "std::asin(clampf(p.z, -1.0f, 1.0f))", "std::asin(clampf(-p.z, -1.0f, 1.0f))", ["fusion", "pipeline"]),
    ("fusion: rotación al mundo mal (termino w)", "core/fusion.cpp",
     "return v + t * w_ + cross(q, t);\n}\n\nVec3 Fusion6::upInBody", "return v - t * w_ + cross(q, t);\n}\n\nVec3 Fusion6::upInBody", ["fusion", "pipeline"]),
    ("fusion: update sin inicializar integra", "core/fusion.cpp",
     "  if (!init_) return;\n  float an", "  float an", ["fusion"]),
    # --- sesgo del giroscopio ---
    ("sesgo: sin cota al paso de la re-estimacion (absorbe giro lento)", "core/gyro_bias.cpp",
     "if (sn > tun::kBiasMaxStepDps) mean = bias_ + step * (tun::kBiasMaxStepDps / sn);", "(void)sn;", ["bias"]),
    ("sesgo: cota al paso demasiado grande (0.1)", "config/tuning.h",
     "kBiasMaxStepDps = 0.02f", "kBiasMaxStepDps = 0.1f", ["bias"]),
    ("sesgo: no guarda la media cruda de la ventana (log de banco)", "core/gyro_bias.cpp",
     "  raw_mean_ = mean;", "  (void)0;", ["bias"]),
    ("sesgo: acepta giro constante como sesgo", "core/gyro_bias.cpp",
     "if (norm(mean) > tun::kBiasMaxDps) return false;", "if (false) return false;", ["bias"]),
    ("sesgo: el movimiento no reinicia la ventana", "core/gyro_bias.cpp",
     "norm(g - ref_g_) < tun::kBiasQuietGyroDps", "norm(g - ref_g_) < 1000.0f", ["bias"]),
    ("sesgo: la re-estimación usa siempre la ventana larga", "core/gyro_bias.cpp",
     "float s = valid_ ? tun::kBiasRefreshWindowS : tun::kBiasInitialWindowS;", "float s = tun::kBiasInitialWindowS;", ["bias"]),
    ("sesgo: gravedad absurda no impide empezar", "core/gyro_bias.cpp",
     "bool plausible = std::fabs(an - 1.0f) < 0.1f;", "bool plausible = std::fabs(an - 1.0f) < 100.0f;", ["bias"]),
    ("sesgo: no promedia (usa la ultima muestra)", "core/gyro_bias.cpp",
     "Vec3 mean = sum_g_ * (1.0f / n_);", "Vec3 mean = ref_g_;", ["bias"]),
    # --- sync ---
    ("sync: promedio sin envolver el rumbo", "core/sync.cpp",
     "sum_daz += wrap180(buf_[i].az_deg - az0);", "sum_daz += buf_[i].az_deg - az0;", ["guide"]),
    ("sync: confirma sin muestras suficientes", "core/sync.cpp",
     "if (count_ < tun::kSyncMinSamples) return false;", "if (count_ < 0) return false;", ["guide", "fsm"]),
    ("sync: el anillo de muestras no avanza", "core/sync.cpp",
     "head_ = (head_ + 1) % tun::kSyncAvgSamples;", "head_ = 0;", ["guide"]),
    ("sync: clear no invalida", "core/sync.cpp",
     "  count_ = 0;\n  head_ = 0;\n  valid_ = false;", "  count_ = 0;\n  head_ = 0;", ["guide", "fsm"]),
    # --- guía ---
    ("guia: signo del giro faltante", "core/guide.cpp",
     "o.d_giro_deg = wrap180((ref.az_deg + t.giro_deg) - now.az_deg);", "o.d_giro_deg = wrap180(now.az_deg - (ref.az_deg + t.giro_deg));", ["guide", "fsm", "pipeline"]),
    ("guia: el giro no envuelve", "core/guide.cpp",
     "o.d_giro_deg = wrap180((ref.az_deg + t.giro_deg) - now.az_deg);", "o.d_giro_deg = ((ref.az_deg + t.giro_deg) - now.az_deg);", ["guide"]),
    ("guia: altura ignora la referencia del sync", "core/guide.cpp",
     "o.d_alt_deg = (ref.el_deg + t.altura_deg) - now.el_deg;", "o.d_alt_deg = t.altura_deg - now.el_deg;", ["guide", "fsm", "pipeline"]),
    ("guia: sin histeresis al salir de EN MIRA", "core/guide.cpp",
     "if (o.dist_deg > tun::kInViewExitDeg) state_ = GuideState::Near;", "if (o.dist_deg > tun::kInViewEnterDeg) state_ = GuideState::Near;", ["guide"]),
    ("guia: sin histeresis entre LEJOS y CERCA", "core/guide.cpp",
     "if (o.dist_deg < tun::kFarExitDeg) state_ = GuideState::Near;", "if (o.dist_deg < tun::kFarEnterDeg) state_ = GuideState::Near;", ["guide"]),
    ("guia: umbral de EN MIRA demasiado generoso", "core/guide.cpp",
     "else if (o.dist_deg < tun::kInViewEnterDeg) state_ = GuideState::InView;", "else if (o.dist_deg < 8.0f) state_ = GuideState::InView;", ["guide", "pipeline"]),
    ("guia: estrella invertida en vertical", "core/guide.cpp",
     "o.star_y_px = -uy * r;", "o.star_y_px = uy * r;", ["guide"]),
    ("guia: flecha con ejes cambiados", "core/guide.cpp",
     "o.arrow_rad = std::atan2(o.d_alt_deg, o.d_giro_deg);", "o.arrow_rad = std::atan2(o.d_giro_deg, o.d_alt_deg);", ["guide"]),
    ("guia: punteros sin saturar", "core/guide.cpp",
     "o.giro_ptr = clampf(o.d_giro_deg / tun::kScaleDeg, -1.0f, 1.0f);", "o.giro_ptr = o.d_giro_deg / tun::kScaleDeg;", ["guide"]),
    # --- marcas ---
    ("marcas: corrección de paralaje con signo mal", "core/marks.cpp",
     "t.giro_deg -= parallaxDeg(off_lat_m, k.distancia_m)", "t.giro_deg += parallaxDeg(off_lat_m, k.distancia_m)", ["guide"]),
    ("marcas: corrige aunque falte la distancia", "core/marks.cpp",
     "if (k.distancia_m <= 0.0f || m1.distancia_m <= 0.0f) return t;", "if (false) return t;", ["guide"]),
    ("marcas: la altura no se corrige", "core/marks.cpp",
     "t.altura_deg -= parallaxDeg(off_vert_m, k.distancia_m)", "t.altura_deg += parallaxDeg(off_vert_m, k.distancia_m)", ["guide"]),
    # --- montaje ---
    ("montaje: giro de pantalla a 90 en lugar de 270", "core/mount.cpp",
     "else { m.mount = Mount::VertLeft; m.screen_rotation_deg = 270; }", "else { m.mount = Mount::VertLeft; m.screen_rotation_deg = 90; }", ["guide"]),
    ("montaje: pantalla hacia abajo no cuenta como plano", "core/mount.cpp",
     "std::fabs(u.z) >= tun::kMountFlatMinUp", "u.z >= tun::kMountFlatMinUp", ["guide"]),
    ("montaje: eje de apuntado vertical equivocado", "core/mount.cpp",
     "m.pointing_axis = {0, 0, -1};", "m.pointing_axis = {0, 0, 1};", ["guide", "pipeline"]),
    # --- botones ---
    ("botones: el largo se repite", "core/buttons.cpp",
     "a_.long_fired = true;", "", ["buttons"]),
    ("botones: el largo de B se repite", "core/buttons.cpp",
     "b_.long_fired = true;", "", ["buttons"]),
    ("botones: corto despues de un largo", "core/buttons.cpp",
     "if (a_prev && !a_.down && !a_.involved && !a_.long_fired) o.a_short = true;",
     "if (a_prev && !a_.down && !a_.involved) o.a_short = true;", ["buttons"]),
    ("botones: sin antirrebote", "core/buttons.cpp",
     "static_cast<uint32_t>(now - b.raw_since) >= tun::kDebounceMs", "static_cast<uint32_t>(now - b.raw_since) >= 1u", ["buttons"]),
    ("botones: A+B se dispara a 1 s", "core/buttons.cpp",
     "held >= tun::kComboMs) {", "held >= tun::kLongPressMs) {", ["buttons"]),
    ("botones: A+B no suprime los eventos individuales", "core/buttons.cpp",
     "    a_.involved = true;\n    b_.involved = true;\n  }\n\n  // Liberaciones", "  }\n\n  // Liberaciones", ["buttons"]),
    ("botones: boton atascado al arrancar cuenta", "core/buttons.cpp",
     "a_.ignore = raw_a;", "a_.ignore = false;", ["buttons"]),
    ("botones: el reloj de 32 bits da la vuelta", "core/buttons.cpp",
     "uint32_t held = now - a_.t_down;", "uint64_t held = static_cast<uint64_t>(now) - a_.t_down;", ["buttons"]),
    ("botones: largo a 500 ms", "core/buttons.cpp",
     "if (held >= tun::kLongPressMs) {\n      a_.long_fired", "if (held >= 500) {\n      a_.long_fired", ["buttons"]),
    # --- autoprueba ---
    ("autoprueba: ignora giroscopio muerto", "core/selftest.cpp",
     "|| !any_gyro_nonzero) {", "|| (any_gyro_nonzero && false)) {", ["selftest"]),
    ("autoprueba: ignora gravedad absurda", "core/selftest.cpp",
     "g >= tun::kSelfTestGravMin && g <= tun::kSelfTestGravMax", "g >= 0.0f && g <= 100.0f", ["selftest"]),
    ("autoprueba: todo ID es conocido", "core/selftest.cpp",
     "r.id_known = isKnownImuId(r.who_am_i);", "r.id_known = true;", ["selftest"]),
    ("autoprueba: ID invalido pasa", "core/selftest.cpp",
     "if (st != ImuStatus::Ok) {", "if (false) {", ["selftest"]),
    ("autoprueba: la mayoria de lecturas malas pasa", "core/selftest.cpp",
     "if (good < tun::kSelfTestSamples / 2) {", "if (false) {", ["selftest"]),
    ("autoprueba: MPU-9255 no reconocido", "core/selftest.cpp",
     "id == 0x71 || id == 0x73 || id == 0x70", "id == 0x71 || id == 0x70", ["selftest"]),
    ("autoprueba: sin respuesta no es grave", "core/selftest.cpp",
     "if (st == ImuStatus::NoAck || st == ImuStatus::Timeout) {", "if (false) {", ["selftest"]),
    # --- máquina de estados ---
    ("fsm: el error grave no tiene salida", "core/app_fsm.cpp",
     "if (b.a_short || b.b_short) enter(Phase::SelfTest, now);", "if (false) enter(Phase::SelfTest, now);", ["fsm"]),
    ("fsm: la lista de marcas no da la vuelta", "core/app_fsm.cpp",
     "(model_.mark_idx + 1) % kNumMarcas", "(model_.mark_idx + 1) % (kNumMarcas + 1)", ["fsm"]),
    ("fsm: A largo no alterna modo noche en la guia", "core/app_fsm.cpp",
     "    case Phase::Guide: {\n      if (b.a_long) model_.night = !model_.night;", "    case Phase::Guide: {", ["fsm"]),
    ("fsm: A+B no borra la calibracion", "core/app_fsm.cpp",
     "if (b.combo) {  // A+B 3 s: borrar calibración", "if (false) {  // A+B 3 s: borrar calibración", ["fsm"]),
    ("fsm: borrar calibracion deja el sync viejo", "core/app_fsm.cpp",
     "void AppFsm::startBias(uint32_t now) {\n  sync_.clear();", "void AppFsm::startBias(uint32_t now) {", ["fsm"]),
    ("fsm: IMU perdido con codigo equivocado", "core/app_fsm.cpp",
     "model_.fatal = FatalReason::ImuLost;", "model_.fatal = FatalReason::ImuNoAck;", ["fsm"]),
    ("fsm: la autoprueba no espera el minimo", "core/app_fsm.cpp",
     "if (st_done_ && model_.phase_ms >= tun::kSelfTestMinMs) {", "if (st_done_) {", ["fsm"]),
    ("fsm: tras el sync guia a la marca 1", "core/app_fsm.cpp",
     "model_.mark_idx = kNumMarcas > 1 ? 1 : 0;", "model_.mark_idx = 0;", ["fsm"]),
    ("fsm: el sync no recibe muestras", "core/app_fsm.cpp",
     "if (pose_valid) sync_.push(pose);", "", ["fsm", "pipeline"]),
    ("fsm: el logo dura cero", "core/app_fsm.cpp",
     "if (model_.phase_ms >= tun::kLogoMs) enter(Phase::SelfTest, now);", "enter(Phase::SelfTest, now);", ["fsm"]),
    ("fsm: modo noche activo por defecto", "core/app_fsm.h",
     "", "", []),  # placeholder, se reemplaza abajo
]
MUTANTS.pop()
MUTANTS.append(("ui model: modo noche por defecto", "core/app_fsm.h",
                "  bool night = false;", "  bool night = true;", ["fsm"]))


def run_mutant(idx, m):
    name, rel, old, new, tests = m
    tmp = tempfile.mkdtemp(prefix=f"mut{idx}_")
    try:
        os.makedirs(os.path.join(tmp, "test"))
        shutil.copytree(os.path.join(M2, "src"), os.path.join(tmp, "src"))
        shutil.copytree(HERE, os.path.join(tmp, "test", "host"),
                        ignore=shutil.ignore_patterns("__pycache__", "mutate.py"))
        path = os.path.join(tmp, "src", rel)
        text = open(path, encoding="utf8").read()
        if text.count(old) != 1:
            return idx, "invalido", f"el texto original aparece {text.count(old)} veces"
        open(path, "w", encoding="utf8").write(text.replace(old, new))
        out_dir = os.path.join(tmp, "out")
        os.makedirs(out_dir)
        for t in tests:
            compiled, passed, out = build_and_run(os.path.join(tmp, "test", "host", f"test_{t}.cpp"),
                                                  os.path.join(tmp, "src"), out_dir)
            if not compiled:
                return idx, "invalido", f"no compila ({t}): {out[:200]}"
            if not passed:
                return idx, "muerto", f"detectado por test_{t}"
        return idx, "SOBREVIVE", "ninguna prueba lo detecta"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    # Línea base: sin mutar, todo debe pasar (si no, el resultado no significa nada).
    base_dir = os.path.join(M2, ".pio", "host_tests")
    os.makedirs(base_dir, exist_ok=True)
    for t in sorted({t for m in MUTANTS for t in m[4]}):
        compiled, passed, out = build_and_run(os.path.join(HERE, f"test_{t}.cpp"), os.path.join(M2, "src"), base_dir)
        if not passed:
            print(f"Linea base rota en test_{t}:\n{out}")
            sys.exit(2)
    results = {}
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        for idx, status, info in ex.map(lambda a: run_mutant(*a), list(enumerate(MUTANTS))):
            results[idx] = (status, info)
    bad = 0
    for idx, m in enumerate(MUTANTS):
        status, info = results[idx]
        print(f"[{status:9}] {m[0]}  ({info})")
        if status != "muerto":
            bad += 1
    killed = sum(1 for s, _ in results.values() if s == "muerto")
    print(f"\nMutantes: {len(MUTANTS)}  muertos: {killed}  sobreviven/invalidos: {bad}")
    sys.exit(0 if bad == 0 else 1)


if __name__ == "__main__":
    main()
