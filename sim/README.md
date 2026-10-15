# sim/: M1 y M2 simulados para probar el protocolo sin hardware

Un M1 falso y hasta diez M2 falsos hablan el protocolo de `protocolo/` con **los mismos bytes** que irán por el aire. Reproducen: heartbeat cada 10 s, `ASSIGN` inmediato, el ciclo `DOCK_REQ` → `DOCK_REF` → `ACK` con reintentos, `STATUS` cada 10 s, el watchdog de 3 heartbeats (el M2 sigue guiando sin base), y pérdida, desorden y duplicados con tasa configurable.

Los nodos (`euler_sim/m1.py`, `m2.py`) son máquinas de estado puras. Se montan sobre dos redes:

| Red | Para qué | Determinista |
|---|---|---|
| `virtual.py` | Pruebas exactas y barridos de semillas; el reloj es virtual, 240 s simulados tardan milisegundos | Sí (misma semilla, misma historia) |
| `udpnet.py` | Sockets UDP reales en `127.0.0.1`, un hilo por nodo, **reloj escalable** (`--scale 25`: el HB de 10 s sale cada 0.4 s) | No (planificador del SO); topes holgados |

En localhost no hay AP: el "broadcast" se emula mandando el HB a cada M2 por separado. La pérdida y el desorden se aplican por receptor.

## Probar

Desde la raíz del repo (Python 3.11, `pip install -r requirements-dev.txt`):

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

- `tests/test_escenarios.py`: HB cada 10 s exactos; contenido del HB; `ASSIGN` inmediato; HB de 134 B con 10 asignaciones; acople limpio y cada pérdida posible (`DOCK_REQ`, su `ACK`, `DOCK_REF`, `ACK` de la referencia); solves en fila; M1 muerto; referencia tardía; sin solución; duplicados; `STATUS`; watchdog exacto a 30 s, error leve, el M2 sigue guiando y se recupera; HB atrasado, repetido, de otra base, con la secuencia dando la vuelta o reiniciada; paquetes corruptos; determinismo por semilla; un M2 que se reinicia (1 y 3 acoples antes) se acopla al primer intento; `DOCK_REQ` duplicado tras `DONE`; sin `DOCK_REF` el M2 falla a ACK + 60 s con un solo `DOCK_REQ`; sin HB no hay `DOCK_REQ`; la regla de objetivo del M2 (elección local, `ASSIGN`, HB con otro id, refresco de RA, cambio de base); el HB extra sin correr el periodo.
- `tests/test_barrido.py`: 10 M2 a la vez, 240 s simulados, **24 semillas por nivel** de pérdida.
- `tests/test_red_y_reloj.py`: el reloj escalado y las tasas medidas de pérdida, desorden y duplicados.
- `tests/test_udp.py`: lo mismo sobre sockets reales (HB, acople, `ASSIGN`, 10 M2 con pérdida, sin base y recuperación, M1 apagado).

## Cifras del barrido [estimado: simulador, no medido]

`python -m euler_sim sweep --seeds 24` (la primera fila sale de `--reorder 0 --losses 0`; 24 semillas por fila, 10 M2; desorden del 20 % de los paquetes con hasta 3 s de retraso salvo la primera fila; **con el HB extra a los 50 ms**, que es la especificación). Los 10 M2 piden acople a la vez en t = 20 s (el que aún no oyó un HB reintenta cada 0.25 s: sin HB no hay `DOCK_REQ`) y el solve falso dura 2 s, así que 20 s es el mínimo posible. Los máximos son los del barrido, no promedios:

| Pérdida | Acoples completos (mínimo de 10) | Acople más lento | Asignación asentada (máx.) | Borrado asentado (máx.) | Estado final correcto |
|---|---|---|---|---|---|
| 0, sin desorden | 10 | 20.0 s | 0.25 s | 0.25 s | 24/24 |
| 0 | 10 | 21.4 s | 2.75 s | 2.00 s | 24/24 |
| 5 % | 10 | 21.0 s | 2.75 s | 8.50 s | 24/24 |
| 10 % | 10 | 22.2 s | 6.50 s | 6.50 s | 24/24 |
| 20 % | 10 | 23.0 s | 6.50 s | 6.50 s | 24/24 |
| 30 % | 10 | 21.8 s | 56.50 s | 27.00 s | 24/24 |
| 50 % | 8 | 21.4 s | 86.50 s | 46.50 s | 24/24 |

Con desorden de hasta 15 s (dos HB consecutivos pueden cruzarse) y 20 % de pérdida: mínimo 9 acoples, asignación máx. 16.50 s, borrado máx. 16.50 s, 24/24 finales correctos.

Referencia sin HB extra (`--sin-hb-extra`, mismo código): asignación máx. 26.50 s (5 %), 16.50 s (10 %), 18.00 s (20 %); borrado máx. 8.50 s (5 %), 16.50 s (10 %), 16.50 s (20 %), 77.25 s (50 %). Las cifras de la tabla anterior (commit `ba8731a`, sin HB extra y con el borrado a 27.0 s al 20 %) quedan superadas por esta corrida.

Lectura: el acople aguanta hasta 30 % de pérdida con los 10 M2 a la vez; con 50 % algún M2 agota sus 8 reintentos. El HB extra no cambia los acoples (la corrida `--sin-hb-extra` da los mismos); lo que baja es el tiempo de asentamiento de una asignación o de un borrado hasta el siguiente HB que llegue, de 16-18 s a 6.5 s con 10-20 % de pérdida. Con 30 % o más domina la pérdida de los propios HB y casi no cambia. Que los acoples sean ahora más (10 contra 9 al 30 %) viene de las reglas R1, R2 y R5 del retrabajo, no del HB extra.

Los parámetros del simulador (solve de 2 s, reintentos a 1 s, 8 intentos, latencia de 5 ms) son supuestos, no mediciones; el tiempo real del solve se mide en el Hito 1.

## Mutación (autoverificación)

`mutate.py` (raíz del repo) aplica cada mutante a una copia temporal de `protocolo/` y `sim/`, corre `pytest` y exige que falle; reporta los que sobreviven y las funciones de prueba que ningún mutante hizo fallar. El resultado de la última corrida está en el cierre del proyecto.

## Paso del manual de armado al que pertenece

Es herramienta de prueba, no se arma. Va junto a la prueba de red del M1 y del M2 ("verificar el protocolo sin hardware").
