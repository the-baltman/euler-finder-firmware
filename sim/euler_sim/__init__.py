"""Simulador del protocolo EULER finder: un M1 falso y N M2 falsos.

Los nodos (m1.py, m2.py) son maquinas de estado puras: reciben bytes y tiempo, devuelven bytes por un
callback. No saben si estan sobre la red virtual (virtual.py, determinista, para pruebas y barridos de
semillas) o sobre UDP real en localhost (udpnet.py, con reloj escalable).
"""
import sys
from pathlib import Path

# El codec vive en protocolo/ (una sola copia); se agrega a la ruta para que `python -m euler_sim` funcione sin instalar.
_PROTOCOLO = Path(__file__).resolve().parents[2] / "protocolo"
if str(_PROTOCOLO) not in sys.path:
    sys.path.insert(0, str(_PROTOCOLO))

BROADCAST = "broadcast"   # destino del HB: todos los M2 del AP
