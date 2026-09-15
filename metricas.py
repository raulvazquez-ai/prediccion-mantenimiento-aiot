import pandas as pd

# Cargar los datos
df = pd.read_csv("detecciones_e2.csv")
df['phase'] = df['phase'].astype(str).str.lower().str.strip()

fases_ordenadas = ['normal', 'degradation', 'failure']
resultados = []

for fase in fases_ordenadas:
    subset = df[df['phase'] == fase]
    total = len(subset)
    
    if total == 0:
        continue
        
    t_inicio_fase = subset['timestamp'].iloc[0]
    
    # Función auxiliar para calcular alertas y latencia
    def calc_metricas(col_anom):
        alertas = subset[col_anom].sum()
        anomalias = subset[subset[col_anom] == True]
        
        if alertas == 0:
            latencia_str = "N/A"
        else:
            t_primera_alerta = anomalias['timestamp'].iloc[0]
            latencia_segundos = t_primera_alerta - t_inicio_fase
            latencia_str = f"{latencia_segundos:.1f}s"
            
        tasa = (alertas / total) * 100
        return f"{alertas}/{total} ({tasa:.0f}%) | Lat: {latencia_str}"

    resultados.append({
        'Fase': fase.capitalize(),
        'Umbral Fijo': calc_metricas('anomaly_fixed'),
        'Z-score Adapt.': calc_metricas('anomaly_zscore'),
        'IF Estático': calc_metricas('anomaly_if_static'),
        'Ensamble (Propuesta)': calc_metricas('anomaly_ensemble')
    })

# Mostrar la tabla
tabla_df = pd.DataFrame(resultados)
print("\n=== TABLA DE MÉTRICAS OPERATIVAS (TASA DE ALERTAS Y LATENCIA) ===")
print(tabla_df.to_markdown(index=False))