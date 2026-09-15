import pandas as pd
import matplotlib.pyplot as plt

CONTAMINATION_USADA = 0.05

df = pd.read_csv("detecciones_e2.csv")
df['time_rel'] = df['timestamp'] - df['timestamp'].iloc[0]
df['phase'] = df['phase'].astype(str).str.lower().str.strip()

fig, axes = plt.subplots(4, 1, figsize=(14, 12), sharex=True)
fig.suptitle('Análisis Comparativo: 3 Baselines vs Propuesta de Ensamble', fontsize=16)

modelos = [
    ('1. Baseline: Umbral Fijo', 'score_fixed', 'anomaly_fixed', 'blue'),
    ('2. Baseline: Z-Score Adaptativo', 'score_zscore', 'anomaly_zscore', 'green'),
    ('3. Baseline: Isolation Forest Estático', 'score_if_static', 'anomaly_if_static', 'purple'),
    ('4. Propuesta: Ensamble (Z-Score + IF)', 'score_ensemble', 'anomaly_ensemble', 'darkred')
]

colores_fase = {'normal': '#d4edda', 'degradation': '#fff3cd', 'failure': '#f8d7da'}
fases = df['phase'].unique()

for i, (titulo, col_score, col_anom, color) in enumerate(modelos):
    ax = axes[i]
    ax.plot(df['time_rel'], df[col_score], color=color, label='Score', linewidth=1.5)
    
    if "Umbral Fijo" in titulo:
        ax.axhline(y=0.7, color='red', linestyle='--', alpha=0.7, label='Umbral (0.7)')
    elif "Z-Score" in titulo or "Ensamble" in titulo:
        ax.axhline(y=3.0, color='red', linestyle='--', alpha=0.7, label='Umbral Z (3.0)')
    
    anomalias = df[df[col_anom] == True]
    ax.scatter(anomalias['time_rel'], anomalias[col_score], color='red', label='Alerta', zorder=5)
    
    for fase in fases:
        mask = df['phase'] == fase
        if mask.any():
            start, end = df[mask]['time_rel'].min(), df[mask]['time_rel'].max()
            ax.axvspan(start, end, color=colores_fase.get(fase, '#e2e3e5'), alpha=0.3)
            
    ax.set_title(titulo)
    ax.set_ylabel('Score')
    ax.legend(loc='upper left')
    ax.grid(True, linestyle='--', alpha=0.6)

plt.xlabel('Tiempo (segundos)')
plt.tight_layout()
plt.savefig("comparativa_4_estrategias.png", dpi=300)
plt.show()