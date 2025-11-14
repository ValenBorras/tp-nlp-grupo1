from pathlib import Path

# Rutas
INPUT_FILE = "./data/noticias_etiquetadas.json"
OUTPUT_FILE = "./data/resumenes"
EVAL_METRICS_FILE = "./data/metricas_bertscore.json"
EVAL_MODEL_NAME = "bert-base-multilingual-cased"
EVAL_LANG = "es"
EVAL_RESCALE_WITH_BASELINE = True

# Parámetros
LOTE = 10
