// Constantes de ajuste del nivelador M2 (demo JIJE).
// Las marcadas [estimado] son valores iniciales razonables, NO medidos: se ajustan
// en el salón con el sensor real. Ninguna se muestra en pantalla como cifra.
#pragma once

namespace euler {
namespace tun {

// --- Muestreo ---
constexpr int kSampleHz = 100;                      // Hz, tarea de control con periodo fijo
constexpr float kSamplePeriodS = 1.0f / kSampleHz;  // s
constexpr float kDtMinS = 0.005f;                   // s, límite inferior del dt medido
constexpr float kDtMaxS = 0.020f;                   // s, límite superior del dt medido

// --- Fusión de 6 ejes (giroscopio + acelerómetro, sin magnetómetro) ---
constexpr float kFusionKp = 1.0f;     // 1/s, ganancia de corrección por gravedad [estimado]
constexpr float kAccelGateG = 0.15f;  // g, se ignora el acelerómetro si |a| se aleja de 1 g más que esto

// --- Sesgo del giroscopio ---
constexpr float kBiasInitialWindowS = 3.0f;  // s quieto para la primera medición (arquitectura 5.1)
constexpr float kBiasRefreshWindowS = 2.0f;  // s quieto para re-estimar después (arquitectura 5.2)
constexpr float kBiasQuietGyroDps = 1.0f;    // °/s, desviación máxima respecto a la primera muestra de la ventana [estimado]
constexpr float kBiasQuietAccelG = 0.05f;    // g, idem para el acelerómetro [estimado]
constexpr float kBiasMaxDps = 10.0f;         // °/s, un "sesgo" mayor se descarta (no estaba quieto) [estimado]

// --- Sync ---
constexpr int kSyncAvgSamples = 20;  // muestras (0.2 s) que se promedian al confirmar el sync
constexpr int kSyncMinSamples = 5;   // mínimo de muestras para aceptar un sync

// --- Guía ---
constexpr float kFarEnterDeg = 22.0f;    // pasa a LEJOS por encima de esto [estimado]
constexpr float kFarExitDeg = 18.0f;     // vuelve a CERCA por debajo de esto [estimado]
constexpr float kInViewEnterDeg = 2.0f;  // EN MIRA por debajo de esto [estimado, ajustar en el salón]
constexpr float kInViewExitDeg = 3.0f;   // sale de EN MIRA por encima de esto [estimado]
constexpr float kScaleDeg = 25.0f;       // fondo de escala de punteros y de la estrella [estimado]
constexpr float kStarRimPx = 95.0f;      // px, radio donde la estrella queda "en el borde"

// --- Botones ---
constexpr unsigned kDebounceMs = 20;     // ms de señal estable para aceptar un cambio
constexpr unsigned kLongPressMs = 1000;  // ms, pulsación larga (mapa de botones 5.3)
constexpr unsigned kComboMs = 3000;      // ms, A+B juntos (borrar calibración)

// --- Montaje (gravedad) ---
constexpr float kMountFlatMinUp = 0.7f;  // componente de "arriba" sobre el eje de la pantalla para considerar plano [estimado]

// --- Autoprueba ---
constexpr int kSelfTestSamples = 20;      // lecturas de verificación del IMU
constexpr float kSelfTestGravMin = 0.7f;  // g, |a| medio mínimo creíble
constexpr float kSelfTestGravMax = 1.3f;  // g, |a| medio máximo creíble
constexpr int kImuFaultReads = 5;         // lecturas fallidas seguidas para declarar IMU perdido

// --- Tiempos de pantalla ---
constexpr unsigned kLogoMs = 1800;         // ms de logo
constexpr unsigned kSelfTestMinMs = 1200;  // ms mínimos mostrando la autoprueba
constexpr unsigned kSyncToastMs = 1200;    // ms de "Sync listo"

}  // namespace tun
}  // namespace euler
