from pydantic import BaseModel


class SummOut(BaseModel):
    ministerio: str
    total_articulos: int
    resumen: str
