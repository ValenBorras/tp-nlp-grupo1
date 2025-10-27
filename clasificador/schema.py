from __future__ import annotations
from pydantic import BaseModel
from typing import List

class ClasifOut(BaseModel):
    idx: int
    ministerio: List[str]

MINISTERIOS_VALIDOS = {"Salud", "Educación", "Seguridad", "Trabajo", "Economía"}
