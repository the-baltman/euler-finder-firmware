// =====================================================================================
// MARCAS DEL SALÓN  (el archivo que Baltasar edita el día del armado)
// =====================================================================================
// Cada marca se mide RELATIVA A LA MARCA 1, parado en el punto donde va a quedar el nivelador:
//   giro_deg    : cuántos grados hay que girar desde la marca 1 hasta esta (+ = a la derecha).
//   altura_deg  : cuántos grados hay que subir desde la marca 1 hasta esta (+ = arriba).
//   distancia_m : distancia del pivote del nivelador a la marca, en metros (0 = no corregir).
// Cómo medirlos (cinta o transportador) está en m2/README.md.
//
// REGLAS (el programa no compila si se rompen):
//   - La primera marca es la marca 1 y es el origen: giro 0 y altura 0.
//   - Mínimo 2 marcas, máximo kMaxMarcas.
//   - |giro| <= 180 y |altura| <= 80.
//
// Las filas con ejemplo = true son VALORES DE EJEMPLO, no medidos. Cámbialos por los del salón
// y pon ejemplo = false (la pantalla muestra "ej." junto al nombre mientras sea ejemplo).
// =====================================================================================
#pragma once

namespace euler {

struct Marca {
  const char* nombre;   // corto: cabe en la pantalla redonda
  float giro_deg;       // grados, relativo a la marca 1
  float altura_deg;     // grados, relativo a la marca 1
  float distancia_m;    // m, del pivote a la marca (0 = desconocida, sin corrección de paralaje)
  bool ejemplo;         // true = valor de ejemplo, no medido
};

// Desplazamiento entre el punto de giro (pivote) y la línea de mira del nivelador, en metros.
// Con 0 no se corrige nada. Si no es 0, cada marca debe traer su distancia_m.
// + lateral = la mira queda a la derecha del pivote; + vertical = la mira queda arriba del pivote.
constexpr float OFFSET_PIVOTE_MIRA_LATERAL_M = 0.0f;
constexpr float OFFSET_PIVOTE_MIRA_VERTICAL_M = 0.0f;

constexpr int kMaxMarcas = 8;

constexpr Marca MARCAS[] = {
    // nombre        giro   altura  dist_m  ejemplo
    {"Marca 1",       0.0f,  0.0f,   5.0f,  true},   // origen: no cambiar giro ni altura
    {"Marca 2",      25.0f,  8.0f,   5.0f,  true},   // EJEMPLO
    {"Marca 3",     -18.0f, 15.0f,   5.0f,  true},   // EJEMPLO
};

constexpr int kNumMarcas = static_cast<int>(sizeof(MARCAS) / sizeof(MARCAS[0]));

constexpr bool marcasValidas() {
  if (kNumMarcas < 2 || kNumMarcas > kMaxMarcas) return false;
  if (MARCAS[0].giro_deg != 0.0f || MARCAS[0].altura_deg != 0.0f) return false;
  for (int i = 0; i < kNumMarcas; i++) {
    float g = MARCAS[i].giro_deg;
    float a = MARCAS[i].altura_deg;
    if (g > 180.0f || g < -180.0f || a > 80.0f || a < -80.0f) return false;
    if (MARCAS[i].distancia_m < 0.0f) return false;
  }
  return true;
}

static_assert(marcasValidas(),
              "marcas.h: la marca 1 debe ser 0,0; entre 2 y 8 marcas; |giro|<=180, |altura|<=80, distancia>=0");

}  // namespace euler
