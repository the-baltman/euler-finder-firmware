# Protocolo M1 ↔ M2 de EULER finder: especificación (versión 1)

Fuente única de los tamaños, campos y periodos: `Architecture/Operacion/arquitectura-operativa.md` del repo de notas (v2), secciones 4 y 6. Este documento convierte esa tabla en bytes exactos y fija lo que la tabla no decía. Todo lo que **no** sale de la arquitectura va marcado **[propuesto]** y está listado en la sección 7 para que `c-morty` lo arbitre.

Implementación de referencia: `euler_proto.py` (Python). Vectores dorados: `vectores_dorados.txt`. El M2 (C++) debe producir y rechazar exactamente los mismos bytes.

## 1. Convenciones

- **Little-endian**, sin relleno entre campos. Un datagrama UDP = un paquete.
- Enteros sin signo `u8/u16/u32/u64`; con signo `i32`; decimal `f32` IEEE-754.
- Ángulos: enteros en unidades de **1e-7 grado**. Hora: **ms desde 1970-01-01 UTC** (`u64`) **[propuesto: la tabla solo dice "hora UTC ms"]**.
- `Nx` es el ID fijo del nivelador, **1 a 10** (N1..N10 grabados en el firmware). `0` y `11..255` son inválidos **[propuesto: no hay ID de difusión]**.
- Primer byte de todo paquete: el **tipo**. La **versión** viaja solo en el `HB` (ver hallazgo H2).

## 2. Tipos y versión

| Código | Paquete | Dirección | Periodo / disparo | Tamaño |
|---|---|---|---|---|
| `0x01` | `HB` | M1 → difusión | cada **10 s** | 24 B + 11 B × n (n ≤ 10; 134 B con 10) |
| `0x02` | `DOCK_REQ` | M2 → M1 | botón de acople; reintentos | 4 B |
| `0x03` | `DOCK_REF` | M1 → M2 | tras resolver el cielo; reintentos | 30 B |
| `0x04` | `ACK` | ambos | ver sección 5.3 | 4 B |
| `0x05` | `STATUS` | M2 → M1 | cada **10 s** | 9 B |
| `0x06` | `ASSIGN` | M1 → M2 | inmediato al asignar | 12 B |

Versión del protocolo: **1** (`HB`, byte 1). Cualquier otro valor se rechaza. Los códigos de tipo son **[propuesto]**: la tabla no los numera.

## 3. Formato de cada paquete

Offsets en bytes desde el inicio del datagrama.

### 3.1 `HB` (24 B de cabecera + 11 B por asignación)

| Off | Tam | Tipo | Campo | Notas |
|---|---|---|---|---|
| 0 | 1 | u8 | tipo = `0x01` | |
| 1 | 1 | u8 | versión = `1` | |
| 2 | 2 | u16 | ID base | |
| 4 | 2 | u16 | secuencia | +1 por HB, con vuelta 65535 → 0 |
| 6 | 8 | u64 | hora UTC ms | instante de envío |
| 14 | 4 | i32 | latitud | 1e-7°, −900 000 000 … +900 000 000 |
| 18 | 4 | i32 | longitud | 1e-7°, −1 800 000 000 … +1 800 000 000 |
| 22 | 1 | u8 | banderas | ver 3.1.1 |
| 23 | 1 | u8 | n asignaciones | 0 … 10 |
| 24 + 11·i | 1 | u8 | Nx | 1 … 10, sin repetir dentro del HB |
| 25 + 11·i | 2 | u16 | id objetivo | |
| 27 + 11·i | 4 | **u32** | RA | 1e-7°, 0 … 3 599 999 999 (**ver H1**) |
| 31 + 11·i | 4 | i32 | Dec | 1e-7°, −900 000 000 … +900 000 000 |

Largo exacto = `24 + 11·n`. La suma de campos da 24 y 11, y 24 + 110 = **134 B** como dice la tabla (verificado).

#### 3.1.1 Banderas del HB

| Bit | Significado |
|---|---|
| 0 | base movida |
| 1 | solve OK |
| 2 | hora válida |
| 3 | ubicación válida |
| 4-7 | reservados: deben ir en 0; si no, se rechaza |

El orden de los bits **[propuesto]**: la tabla da los cuatro nombres, no las posiciones.

### 3.2 `DOCK_REQ` (4 B)

| Off | Tam | Tipo | Campo |
|---|---|---|---|
| 0 | 1 | u8 | tipo = `0x02` |
| 1 | 1 | u8 | Nx |
| 2 | 2 | u16 | secuencia (la fija el M2, +1 por acople nuevo; un reintento repite la misma) |

### 3.3 `DOCK_REF` (30 B)

| Off | Tam | Tipo | Campo | Notas |
|---|---|---|---|---|
| 0 | 1 | u8 | tipo = `0x03` | |
| 1 | 1 | u8 | Nx | |
| 2 | 2 | u16 | secuencia | la del `DOCK_REQ` que contesta |
| 4 | 8 | u64 | hora UTC ms | **instante del solve**, no de envío |
| 12 | 16 | 4 × f32 | cuaternión cámara → ENU | orden (w, x, y, z) **[propuesto]**; norma 1 ± 1e-3 **[estimado]**, sin NaN ni infinito |
| 28 | 1 | u8 | estrellas emparejadas | **0 = sin solución válida [propuesto]** |
| 29 | 1 | u8 | banderas | bit 0 = la referencia sale de una imagen de ejemplo (corrida 1, sin óptica) **[propuesto]**; bits 1-7 en 0 |

### 3.4 `ACK` (4 B)

| Off | Tam | Tipo | Campo |
|---|---|---|---|
| 0 | 1 | u8 | tipo = `0x04` |
| 1 | 1 | u8 | Nx |
| 2 | 2 | u16 | secuencia que se confirma |

### 3.5 `STATUS` (9 B)

| Off | Tam | Tipo | Campo | Notas |
|---|---|---|---|---|
| 0 | 1 | u8 | tipo = `0x05` | |
| 1 | 1 | u8 | Nx | |
| 2 | 1 | u8 | batería % | 0 … 100 |
| 3 | 1 | u8 | estado | 0 … 6 **[propuesto]**: 0 autoprueba, 1 elegir base, 2 acople, 3 montaje, 4 sync, 5 guía, 6 error grave (a partir del diagrama de la sección 5) |
| 4 | 2 | u16 | segundos desde el sync | satura en 65 535; el simulador usa 65 535 como "nunca" |
| 6 | 2 | u16 | corrección del último sync | centésimas de grado |
| 8 | 1 | u8 | calidad | 0 … 100 **[propuesto]** |

### 3.6 `ASSIGN` (12 B)

| Off | Tam | Tipo | Campo |
|---|---|---|---|
| 0 | 1 | u8 | tipo = `0x06` |
| 1 | 1 | u8 | Nx destinatario |
| 2 | 2 | u16 | id objetivo |
| 4 | 4 | **u32** | RA, 1e-7°, 0 … 3 599 999 999 (**ver H1**) |
| 8 | 4 | i32 | Dec, 1e-7° |

## 4. Reglas del receptor: qué se rechaza

Un paquete se **descarta entero** (sin cambiar ningún estado) si ocurre cualquiera de estos, evaluados en este orden. Cada uno tiene su clase de error en el codec y su vector en `vectores_dorados.txt`.

1. Datagrama vacío → `TruncatedPacket`.
2. Tipo fuera de 1..6 → `UnknownType`.
3. `HB` con versión ≠ 1 → `VersionMismatch` (se revisa **antes** que el largo: otra versión podría tener otro tamaño).
4. Menos bytes de los que exige el tipo (o que `24 + 11·n` en el HB) → `TruncatedPacket`.
5. Más bytes → `TrailingBytes`.
6. Cualquier campo fuera de rango (Nx, ángulos, batería, estado, calidad, bits reservados, Nx repetido en el HB, cuaternión no unitario o con NaN) → `InvalidField`.

Además, a nivel de comportamiento (el simulador lo implementa y lo prueba): paquete en la dirección equivocada (un HB al M1, un `DOCK_REQ` a un M2), `Nx` ajeno, `HB` de otra base mientras la actual vive, `HB` atrasado o repetido: se cuentan y se ignoran.

**Número de secuencia del HB.** Con aritmética módulo 2¹⁶, un HB cuya secuencia es la misma o una de las **8** anteriores a la última aceptada se descarta (llegó atrasado o repetido); un salto mayor hacia atrás se toma como un M1 reiniciado y se acepta. La ventana de 8 es **[propuesto]**.

## 5. Comportamiento

Los periodos de 10 s y el watchdog de 3 HB salen de la arquitectura. Todo valor marcado **[estimado: simulador]** es un parámetro del simulador, no una medición ni una decisión de diseño.

### 5.1 Heartbeat y asignaciones

- El M1 difunde un `HB` cada **10 s exactos**, con la lista completa de asignaciones vigentes (el HB es la **fuente de verdad**: si ya no nombra al M2, el M2 se queda sin objetivo).
- El M1 manda un `ASSIGN` unicast **de inmediato** al asignar. No hay `ASSIGN` de borrado: quitar una asignación se propaga solo por el siguiente HB (≤ 10 s).

### 5.2 Watchdog del M2

- Si pasan **3 periodos (30 s)** sin un HB aceptado, el M2 marca **"sin base"** como error **leve**. El reloj parte del **último HB aceptado**, o del **encendido** si nunca llegó uno. Un HB atrasado o repetido no lo reinicia.
- El M2 **sigue guiando** con el último objetivo, su sync y su propio reloj (hora del último HB + tiempo local). Si vuelve un HB, la bandera se apaga sola.
- Si la base se perdió, el M2 acepta el HB de cualquier base y reinicia su secuencia (cubre un M1 reiniciado o cambiado).

### 5.3 Acople: `DOCK_REQ` → `DOCK_REF` → `ACK`

La tabla dice que `ACK` va "ambos" pero no qué confirma. **[propuesto]**: lo determina la dirección y la secuencia.

```
M2 ──DOCK_REQ(Nx, s)──────────────▶ M1       (reintento cada 1 s [estimado], hasta 8 veces, misma s)
M2 ◀────────────ACK(Nx, s)────────── M1       confirma que recibió la petición; no vuelve a resolver
                                              el M1 resuelve el cielo (una cámara: acoples en fila)
M2 ◀────────DOCK_REF(Nx, s, …)────── M1       reintento cada 1 s [estimado], hasta 8 veces
M2 ──ACK(Nx, s)───────────────────▶ M1       confirma la referencia; el M1 deja de reenviar
```

- Un `DOCK_REQ` repetido (misma `s`) se reconfirma con `ACK` pero **no** se resuelve otra vez. Una `s` nueva descarta al acople anterior; una `s` más vieja que la actual se ignora.
- El M2 espera el `DOCK_REF` hasta 60 s **[estimado]** tras el primer ACK; debe cubrir la fila de solves de los demás M2. Si agota sus intentos: error de acople, **no se sincroniza**.
- Un `DOCK_REF` repetido se reconfirma con `ACK` pero **no se reaplica**.
- Un `DOCK_REF` que llega **después** de que el M2 se rindió se **ignora**. Es una decisión de seguridad física: la referencia vale para el instante en que el M2 estaba en la cavidad; si el usuario ya lo sacó, aplicarla daría una orientación falsa.
- `estrellas emparejadas = 0` significa que el M1 no resolvió: el M2 lo confirma con `ACK` pero **no** se sincroniza.
- La hora del `DOCK_REF` es la del solve. **No** debe usarse para poner el reloj del M2 (un reenvío llega con segundos de retraso); el reloj sale del HB.

### 5.4 STATUS

El M2 manda `STATUS` cada **10 s** una vez que oyó al menos un HB. Sin `ACK`: el siguiente lo reemplaza.

## 6. Cómo se prueba

- `pytest protocolo/` (desde la raíz del repo): ida y vuelta, bordes, rechazos, fuzz y vectores dorados.
- `vectores_dorados.txt` está armado **a mano**, byte por byte, sin usar el codec; formato en su cabecera. Las pruebas en C++ del M2 deben recorrer las mismas líneas `VALID` (decodificar y volver a codificar da los mismos bytes) y `INVALID` (rechazar).
- El comportamiento de la sección 5 lo ejercita `sim/` (ver `sim/README.md`).

## 7. Hallazgos y puntos abiertos para el arbitraje

**H1 — RA no cabe en `i32` (inconsistencia de la tabla).** La tabla dice RA y Dec como `i32` en 1e-7°. Dec (±90°) y longitud (±180°) caben, pero **RA va de 0° a 360° = 3 600 000 000 > 2 147 483 647**: un `i32` solo llega a 214.7°, la mitad del cielo. **No lo corregí en silencio**: el codec usa `u32` para RA en `HB` y `ASSIGN`, que da **los mismos bytes** que el `i32` para RA < 214.7483647°, y los vectores dorados incluyen RA = 2 147 483 648 (214.7483648°, un valor más que el máximo de un `i32`) y 3 599 999 999 (casi 360°) en el HB, y RA = 16 909 060 en el ASSIGN. Alternativa: RA como `i32` en (−180°, +180°] envuelto. Hay que decidir y actualizar la arquitectura; es un solo cambio en `euler_proto.py` (`_HB_ASG`, `_ASSIGN`, `RA_MAX_E7`).

**H2 — La versión solo viaja en el `HB`.** Los otros cinco paquetes no llevan versión. Un M2 de otra versión solo se entera por el HB. Recomendación: el M2 no manda ni acepta nada hasta aceptar un HB con su versión. El simulador no lo impone.

**H3 — `ASSIGN` no tiene secuencia ni `ACK`.** Dos consecuencias medidas en el simulador (cifras en `sim/README.md`): (a) un HB armado **antes** del ASSIGN que llega **después** lo borra hasta el siguiente HB (≤ 10 s más; reproducido en `test_h3_a_nivel_de_m2…`); (b) un `ASSIGN` perdido solo se recupera con el HB. Mitigación probada sin cambiar tamaños: tras un `ASSIGN`, el M1 manda un **HB extra** a los 50 ms **[estimado]** (agrupa ráfagas). Otra opción es añadir una secuencia al `ASSIGN` (cambia su tamaño de 12 B). No es la especificación: está tras `M1Config(hb_after_assign=True)`.

**H4 — Campos que la tabla nombra sin definir.** Los fijé así y hay que confirmarlos: posiciones de bits de las banderas del HB; banderas y significado de `estrellas = 0` en `DOCK_REF`; orden del cuaternión; códigos de `estado` y escala de `calidad` en `STATUS`; época de la hora (Unix); qué confirma cada `ACK`; códigos numéricos de tipo; ID de difusión (no hay).

**H5 — Tamaños.** Verificados sumando campos: 24 B + 11 B/asignación, 134 B con 10, 4, 30, 4, 9 y 12 B. La tabla es consistente en tamaños; la única inconsistencia de formato es H1.

**H6 — Primer HB.** Tras unirse al AP, el M2 espera hasta 10 s a su primer HB (no puede pedir uno). Si no llega ninguno en 30 s desde el encendido, declara "sin base".
