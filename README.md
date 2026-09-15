# Inteligencia y Seguridad sobre un Pipeline AIoT (Mantenimiento Predictivo) 🏭⚙️

Este proyecto presenta el diseño, evaluación e implementación de una arquitectura AIoT completa para la monitorización de maquinaria pesada. El sistema aborda el ciclo de vida del dato industrial, pasando de la detección reactiva de anomalías a la estimación proactiva de la Vida Útil Restante (RUL) directamente en el *Edge*.

El reto principal radica en gestionar el **Concept Drift** (desgaste paulatino de los motores) sin saturar los sistemas con falsas alarmas, manteniendo restricciones estrictas de latencia, memoria y ciberseguridad.

## 🧠 Arquitectura Analítica

El sistema se compone de cuatro pilares operativos evaluados empíricamente:

### 1. Detección Robusta al Drift (Ensamble)
Se descartaron algoritmos estáticos debido a su colapso frente a la deriva de datos (*Model Degradation*). La solución implementada es un **Ensamble**:
*   **Detector Principal:** Z-Score Adaptativo sobre picos máximos para garantizar la reactividad.
*   **Validador de Contexto:** *Isolation Forest* estático para anclar la normalidad y eliminar falsos positivos generados por ruido operativo.

### 2. Mantenimiento Predictivo (RUL)
Sustituyendo el enfoque reactivo, se entrenó un modelo **Random Forest Regressor** capaz de estimar la Vida Útil Restante del motor. El análisis de importancia de variables demostró que la desviación estándar de la vibración (`vibration_std`) es el predictor dominante, permitiendo simplificar la sensórica física.

### 3. Despliegue en el Edge (Perfilado y Optimización)
Se evaluó el coste computacional para trasladar la inferencia desde la nube hacia un *Edge Server* local:
*   Se descartaron modelos pesados (Scikit-learn) y cuantizaciones extremas (TFLite int8) por latencia o pérdida crítica de precisión.
*   La solución óptima desplegada fue el modelo en formato **ONNX**, logrando un tamaño asumible (254 MB) y una latencia de inferencia ultrabaja (0.0180 ms), garantizando disponibilidad *offline* y privacidad de los datos.

### 4. Threat Modeling (Ciberseguridad)
Se auditó la arquitectura frente a ataques dirigidos, demostrando que:
*   Los modelos basados en árboles son matemáticamente inmunes a ataques adversariales (FGSM).
*   El *Sensor Spoofing* coordinado puede evadir la detección engañando a la ventana temporal adaptativa.
*   El *Data Poisoning* en reentrenamientos locales representa el mayor riesgo, mitigable únicamente mediante infraestructuras de firmas de procedencia (*Provenance*).

## 🛠️ Tecnologías Utilizadas

*   **Python (Scikit-learn, NumPy, Pandas)** para el modelado y evaluación analítica.
*   **ONNX** para la serialización y optimización de latencia en inferencias Edge.
*   **MQTT (Paho) & InfluxDB** como ecosistema de mensajería y almacenamiento de series temporales.
*   **Docker** para el aislamiento e integración de la infraestructura base.

## 🚀 Ejecución de la Demostración

La evaluación en vivo de la detección en tiempo real se ejecuta sobre el pipeline MQTT:

```bash
# 1. Levantar infraestructura (Mosquitto + InfluxDB + Grafana)
docker-compose up -d

# 2. Iniciar el simulador de telemetría (Terminal 1)
python simulador_e2.py --fast

# 3. Lanzar el nodo Edge con el Ensamble (Terminal 2)
python cliente_e2_skeleton.py

# 4. Generar métricas y gráficas de rendimiento tras la ejecución
python metricas.py
python plot_comparativa.py
