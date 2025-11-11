from pathlib import Path

# Rutas
DATA_DIR = Path(__file__).parent / "data"
INPUT_FILE = DATA_DIR / "noticias.json"
OUTPUT_FILE = DATA_DIR / "noticias_resumidas.json"

# Parámetros
LOTE = 10
