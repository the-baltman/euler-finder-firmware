# Protocolo M1 ↔ M2 de EULER finder: especificación (versión 1)

Fuente única de los tamaños, campos y periodos: `Architecture/Operacion/arquitectura-operativa.md` del repo de notas (v2), secciones 4 y 6. Este documento convierte esa tabla en bytes exactos y fija lo que la tabla no decía. Lo que la tabla no decía lo arbitró `c-morty` el 2026-10-15 (sección 7) y va marcado **[decidido: arbitraje c-morty 2026-10-15]**; los valores que son parámetros del simulador van como **[estimado]**.

Implementación de referencia: `euler_proto.py` (Python). Vectores dorados: `vectores_dorados.txt`. El M2 (C++) debe producir y rechazar exactamente los mismos bytes.

## 1. Convenciones

- **Little-endian**, sin relleno entre campos. Un datagrama UDP = un paquete.
- Enteros sin signo `u8/u16/u32/u64`; con signo `i32`; decimal `f32` IEEE-754.
- Ángulos: enteros en unidades de **1e-7 grado**. Hora: **ms desde 1970-01-01 UTC** (`u64`) **[decidido: arbitraje c-morty 2026-10-15]: época Unix en ms, UTC, sin segundos intercalares**.
- `Nx` es el ID fijo del nivelador, **1 a 10** (N1..N10 grabados en el firmware). `0` y `11..255` son inválidos **[decidido: arbitraje c-morty 2026-10-15]: no hay ID de difusión**.
- Primer byte de todo paquete: el **tipo**. La **versión** viaja solo en el `HB`, con tres reglas [decidido: arbitraje c-morty 2026-10-15]:
  1. El M2 no manda `DOCK_REQ` ni `STATUS` hasta aceptar un `HB` de su versión.
  2. Los códigos de tipo 1 a 6 quedan congelados con su formato v1. Un cambio de formato en un paquete que no sea `HB` usa un **código de tipo nuevo**: el byte de tipo hace de versión para los paquetes cortos.
  3. Si el M2 está "sin base" y descartó algún `HB` por `VersionMismatch` en los últimos 30 s, el mensaje al usuario es "base de otra versión", no "sin base". (Solo la especificación lo pide: el simulador no lo necesita.)

## 2. Tipos y versión

| Código | Paquete | Dirección | Periodo / disparo | Tamaño |
|---|---|---|---|---|
| `0x01` | `HB` | M1 → difusión | cada **10 s** | 24 B + 11 B × n (n ≤ 10; 134 B con 10) |
| `0x02` | `DOCK_REQ` | M2 → M1 | botón de acople; reintentos | 4 B |
| `0x03` | `DOCK_REF` | M1 → M2 | tras resolver el cielo; reintentos | 30 B |
| `0x04` | `ACK` | ambos | ver sección 5.3 | 4 B |
| `0x05` | `STATUS` | M2 → M1 | cada **10 s** | 9 B |
| `0x06` | `ASSIGN` | M1 → M2 | inmediato al asignar | 12 B |

Versión del protocolo: **1** (`HB`, byte 1). Cualquier otro valor se rechaza. Los códigos de tipo 1-6 son [decidido: arbitraje c-morty 2026-10-15] (la tabla no los numera) y están congelados (sección 1, regla 2).

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
| 27 + 11·i | 4 | **u32** | RA | 1e-7°, 0 … 3 599 999 999 (RA `u32`, [decidido: arbitraje c-morty 2026-10-15]) |
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

Las posiciones de los bits son [decidido: arbitraje c-morty 2026-10-15]: la tabla da los cuatro nombres, no las posiciones.

### 3.2 `DOCK_REQ` (4 B)

| Off | Tam | Tipo | Campo |
|---|---|---|---|
| 0 | 1 | u8 | tipo = `0x02` |
| 1 | 1 | u8 | Nx |
| 2 | 2 | u16 | secuencia (la fija el M2, +1 por acople nuevo; un reintento repite la misma; arranca en un valor aleatorio, ver sección 4) |

### 3.3 `DOCK_REF` (30 B)

| Off | Tam | Tipo | Campo | Notas |
|---|---|---|---|---|
| 0 | 1 | u8 | tipo = `0x03` | |
| 1 | 1 | u8 | Nx | |
| 2 | 2 | u16 | secuencia | la del `DOCK_REQ` que contesta |
| 4 | 8 | u64 | hora UTC ms | **instante del solve**, no de envío |
| 12 | 16 | 4 × f32 | cuaternión cuerpo del M2 (cavidad) → ENU | orden (w, x, y, z) **[decidido: arbitraje c-morty 2026-10-15]**; norma 1 ± 1e-3 **[estimado]**, sin NaN ni infinito |
| 28 | 1 | u8 | estrellas emparejadas | **0 = sin solución válida** [decidido: arbitraje c-morty 2026-10-15] |
| 29 | 1 | u8 | banderas | bit 0 = la referencia sale de una imagen de ejemplo (corrida 1, sin óptica) [decidido: arbitraje c-morty 2026-10-15]; bits 1-7 en 0 |

**Convención del cuaternión** [decidido: arbitraje c-morty 2026-10-15]:

- Hamilton, escalar primero, rotación activa: `v_ENU = q ⊗ (0, v) ⊗ q*`.
- ENU: x = Este, y = Norte, z = Arriba.
- **Marco de origen: el cuerpo del M2 acoplado (la cavidad), no la cámara.** Ejes del cuerpo: +X a la derecha de la pantalla, +Y en el borde superior (eje de apuntado), +Z saliendo de la pantalla.
- El M1 compone `q = q_ENU←cám ⊗ q_cám←cavidad`. La calibración fija `q_cám←cavidad` es de cada M1 y vive en el M1: los M2 se intercambian entre bases y cada caja de M1 monta su cámara a su manera, así que el M2 no puede conocerla.
- La norma se calcula en doble precisión sobre los cuatro valores f32 recibidos; el M2 renormaliza antes de usarlo.

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
| 3 | 1 | u8 | estado | 0 … 6 [decidido: arbitraje c-morty 2026-10-15]: 0 autoprueba, 1 elegir base, 2 acople, 3 montaje, 4 sync, 5 guía, 6 error grave (a partir del diagrama de la sección 5) |
| 4 | 2 | u16 | segundos desde el sync | 0 … 65 534, satura en 65 534; 65 535 = nunca [decidido: arbitraje c-morty 2026-10-15] |
| 6 | 2 | u16 | corrección del último sync | centésimas de grado |
| 8 | 1 | u8 | calidad | 0 … 100 [decidido: arbitraje c-morty 2026-10-15]; 0 = sin sync. La correspondencia residuo → calidad la fija el firmware del M2 con los datos de la prueba B |

### 3.6 `ASSIGN` (12 B)

| Off | Tam | Tipo | Campo |
|---|---|---|---|
| 0 | 1 | u8 | tipo = `0x06` |
| 1 | 1 | u8 | Nx destinatario |
| 2 | 2 | u16 | id objetivo |
| 4 | 4 | **u32** | RA, 1e-7°, 0 … 3 599 999 999 (RA `u32`, [decidido: arbitraje c-morty 2026-10-15]) |
| 8 | 4 | i32 | Dec, 1e-7° |

## 4. Reglas del receptor: qué se rechaza

Un paquete se **descarta entero** (sin cambiar ningún estado) si ocurre cualquiera de estos, evaluados en este orden. Cada uno tiene su clase de error en el codec y su vector en `vectores_dorados.txt`.

1. Datagrama vacío → `TruncatedPacket`.
2. Tipo fuera de 1..6 → `UnknownType`.
3. `HB` con versión ≠ 1 → `VersionMismatch` (se revisa **antes** que el largo: otra versión podría tener otro tamaño).
4. `HB` con n > 10 → `InvalidField`, **antes** de revisar el largo (evita desbordes al calcular 24 + 11·n y escribir fuera del arreglo en C++).
5. Menos bytes de los que exige el tipo (o que `24 + 11·n` en el HB) → `TruncatedPacket`.
6. Más bytes → `TrailingBytes`.
7. Cualquier campo fuera de rango (Nx, ángulos, batería, estado, calidad, bits reservados, Nx repetido en el HB, cuaternión no unitario o con NaN) → `InvalidField`.

Además, a nivel de comportamiento (el simulador lo implementa y lo prueba): paquete en la dirección equivocada (un HB al M1, un `DOCK_REQ` a un M2), `Nx` ajeno, `HB` de otra base mientras la actual vive, `HB` atrasado o repetido: se cuentan y se ignoran.

**Número de secuencia del HB.** Con aritmética módulo 2¹⁶, un HB cuya secuencia es la misma o una de las **8** anteriores a la última aceptada se descarta (llegó atrasado o repetido); un salto mayor hacia atrás se toma como un M1 reiniciado y se acepta. La ventana de 8 es [decidido: arbitraje c-morty 2026-10-15].

**Arranque de las secuencias.** El M1 arranca su secuencia de HB, y el M2 la de acople, en un valor aleatorio (`esp_random()` en el M2) [decidido: arbitraje c-morty 2026-10-15] (recomendado): defensa en profundidad para un M2 que se reinicia (sección 5.3).

## 5. Comportamiento

Los periodos de 10 s y el watchdog de 3 HB salen de la arquitectura. Todo valor marcado **[estimado: simulador]** es un parámetro del simulador, no una medición ni una decisión de diseño.

### 5.1 Heartbeat y asignaciones

- El M1 difunde un `HB` cada **10 s exactos**, con la lista completa de asignaciones vigentes.
- El M1 manda un `ASSIGN` unicast **de inmediato** al asignar. No hay `ASSIGN` de borrado: quitar una asignación se propaga por el HB.
- Tras cualquier cambio de asignaciones (asignar o quitar), el M1 manda un HB extra a los 50 ms **[estimado]**; varios cambios en esa ventana salen en un solo HB. El HB periódico no se corre.
- **Regla de objetivo del M2** (por flanco y por `target_id`, nunca por valor):
  - Un `ASSIGN` propio **siempre** se aplica: `asignado = objetivo = ASSIGN` y el objetivo deja de ser local.
  - Con cada HB aceptado, `nuevo` es la entrada de mi Nx, o ninguna. Si el `target_id` de `nuevo` es distinto del de `asignado` (aparecer o desaparecer cuenta como cambio): `asignado = nuevo`; si `nuevo` existe, es el objetivo y deja de ser local; si no existe y el objetivo no es local, el M2 se queda sin objetivo.
  - Si el `target_id` es el mismo y el objetivo no es local, el objetivo se refresca con `nuevo` (RA y Dec cambian: el M1 recalcula la Luna y los planetas). Si es local, no se toca.
  - `asignado` se borra al encender y cuando cambia el `base_id`; **no** cuando vuelve la misma base.
- La elección con botones es local en v1: el M1 no la conoce (`STATUS` no lleva objetivo). Llevarla al M1 es para v2, con un código de tipo nuevo.

### 5.2 Watchdog del M2

- Si pasan **3 periodos (30 s)** sin un HB aceptado, el M2 marca **"sin base"** como error **leve**. El reloj parte del **último HB aceptado**, o del **encendido** si nunca llegó uno. Un HB atrasado o repetido no lo reinicia.
- El M2 **sigue guiando** con el último objetivo, su sync y su propio reloj (hora del último HB + tiempo local). Si vuelve un HB, la bandera se apaga sola.
- Si la base se perdió, el M2 acepta el HB de cualquier base y reinicia su secuencia (cubre un M1 reiniciado o cambiado).

### 5.3 Acople: `DOCK_REQ` → `DOCK_REF` → `ACK`

La tabla dice que `ACK` va "ambos" pero no qué confirma. [decidido: arbitraje c-morty 2026-10-15]: lo determina la dirección y la secuencia.

```
M2 ──DOCK_REQ(Nx, s)──────────────▶ M1       (reintento cada 1 s [estimado], hasta 8 veces, misma s)
M2 ◀────────────ACK(Nx, s)────────── M1       confirma que recibió la petición; no vuelve a resolver
                                              el M1 resuelve el cielo (una cámara: acoples en fila)
M2 ◀────────DOCK_REF(Nx, s, …)────── M1       reintento cada 1 s [estimado], hasta 8 veces
M2 ──ACK(Nx, s)───────────────────▶ M1       confirma la referencia; el M1 deja de reenviar
```

- Un `DOCK_REQ` con la secuencia del acople **en curso** (en cola, resolviendo o esperando ACK) se reconfirma con `ACK` y no se resuelve otra vez. Uno **más viejo** que el acople en curso se ignora. En cualquier otro caso (no hay acople, el anterior ya cerró, con cualquier secuencia, o la secuencia es más nueva) es un acople nuevo. Así, un M2 que se reinicia y vuelve a contar desde su valor de arranque se acopla al primer intento. Si se reinició **durante** un acople, su primer intento puede fallar, acotado a 8 × 1 s.
- El M2 espera el `DOCK_REF` hasta 60 s **[estimado]** tras el primer ACK; debe cubrir la fila de solves de los demás M2. Si no llega, error de acople; no reenvía `DOCK_REQ`. Peor caso: 8 × 1 s sin ACK, o ACK + 60 s. Si agota sus intentos: error de acople, **no se sincroniza**.
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

## 7. Decisiones del arbitraje (c-morty, 2026-10-15)

**H1 — RA es `u32` en [0, 3 599 999 999], en 1e-7°.** Dec sigue en `i32`. La tabla decía `i32`, que solo llega a 214.7° (la mitad del cielo). RA es un ángulo de 0 a 360° por convención; con signo habría que envolver en ambos extremos y el corte de ±180° caería a mitad del cielo, donde un error de signo en C++ se ve como un objetivo válido. Para RA < 214.748°, `u32` produce los mismos bytes que el `i32` de la tabla. Los vectores dorados ejercitan RA > 2³¹ en el HB (`hb_dos_asignaciones`) y en el `ASSIGN` (`assign_ra_alta`). *Descartado:* RA firmado en (−180°, 180°], por cambiar la semántica de un campo que todos leen como "0 a 24 h".

**H2 — La versión solo viaja en el `HB`; se queda así, con tres reglas** (sección 1). *Descartado:* un byte de versión en los seis paquetes, porque cambia los seis tamaños de la tabla y no da nada que no dé la regla 2.

**H3 — `ASSIGN` sin secuencia ni `ACK`; se queda en 12 B y el HB extra es la especificación** (sección 5.1). La carrera es real en el aire: con modem sleep sincronizado al DTIM, el AP retiene el broadcast hasta el siguiente DTIM, mientras que el unicast se entrega cuando el M2 lo pide, así que un HB viejo puede llegar después del `ASSIGN`. Con el HB extra, el hueco es de unos 50 ms; solo si se pierden el `ASSIGN` y el HB extra hay que esperar el siguiente HB (≤ 10 s). El M2 sigue guiando sin base: lo peor que pasa es guiar el objetivo anterior durante un periodo, a la vista del usuario y sin riesgo físico. Cifras medidas: `sim/README.md`. *Descartado:* época o secuencia en `ASSIGN` (14 B): no arregla el `ASSIGN` perdido, que es el caso dominante con pérdida, y arreglarlo exige ACK y reintentos con estado nuevo en los dos lados.

**H4 — Campos que la tabla nombra sin definir.** Quedan confirmados como [decidido: arbitraje c-morty 2026-10-15]: bits 0-3 de las banderas del HB; bit 0 del `DOCK_REF` = imagen de ejemplo y `estrellas = 0` = sin solución; orden (w, x, y, z) del cuaternión; estado 0-6 y calidad 0-100 en `STATUS`; época Unix en ms (UTC); `ACK` por dirección y secuencia; códigos de tipo 1-6; sin ID de difusión; ventana de secuencia del HB de 8. Se agregan: la convención y el marco del cuaternión (3.3), `segundos desde el sync` saturando en 65 534 con 65 535 = nunca (3.5), `calidad = 0` = sin sync (3.5) y el arranque aleatorio de las secuencias (4). *Descartado:* cuaternión "cámara → ENU" literal con la calibración en el M2, porque los M2 se intercambian entre bases y no pueden conocerla.

**H5 — Tamaños.** Verificados sumando campos: 24 B + 11 B/asignación, 134 B con 10, 4, 30, 4, 9 y 12 B. La tabla es consistente en tamaños; la única inconsistencia de formato era H1 (decidida arriba).

**H6 — Primer HB.** Tras unirse al AP, el M2 espera hasta 10 s a su primer HB (no puede pedir uno). Si no llega ninguno en 30 s desde el encendido, declara "sin base".
