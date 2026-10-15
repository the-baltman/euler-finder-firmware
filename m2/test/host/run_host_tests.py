#!/usr/bin/env python3
"""Compila y corre las pruebas de host (g++ -std=c++17). Uso:
    python test/host/run_host_tests.py            # todas
    python test/host/run_host_tests.py fusion     # una (por nombre sin test_)
"""
import os
import subprocess
import sys
import glob

HERE = os.path.dirname(os.path.abspath(__file__))
M2 = os.path.abspath(os.path.join(HERE, "..", ".."))


def build_and_run(test_cpp, src_root, out_dir, quiet=False):
    """Devuelve (compila, pasa, salida)."""
    name = os.path.splitext(os.path.basename(test_cpp))[0]
    exe = os.path.join(out_dir, name + (".exe" if os.name == "nt" else ""))
    srcs = sorted(glob.glob(os.path.join(src_root, "core", "*.cpp")))
    # El test incluye "../../src/..." relativo a su ubicación: se compila una copia del test
    # junto a la copia del árbol src para que los includes apunten a la misma raíz.
    cmd = ["g++", "-std=c++17", "-O1", "-Wall", "-Wextra", "-Werror", "-o", exe, test_cpp] + srcs
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        return False, False, r.stdout + r.stderr
    p = subprocess.run([exe], capture_output=True, text=True)
    return True, p.returncode == 0, p.stdout + p.stderr


def main():
    want = sys.argv[1:]
    out_dir = os.path.join(M2, ".pio", "host_tests")
    os.makedirs(out_dir, exist_ok=True)
    tests = sorted(glob.glob(os.path.join(HERE, "test_*.cpp")))
    if want:
        tests = [t for t in tests if os.path.basename(t)[5:-4] in want]
    ok_all = True
    for t in tests:
        compiled, passed, out = build_and_run(t, os.path.join(M2, "src"), out_dir)
        status = "OK " if passed else ("NO COMPILA" if not compiled else "FALLA")
        print(f"[{status}] {os.path.basename(t)}")
        print(out.rstrip())
        ok_all &= passed
    print("RESULTADO:", "todas pasan" if ok_all else "HAY FALLAS")
    sys.exit(0 if ok_all else 1)


if __name__ == "__main__":
    main()
