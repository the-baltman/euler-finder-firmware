# M2 - Nivelador de EULER finder (demo JIJE)

Firmware del nivelador: una pantalla redonda y un IMU te guian para apuntar el equipo hacia las marcas del salon. No necesita internet, GPS ni magnetometro.

Este README es para armarlo y dejarlo funcionando. Lo que dice "[por verificar]" no se ha probado con las piezas reales.

**Alcance de la demo.** El nivelador guia hacia marcas medidas de antemano en el salon. No localiza estrellas ni da cifras de precision; la pantalla no muestra ninguna.

## 1. Alimentacion (leelo antes de conectar nada)

**USB y bateria nunca van conectados al mismo tiempo.** Los dos entran por el mismo pin 3V3 (el regulador de la placa y el buck-boost TPS63020) y se pelean.

| Situacion | Permitido |
|---|---|
| Programar por USB-C | Solo con SW1 en OFF y la bateria desconectada de la placa |
| Cargar la Li-Po | Con SW1 en OFF |
| Monitor serie | Por USB-C, con SW1 en OFF |
| Demo | Solo bateria (SW1 ON, sin cable USB) |

Regla simple: o USB, o bateria. Si cambias de una a otra, primero apaga SW1 y desconecta la fuente anterior.

> **La bateria nadie la vigila.** El firmware no mide la Li-Po y el convertidor sigue funcionando hasta que la
> celda esta casi vacia. Antes de cada sesion mide la celda con el multimetro (SW1 en OFF, en su conector): si
> esta cerca de 3.5 V, cargala; bajo ~3.3 V no se usa. Carga siempre vigilada, sobre una superficie que no arda,
> nunca tapada ni dentro de una mochila. Con el plan B (Li-Po al pin 5V) la regla de USB y bateria es la misma.
> Detalle: nota de electronica `demo-jije.md`, secciones 3.2, 3.4, 5 y 6.

## 2. Instalar y compilar

Necesitas Python 3 (ya lo tienes si corres los scripts del proyecto) e internet la primera vez.

```
pip install --user platformio
cd C:\Users\Baltman\Documents\Arduino\euler-finder-firmware
python -m platformio run -d m2
```

La primera compilacion descarga el framework y las librerias (Adafruit GFX y GC9A01A): tarda varios minutos. Las siguientes son rapidas. Debe terminar en `SUCCESS` sin avisos.

Las versiones estan fijadas en `platformio.ini` y no hay que actualizarlas: el codigo usa la API 2.x de Arduino-ESP32 (`ledcSetup`/`ledcAttachPin`) y una plataforma mas nueva ya no compilaria este commit.

| Componente | Version fijada |
|---|---|
| Plataforma `espressif32` (trae Arduino-ESP32 2.0.17) | 7.1.3 |
| Adafruit GFX Library | 1.12.6 |
| Adafruit GC9A01A | 1.1.0 |
| Adafruit BusIO | 1.17.4 |

Alternativa con ventanas: en VS Code instala la extension "PlatformIO IDE", abre la carpeta `m2` y usa el boton de la palomita (Build) y la flecha (Upload) de la barra de abajo.

La placa es la ESP32-C3 SuperMini. PlatformIO no la tiene como tal, asi que `platformio.ini` usa `esp32-c3-devkitm-1` (mismo chip). Con `ARDUINO_USB_CDC_ON_BOOT=1` el `Serial` sale por el USB-C de la placa.

## 3. Flashear desde Windows (BOOT + USB)

1. SW1 en OFF y bateria desconectada de la placa.
2. Mantén presionado **BOOT** en la SuperMini.
3. Sin soltarlo, conecta el cable USB-C a la computadora.
4. Suelta BOOT. La placa queda en modo de descarga y Windows crea un puerto COM nuevo (Administrador de dispositivos > Puertos).
5. Sube el programa:
   ```
   python -m platformio run -d m2 -t upload --upload-port COM5
   ```
   Cambia `COM5` por el tuyo. Si no pones `--upload-port` PlatformIO intenta detectarlo solo.
6. Cuando termine, presiona **RST** (o desconecta y vuelve a conectar el USB) para que arranque el programa.

Si el flasheo falla con "Failed to connect", repite desde el paso 2: casi siempre es que BOOT no estaba presionado al conectar.

Ver lo que imprime el equipo (ayuda para las pruebas de abajo):
```
python -m platformio device monitor -d m2
```
Si el monitor no abre, el numero de COM cambio despues de reiniciar: ejecuta `python -m platformio device list` y usa `--port COMx`. Para salir: Ctrl+C.

## 4. Paso 0 - Prueba de ejes (una sola vez, con el IMU ya montado en la caja)

El modulo IMU puede estar soldado girado respecto a la caja, y el firmware no lo puede adivinar. Esta prueba lo confirma.

Convencion de la caja (la usa `kImuAxisMap` en `src/config/pins.h`): x = derecha de la pantalla, y = arriba de la pantalla, z = sale de la pantalla hacia ti.

1. Abre el monitor serie (seccion 3) y deja el equipo quieto sobre la mesa mientras la pantalla dice "Midiendo" (unos 3 s).
2. Cuando pase a "Marca 1" veras lineas cada medio segundo:
   ```
   [pose] giro=12.3 altura=-4.1 marca=0 estado=2
   ```
3. Sin pulsar nada mas, mueve el equipo:
   - Sube el punto de mira: en montaje plano es el borde superior de la pantalla, en montaje vertical (como un celular) es la parte trasera. **`altura` debe subir.**
   - Gira el equipo hacia tu derecha, sobre su propio eje, sin inclinarlo. **`giro` debe subir.**
   - Inclinar no debe mover mucho `giro`, y girar no debe mover mucho `altura`.
4. Si algo sube cuando debia bajar, invierte el signo de ese eje en `kImuAxisMap` (`sign`: +1 a -1). Si inclinar mueve `giro` y girar mueve `altura`, los ejes estan cruzados: cambia el orden en `idx` (0 = x del chip, 1 = y, 2 = z). Ejemplo: `{{1, 0, 2}, {+1, -1, +1}}`.
5. Recompila, flashea y repite hasta que las tres comprobaciones salgan bien.

Si la pantalla elige el montaje equivocado (plano vs vertical), tambien es sintoma de un eje z mal asignado: corrige primero `kImuAxisMap`. [por verificar con el IMU real: el orden de ejes depende del modulo]

La primera vez, aprovecha para comprobar la autoprueba: en el monitor sale `[autoprueba] ok=1 id=0x71 ...`. Un `id` distinto con `ok=1` es un posible clon (la pantalla lo avisa y el equipo sigue). `0x71` es lo esperado para el MPU-9250 [por verificar].

## 5. Medir las marcas y escribir `marcas.h`

Archivo: `m2/src/config/marcas.h`. Cada marca se mide **relativa a la marca 1**, desde el punto exacto donde va a quedar el nivelador en la demo.

Para cada marca necesitas:

| Campo | Que es |
|---|---|
| `giro_deg` | Grados que hay que girar desde la marca 1 hasta esta (+ = a la derecha) |
| `altura_deg` | Grados que hay que subir desde la marca 1 (+ = arriba) |
| `distancia_m` | Distancia en metros del pivote del nivelador a la marca (0 = desconocida, sin correccion) |

La marca 1 es el origen: `giro 0, altura 0`. El programa no compila si no es asi, ni con menos de 2 o mas de 8 marcas.

### Donde poner las marcas y como girar

- Pon las marcas **lo mas lejos que permita el salon: 10 m ideal, 5 m minimo.** Entre mas lejos, menos pesa cualquier error de medicion de tu cinta o de donde apoyas el equipo.
- Al medir y en la demo, el nivelador **se gira sobre su propio eje** (el pivote, p. ej. un tornillo o una base giratoria). No lo gires con el brazo extendido: eso mueve el punto de giro y cambia los angulos que mediste.
- El nivelador queda fijo en el mismo lugar que al medir. Marca el punto en el piso con cinta.

### Medir con cinta (funciona sin transportador)

1. Marca en el piso el punto del pivote. Define tus ejes: `x` a la derecha, `y` hacia adelante (hacia donde miras la marca 1), `z` hacia arriba.
2. Con la cinta mide, para cada marca, su posicion respecto al pivote: `x`, `y` (a lo largo del piso) y `z` (altura de la marca respecto a la altura de la mira del nivelador). Todo en metros.
3. Calcula (la marca 1 es la de referencia):
   ```
   giro_i    = atan2(x_i, y_i) - atan2(x_1, y_1)              [grados]
   altura_i  = atan2(z_i, sqrt(x_i^2 + y_i^2)) - atan2(z_1, sqrt(x_1^2 + y_1^2))
   distancia = sqrt(x_i^2 + y_i^2 + z_i^2)                    [m]
   ```
   Con Python: `import math; math.degrees(math.atan2(x, y))`.
4. Si prefieres transportador o una app de nivel, vale igual mientras midas desde el pivote y relativo a la marca 1.

### Ejemplo de `marcas.h`

```cpp
constexpr Marca MARCAS[] = {
    // nombre        giro   altura  dist_m  ejemplo
    {"Pizarron",      0.0f,  0.0f,   9.5f,  false},  // origen: giro y altura en 0
    {"Puerta",       25.0f,  8.0f,   7.2f,  false},
    {"Ventana",     -18.0f, 15.0f,   8.8f,  false},
};
```
Mientras `ejemplo = true` la pantalla escribe "ej." junto al nombre. **Los valores que trae el archivo son de ejemplo, no del salon: cambialos todos y pon `ejemplo = false`.** Nombres cortos y sin tildes: cabe poco en la pantalla redonda.

### `distancia_m` y los offsets del pivote (paralaje)

El punto donde gira el nivelador (pivote) no es el mismo que la linea de mira. Esa diferencia, vista desde cerca, cambia el angulo real a cada marca; vista desde lejos casi desaparece. El firmware puede corregirlo:

1. Mide con la cinta el desplazamiento del centro de la linea de mira respecto al pivote, en metros:
   - `OFFSET_PIVOTE_MIRA_LATERAL_M`: positivo si la mira queda a la derecha del pivote.
   - `OFFSET_PIVOTE_MIRA_VERTICAL_M`: positivo si la mira queda arriba del pivote.
2. Escribelos en `marcas.h`. Con `0` y `0` no se corrige nada (valor por defecto).
3. Si los usas, **todas las marcas necesitan su `distancia_m`** (incluida la marca 1). Si a alguna le falta (0), el firmware no corrige esa marca.

Para un offset chico y marcas lejanas la correccion es poca; por eso conviene medir lejos y dejar los offsets en 0 si la mira cae casi sobre el pivote.

Despues de editar `marcas.h`: compila y flashea de nuevo (seccion 2 y 3).

## 6. La demo en 5 pasos

Botones: **A** y **B**. Pulsacion larga = 1 s.

1. **Mide la celda** (seccion 1) y **enciende** (SW1 ON, solo bateria) con el equipo **quieto sobre una superficie**. Salen el logo y la autoprueba ("IMU OK", "Pantalla OK").
2. **Espera "Midiendo"** (unos 3 s, no lo muevas). El anillo se llena y el equipo mide solo su desviacion en reposo. Si lo mueves, el anillo no avanza hasta que vuelva a estar quieto.
3. **Apunta a la marca 1 y manten B 1 s.** La pantalla dice "Marca 1" y "Apunta y sujeta B"; el anillo se llena y sale "Sync listo". El equipo ahora sabe donde esta la marca 1.
4. **Sigue la guia hacia la marca 2.** Lejos de la marca ves una flecha y la estrella en el borde; cerca, las escalas (giro abajo, altura a la derecha) y la estrella se acerca al centro. Cuando sale **"EN MIRA"** estas apuntando a la marca.
5. **A (corta) pasa a la siguiente marca**, y asi en ciclo. A larga (1 s) alterna modo noche (opcional). Para empezar de cero, mantén **A+B 3 s**: borra el sync y vuelve a medir.

Notas de uso:
- Presionar B mueve un poco el equipo; por eso el sync promedia las ultimas muestras (0.2 s) en vez de usar una sola. Aun asi, sujetalo firme sobre la marca 1 mientras presionas.
- El rumbo se mantiene solo con el giroscopio (sin brujula), asi que **se va desviando con el tiempo y con mucho movimiento**. Si la estrella deja de coincidir con las marcas, vuelve a apuntar a la marca 1 y manten B otra vez.
- Cerca del cenit (altura cercana a 90) el giro pierde sentido; la demo no necesita marcas ahi.
- Los umbrales de la guia (cuando dice "EN MIRA", que tan lejos es "lejos") estan en `src/config/tuning.h` marcados [estimado]: se ajustan en el salon.

## 7. Si algo falla

| Sintoma | Que revisar |
|---|---|
| **Pantalla negra** | 1) Lo primero: ¿imprime el monitor serie `[fase] ...`? Si si, el programa corre y el problema es la pantalla; si no, es alimentacion o flasheo. 2) Alimentacion 3V3 y GND del modulo. 3) Luz de fondo: BL en GPIO3. 4) Conexiones SPI: **SCL del modulo va a GPIO6 (reloj SPI)** y **SDA a GPIO7**; no es I2C. CS=GPIO10, DC=GPIO4, RST=GPIO5. 5) Si la imagen sale corrupta, baja `kTftSpiHz` en `src/config/pins.h`. [por verificar con la pantalla] |
| **"IMU no responde / Revisa SDA y SCL"** | SDA=GPIO0, SCL=GPIO1 (no los pines I2C por defecto de Arduino). Revisa 3V3 y GND del IMU, soldaduras, (el firmware prueba las direcciones I2C 0x68 y 0x69). Pulsa A o B para repetir la autoprueba. |
| **"IMU con datos raros / Puede ser clon malo"** | El IMU responde pero con datos que no son creibles (gravedad absurda o giroscopio en cero exacto). Cambia el modulo. |
| **"IMU se desconecto"** | Cable suelto durante el uso (vibracion). Revisa SDA, SCL y alimentacion; A o B reintenta. |
| **"Posible clon (ID xx)"** | El chip contesta con un ID distinto de los conocidos pero con datos creibles: el equipo sigue funcionando; ojo con que el comportamiento puede variar. |
| **Se queda en "Midiendo"** | Se esta moviendo. Apoyalo quieto (a los 8 s sale el aviso "Apoyalo quieto"). |
| **No flashea** | BOOT al conectar el USB (seccion 3), cable USB con datos (no solo carga), SW1 en OFF. |
| **Se reinicia solo** | La tarea de control se colgo y el equipo se reinicia solo. Si se bloqueo, sale `[error] la tarea de control no responde, reiniciando` (la vigilancia del loop, a los 3 s). Si se quedo en un bucle activo, sale `Task watchdog got triggered` (el TWDT del SDK, a los 5 s). Guarda el mensaje y avisa. [por verificar en banco: ver la prueba de cuelgue en la seccion 8] |
| **El monitor no muestra nada** | Reabre el monitor despues de reiniciar la placa (el puerto USB se reconecta). |

## 8. Pruebas en la computadora (sin hardware)

La logica (fusion, sync, guia, botones, marcas) se prueba en Windows sin la placa:
```
python m2/test/host/run_host_tests.py     # 7 pruebas, deben pasar todas
python m2/test/host/mutate.py             # rompe el codigo a proposito: todos los mutantes deben morir
```
Necesitan un compilador de C++ (g++) en el PATH.

### Prueba de cuelgue (con la placa) [por verificar en banco]

Comprueba que el equipo se reinicia solo si la tarea de control se cuelga. Hay dos entornos de prueba; cada uno se cuelga a proposito a los 15 s del arranque.

1. Bloqueo de la tarea: `python -m platformio run -d m2 -e prueba-cuelgue -t upload`. Con el monitor abierto, a unos 18 s debe salir `[error] la tarea de control no responde, reiniciando` y volver el logo.
2. Bucle activo: `python -m platformio run -d m2 -e prueba-cuelgue-activo -t upload`. A unos 20 s debe salir `Task watchdog got triggered` (panic del SDK) y volver el logo.
3. Al terminar, vuelve a flashear el entorno normal: `python -m platformio run -d m2 -t upload`. Los entornos de prueba no se dejan en el equipo de la demo.

## 9. Mapa de archivos

| Que | Donde |
|---|---|
| Pines, bus I2C/SPI, `kImuAxisMap` | `src/config/pins.h` |
| Marcas del salon, offsets | `src/config/marcas.h` |
| Umbrales y tiempos de la guia | `src/config/tuning.h` |
| Fusion, sync, guia, botones (logica pura) | `src/core/` |
| Controladores de IMU y pantalla | `src/drivers/` |
| Pantallas | `src/ui/` |
| Pruebas de la computadora | `test/host/` |
| Configuracion de PlatformIO | `platformio.ini` |
