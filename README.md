# PIC 2025/2026 · E2 — Stack de Motor Industrial

## Qué es esto

Un pipeline IoT completo y funcional que simula un motor industrial instrumentado con tres sensores: **vibración**, **temperatura** y **corriente**. El motor se degrada progresivamente hasta el fallo.

Vosotros construís la capa de inteligencia (detección de anomalías, predicción, análisis edge) y seguridad (threat model) sobre este pipeline.

## Arquitectura

```
simulador_e2.py          (vuestro PC — fuera de Docker)
      │
      │  MQTT (pic/e2/vibration, pic/e2/temperature, pic/e2/current)
      ▼
┌─────────────┐
│  Mosquitto  │ ◄── puerto 1883
└──────┬──────┘
       │
       ├──► ingestor_e2.py ──► InfluxDB ◄── puerto 8086
       │                          │
       │                          ▼
       │                       Grafana  ◄── puerto 3000 (admin / pic2026)
       │
       └──► cliente_e2_skeleton.py  (vuestro PC — vuestro código)
```

## Requisitos

- **Docker** y **Docker Compose** (v2)
- **Python 3.9+** en vuestro PC
- Paquetes Python: `pip install -r requirements.txt`

## Arranque rápido

```bash
# 1. Levantar la infraestructura (Mosquitto + InfluxDB + Grafana + Ingestor)
docker-compose up -d

# 2. Esperar ~10 segundos a que todo arranque

# 3. Lanzar el simulador (en otra terminal)
python simulador_e2.py              # modo normal: ~12 minutos
python simulador_e2.py --fast       # modo rápido: ~90 segundos
python simulador_e2.py --seed 42    # semilla fija (reproducible)

# 4. Lanzar vuestro cliente (en otra terminal)
python cliente_e2_skeleton.py

# 5. Ver datos en Grafana
#    Abrir http://localhost:3000
#    Dashboard: "E2 — Motor Industrial"

# 6. Evaluar la Tarea 1 (Métricas y Gráficas comparativas)
#    Instalr las dependencias necesarias en la terminal local antes de ejecutar los scripts de la T1:
pip install paho-mqtt numpy scikit-learn joblib pandas tabulate

#    Una vez el cliente haya procesado las 3 fases y generado el 'detecciones_e2.csv':
python metricas.py              # Calcula y muestra por consola la tabla de Falsos Positivos y Latencia.
python plot_comparativa.py      # Genera visualmente la imagen 'comparativa_4_estrategias.png'.

# 7. Ejecutar el notebook "Demostracion_T2_T3_T4.ipynb"
#    Abrir http://localhost:8888/?token=pic2026
#    Contiene las demostraciones empíricas de las tareas T2, T3 y T4 que aparecen explicadas en la memoria
```

## Simulador: tres fases

| Fase | Duración (modo normal) | Qué ocurre |
|------|----------------------|------------|
| **Normal** | ~4 min | Comportamiento estable. Baseline para entrenar. |
| **Degradación** | ~4 min | Desgaste progresivo + drift estacional en temperatura. Las features suben gradualmente. |
| **Fallo** | ~4 min | Spikes de vibración, stuck-at de temperatura, y **anomalías colectivas** (vibración sube pero corriente no sigue — físicamente imposible). |

### Anomalía colectiva

En la fase de fallo, hay momentos donde la vibración sube pero la corriente se mantiene estable. Esto es **físicamente imposible** (más vibración implica más fricción implica más consumo eléctrico). Un detector que mire cada sensor por separado no la verá. Solo se detecta cruzando features entre sensores.

## Formato de los mensajes MQTT

Cada sensor publica en su topic (`pic/e2/vibration`, `pic/e2/temperature`, `pic/e2/current`):

```json
{
  "device_id": "motor-01",
  "timestamp": 1716900000.123,
  "value": 2.54,
  "phase": "normal"
}
```

## Dataset histórico: `motor_historical.csv`

500 motores con ciclos de vida completos, para la **Tarea T2** (predicción de RUL). Columnas:

| Columna | Descripción |
|---------|-------------|
| `motor_id` | Identificador del motor (1–500) |
| `cycle` | Número de ciclo (1 hasta fallo) |
| `vibration_mean` | Media de vibración en el ciclo (mm/s) |
| `vibration_std` | Desviación estándar de vibración |
| `temperature_mean` | Media de temperatura (°C) |
| `temperature_slope` | Pendiente de temperatura dentro del ciclo |
| `current_mean` | Media de corriente (A) |
| `current_std` | Desviación estándar de corriente |
| `RUL` | Remaining Useful Life — ciclos restantes (capped a 125) |

El RUL está recortado a 125: si quedan más de 125 ciclos, el valor es 125. Esto refleja la realidad industrial (no tiene sentido predecir con precisión si un motor le quedan 200 o 250 ciclos — solo importa cuando se acerca al fallo).

## Ficheros del stack

| Fichero | Qué es | ¿Lo tocáis? |
|---------|--------|-------------|
| `docker-compose.yml` | Infraestructura completa | Sí* |
| `simulador_e2.py` | Generador de datos del motor | No |
| `ingestor_e2.py` | Bridge MQTT → InfluxDB (corre en Docker) | No |
| `mosquitto/mosquitto.conf` | Config del broker | No |
| `grafana/provisioning/` | Dashboard y datasource auto-configurados | No |
| `motor_historical.csv` | Dataset para T2 (RUL) | Solo lectura |
| **`cliente_e2_skeleton.py`** | **Vuestro punto de partida para T1** | **Sí** |
| **`metricas.py`** | **Script evaluador de la T1 (FPR y Latencias)** | **Sí** |
| **`plot_comparativa.py`** | **Script generador de gráficas de la T1** | **Sí** |
| **`Demostracion_T2_T3_T4.ipynb`**| **Notebook con las demostraciones empíricas de  T2 T3 y T4** | **Sí** |
| `models/` | Directorio con los modelos exportados (.pkl, .onnx, .tflite) | **Sí** |
| `detecciones_e2.csv` | Archivo generado automáticamente por el cliente (Logs) | Autogenerado |
| `comparativa_4_estrategias.png`| Imagen generada automáticamente por el plot de evaluación | Autogenerado |
| `requirements.txt` | Dependencias Python | Sí* |
| `Dockerfile.ingestor` | Apoyo docker para ingestor_e2.py| Sí* |
| `Dockerfile.jupyter` | Apoyo docker para lanzar el notebook| Sí* |

**Los archivos con asterisco no era necesario modificarlos, pero decidimos hacerlo para garantizar un correcto funcionamiento de la entrega, en la última sección de este readme está más explicado*

## Puertos

| Servicio | Puerto | Credenciales |
|----------|--------|-------------|
| Mosquitto | 1883 | Sin autenticación |
| InfluxDB | 8086 | admin / picpass2026 · Token: `e2-token-pic-2026` |
| Grafana | 3000 | admin / pic2026 (o acceso anónimo) |
| Jupyter Notebook | 8888 | Token: `pic2026` |

## Parar y limpiar

```bash
# Parar todo
docker-compose down

# Parar y borrar datos (empezar de cero)
docker-compose down -v
```

## Problemas frecuentes

**"No se puede conectar al broker"** → ¿Está corriendo Docker? Ejecuta `docker-compose up -d` y espera 10 segundos.

**"El simulador va muy lento"** → Usa `--fast` para iterar. El modo normal es para la evaluación final.

**"No veo datos en Grafana"** → Asegúrate de que el simulador está corriendo. El rango temporal del dashboard es "últimos 15 minutos" — si el simulador terminó hace rato, ajusta el rango.

**"InfluxDB no arranca"** → Borra volúmenes: `docker-compose down -v && docker-compose up -d`.

---

*PIC 2025/2026 · ESEI · Universidade de Vigo · E2 Stack v1*




## EXTRA: Explicación de modificación de los archivos docker y requirements:

Originalmente no era necesario modificar los archivos Dockerfile ni requirements.txt, además solo existian 2 archivos docker `docker-compose.yml` y `Dockerfile.ingestor`. 

Pero al realizar las pruebas empíricas del notebook `Demostracion_T2_T3_T4.ipynb`, sobretodo en las de la T4, las librerías utilizadas para demostraciones de seguridad eran incompatibles con las del `requirements.txt` original, además, eran necesarias bastantes más librerías para ejecutar las pruebas. O por ejemplo, la versión de Python=3.11 daría error mientras que la 3.10 no.

Ejemplo de error: *ERROR: Could not find a version that satisfies the requirement tensorflow<2.11*

Debido a bastantes errores de versiones incompatibles, para facilitar la ejecución del notebook decidimos automatizar el entorno del notebook usando el archivo docker y añadiendo las librerías que faltaban en `requirements.txt` para garantizar que no suceda ningún error al ejecutar el notebook y además que este se cree de manera automática y para ello tuvimos que añadir el nuevo archivo docker que aparece en esta entrega `Dockerfile.jupyter`, creando así el entorno correcto.