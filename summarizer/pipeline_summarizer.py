from math import ceil
from pathlib import Path
from typing import List, Dict
import json, time
from json import dumps, loads

from .config import INPUT_FILE, OUTPUT_FILE, LOTE
from .schema import SummOut
from .prompts import SUMMARIZE_PROMPT_SYSTEM, SUMMARIZE_PROMPT_USER
from clasificador.openrouter_client import call_openrouter_api
from utils.time_utils import format_duration_hms

def resumir_articulo(articulo: Dict) -> str:
    """Genera un resumen de un artículo usando OpenRouter"""
    titulo = articulo.get("Titulo", "")
    cuerpo = articulo.get("Cuerpo") or articulo.get("Descripcion") or ""
    
    messages = [
        {"role": "system", "content": SUMMARIZE_PROMPT_SYSTEM},
        {"role": "user", "content": SUMMARIZE_PROMPT_USER.format(titulo=titulo, cuerpo=cuerpo)}
    ]
    
    try:
        resumen = call_openrouter_api(messages)
        return resumen.strip()
    except Exception as e:
        print(f"   ! Error resumiendo artículo '{titulo}': {e}")
        return ""

def run_pipeline() -> None:
    print("════════════════════════════════════════")
    print(" Summarizer de noticias 📰✨ ")
    print("════════════════════════════════════════")
    print(f"Archivo entrada:  {INPUT_FILE}")
    print(f"Archivo salida:   {OUTPUT_FILE}")
    print(f"Tamaño de lote:   {LOTE}")
    print("────────────────────────────────────────")

    t0 = time.time()
    articulos = loads(Path(INPUT_FILE).read_text(encoding="utf-8"))
    total_articulos = len(articulos)
    print(f"Leídos {total_articulos} artículos en {format_duration_hms(time.time()-t0)}")

    if total_articulos == 0:
        print("No hay artículos para procesar. Saliendo.")
        return

    total_lotes = ceil(total_articulos / LOTE)
    print(f"Procesando en {total_lotes} lote(s)…")
    print("────────────────────────────────────────")

    resultados: List[SummOut] = []
    t_inicio_global = time.time()

    for indice_lote, inicio_lote in enumerate(range(0, total_articulos, LOTE), start=1):
        fin_lote_excl = min(inicio_lote + LOTE, total_articulos)
        items_lote = articulos[inicio_lote:fin_lote_excl]
        print(f"[Lote {indice_lote}/{total_lotes}] Índices {inicio_lote}..{fin_lote_excl - 1}")

        t_inicio_lote = time.time()

        for i, item in enumerate(items_lote):
            resumen = resumir_articulo(item)
            resultados.append(SummOut(idx=inicio_lote + i, resumen=resumen))

        print(f"   ✓ Lote OK en {format_duration_hms(time.time() - t_inicio_lote)}")
        print("────────────────────────────────────────")

    salida = []
    for idx, item in enumerate(articulos):
        resumen = next((r.resumen for r in resultados if r.idx == idx), "")
        salida.append({**item, "Resumen": resumen})

    print(f"Escribiendo {OUTPUT_FILE}…")
    Path(OUTPUT_FILE).write_text(json.dumps(salida, ensure_ascii=False, indent=2), encoding="utf-8")

    duracion_total = time.time() - t_inicio_global
    print("════════════════════════════════════════")
    print(f" ¡Proceso completo en {format_duration_hms(duracion_total)}! ✅ ")
    print("════════════════════════════════════════")


if __name__ == "__main__":
    run_pipeline()
