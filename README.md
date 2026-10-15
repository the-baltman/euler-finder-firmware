# EULER finder: firmware y software

Código del sistema EULER finder: una estación base que resuelve el cielo con plate solving y niveladores que guían a cada telescopio hacia su objetivo. Uno encuentra, todos apuntan.

| Carpeta | Qué contiene |
|---|---|
| `protocolo/` | Especificación de los paquetes entre la base (M1) y los niveladores (M2), codec de referencia en Python y pruebas |
| `m1/` | Estación base en Raspberry Pi 5 (Python): autoprueba, plate solving, ciclos, red, BLE, efemérides, anillo LED, registro |
| `m2/` | Nivelador en ESP32-C3 (PlatformIO): IMU, fusión, calibración (acople y sync), pantalla guía GC9A01, botones, red |
| `sim/` | Base y nivelador simulados en PC para probar el protocolo sin hardware |

Estado: corrida 1 en desarrollo (octubre 2026). La óptica de la estación todavía no existe, así que el M1 se prueba con imágenes de ejemplo y cielo sintético. Ninguna cifra de precisión está medida todavía.

Proyecto de Baltasar Zamudio Zavala y Joshua Salinas Zarco, Ingeniería en Mecatrónica, UVAQ, Morelia, México.
