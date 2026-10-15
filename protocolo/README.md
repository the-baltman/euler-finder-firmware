# protocolo/: paquetes entre la base (M1) y los niveladores (M2)

| Archivo | Qué es |
|---|---|
| `ESPECIFICACION.md` | Formato de cada paquete (little-endian, tamaños exactos), reglas de rechazo, comportamiento y decisiones del arbitraje |
| `euler_proto.py` | Codec de referencia en Python: `encode` / `decode`; rechaza truncados, tipo desconocido, versión distinta, bytes de más y campos fuera de rango |
| `vectores_dorados.txt` | Paquetes válidos e inválidos armados a mano, byte por byte; los leen estas pruebas y deben leerlos las del M2 (C++) |
| `tests/` | Pruebas `pytest` del codec y de los vectores |

## Probar (sin hardware)

Requiere Python 3.11 y `pytest` (versión fijada en `requirements-dev.txt`). Desde la raíz del repo:

```
pip install -r requirements-dev.txt
python -m pytest protocolo -q
```

Esperado: todas pasan. El comportamiento entre M1 y M2 se prueba en `sim/`.

## Usar el codec

```python
import euler_proto as p
datos = p.encode(p.DockReq(nx=3, seq=48879))   # b'\x02\x03\xef\xbe'
p.decode(datos)                                 # DockReq(nx=3, seq=48879)
p.decode(datos[:-1])                            # lanza p.TruncatedPacket
```

Todos los errores heredan de `p.ProtocolError`; quien recibe descarta el datagrama.

## Paso del manual de armado al que pertenece

Este módulo no se arma ni se flashea: es la referencia del protocolo. El QR de `ESPECIFICACION.md` y de `vectores_dorados.txt` va junto a los pasos de red del M1 y del M2 (heartbeat y acople).
