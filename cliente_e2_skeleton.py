#!/usr/bin/env python3
"""
PIC 2025/2026 · E2 — Cliente de detección de anomalías (skeleton)
=================================================================
Este archivo es vuestro punto de partida para la Tarea T1.
La infraestructura (MQTT, ventanas, features) ya está resuelta.
Vuestro trabajo está en las funciones marcadas con # TODO.

Uso:
    1. Levantar el stack:   docker-compose up -d
    2. Lanzar simulador:    python simulador_e2.py [--fast]
    3. Lanzar este cliente:  python cliente_e2_skeleton.py

Requisitos (fuera de Docker):
    pip install paho-mqtt numpy scikit-learn joblib
"""

import json
import math
import time
import joblib
from collections import deque

import numpy as np
import paho.mqtt.client as mqtt
from sklearn.ensemble import IsolationForest

# ── Configuración ─────────────────────────────────────────────────
BROKER_HOST = "localhost"
BROKER_PORT = 1883
TOPIC_PREFIX = "pic/e2"
SENSORS = ["vibration", "temperature", "current"]
WINDOW_SECONDS = 30       # tamaño de ventana en segundos
EVAL_INTERVAL = 3.0       # evaluar cada N segundos
CSV_LOG = "detecciones_e2.csv"


# ══════════════════════════════════════════════════════════════════
# VENTANA DE SENSORES — NO MODIFICAR
# ══════════════════════════════════════════════════════════════════

class VentanaSensores:
    """Mantiene una ventana deslizante temporal con datos de N sensores.
    Gestiona timestamps, sincronización y limpieza automática."""

    def __init__(self, sensors, window_seconds=30):
        self.sensors = sensors
        self.window_seconds = window_seconds
        # Cada sensor tiene su propia deque de (timestamp, value)
        self.buffers = {s: deque() for s in sensors}

    def add(self, sensor, timestamp, value):
        """Añade un dato y limpia los que caen fuera de la ventana."""
        if sensor not in self.buffers:
            return
        self.buffers[sensor].append((timestamp, value))
        self._clean(sensor, timestamp)

    def _clean(self, sensor, now):
        buf = self.buffers[sensor]
        cutoff = now - self.window_seconds
        while buf and buf[0][0] < cutoff:
            buf.popleft()

    def get_values(self, sensor):
        """Devuelve array numpy con los valores del sensor en la ventana."""
        buf = self.buffers[sensor]
        if not buf:
            return np.array([])
        return np.array([v for _, v in buf])

    def ready(self, min_samples=10):
        """True si todos los sensores tienen al menos min_samples datos."""
        return all(len(self.buffers[s]) >= min_samples for s in self.sensors)

    def get_features(self):
        """Extrae features de la ventana actual."""
        features = {}

        for sensor in self.sensors:
            vals = self.get_values(sensor)
            if len(vals) < 5:
                return None  # ventana insuficiente

            features[f"{sensor}_mean"] = np.mean(vals)
            features[f"{sensor}_std"] = np.std(vals)
            features[f"{sensor}_min"] = np.min(vals)
            features[f"{sensor}_max"] = np.max(vals)
            features[f"{sensor}_range"] = np.ptp(vals)

            # Slope: pendiente por mínimos cuadrados
            x = np.arange(len(vals))
            if len(vals) > 1:
                slope = np.polyfit(x, vals, 1)[0]
            else:
                slope = 0.0
            features[f"{sensor}_slope"] = slope

        # ── Features cruzadas (TODO 1b) ───────────────────────────
        features.update(self._cross_features())

        return features

    def _cross_features(self):
        """
        ╔══════════════════════════════════════════════════════════╗
        ║  TODO 1b — IMPLEMENTAR FEATURES CRUZADAS                 ║
        ╚══════════════════════════════════════════════════════════╝
        """
        cross = {}
        vib = self.get_values("vibration")
        curr = self.get_values("current")
        temp = self.get_values("temperature")
        
        if len(vib) > 5 and len(curr) > 5 and len(temp) > 5:
            min_len = min(len(vib), len(curr), len(temp))
            v_trim, c_trim, t_trim = vib[-min_len:], curr[-min_len:], temp[-min_len:]
            
            # Ratio Ineficiencia
            cross["ratio_vib_curr"] = np.mean(v_trim) / max(np.mean(c_trim), 0.01)
            # Correlación termodinámica
            corr = np.corrcoef(v_trim, t_trim)[0, 1]
            cross["corr_vib_temp"] = 0.0 if np.isnan(corr) else corr
            # Diferencia de pendientes
            cross["diff_slopes_vib_curr"] = np.polyfit(np.arange(min_len), v_trim, 1)[0] - np.polyfit(np.arange(min_len), c_trim, 1)[0]
            
        return cross


# ══════════════════════════════════════════════════════════════════
# FUNCIONES DE DETECCIÓN — VUESTRO TRABAJO
# ══════════════════════════════════════════════════════════════════

def detectar_anomalia(features, modelo=None, historial=None):
    """
    ╔══════════════════════════════════════════════════════════════╗
    ║  TODO 1a — IMPLEMENTAR DETECTOR                              ║
    ╚══════════════════════════════════════════════════════════════╝
    """
    if not modelo:
        modelo = {
            "iforest": IsolationForest(contamination=0.05, random_state=42),
            "is_fitted": False,
            "window_size": 100, 
            "z_threshold": 3.0, 
            "fixed_ratio_threshold": 0.7 
        }

    resultados = {
        "anomaly_fixed": False, "score_fixed": 0.0,
        "anomaly_zscore": False, "score_zscore": 0.0,
        "anomaly_if_static": False, "score_if_static": 0.0,
        "anomaly_ensemble": False, "score_ensemble": 0.0,
        "modelo_actualizado": modelo
    }

    ratio_actual = features.get("ratio_vib_curr", 0)

    # 1. BASELINE 1: UMBRAL FIJO
    resultados["score_fixed"] = float(ratio_actual)
    if ratio_actual > modelo["fixed_ratio_threshold"]:
        resultados["anomaly_fixed"] = True

    # 2. BASELINE 2: Z-SCORE ADAPTATIVO (Sobre media del ratio)
    if historial and len(historial) > 5:
        ratios_pasados = [h["features"].get("ratio_vib_curr", 0) for h in historial[-modelo["window_size"]:]]
        media_movil, std_movil = np.mean(ratios_pasados), np.std(ratios_pasados)
        if std_movil > 0:
            z_score_normal = abs(ratio_actual - media_movil) / std_movil
            resultados["score_zscore"] = float(z_score_normal)
            resultados["anomaly_zscore"] = bool(z_score_normal > modelo["z_threshold"])

    # 3. BASELINE 3: ISOLATION FOREST ESTÁTICO
    keys = [k for k in sorted(features.keys()) if k not in ("timestamp", "time_rel", "phase", "resultado")]
    x_val = np.array([features[k] for k in keys]).reshape(1, -1)

    if historial and len(historial) >= modelo["window_size"] and not modelo["is_fitted"]:
        X_train = np.array([[h["features"][k] for k in keys] for h in historial])
        modelo["iforest"].fit(X_train)
        modelo["is_fitted"] = True
        print(f"✅ IF Entrenado (Estático). Modelos listos.")
        joblib.dump(modelo, 'detector_t1.pkl')
        print(f"💾 Artefacto guardado: 'detector_t1.pkl' listo para la Tarea 4")

    if modelo["is_fitted"]:
        prediccion = modelo["iforest"].predict(x_val)[0]
        score_crudo = -1.0 * modelo["iforest"].score_samples(x_val)[0]
        resultados["score_if_static"] = float(score_crudo)
        resultados["anomaly_if_static"] = bool(prediccion == -1)

    # 4. PROPUESTA FINAL: ENSAMBLE (Z-Score Max + IF Estático)
    feature_max = features.get("vibration_max", 0)
    z_score_max = 0.0
    anomalia_z_max = False
    
    if historial and len(historial) > 5:
        historico_max = [h["features"].get("vibration_max", 0) for h in historial[-modelo["window_size"]:]]
        media_max, std_max = np.mean(historico_max), np.std(historico_max)
        if std_max > 0:
            z_score_max = abs(feature_max - media_max) / std_max
            anomalia_z_max = bool(z_score_max > modelo["z_threshold"])

    resultados["score_ensemble"] = float(z_score_max)
    resultados["anomaly_ensemble"] = bool(anomalia_z_max and resultados["anomaly_if_static"])

    return resultados


def estrategia_drift(historial):
    """
    ╔══════════════════════════════════════════════════════════════╗
    ║  TODO 1c — ESTRATEGIA DE ADAPTACIÓN AL DRIFT                 ║
    ╚══════════════════════════════════════════════════════════════╝
    Nuestra adaptación al drift se calcula de forma continua en cada
    iteración mediante la ventana deslizante del Z-Score Adaptativo.
    No necesitamos forzar un reentrenamiento aquí.
    """
    pass


# ══════════════════════════════════════════════════════════════════
# BUCLE PRINCIPAL 
# ══════════════════════════════════════════════════════════════════

class ClienteE2:
    """Cliente MQTT que consume el stream y ejecuta detección."""

    def __init__(self):
        self.ventana = VentanaSensores(SENSORS, WINDOW_SECONDS)
        self.historial = []
        self.modelo = {}  # Inicia como dict vacío para el Ensamble
        self.last_eval = 0
        self.log_file = None
        self._init_log()

    def _init_log(self):
        # NOTA: Única modificación de la estructura para soportar las 4 columnas del análisis
        self.log_file = open(CSV_LOG, "w")
        self.log_file.write("timestamp,score_fixed,anomaly_fixed,score_zscore,anomaly_zscore,score_if_static,anomaly_if_static,score_ensemble,anomaly_ensemble,phase\n")

    def on_connect(self, client, userdata, flags, reason_code, properties):
        print(f"[cliente] Conectado a MQTT ({reason_code})")
        for sensor in SENSORS:
            topic = f"{TOPIC_PREFIX}/{sensor}"
            client.subscribe(topic, qos=0)
            print(f"  Suscrito a {topic}")

    def on_message(self, client, userdata, msg):
        try:
            data = json.loads(msg.payload.decode())
            sensor = msg.topic.replace(f"{TOPIC_PREFIX}/", "")
            self.ventana.add(sensor, data["timestamp"], data["value"])

            # Evaluar periódicamente
            now = time.time()
            if now - self.last_eval >= EVAL_INTERVAL and self.ventana.ready():
                self.last_eval = now
                self._evaluar(data.get("phase", "?"))

        except Exception as e:
            print(f"[cliente] Error: {e}")

    def _evaluar(self, phase):
        features = self.ventana.get_features()
        if features is None:
            return

        # Detección
        resultado = detectar_anomalia(features, self.modelo, self.historial)
        self.modelo = resultado.pop("modelo_actualizado") # Actualiza el modelo interno
        self.historial.append({"features": features, "resultado": resultado})

        # Adaptación al drift (cada 20 evaluaciones)
        if len(self.historial) % 20 == 0:
            estrategia_drift(self.historial)

        # Log por consola adaptado al Ensamble
        ts = time.strftime("%H:%M:%S")
        is_anom = resultado["anomaly_ensemble"]

        if is_anom:
            color = "\033[91m"  # rojo
            label = "⚠ ANOMALÍA"
        else:
            color = "\033[92m"  # verde
            label = "  normal"
        reset = "\033[0m"

        print(
            f"{color}[{ts}] {label} (Ens)  "
            f"UF:{int(resultado['anomaly_fixed'])} "
            f"ZS:{int(resultado['anomaly_zscore'])} "
            f"IF:{int(resultado['anomaly_if_static'])} "
            f"[{phase}]{reset}"
        )

        # CSV adaptado a 4 columnas
        self.log_file.write(f"{time.time()},"
            f"{resultado['score_fixed']},{resultado['anomaly_fixed']},"
            f"{resultado['score_zscore']},{resultado['anomaly_zscore']},"
            f"{resultado['score_if_static']},{resultado['anomaly_if_static']},"
            f"{resultado['score_ensemble']},{resultado['anomaly_ensemble']},{phase}\n")
        self.log_file.flush()

    def run(self):
        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2, client_id="e2-cliente"
        )
        client.on_connect = self.on_connect
        client.on_message = self.on_message

        print(f"[cliente] Conectando a {BROKER_HOST}:{BROKER_PORT}...")
        try:
            client.connect(BROKER_HOST, BROKER_PORT)
        except ConnectionRefusedError:
            print(f"ERROR: No se puede conectar al broker.")
            print("¿Está corriendo? Ejecuta: docker-compose up -d")
            return

        print(f"[cliente] Ventana: {WINDOW_SECONDS}s · Evaluación cada {EVAL_INTERVAL}s")
        print(f"[cliente] Log → {CSV_LOG}")
        print()

        try:
            client.loop_forever()
        except KeyboardInterrupt:
            print("\n[cliente] Detenido. Log guardado en", CSV_LOG)
        finally:
            if self.log_file:
                self.log_file.close()
            client.disconnect()


if __name__ == "__main__":
    ClienteE2().run()