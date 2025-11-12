import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List
import time

from .config import INPUT_FILE, OUTPUT_FILE
from .schema import SummOut
from .prompts import SUMMARIZE_PROMPT_SYSTEM, SUMMARIZE_PROMPT_USER
from clasificador.schema import MINISTERIOS_VALIDOS
from clasificador.openrouter_client import call_openrouter_api
from utils.time_utils import format_duration_hms


def _truncate(texto: str, max_chars: int) -> str:
    """Corta una cadena al tamaño máximo indicado, agregando un elipsis si se recorta."""
    texto = (texto or "").strip()
    if len(texto) <= max_chars:
        return texto
    return texto[:max_chars - 1].rstrip() + "…"


def _formatear_articulos(articulos: Iterable[Dict]) -> str:
    """Arma un bloque de texto numerado con título, fuente, fecha y contenido de cada artículo."""
    segmentos: List[str] = []
    for idx, articulo in enumerate(articulos, start=1):
        titulo = _truncate(articulo.get("Titulo", ""), 220)
        descripcion = _truncate(articulo.get("Descripcion", ""), 380)
        cuerpo = _truncate(
            articulo.get("Cuerpo") or articulo.get("Descripcion") or "", 900
        )
        fuente = articulo.get("Fuente", "")
        fecha = articulo.get("Fecha", "")
        segmentos.append(
            f"{idx}. Título: {titulo}\n"
            f"   Fuente: {fuente} | Fecha: {fecha}\n"
            f"   Descripción: {descripcion}\n"
            f"   Cuerpo: {cuerpo}"
        )
    return "\n\n".join(segmentos)


def _envolver_markdown(ministerio: str, total: int, cuerpo: str) -> str:
    """Crea una salida Markdown estándar con encabezado y metadatos para el resumen."""
    fecha = datetime.now().date().isoformat()
    contenido = cuerpo.strip() or "_No se generó un resumen._"
    return (
        f"## Informe Ejecutivo: {ministerio}\n\n"
        f"- **Fecha:** {fecha}\n"
        f"- **Artículos analizados:** {total}\n\n"
        f"{contenido}"
    )


def resumir_ministerio(ministerio: str, articulos: List[Dict]) -> str:
    """Genera un resumen agregado para un ministerio usando OpenRouter."""
    listado = _formatear_articulos(articulos)
    messages = [
        {"role": "system", "content": SUMMARIZE_PROMPT_SYSTEM},
        {
            "role": "user",
            "content": SUMMARIZE_PROMPT_USER.format(
                ministerio=ministerio, total=len(articulos), noticias=listado
            ),
        },
    ]

    try:
        respuesta = call_openrouter_api(messages)
        return respuesta.strip()
    except Exception as exc:
        print(f"   ! Error generando resumen del ministerio '{ministerio}': {exc}")
        return ""


def run_pipeline(ministerio: str) -> None:
    input_file = Path(INPUT_FILE)
    output_file = Path(OUTPUT_FILE)

    print("════════════════════════════════════════")
    print(" Summarizer por ministerio 📰✨ ")
    print("════════════════════════════════════════")
    print(f"Archivo entrada:  {input_file}")
    print(f"Archivo salida:   {output_file}")
    print(f"Ministerio:       {ministerio}")
    print("────────────────────────────────────────")

    t0 = time.time()
    articulos = json.loads(input_file.read_text(encoding="utf-8"))
    total_articulos = len(articulos)
    print(
        f"Leídos {total_articulos} artículos en "
        f"{format_duration_hms(time.time() - t0)}"
    )

    if total_articulos == 0:
        print("No hay artículos para procesar. Saliendo.")
        return

    articulos_filtrados = [
        articulo
        for articulo in articulos
        if ministerio in (articulo.get("ministerio") or [])
    ]

    if not articulos_filtrados:
        print(f"No se encontraron artículos etiquetados con '{ministerio}'.")
        output = SummOut(
            ministerio=ministerio, total_articulos=0, resumen=_envolver_markdown(ministerio, 0, "")
        ).model_dump()
        output_file.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        return

    print(
        f"Procesando {len(articulos_filtrados)} artículos asociados al ministerio "
        f"{ministerio}…"
    )

    t_inicio = time.time()
    resumen = resumir_ministerio(ministerio, articulos_filtrados)
    duracion = format_duration_hms(time.time() - t_inicio)
    print(f"   ✓ Resumen generado en {duracion}")
    print("────────────────────────────────────────")

    resumen_markdown = _envolver_markdown(ministerio, len(articulos_filtrados), resumen)

    salida = SummOut(
        ministerio=ministerio,
        total_articulos=len(articulos_filtrados),
        resumen=resumen_markdown,
    ).model_dump()

    print(f"Escribiendo {output_file}…")
    output_file.write_text(json.dumps(salida, ensure_ascii=False, indent=2), encoding="utf-8")

    print("════════════════════════════════════════")
    print(
        f" ¡Proceso completo en {format_duration_hms(time.time() - t0)}! ✅ "
    )
    print("════════════════════════════════════════")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Genera un resumen agregado por ministerio a partir de noticias etiquetadas."
    )
    parser.add_argument(
        "--ministerio",
        required=True,
        help=f"Ministerio objetivo ({', '.join(sorted(MINISTERIOS_VALIDOS))})",
    )
    args = parser.parse_args()
    ministerio_normalizado = args.ministerio.strip()
    if ministerio_normalizado not in MINISTERIOS_VALIDOS:
        parser.error(
            f"Ministerio inválido '{args.ministerio}'. Debe ser uno de: "
            f"{', '.join(sorted(MINISTERIOS_VALIDOS))}."
        )
    args.ministerio = ministerio_normalizado
    return args


if __name__ == "__main__":
    params = _parse_args()
    run_pipeline(params.ministerio)
