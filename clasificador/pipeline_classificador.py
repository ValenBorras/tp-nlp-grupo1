from math import ceil
from pathlib import Path
from typing import Any, List, Dict
import json, time
from json import dumps, loads
from pydantic import ValidationError
import sys
sys.stdout.reconfigure(encoding="utf-8")

from .config import INPUT_FILE, OUTPUT_FILE, LOTE
from .schema import ClasifOut, MINISTERIOS_VALIDOS
from .prompts import CLASIF_PROMPT_SYSTEM, CLASIF_PROMPT_USER
from .openrouter_client import call_openrouter_api, extract_json_from_plain_text
from utils.time_utils import format_duration_hms


def validar_y_normalizar_salida(salida_modelo: Any) -> List[ClasifOut]:
    """
    Valida que la salida del modelo sea una lista de dicts compatibles con `ClasifOut`
    y normaliza los ministerios: filtra inválidos y elimina duplicados preservando el orden.
    """
    if not isinstance(salida_modelo, list):
        raise ValueError("La salida del modelo no es una lista JSON.")

    resultados: List[ClasifOut] = []

    for registro_dict in salida_modelo:
        registro = ClasifOut(**registro_dict)

        ministerios_incluidos: set[str] = set()
        ministerios_normalizados: List[str] = []

        for ministerio in registro.ministerio:
            if ministerio in MINISTERIOS_VALIDOS and ministerio not in ministerios_incluidos:
                ministerios_incluidos.add(ministerio)
                ministerios_normalizados.append(ministerio)

        resultados.append(
            ClasifOut(idx=registro.idx, ministerio=ministerios_normalizados)
        )

    return resultados

def clasificar_lote(lote: List[Dict], start_idx: int) -> List[ClasifOut]:
    """
    Envía un lote de items al modelo para obtener su clasificación y normaliza la salida.

    Parámetros:
    - lote: lista de diccionarios con los campos originales (Titulo, Descripcion, Cuerpo, ...).
    - start_idx: índice base usado para generar el campo `idx` de cada item en el payload.

    Retorna:
    - Lista de objetos ClasifOut validados y con los ministerios normalizados (sin duplicados y filtrando inválidos).

    Excepciones:
    - Lanza errores si la respuesta del modelo no es JSON válido o no cumple el esquema esperado.
    """
    compact = [{
        "idx": start_idx + i,
        "titulo": (it.get("Titulo") or "")[:300],
        "description": (it.get("Descripcion") or "")[:800],
        "body": (it.get("Cuerpo") or "")[:2000],
    } for i, it in enumerate(lote)]

    user_payload = {
        "instrucciones": CLASIF_PROMPT_USER, 
        "items": compact
    }

    messages = [
        {
            "role": "system", 
            "content": CLASIF_PROMPT_SYSTEM
        },
        {
            "role": "user", 
            "content": dumps(user_payload, ensure_ascii=False)
        }
    ]

    content = call_openrouter_api(messages)
    raw = extract_json_from_plain_text(content)
    try:
        return validar_y_normalizar_salida(raw)
    except ValidationError as ve:
        raise RuntimeError(f"Respuesta inválida del modelo: {ve}") from ve


def run_pipeline() -> None:
    """
    Orquesta el pipeline completo de clasificación de noticias.

    Qué hace:
    - Lee INPUT_FILE (JSON) con la lista de artículos.
    - Divide los artículos en lotes de tamaño LOTE y envía cada lote al modelo.
    - Reintenta el envío de cada lote hasta MAX_REINTENTOS aplicando backoff exponencial.
    - Valida y normaliza la salida del modelo contra el esquema ClasifOut.
    - Ensambla los resultados y escribe OUTPUT_FILE (JSON) al finalizar.

    Efectos secundarios y observaciones:
    - Es intensivo en I/O y en llamadas de red; imprime progreso, errores y métricas por stdout.
    - Si un lote falla tras MAX_REINTENTOS, la función relanza la excepción y termina el proceso.

    Excepciones:
    - Puede lanzar errores de lectura/escritura de archivos, de validación (pydantic) o de la API.
    """
    print("════════════════════════════════════════")
    print(" Clasificador de noticias con Minimax M2 (Open Routes) 🚀 ")
    print("════════════════════════════════════════")
    print(f"Archivo entrada:  {INPUT_FILE}")
    print(f"Archivo salida:   {OUTPUT_FILE}")
    print(f"Tamaño de lote:   {LOTE}")
    print("────────────────────────────────────────")

    t0 = time.time()
    articulos = loads(Path(INPUT_FILE).read_text(encoding="utf-8"))
    total_articulos = len(articulos)
    print(f"Leídos {total_articulos} articulos en {format_duration_hms(time.time()-t0)}")
    
    if total_articulos == 0:
        print("No hay articulos para procesar. Saliendo.")
        return

    total_lotes = ceil(total_articulos / LOTE)
    print(f"Procesando en {total_lotes} lote(s)…")
    print("────────────────────────────────────────")

    resultados: List[ClasifOut] = []
    t_inicio_global = time.time()

    MAX_REINTENTOS = 3
    BACKOFF_INICIAL_S = 1.0

    for indice_lote, inicio_lote in enumerate(range(0, total_articulos, LOTE), start=1):
        fin_lote_excl = min(inicio_lote + LOTE, total_articulos)
        fin_lote_incl = fin_lote_excl - 1
        items_lote = articulos[inicio_lote:fin_lote_excl]

        print(f"[Lote {indice_lote}/{total_lotes}] Índices {inicio_lote}..{fin_lote_incl} (n={len(items_lote)})")

        t_inicio_lote = time.time()
        backoff_actual = BACKOFF_INICIAL_S

        for intento in range(1, MAX_REINTENTOS + 1):
            try:
                print("   • Enviando a modelo…")
                respuestas_lote = clasificar_lote(items_lote, inicio_lote)
                print(f"   • Devueltos {len(respuestas_lote)} registros. Validando/normalizando…")
                resultados.extend(respuestas_lote)
                break  # éxito → salir del bucle de reintentos
            except Exception as err:
                print(f"   ! Error en lote (intento {intento}/{MAX_REINTENTOS}): {err}")
                if intento == MAX_REINTENTOS:
                    print("   ✖ Abortando este lote por 3 fallos consecutivos.")
                    raise
                print(f"   ↺ Reintentando en {backoff_actual:.1f}s…")
                time.sleep(backoff_actual)
                backoff_actual *= 2  # backoff exponencial


        duracion_lote = time.time() - t_inicio_lote
        procesados = fin_lote_excl 
        porcentaje = (procesados / total_articulos) * 100.0

        transcurrido = time.time() - t_inicio_global
        tiempo_promedio_por_item = (transcurrido / procesados) if procesados else 0.0
        eta_segundos = (total_articulos - procesados) * tiempo_promedio_por_item

        print(f"   ✓ Lote OK en {format_duration_hms(duracion_lote)} | "
              f"Progreso: {procesados}/{total_articulos} ({porcentaje:.1f}%) | "
              f"ETA ~ {format_duration_hms(eta_segundos)}")
        print("────────────────────────────────────────")

    clasificacion_por_indice: Dict[int, List[str]] = {r.idx: r.ministerio for r in resultados}
    if len(clasificacion_por_indice) != len(resultados):
        print("⚠ Aviso: hay índices repetidos en la salida del modelo.")

    print("Reconstruyendo objetos finales…")
    t_inicio_ensamble = time.time()

    salida: List[Dict] = []
    sin_clasificacion = 0

    for idx, item in enumerate(articulos):
        ministerios = clasificacion_por_indice.get(idx, [])
        if not ministerios:
            sin_clasificacion += 1

        salida.append({
            "Titulo": item.get("Titulo", ""),
            "Descripcion": item.get("Descripcion", ""),
            "Autor": item.get("Autor", ""),
            "Fuente": item.get("Fuente", ""),
            "Fecha": item.get("Fecha", ""),
            "Link": item.get("Link", ""),
            "Cuerpo": item.get("Cuerpo", ""),
            "Fuente_base": item.get("Fuente_base", ""),
            "Extraido_en": item.get("Extraido_en", ""),
            "ministerio": ministerios
        })

    print(f"Hecho en {format_duration_hms(time.time() - t_inicio_ensamble)}. "
          f"Items sin clasificación: {sin_clasificacion}/{total_articulos}")

    # Persistencia
    print(f"Escribiendo {OUTPUT_FILE}…")
    t_inicio_guardado = time.time()
    Path(OUTPUT_FILE).write_text(json.dumps(salida, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Listo en {format_duration_hms(time.time() - t_inicio_guardado)}")

    # Resumen
    duracion_total = time.time() - t_inicio_global
    print("════════════════════════════════════════")
    print(f" ¡Proceso completo en {format_duration_hms(duracion_total)}! ✅ ")
    print("════════════════════════════════════════")

if __name__ == "__main__":
    run_pipeline()