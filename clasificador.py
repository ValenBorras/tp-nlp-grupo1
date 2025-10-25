# -*- coding: utf-8 -*-
from __future__ import annotations
from pydantic import BaseModel, ValidationError
from typing import List, Any
from pathlib import Path
import json, os, time, re, requests
from math import ceil

# =========================
# Config
# =========================
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_CHAT_URL = f"{OLLAMA_HOST}/api/chat"
MODEL_NAME = os.getenv("OLLAMA_MODEL", "gpt-oss:20b")
INPUT_FILE = "test_file.json"
OUTPUT_FILE = "noticias_etiquetadas.json"

# Tamaño de lote (ajústalo según memoria/contexto de tu modelo)
LOTE = int(os.getenv("CLASIF_LOTE", "20"))

# =========================
# Esquemas
# =========================
class ClasifOut(BaseModel):
    idx: int
    ministerio: List[str]

MINISTERIOS_VALIDOS = {"Salud", "Educación", "Seguridad", "Trabajo", "Economía"}

CLASIF_PROMPT_SYSTEM = """Eres un asistente que SOLO responde en JSON válido y NADA más.
No incluyas explicaciones ni bloques de código. Responde estrictamente con un JSON que cumpla el esquema pedido.
"""

CLASIF_PROMPT_USER = """Clasifica cada item en ministerios de este conjunto exacto: {Salud, Educación, Seguridad, Trabajo, Economía}.
Puedes asignar uno o varios ministerios por item (lista).
Analiza TÍTULO, DESCRIPTION y, si está, BODY (puede venir truncado).

Formato de respuesta: EXCLUSIVAMENTE una lista JSON de objetos:
[
  {"idx": <int>, "ministerio": ["Salud", "Economía"]},
  ...
]

Reglas IMPORTANTES:
- No inventes campos extra.
- "idx" debe coincidir con el índice provisto en el payload de entrada.
- "ministerio" debe ser una lista de strings del conjunto permitido (sensibles a mayúsculas y acentos).
- No agregues texto antes o después del JSON.
"""

# =========================
# Utilidades
# =========================
json_array_regex = re.compile(r"\[\s*(?:\{.*?\})\s*(?:,\s*\{.*?\}\s*)*\]", re.DOTALL)

def _hms(sec: float) -> str:
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    if h: return f"{h}h {m}m {s}s"
    if m: return f"{m}m {s}s"
    return f"{s}s"

def extract_json_array(text: str) -> Any:
    """
    Intenta cargar el texto como JSON.
    Si falla, intenta extraer el ÚLTIMO array JSON con regex.
    """
    text = text.strip()
    # fast path
    try:
        return json.loads(text)
    except Exception:
        pass

    # extraer el último array tipo [...] del texto
    matches = list(json_array_regex.finditer(text))
    if not matches:
        raise ValueError("No se encontró un array JSON en la respuesta del modelo.")
    candidate = matches[-1].group(0)
    return json.loads(candidate)

def call_ollama_chat(messages: list[dict], model: str = MODEL_NAME, temperature: float = 0.2, timeout: int = 600) -> str:
    """
    Llama a /api/chat de Ollama. Devuelve el 'content' del mensaje del asistente.
    """
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature}
    }
    t0 = time.time()

    resp = requests.post(OLLAMA_CHAT_URL, json=payload, timeout=timeout)
    dt = time.time() - t0
    # info básica de timings de red/modelo
    print(f"      ↳ HTTP {resp.status_code} en {_hms(dt)}")
    resp.raise_for_status()
    data = resp.json()

    return data["message"]["content"]

def validar_y_normalizar_salida(raw_list: Any) -> list[ClasifOut]:
    if not isinstance(raw_list, list):
        raise ValueError("La salida del modelo no es una lista JSON.")
    parsed: list[ClasifOut] = []
    for obj in raw_list:
        item = ClasifOut(**obj)
        # Normalización: filtrar ministerios inválidos y deduplicar
        ministerios_filtrados = []
        seen = set()
        for m in item.ministerio:
            if m in MINISTERIOS_VALIDOS and m not in seen:
                ministerios_filtrados.append(m)
                seen.add(m)
        item = ClasifOut(idx=item.idx, ministerio=ministerios_filtrados)
        parsed.append(item)
    return parsed

def clasificar_lote(sub_items: list[dict], start_idx: int) -> list[ClasifOut]:
    """
    Envía un lote a Ollama y devuelve lista de ClasifOut validada.
    """
    # Compactar payload
    compact = []
    for i, it in enumerate(sub_items):
        compact.append({
            "idx": start_idx + i,
            "titulo": it.get("Titulo", "")[:300],
            "description": it.get("Descripcion", "")[:800],
            "body": (it.get("Cuerpo", "")[:2000])  # truncado para no romper contexto
        })

    user_payload = json.dumps({
        "instrucciones": CLASIF_PROMPT_USER,
        "items": compact
    }, ensure_ascii=False)

    # Mensajes estilo chat
    messages = [
        {"role": "system", "content": CLASIF_PROMPT_SYSTEM},
        {"role": "user", "content": user_payload}
    ]

    # Llamada
    content = call_ollama_chat(messages)

    # Parseo robusto a JSON
    raw = extract_json_array(content)

    # Validación con Pydantic
    try:
        return validar_y_normalizar_salida(raw)
    except ValidationError as ve:
        raise RuntimeError(f"Respuesta inválida del modelo: {ve}") from ve

# =========================
# Main
# =========================
def main() -> None:
    print("════════════════════════════════════════")
    print(" Clasificador de noticias con Ollama 🚀 ")
    print("════════════════════════════════════════")
    print(f"Modelo:           {MODEL_NAME}")
    print(f"Ollama endpoint:  {OLLAMA_CHAT_URL}")
    print(f"Archivo entrada:  {INPUT_FILE}")
    print(f"Archivo salida:   {OUTPUT_FILE}")
    print(f"Tamaño de lote:   {LOTE}")
    print("────────────────────────────────────────")

    # Leer items
    t0 = time.time()
    raw = Path(INPUT_FILE).read_text(encoding="utf-8")
    items = json.loads(raw)
    n = len(items)
    print(f"Leídos {n} items en {_hms(time.time()-t0)}")

    if n == 0:
        print("No hay items para procesar. Saliendo.")
        return

    total_batches = ceil(n / LOTE)
    print(f"Procesando en {total_batches} lote(s)...")
    print("────────────────────────────────────────")

    resultados: list[ClasifOut] = []
    start_global = time.time()

    for bidx, start in enumerate(range(0, n, LOTE), start=1):
        sub = items[start:start+LOTE]
        end = min(start + LOTE, n) - 1
        print(f"[Lote {bidx}/{total_batches}] Índices {start}..{end} (n={len(sub)})")

        # Reintentos básicos por si el modelo se va de formato
        intentos = 0
        backoff = 1.0

        t_batch = time.time()
        while True:
            try:
                print("   • Enviando a modelo…")
                lote_res = clasificar_lote(sub, start)
                print(f"   • Devueltos {len(lote_res)} registros. Validando/normalizando…")
                resultados.extend(lote_res)
                break
            except Exception as e:
                intentos += 1
                print(f"   ! Error en lote (intento {intentos}/3): {e}")
                if intentos >= 3:
                    print("   ✖ Abortando este lote por 3 fallos consecutivos.")
                    raise
                print(f"   ↺ Reintentando en {backoff:.1f}s…")
                time.sleep(backoff)
                backoff *= 2

        dt_batch = time.time() - t_batch
        done = min(end + 1, n)
        pct = (done / n) * 100.0
        elapsed = time.time() - start_global
        # ETA simple: proporcional al promedio de tiempo por item
        avg_per_item = elapsed / done
        remaining = n - done
        eta = remaining * avg_per_item
        print(f"   ✓ Lote OK en {_hms(dt_batch)} | Progreso: {done}/{n} ({pct:.1f}%) | ETA ~ {_hms(eta)}")
        print("────────────────────────────────────────")

    # idx -> ministerio
    by_idx = {r.idx: r.ministerio for r in resultados}
    if len(by_idx) != len(resultados):
        print(f"⚠ Aviso: hay índices repetidos en la salida del modelo (mapeados {len(by_idx)} de {len(resultados)}).")

    # Reconstrucción del objeto final
    print("Reconstruyendo objetos finales…")
    t_build = time.time()
    salida = []
    missing = 0
    for idx, it in enumerate(items):
        m = by_idx.get(idx, [])
        if not m:
            missing += 1
        salida.append({
            "Titulo": it.get("Titulo", ""),
            "Descripcion": it.get("Descripcion", ""),
            "Autor": it.get("Autor", ""),
            "Fuente": it.get("Fuente", ""),
            "Fecha": it.get("Fecha", ""),
            "Link": it.get("Link", ""),
            "Cuerpo": it.get("Cuerpo", ""),
            "Fuente_base": it.get("Fuente_base", ""),
            "Extraido_en": it.get("Extraido_en", ""),
            "ministerio": m
        })
    print(f"Hecho en {_hms(time.time()-t_build)}. Items sin clasificación: {missing}/{n}")

    # Guardar
    print(f"Escribiendo {OUTPUT_FILE}…")
    t_save = time.time()
    Path(OUTPUT_FILE).write_text(json.dumps(salida, ensure_ascii=False, indent=2), encoding="utf-8")
    size = Path(OUTPUT_FILE).stat().st_size
    print(f"Listo: {OUTPUT_FILE} ({len(salida)} items, {size/1024:.1f} KiB) en {_hms(time.time()-t_save)}")

    total_time = time.time() - start_global
    print("════════════════════════════════════════")
    print(f" ¡Proceso completo en {_hms(total_time)}! ✅ ")
    print("════════════════════════════════════════")

if __name__ == "__main__":
    main()
