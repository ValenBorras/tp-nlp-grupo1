import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from clasificador.schema import MINISTERIOS_VALIDOS

from .config import (
    EVAL_LANG,
    EVAL_METRICS_FILE,
    EVAL_MODEL_NAME,
    EVAL_RESCALE_WITH_BASELINE,
    INPUT_FILE,
    OUTPUT_FILE,
)

DEFAULT_MODEL = EVAL_MODEL_NAME
DEFAULT_PRED_PATH = Path(OUTPUT_FILE)
DEFAULT_SOURCE_PATH = Path(INPUT_FILE)
DEFAULT_OUTPUT_PATH = Path(EVAL_METRICS_FILE)


@dataclass
class SummaryRecord:
    ministerio: str
    resumen: str


@dataclass
class ArticleRecord:
    ministerios: List[str]
    contenido: str


def _load_json(path: Path) -> List[SummaryRecord]:
    """Carga un JSON con resúmenes generados y lo normaliza a SummaryRecord."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return [_to_summary_record(data, path)]
    if isinstance(data, list):
        return [_to_summary_record(item, path) for item in data]
    raise ValueError(
        f"El archivo {path} debe contener un diccionario o una lista de diccionarios."
    )


def _to_summary_record(raw: Dict, source: Path) -> SummaryRecord:
    """Convierte un diccionario en un SummaryRecord validando campos obligatorios."""
    try:
        ministerio = raw["ministerio"]
        resumen = raw["resumen"]
    except KeyError as exc:
        raise KeyError(
            f"Falta la clave requerida {exc} en {source}. Se esperaban "
            "'ministerio' y 'resumen'."
        ) from exc
    if not isinstance(ministerio, str) or not isinstance(resumen, str):
        raise TypeError(
            f"Los campos 'ministerio' y 'resumen' deben ser cadenas. Found: "
            f"type(ministerio)={type(ministerio)}, type(resumen)={type(resumen)}."
        )
    return SummaryRecord(ministerio=ministerio, resumen=resumen)


def _match_pairs(
    preds: Iterable[SummaryRecord], refs: Iterable[SummaryRecord]
) -> Tuple[List[str], List[str], List[str]]:
    preds_by_key: Dict[str, SummaryRecord] = {item.ministerio: item for item in preds}
    refs_by_key: Dict[str, SummaryRecord] = {item.ministerio: item for item in refs}

    missing_preds = sorted(set(refs_by_key) - set(preds_by_key))
    extra_preds = sorted(set(preds_by_key) - set(refs_by_key))

    if missing_preds:
        print(
            "⚠️  Aviso: no se encontraron predicciones para los ministerios "
            f"{', '.join(missing_preds)}. Se omitirán en el cálculo.",
            file=sys.stderr,
        )
    if extra_preds:
        print(
            "⚠️  Aviso: hay predicciones sin referencia para los ministerios "
            f"{', '.join(extra_preds)}. Se omitirán en el cálculo.",
            file=sys.stderr,
        )

    common_keys = sorted(set(preds_by_key) & set(refs_by_key))

    return (
        common_keys,
        [preds_by_key[key].resumen for key in common_keys],
        [refs_by_key[key].resumen for key in common_keys],
    )


def _load_articles(path: Path) -> List[ArticleRecord]:
    """Lee artículos etiquetados y devuelve una lista con ministerios y contenido completo."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(
            f"El archivo {path} debe contener una lista de artículos con campo 'ministerio'."
        )

    registros: List[ArticleRecord] = []
    for idx, raw in enumerate(data):
        ministerios = raw.get("ministerio") or []
        if not ministerios:
            continue
        if isinstance(ministerios, str):
            ministerios = [ministerios]
        ministerios = [str(m).strip() for m in ministerios if str(m).strip()]
        if not ministerios:
            continue
        partes: List[str] = []
        for campo in ("Titulo", "Descripcion", "Cuerpo"):
            valor = raw.get(campo)
            if isinstance(valor, str) and valor.strip():
                partes.append(valor.strip())
        if not partes:
            continue
        contenido = "\n\n".join(partes)
        registros.append(ArticleRecord(ministerios=ministerios, contenido=contenido))
    return registros


def _aggregate_articles_by_ministerio(
    articulos: Iterable[ArticleRecord],
) -> Dict[str, str]:
    """Agrupa artículos por ministerio concatenando sus fragmentos en un solo texto."""
    agregados: Dict[str, List[str]] = {}
    for articulo in articulos:
        for ministerio in articulo.ministerios:
            agregados.setdefault(ministerio, []).append(articulo.contenido)
    return {
        ministerio: "\n\n".join(fragmentos) for ministerio, fragmentos in agregados.items()
    }


def _compute_bertscore(
    preds: Sequence[str],
    refs: Sequence[str],
    *,
    lang: str,
    model_type: Optional[str],
    rescale_with_baseline: bool,
) -> Tuple[List[float], List[float], List[float]]:
    """Calcula precision, recall y f1 de BERTScore para pares de textos."""
    try:
        from bert_score import score
    except ImportError as exc:
        raise ImportError(
            "No se pudo importar 'bert_score'. Asegúrate de instalar la dependencia "
            "ejecutando 'pip install bert-score torch'."
        ) from exc

    precision, recall, f1 = score(
        preds,
        refs,
        lang=lang,
        model_type=model_type,
        rescale_with_baseline=rescale_with_baseline,
    )
    return (
        [float(val) for val in precision],
        [float(val) for val in recall],
        [float(val) for val in f1],
    )


def evaluate_bertscore(
    pred_path: Path,
    source_path: Path,
    ministerio: str,
    *,
    lang: str = EVAL_LANG,
    model_type: Optional[str] = DEFAULT_MODEL,
    rescale_with_baseline: bool = EVAL_RESCALE_WITH_BASELINE,
) -> Dict:
    """Evalúa BERTScore para el resumen generado de un ministerio dado."""
    pred_records = _load_json(pred_path)
    objetivo = next(
        (registro for registro in pred_records if registro.ministerio == ministerio),
        None,
    )
    if objetivo is None:
        raise ValueError(
            f"No se encontró un resumen generado para el ministerio '{ministerio}' "
            f"en {pred_path}."
        )

    articulos = _load_articles(source_path)
    referencias = _aggregate_articles_by_ministerio(articulos)
    referencia = referencias.get(ministerio)

    if not referencia:
        raise ValueError(
            f"No se pudieron construir referencias a partir de {source_path} "
            f"para el ministerio '{ministerio}'."
        )

    precision, recall, f1 = _compute_bertscore(
        [objetivo.resumen],
        [referencia],
        lang=lang,
        model_type=model_type,
        rescale_with_baseline=rescale_with_baseline,
    )

    resultado = {
        "ministerio": ministerio,
        "precision": precision[0],
        "recall": recall[0],
        "f1": f1[0],
        "config": {
            "lang": lang,
            "model_type": model_type,
            "rescale_with_baseline": rescale_with_baseline,
            "pred_path": str(pred_path),
            "source_path": str(source_path),
            "ministerio": ministerio,
        },
    }
    return resultado


def _pretty_print(results: Dict) -> None:
    """Muestra en consola las métricas calculadas para un ministerio."""
    print("════════════════════════════════════════")
    print(" Métricas BERTScore ")
    print("════════════════════════════════════════")
    print(
        f"{results['ministerio']:>15} → "
        f"P: {results['precision']:.4f} | "
        f"R: {results['recall']:.4f} | "
        f"F1: {results['f1']:.4f}"
    )
    print("════════════════════════════════════════")


def print_bertscore_report(results: Dict) -> None:
    """Función pública para mostrar métricas en consola."""
    _pretty_print(results)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI principal para calcular BERTScore sobre un ministerio específico."""
    parser = argparse.ArgumentParser(
        description="Calcula BERTScore para un ministerio específico usando el resumen generado."
    )
    parser.add_argument(
        "--ministerio",
        required=True,
        choices=sorted(MINISTERIOS_VALIDOS),
        help="Ministerio a evaluar (debe coincidir con el usado al generar el resumen).",
    )
    args = parser.parse_args(argv)
    ministerio = args.ministerio.strip()

    results = evaluate_bertscore(
        pred_path=DEFAULT_PRED_PATH,
        source_path=DEFAULT_SOURCE_PATH,
        ministerio=ministerio,
    )

    _pretty_print(results)

    DEFAULT_OUTPUT_PATH.write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nMétricas guardadas en {DEFAULT_OUTPUT_PATH}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

