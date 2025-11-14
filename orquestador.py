import subprocess
import sys
from datetime import datetime
from pathlib import Path
from clasificador.schema import MINISTERIOS_VALIDOS

# Python del venv (clave para evitar errores)
PY = sys.executable


# -------------------------------
# Funciones auxiliares
# -------------------------------

def log_path(script_name: str) -> Path:
    """Genera un path de log con timestamp."""
    logs_dir = Path("data/outputs/logs")
    logs_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return logs_dir / f"{script_name}_{ts}.log"


def run(command: list[str], log_file: Path):
    """Ejecuta un comando python y guarda stdout/stderr en un log."""
    print(f"\n▶ Ejecutando: {' '.join(command)}")
    print(f"   ➜ Log: {log_file}")

    with log_file.open("w", encoding="utf-8") as lf:
        process = subprocess.Popen(
            command,
            stdout=lf,
            stderr=lf,
            text=True
        )
        process.wait()

    if process.returncode == 0:
        print("   ✓ OK")
    else:
        print("   ✗ ERROR (ver log)")


# -------------------------------
# Orquestación
# -------------------------------

def main():

    print("\n══════════════════════════════════════════")
    print("      ORQUESTADOR COMPLETO DE PIPELINES")
    print("══════════════════════════════════════════")

    print(f"\nUsando Python: {PY}")

    # -------------------------------------------------------
    # 1) Scraper → obtiene noticias (se ejecuta como script)
    # -------------------------------------------------------
    run(
        [PY, "newsScraper.py"],
        log_path("newsScraper")
    )

    # -------------------------------------------------------
    # 2) Clasificador → ejecutado como módulo
    # -------------------------------------------------------
    run(
        [PY, "-m", "clasificador.pipeline_classificador"],
        log_path("pipeline_classificador")
    )

    # -------------------------------------------------------
    # 3) Summarizer por ministerio → ejecutado como módulo
    # -------------------------------------------------------
    for ministerio in MINISTERIOS_VALIDOS:
        print(f"\n📌 Generando resumen para: {ministerio}")

        run(
            [PY, "-m", "summarizer.pipeline_summarizer", "--ministerio", ministerio],
            log_path(f"summarizer_{ministerio}")
        )

    print("\n🎉 Todos los procesos han finalizado.")
    print("→ Revisar logs en ./data/outputs/logs/")
    print("→ Revisar resúmenes en ./data/resumenes/")


if __name__ == "__main__":
    main()
