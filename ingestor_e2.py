"""
PIC 2025/2026 · E2 — Ingestor MQTT → InfluxDB
Este servicio corre dentro de Docker. No lo modifiquéis.
Se suscribe a pic/e2/# y escribe cada mensaje en InfluxDB.
"""

import os
import json
import time
import paho.mqtt.client as mqtt
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

# ── Configuración desde variables de entorno ──────────────────────
MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
INFLUX_URL = os.getenv("INFLUXDB_URL", "http://localhost:8086")
INFLUX_TOKEN = os.getenv("INFLUXDB_TOKEN", "e2-token-pic-2026")
INFLUX_ORG = os.getenv("INFLUXDB_ORG", "pic")
INFLUX_BUCKET = os.getenv("INFLUXDB_BUCKET", "motor")

TOPIC_PREFIX = "pic/e2/"

# ── InfluxDB ──────────────────────────────────────────────────────
influx_client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
write_api = influx_client.write_api(write_options=SYNCHRONOUS)


def on_connect(client, userdata, flags, reason_code, properties):
    print(f"[ingestor] Conectado a MQTT ({reason_code}). Suscribiendo a {TOPIC_PREFIX}#")
    client.subscribe(f"{TOPIC_PREFIX}#", qos=1)


def on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode())
        sensor_type = msg.topic.replace(TOPIC_PREFIX, "")

        point = (
            Point("sensor_reading")
            .tag("device_id", data.get("device_id", "unknown"))
            .tag("sensor_type", sensor_type)
            .field("value", float(data["value"]))
        )

        # Añadir tramo si viene en el payload (útil para análisis)
        if "phase" in data:
            point = point.tag("phase", data["phase"])

        write_api.write(bucket=INFLUX_BUCKET, record=point)

    except Exception as e:
        print(f"[ingestor] Error procesando mensaje: {e}")


# ── Bucle principal ───────────────────────────────────────────────
def main():
    print("[ingestor] Esperando 5s a que arranquen Mosquitto e InfluxDB...")
    time.sleep(5)

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="e2-ingestor")
    client.on_connect = on_connect
    client.on_message = on_message

    while True:
        try:
            client.connect(MQTT_HOST, MQTT_PORT)
            break
        except Exception:
            print("[ingestor] Mosquitto no disponible, reintentando en 3s...")
            time.sleep(3)

    client.loop_forever()


if __name__ == "__main__":
    main()
