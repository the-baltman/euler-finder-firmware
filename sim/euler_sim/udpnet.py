"""Red real: cada nodo es un hilo con su socket UDP en 127.0.0.1 y el reloj es escalable.

El "broadcast" del AP se emula mandando el datagrama a cada M2 por separado (en localhost no hay AP).
La perdida y el desorden se aplican en el emisor: cada copia espera su retraso en un monton y sale
cuando le toca. El resultado NO es determinista (depende del planificador del SO); por eso las pruebas
exactas usan virtual.py y aqui se prueba que el mismo codigo funciona sobre sockets reales.
"""
from __future__ import annotations

import heapq
import itertools
import random
import select
import socket
import threading
from typing import Callable, Dict, Optional

from . import BROADCAST
from .clock import ScaledClock
from .impair import Impairment
from .m1 import M1Config, M1Core
from .m2 import M2Config, M2Core

_MAX_WAIT_WALL_S = 0.01     # tope de espera por iteracion: acota la latencia de reaccion a comandos y a stop()


class _Node(threading.Thread):
    def __init__(self, net: "UdpNet", name: str, sock: socket.socket, seed: int):
        super().__init__(name=name, daemon=True)
        self.net = net
        self.sock = sock
        self.rng = random.Random(seed)
        self.lock = threading.RLock()
        self.alive = True
        self.core = None
        self._delayed: list = []
        self._ids = itertools.count()

    def schedule(self, dest, data: bytes) -> None:
        """Pone en cola las copias del datagrama segun el deterioro (perdida / retraso / duplicado)."""
        for delay in self.net.impair.plan(self.rng):
            heapq.heappush(self._delayed, (self.net.clock.now() + delay, next(self._ids), dest, data))

    def _flush(self, now: float) -> None:
        while self._delayed and self._delayed[0][0] <= now:
            _, _, dest, data = heapq.heappop(self._delayed)
            try:
                self.sock.sendto(data, dest)
            except OSError:
                pass            # el destino ya cerro (fin de la prueba): equivale a un datagrama perdido

    def run(self) -> None:
        clock = self.net.clock
        while not self.net.stopping.is_set():
            with self.lock:
                if self.alive:
                    now = clock.now()
                    self._flush(now)
                    self.core.tick(now)
                    deadline = self.core.next_deadline()
                    if self._delayed:
                        deadline = min(deadline, self._delayed[0][0])
                else:
                    deadline = float("inf")
            wait = min(max(clock.to_wall(deadline - clock.now()), 0.0), _MAX_WAIT_WALL_S)
            try:
                readable, _, _ = select.select([self.sock], [], [], wait)
            except (OSError, ValueError):
                return
            if not readable:
                continue
            try:
                data, _ = self.sock.recvfrom(2048)
            except OSError:
                continue         # en Windows un ICMP "puerto cerrado" aparece como error de lectura
            with self.lock:
                if self.alive:
                    self.core.on_packet(data, clock.now())


def _udp_socket() -> socket.socket:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    s.setblocking(False)
    if hasattr(socket, "SIO_UDP_CONNRESET"):
        try:
            s.ioctl(socket.SIO_UDP_CONNRESET, False)
        except OSError:
            pass
    return s


class UdpNet:
    def __init__(self, scale: float = 25.0, seed: int = 0, impair: Optional[Impairment] = None,
                 m1_cfg: Optional[M1Config] = None):
        self.clock = ScaledClock(scale)
        self.impair = impair or Impairment()
        self.stopping = threading.Event()
        self._seed = seed
        self._m2_addr: Dict[int, tuple] = {}
        self._m1_sock = _udp_socket()
        self._m1_node = _Node(self, "M1", self._m1_sock, seed)
        self.m1 = M1Core(m1_cfg or M1Config(), self._m1_send)
        self._m1_node.core = self.m1
        self.m2: Dict[int, M2Core] = {}
        self._m2_nodes: Dict[int, _Node] = {}
        self._started = False

    # --- Armado ---

    def add_m2(self, nx: int, **cfg) -> M2Core:
        if self._started:
            raise RuntimeError("agrega los M2 antes de start()")
        sock = _udp_socket()
        node = _Node(self, f"M2-{nx}", sock, self._seed * 1000 + nx)
        core = M2Core(M2Config(nx=nx, **cfg), lambda data, node=node: node.schedule(self._m1_sock.getsockname(), data))
        node.core = core
        self.m2[nx] = core
        self._m2_nodes[nx] = node
        self._m2_addr[nx] = sock.getsockname()
        return core

    def _m1_send(self, dst, data: bytes) -> None:
        targets = sorted(self._m2_addr) if dst == BROADCAST else [dst]
        for nx in targets:
            self._m1_node.schedule(self._m2_addr[nx], data)

    # --- Ciclo de vida ---

    def start(self) -> "UdpNet":
        self._started = True
        self.clock.reset()
        self._m1_node.start()
        for n in self._m2_nodes.values():
            n.start()
        return self

    def stop(self) -> None:
        self.stopping.set()
        for n in [self._m1_node, *self._m2_nodes.values()]:
            if n.is_alive():
                n.join(timeout=2.0)
            n.sock.close()

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()

    # --- Control ---

    def now(self) -> float:
        return self.clock.now()

    def run_for(self, sim_s: float) -> None:
        """Espera (tiempo real) lo que dura sim_s segundos simulados."""
        self.stopping.wait(self.clock.to_wall(sim_s))

    def run_until(self, sim_t: float) -> None:
        self.run_for(max(0.0, sim_t - self.now()))

    def m1_do(self, fn: Callable[[M1Core], object]):
        with self._m1_node.lock:
            return fn(self.m1)

    def m2_do(self, nx: int, fn: Callable[[M2Core], object]):
        with self._m2_nodes[nx].lock:
            return fn(self.m2[nx])

    def kill_m1(self) -> None:
        with self._m1_node.lock:
            self._m1_node.alive = False

    def revive_m1(self) -> None:
        with self._m1_node.lock:
            self._m1_node.alive = True
