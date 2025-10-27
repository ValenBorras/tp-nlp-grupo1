from __future__ import annotations
import os

INPUT_FILE = os.getenv("INPUT_FILE", "./data/noticias_test.json")
OUTPUT_FILE = os.getenv("OUTPUT_FILE", "./data/noticias_etiquetadas_test.json")

LOTE = int(os.getenv("CLASIF_LOTE", "20"))
TEMPERATURE = float(os.getenv("CLASIF_TEMPERATURE", "0.2"))
TIMEOUT = int(os.getenv("CLASIF_TIMEOUT", "600")) 
TOP_P = 0.9
