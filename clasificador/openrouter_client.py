from __future__ import annotations
import os, json, re, time, requests
from json import dumps
from typing import Any, List, Dict
from .config import TEMPERATURE, TOP_P

OPENROUTER_API_URL = os.getenv("OPENROUTER_API_URL", "https://openrouter.ai/api/v1/chat/completions")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL   = os.getenv("OPENROUTER_MODEL", "minimax/minimax-m2:free")
REQUEST_TIMEOUT    = float(os.getenv("OPENROUTER_TIMEOUT", "120"))

# Regex robusto para extraer un ARRAY JSON aunque venga rodeado de texto/código
_json_array_regex = re.compile(r"\[\s*(?:\{.*?\})\s*(?:,\s*\{.*?\}\s*)*\]", re.DOTALL)

def extract_json_from_plain_text(text: str) -> Any:
    """
    Intenta parsear un array JSON directo; si falla, busca la primera coincidencia
    que 'parezca' un array JSON y la parsea.
    """
    text = (text or "").strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
    except Exception:
        pass

    m = _json_array_regex.search(text)
    if not m:
        raise ValueError("No se encontró un array JSON en la respuesta del modelo.")
    return json.loads(m.group(0))

def call_openrouter_api(messages: List[Dict[str, str]]) -> str:
    """
    Envía un chat completion a OpenRouter y devuelve el 'content' del primer choice.
    `messages` debe ser una lista de dicts con 'role' y 'content' (igual que en Ollama).
    """
    if not OPENROUTER_API_KEY:
        raise RuntimeError("Falta OPENROUTER_API_KEY en variables de entorno.")

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": messages,
        "temperature": TEMPERATURE,
        "top_p": TOP_P,
        "response_format": {"type": "text"},
    }

    response = requests.post(
        OPENROUTER_API_URL, 
        headers=headers, 
        data=dumps(payload, ensure_ascii=False), 
        timeout=REQUEST_TIMEOUT
    )
    
    if response.status_code != 200:
        raise RuntimeError(f"OpenRouter {response.status_code}: {response.text[:500]}")

    data = response.json()
    try:
        return data["choices"][0]["message"]["content"]
    except Exception:
        raise RuntimeError(f"Respuesta inesperada de OpenRouter: {json.dumps(data)[:800]}")
