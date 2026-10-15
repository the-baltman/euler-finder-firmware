// Guía (giro y altura hacia la marca, estados con histéresis), marcas con paralaje, sync y montaje.
#include <random>
#include "check.h"
#include "../../src/core/guide.h"
#include "../../src/core/marks.h"
#include "../../src/core/mount.h"
#include "../../src/core/sync.h"

using namespace euler;

static void testErrorsAndSigns() {
  Guide g;
  Pointing ref{100, 5};
  Target t{25, 8};
  // Exactamente sobre la marca 1: faltan 25 a la derecha y 8 arriba.
  GuideOut o = g.update({100, 5}, ref, t);
  CHECK_NEAR(o.d_giro_deg, 25, 1e-4);
  CHECK_NEAR(o.d_alt_deg, 8, 1e-4);
  CHECK_NEAR(o.dist_deg, std::sqrt(25.0 * 25 + 8 * 8), 1e-3);
  // Ya pasado de la marca (a la derecha y arriba): hay que regresar (negativo).
  o = g.update({130, 20}, ref, t);
  CHECK(o.d_giro_deg < 0 && o.d_alt_deg < 0);
  // Envoltura: marca 1 en 170°, +25 -> 195° = -165°; desde 170 faltan +25 (no -335).
  Guide g2;
  o = g2.update({170, 0}, {170, 0}, {25, 0});
  CHECK_NEAR(o.d_giro_deg, 25, 1e-4);
  // Cruzando el 180 del otro lado
  o = g2.update({-175, 0}, {170, 0}, {25, 0});
  CHECK_NEAR(o.d_giro_deg, 10, 1e-3);
  // Objetivo en la misma marca 1: cero.
  o = g2.update({50, 3}, {50, 3}, {0, 0});
  CHECK_NEAR(o.dist_deg, 0, 1e-6);
}

static void testArrowAndStar() {
  Guide g;
  Pointing ref{0, 0};
  GuideOut o = g.update({0, 0}, ref, {20, 0});  // objetivo a la derecha
  CHECK_NEAR(o.arrow_rad, 0, 1e-4);
  CHECK(o.star_x_px > 0);
  CHECK_NEAR(o.star_y_px, 0, 1e-3);
  CHECK(o.giro_ptr > 0);
  o = g.update({0, 0}, ref, {0, 20});  // objetivo arriba
  CHECK_NEAR(o.arrow_rad, 3.14159265 / 2, 1e-4);
  CHECK(o.star_y_px < 0);  // en pantalla "arriba" es y negativo
  CHECK(o.alt_ptr > 0);
  o = g.update({0, 0}, ref, {-20, 0});  // objetivo a la izquierda
  CHECK(std::fabs(o.arrow_rad) > 3.14159 - 1e-3);
  CHECK(o.star_x_px < 0 && o.giro_ptr < 0);
  o = g.update({0, 0}, ref, {0, -20});  // abajo
  CHECK(o.star_y_px > 0 && o.alt_ptr < 0);
  // Punteros saturan en ±1; la estrella nunca pasa del borde.
  o = g.update({0, 0}, ref, {90, 0});
  CHECK_NEAR(o.giro_ptr, 1.0, 1e-6);
  CHECK(std::fabs(o.star_x_px) <= tun::kStarRimPx + 0.01f);
  // La estrella se acerca al centro monótonamente al acercarse.
  float last = 1e9f;
  for (float d = 30; d >= 0; d -= 1.5f) {
    Guide gg;
    GuideOut q = gg.update({0, 0}, ref, {d, 0});
    CHECK(q.star_x_px <= last + 1e-4f);
    last = q.star_x_px;
  }
  GuideOut z = g.update({10, 10}, {10, 10}, {0, 0});
  CHECK_NEAR(z.star_x_px, 0, 1e-4);
  CHECK_NEAR(z.star_y_px, 0, 1e-4);
}

static GuideState at(Guide& g, float dist) { return g.update({0, 0}, {0, 0}, {dist, 0}).state; }

static void testStatesAndHysteresis() {
  Guide g;
  CHECK(at(g, 60) == GuideState::Far);
  CHECK(at(g, 20) == GuideState::Far);   // entre 18 y 22 sigue LEJOS al venir de lejos
  CHECK(at(g, 17) == GuideState::Near);
  CHECK(at(g, 20) == GuideState::Near);  // entre 18 y 22 sigue CERCA al venir de cerca
  CHECK(at(g, 23) == GuideState::Far);
  CHECK(at(g, 10) == GuideState::Near);
  CHECK(at(g, 2.5f) == GuideState::Near);
  CHECK(at(g, 1.5f) == GuideState::InView);
  CHECK(at(g, 2.5f) == GuideState::InView);  // histéresis: sigue EN MIRA entre 2 y 3
  CHECK(at(g, 3.5f) == GuideState::Near);
  CHECK(at(g, 2.5f) == GuideState::Near);    // y al salir no vuelve hasta bajar de 2
  // Temblor alrededor del umbral: sin parpadeo (a lo sumo 1 cambio al cruzar).
  Guide h;
  at(h, 10);
  int changes = 0;
  GuideState prev = at(h, 2.4f);
  std::mt19937 r(7);
  for (int i = 0; i < 400; i++) {
    float d = 2.5f + (static_cast<int>(r() % 100) - 50) * 0.008f;  // 2.1 .. 2.9: dentro de la banda muerta
    GuideState s = at(h, d);
    if (s != prev) changes++;
    prev = s;
  }
  CHECK(changes == 0);
  // reset() vuelve a LEJOS
  g.reset();
  CHECK(at(g, 20) == GuideState::Far);
}

static void testMarksParallax() {
  Marca m1{"1", 0, 0, 5.0f, false};
  Marca mk{"k", 25, 8, 5.0f, false};
  // Sin desplazamiento: no cambia nada.
  Target t = marcaEfectiva(mk, m1, 0, 0);
  CHECK_NEAR(t.giro_deg, 25, 1e-6);
  CHECK_NEAR(t.altura_deg, 8, 1e-6);
  // Misma distancia: la corrección se anula contra la marca 1.
  t = marcaEfectiva(mk, m1, 0.10f, 0.05f);
  CHECK_NEAR(t.giro_deg, 25, 1e-5);
  CHECK_NEAR(t.altura_deg, 8, 1e-5);
  // Dato del scientist: 10 cm a 5 m son 1.15°.
  CHECK_NEAR(std::asin(0.10 / 5.0) * 180 / 3.14159265358979, 1.15, 0.01);
  // Marca más lejos (10 m) con mira 10 cm a la derecha: el pivote debe girar un poco MÁS que lo medido.
  Marca mf{"f", 25, 8, 10.0f, false};
  t = marcaEfectiva(mf, m1, 0.10f, 0.0f);
  double expect = 25 - (std::asin(0.10 / 10.0) - std::asin(0.10 / 5.0)) * 180 / 3.14159265358979;
  CHECK_NEAR(t.giro_deg, expect, 1e-4);
  CHECK(t.giro_deg > 25);
  CHECK_NEAR(t.altura_deg, 8, 1e-6);
  // Vertical: mira 10 cm arriba del pivote, mismo razonamiento.
  t = marcaEfectiva(mf, m1, 0.0f, 0.10f);
  CHECK(t.altura_deg > 8);
  CHECK_NEAR(t.giro_deg, 25, 1e-6);
  // Sin distancia en alguna marca: no se corrige (no inventa).
  Marca nod{"n", 25, 8, 0.0f, false};
  t = marcaEfectiva(nod, m1, 0.10f, 0.10f);
  CHECK_NEAR(t.giro_deg, 25, 1e-6);
  CHECK_NEAR(t.altura_deg, 8, 1e-6);
  // Archivo de marcas del proyecto: la marca 1 es el origen y el índice fuera de rango no revienta.
  CHECK(marcasValidas());
  CHECK_NEAR(objetivoDeMarca(0).giro_deg, 0, 1e-9);
  CHECK_NEAR(objetivoDeMarca(0).altura_deg, 0, 1e-9);
  CHECK_NEAR(objetivoDeMarca(99).giro_deg, 0, 1e-9);
  CHECK_NEAR(objetivoDeMarca(1).giro_deg, MARCAS[1].giro_deg, 1e-4);  // con desplazamiento 0 en el archivo
}

static void testSyncAverage() {
  // Promedio con ruido, cruzando el ±180°: error del promedio menor que el ruido crudo (24 semillas).
  double worst = 0;
  for (int seed = 1; seed <= 24; seed++) {
    std::mt19937 r(seed);
    std::normal_distribution<double> n(0, 0.5);
    Sync s;
    CHECK(!s.commit());  // sin muestras no confirma
    double true_az = 179.6, true_el = 12.0;
    for (int i = 0; i < 50; i++) {
      s.push({wrap180(static_cast<float>(true_az + n(r))), static_cast<float>(true_el + n(r))});
    }
    CHECK(s.commit());
    CHECK(s.valid());
    double e_az = std::fabs(wrap180(static_cast<float>(s.ref().az_deg - true_az)));
    double e_el = std::fabs(s.ref().el_deg - true_el);
    if (e_az > worst) worst = e_az;
    CHECK(e_az < 0.35 && e_el < 0.35);  // sigma 0.5 / sqrt(20) = 0.11
  }
  std::printf("  error del sync tras promediar 20 muestras de sigma 0.5: peor caso %.3f grados (24 semillas) [simulado]\n", worst);
  // Solo cuentan las últimas 20: las viejas no contaminan.
  Sync s;
  for (int i = 0; i < 30; i++) s.push({90, 40});
  for (int i = 0; i < 20; i++) s.push({10, 5});
  CHECK(s.commit());
  CHECK_NEAR(s.ref().az_deg, 10, 1e-3);
  CHECK_NEAR(s.ref().el_deg, 5, 1e-3);
  // Mínimo de muestras
  Sync few;
  for (int i = 0; i < tun::kSyncMinSamples - 1; i++) few.push({1, 1});
  CHECK(!few.commit());
  few.push({1, 1});
  CHECK(few.commit());
  few.clear();
  CHECK(!few.valid());
}

static void testMount() {
  MountInfo m = detectMount({0, 0.05f, 0.99f});  // pantalla hacia arriba
  CHECK(m.mount == Mount::Flat && m.screen_rotation_deg == 0);
  CHECK_NEAR(m.pointing_axis.y, 1, 1e-6);
  m = detectMount({0, 0, -1});  // pantalla hacia abajo: sigue plano
  CHECK(m.mount == Mount::Flat);
  m = detectMount({0, 1, 0.1f});  // vertical, derecho
  CHECK(m.mount == Mount::VertUp && m.screen_rotation_deg == 0);
  CHECK_NEAR(m.pointing_axis.z, -1, 1e-6);
  m = detectMount({0, -1, 0.1f});
  CHECK(m.mount == Mount::VertDown && m.screen_rotation_deg == 180);
  m = detectMount({1, 0.1f, 0.1f});
  CHECK(m.mount == Mount::VertRight && m.screen_rotation_deg == 90);
  m = detectMount({-1, 0.1f, 0.1f});
  CHECK(m.mount == Mount::VertLeft && m.screen_rotation_deg == 270);
  // Umbral: 0.69 de componente en z ya no es plano; 0.71 sí.
  CHECK(detectMount({0, 0.72f, 0.69f}).mount == Mount::VertUp);
  CHECK(detectMount({0, 0.70f, 0.71f}).mount == Mount::Flat);
}

int main() {
  testErrorsAndSigns();
  testArrowAndStar();
  testStatesAndHysteresis();
  testMarksParallax();
  testSyncAverage();
  testMount();
  return reportAndExit("test_guide");
}
