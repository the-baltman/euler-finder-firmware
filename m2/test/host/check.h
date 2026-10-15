// Mini marco de pruebas de host: sin dependencias, un ejecutable por archivo de prueba.
#pragma once
#include <cmath>
#include <cstdio>

static int g_checks = 0, g_fails = 0;

#define CHECK(cond)                                                          \
  do {                                                                       \
    g_checks++;                                                              \
    if (!(cond)) {                                                           \
      g_fails++;                                                             \
      std::printf("  FALLA %s:%d  %s\n", __FILE__, __LINE__, #cond);         \
    }                                                                        \
  } while (0)

#define CHECK_NEAR(a, b, tol)                                                          \
  do {                                                                                 \
    g_checks++;                                                                        \
    double _a = (a), _b = (b), _t = (tol);                                             \
    if (!(std::fabs(_a - _b) <= _t)) {                                                 \
      g_fails++;                                                                       \
      std::printf("  FALLA %s:%d  %s ~ %s  (%.5f vs %.5f, tol %.5f)\n", __FILE__,      \
                  __LINE__, #a, #b, _a, _b, _t);                                       \
    }                                                                                  \
  } while (0)

inline int reportAndExit(const char* name) {
  std::printf("%s: %d comprobaciones, %d fallas\n", name, g_checks, g_fails);
  return g_fails == 0 ? 0 : 1;
}
