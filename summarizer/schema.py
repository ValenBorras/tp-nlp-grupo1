from pydantic import BaseModel

class SummOut(BaseModel):
    idx: int
    resumen: str
