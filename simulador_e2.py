#!/usr/bin/env python3
"""
PIC 2025/2026 · E2 — Simulador de Motor Industrial
===================================================
Publica telemetría de 3 sensores correlacionados (vibración, temperatura,
corriente) por MQTT. El motor pasa por tres fases:

  1. Normal         — comportamiento estable con ruido.
  2. Degradación    — desgaste progresivo + drift estacional.
  3. Fallo inminente — spikes, stuck-at, anomalía colectiva.

Uso:
    python simulador_e2.py                   # modo normal (~12 min)
    python simulador_e2.py --fast            # modo rápido (~90 s)
    python simulador_e2.py --seed 42         # semilla fija
    python simulador_e2.py --host 192.168.1.5  # broker remoto

Requisitos:
    pip install paho-mqtt numpy
"""

import argparse
import json
import math
import sys
import time

import numpy as np
import paho.mqtt.client as mqtt

# ── Configuración por defecto ─────────────────────────────────────
BROKER_HOST = "localhost"
BROKER_PORT = 1883
DEVICE_ID = "motor-01"
TOPIC_PREFIX = "pic/e2"

# Frecuencia de muestreo (muestras/segundo)
RATE_NORMAL = 10
RATE_FAST = 100

# Duración de cada fase en muestras (a RATE_NORMAL = 10 Hz)
# ~4 min por fase = 240s × 10 = 2400 muestras
PHASE_SAMPLES = 2400

# ── Modelo físico del motor ───────────────────────────────────────

# Baselines (fase normal)
VIB_BASE = 2.5       # mm/s RMS
VIB_NOISE = 0.30
TEMP_BASE = 45.0      # °C
TEMP_NOISE = 1.2
CURR_BASE = 4.2       # A
CURR_NOISE = 0.12

# Degradación (lineales sobre la fase)
VIB_DEGRADED = 5.5    # vibración al final de degradación
TEMP_DEGRADED = 58.0
CURR_DEGRADED = 5.8

# Correlaciones
TEMP_VIB_COUPLING = 2.0   # °C extra por cada mm/s de vibración sobre base
CURR_VIB_COUPLING = 0.25  # A extra por cada mm/s de vibración sobre base

# Drift estacional (sinusoide lenta sobre temperatura)
SEASONAL_AMPLITUDE = 3.0  # °C
SEASONAL_PERIOD = PHASE_SAMPLES * 3  # un ciclo completo en toda la simulación


class MotorSimulator:
    """Genera muestras de vibración, temperatura y corriente correlacionadas."""

    def __init__(self, seed=None):
        self.rng = np.random.default_rng(seed)
        self.sample_idx = 0
        self.total_samples = PHASE_SAMPLES * 3

        # Pre-generar puntos de anomalía colectiva en fase 3
        phase3_start = PHASE_SAMPLES * 2
        phase3_end = self.total_samples
        n_collective = 5  # número de anomalías colectivas
        # Distribuirlas en la segunda mitad de la fase 3
        self.collective_anomaly_centers = self.rng.integers(
            phase3_start + PHASE_SAMPLES // 2,
            phase3_end - 50,
            size=n_collective,
        )
        self.collective_anomaly_duration = 15  # muestras (~1.5s a 10Hz)

        # Pre-generar puntos de spikes en fase 3
        n_spikes = 8
        self.spike_indices = self.rng.integers(
            phase3_start + 100, phase3_end - 10, size=n_spikes
        )

        # Stuck-at: un rango de ~30 muestras donde temperatura se congela
        self.stuck_start = phase3_start + PHASE_SAMPLES // 3
        self.stuck_end = self.stuck_start + 30

    def get_phase(self, idx):
        if idx < PHASE_SAMPLES:
            return "normal"
        elif idx < PHASE_SAMPLES * 2:
            return "degradation"
        else:
            return "failure"

    def _degradation_factor(self, idx):
        """0.0 al inicio de degradación → 1.0 al final."""
        if idx < PHASE_SAMPLES:
            return 0.0
        elif idx < PHASE_SAMPLES * 2:
            return (idx - PHASE_SAMPLES) / PHASE_SAMPLES
        else:
            return 1.0

    def _seasonal_drift(self, idx):
        """Drift estacional sinusoidal sobre temperatura."""
        return SEASONAL_AMPLITUDE * math.sin(2 * math.pi * idx / SEASONAL_PERIOD)

    def _is_collective_anomaly(self, idx):
        """Verdadero si estamos en una ventana de anomalía colectiva."""
        for center in self.collective_anomaly_centers:
            if center <= idx < center + self.collective_anomaly_duration:
                return True
        return False

    def _is_spike(self, idx):
        """Verdadero si hay un spike de vibración."""
        return any(abs(idx - s) <= 2 for s in self.spike_indices)

    def _is_stuck(self, idx):
        """Verdadero si temperatura está en stuck-at."""
        return self.stuck_start <= idx < self.stuck_end

    def sample(self):
        """Genera una muestra (vibración, temperatura, corriente) + fase."""
        idx = self.sample_idx
        self.sample_idx += 1
        phase = self.get_phase(idx)
        df = self._degradation_factor(idx)

        # ── Vibración ─────────────────────────────────────────────
        vib = VIB_BASE + df * (VIB_DEGRADED - VIB_BASE)
        vib += self.rng.normal(0, VIB_NOISE * (1 + 0.5 * df))

        # Spike en fase 3
        if phase == "failure" and self._is_spike(idx):
            vib += self.rng.uniform(4.0, 8.0)

        # Anomalía colectiva: vibración sube
        is_collective = self._is_collective_anomaly(idx)
        if is_collective:
            vib += self.rng.uniform(2.5, 4.0)

        vib = max(0.1, vib)

        # ── Temperatura ───────────────────────────────────────────
        temp = TEMP_BASE + df * (TEMP_DEGRADED - TEMP_BASE)
        temp += self._seasonal_drift(idx)
        # Acoplamiento con vibración (la fricción genera calor)
        vib_excess = max(0, vib - VIB_BASE)
        temp += TEMP_VIB_COUPLING * vib_excess * 0.3  # atenuado (inercia térmica)
        temp += self.rng.normal(0, TEMP_NOISE)

        # Stuck-at en fase 3
        if self._is_stuck(idx):
            temp = TEMP_DEGRADED + self._seasonal_drift(self.stuck_start)

        # ── Corriente ─────────────────────────────────────────────
        curr = CURR_BASE + df * (CURR_DEGRADED - CURR_BASE)
        # Acoplamiento con vibración (más fricción = más consumo)
        if not is_collective:
            # Normal: corriente sigue a vibración
            curr += CURR_VIB_COUPLING * vib_excess
        else:
            # ANOMALÍA COLECTIVA: vibración sube pero corriente NO sigue.
            # Esto es físicamente imposible (más vibración = más fricción
            # = más corriente). Solo detectable cruzando sensores.
            pass
        curr += self.rng.normal(0, CURR_NOISE * (1 + 0.3 * df))
        curr = max(0.5, curr)

        return {
            "vibration": round(vib, 3),
            "temperature": round(temp, 2),
            "current": round(curr, 3),
            "phase": phase,
        }

    @property
    def finished(self):
        return self.sample_idx >= self.total_samples


# ── Publicación MQTT ──────────────────────────────────────────────

def publish_loop(client, simulator, rate, device_id=DEVICE_ID, verbose=True):
    """Publica muestras a la frecuencia indicada."""
    dt = 1.0 / rate
    total = simulator.total_samples
    phase_names = {"normal": "NORMAL", "degradation": "DEGRADACIÓN", "failure": "FALLO"}
    last_phase = None

    while not simulator.finished:
        t0 = time.time()
        sample = simulator.sample()
        ts = time.time()

        # Publicar cada sensor en su topic
        for sensor in ("vibration", "temperature", "current"):
            payload = json.dumps({
                "device_id": device_id,
                "timestamp": ts,
                "value": sample[sensor],
                "phase": sample["phase"],
            })
            client.publish(f"{TOPIC_PREFIX}/{sensor}", payload, qos=0)

        # Log de progreso
        if verbose and sample["phase"] != last_phase:
            last_phase = sample["phase"]
            print(f"\n{'='*50}")
            print(f"  FASE: {phase_names[last_phase]}")
            print(f"{'='*50}")

        if verbose and simulator.sample_idx % (rate * 10) == 0:
            pct = simulator.sample_idx / total * 100
            print(
                f"  [{pct:5.1f}%] vib={sample['vibration']:6.2f} mm/s  "
                f"temp={sample['temperature']:5.1f} °C  "
                f"curr={sample['current']:5.3f} A"
            )

        # Respetar frecuencia
        elapsed = time.time() - t0
        sleep_time = dt - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)

    print(f"\n{'='*50}")
    print("  SIMULACIÓN COMPLETADA")
    print(f"{'='*50}")


# ── Main ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="PIC E2 — Simulador de Motor Industrial"
    )
    parser.add_argument("--host", default=BROKER_HOST, help="Host del broker MQTT")
    parser.add_argument("--port", type=int, default=BROKER_PORT, help="Puerto MQTT")
    parser.add_argument("--seed", type=int, default=None, help="Semilla (reproducibilidad)")
    parser.add_argument("--fast", action="store_true", help="Modo rápido (~90s en vez de ~12 min)")
    parser.add_argument("--device-id", default=DEVICE_ID, help="ID del dispositivo")
    args = parser.parse_args()

    rate = RATE_FAST if args.fast else RATE_NORMAL
    duration_s = (PHASE_SAMPLES * 3) / rate
    duration_min = duration_s / 60

    print(f"PIC E2 — Simulador de Motor Industrial")
    print(f"  Broker:     {args.host}:{args.port}")
    print(f"  Device:     {args.device_id}")
    print(f"  Seed:       {args.seed or 'aleatorio'}")
    print(f"  Rate:       {rate} Hz")
    print(f"  Duración:   {duration_min:.1f} min ({duration_s:.0f} s)")
    print(f"  Topics:     {TOPIC_PREFIX}/vibration")
    print(f"              {TOPIC_PREFIX}/temperature")
    print(f"              {TOPIC_PREFIX}/current")
    print(f"  Fases:      normal → degradación → fallo ({PHASE_SAMPLES} muestras/fase)")
    print()

    # Conectar MQTT
    device_id = args.device_id

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="e2-simulador")
    try:
        client.connect(args.host, args.port)
    except ConnectionRefusedError:
        print(f"ERROR: No se puede conectar a {args.host}:{args.port}")
        print("¿Está corriendo el broker? Ejecuta: docker-compose up -d mosquitto")
        sys.exit(1)

    client.loop_start()

    simulator = MotorSimulator(seed=args.seed)

    try:
        publish_loop(client, simulator, rate, device_id=device_id)
    except KeyboardInterrupt:
        print("\nInterrumpido por el usuario.")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
