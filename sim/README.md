# sim/: M1 y M2 simulados para probar el protocolo sin hardware

Un M1 falso y hasta diez M2 falsos hablan el protocolo de `protocolo/` con **los mismos bytes** que irán por el aire. Reproducen: heartbeat cada 10 s, `ASSIGN` inmediato, el ciclo `DOCK_REQ` → `DOCK_REF` → `ACK` con reintentos, `STATUS` cada 10 s, el watchdog de 3 heartbeats (el M2 sigue guiando sin base), y pérdida, desorden y duplicados con tasa configurable.

Los nodos (`euler_sim/m1.py`, `m2.py`) son máquinas de estado puras. Se montan sobre dos redes:

| Red | Para qué | Determinista |
|---|---|---|
| `virtual.py` | Pruebas exactas y barridos de semillas; el reloj es virtual, 240 s simulados tardan milisegundos | Sí (misma semilla, misma historia) |
| `udpnet.py` | Sockets UDP reales en `127.0.0.1`, un hilo por nodo, **reloj escalable** (`--scale 25`: el HB de 10 s sale cada 0.4 s) | No (planificador del SO); topes holgados |

En localhost no hay AP: el "broadcast" se emula mandando el HB a cada M2 por separado. La pérdida y el desorden se aplican por receptor.

## Probar

Desde la raíz del repo (Python 3.11, `pip install pytest`):

```
python -m pytest sim -q                 # todo, incluido UDP real (~25 s)
python -m pytest sim -q -m "not udp"    # solo la red virtual (~7 s)
python mutate.py                        # pruebas de mutación (~6 min), ver abajo
```

Demostración sobre UDP real (10 M2, 10 % de pérdida, 120 s simulados = 5 s reales) y tabla del barrido, desde `sim/`:

```
python -m euler_sim udp --m2 10 --loss 0.1 --scale 25 --duration 120
python -m euler_sim sweep --seeds 24
```

## Qué cubren las pruebas

- `tests/test_escenarios.py`: HB cada 10 s exactos; contenido del HB; `ASSIGN` inmediato; HB de 134 B con 10 asignaciones; acople limpio y cada pérdida posible (`DOCK_REQ`, su `ACK`, `DOCK_REF`, `ACK` de la referencia); solves en fila; M1 muerto; referencia tardía; sin solución; duplicados; `STATUS`; watchdog exacto a 30 s, error leve, el M2 sigue guiando y se recupera; HB atrasado, repetido, de otra base, con la secuencia dando la vuelta o reiniciada; paquetes corruptos; determinismo por semilla.
- `tests/test_barrido.py`: 10 M2 a la vez, 240 s simulados, **24 semillas por nivel** de pérdida.
- `tests/test_red_y_reloj.py`: el reloj escalado y las tasas medidas de pérdida, desorden y duplicados.
- `tests/test_udp.py`: lo mismo sobre sockets reales (HB, acople, `ASSIGN`, 10 M2 con pérdida, sin base y recuperación, M1 apagado).

## Cifras del barrido [estimado: simulador, no medido]

`python -m euler_sim sweep` (24 semillas por fila, 10 M2; desorden del 20 % de los paquetes con hasta 3 s de retraso salvo la primera fila). Los 10 M2 piden acople a la vez y el solve falso dura 2 s, así que 20 s es el mínimo posible. Los máximos son los del barrido, no promedios:

| Pérdida | Acoples completos (mínimo de 10) | Acople más lento | Asignación asentada (máx.) | Borrado asentado (máx.) | Estado final correcto |
|---|---|---|---|---|---|
| 0, sin desorden | 10 | 20.0 s | 0.25 s | 6.5 s | 24/24 |
| 0 | 10 | 21.4 s | 3.0 s | 8.8 s | 24/24 |
| 5 % | 10 | 21.4 s | 26.5 s | 8.5 s | 24/24 |
| 10 % | 10 | 22.4 s | 16.5 s | 16.5 s | 24/24 |
| 20 % | 10 | 23.0 s | 18.0 s | 27.0 s | 24/24 |
| 30 % | 9 | 23.0 s | 57.3 s | 26.5 s | 24/24 |
| 50 % | 7 | 26.0 s | 76.5 s | 56.5 s | 24/24 (4 asentamientos sin cerrar dentro de su ventana) |

Lectura: el acople aguanta hasta 20 % de pérdida con los 10 M2 a la vez; desde 30 % algún M2 agota sus 8 reintentos. Si el `ASSIGN` se pierde (no tiene `ACK`) la asignación espera al HB: con 20 % puede tardar casi dos periodos. Con desorden de hasta 15 s (dos HB consecutivos pueden cruzarse) y 20 % de pérdida: mínimo 9 acoples, asignación máx. 29.5 s, 24/24 finales correctos. Con la variante `hb_after_assign` (hallazgo H3) la asignación baja de 16.5 s a 6.5 s con 10 % de pérdida y de 26.5 s a 2.75 s con 5 %; con 30 % o más casi no cambia.

Los parámetros del simulador (solve de 2 s, reintentos a 1 s, 8 intentos, latencia de 5 ms) son supuestos, no mediciones; el tiempo real del solve se mide en el Hito 1.

## Mutación (autoverificación)

`mutate.py` (raíz del repo) aplica cada mutante a una copia temporal de `protocolo/` y `sim/`, corre `pytest` y exige que falle; reporta los que sobreviven y las funciones de prueba que ningún mutante hizo fallar. El resultado de la última corrida está en el cierre del proyecto.

## Paso del manual de armado al que pertenece

Es herramienta de prueba, no se arma. Va junto a la prueba de red del M1 y del M2 ("verificar el protocolo sin hardware").
