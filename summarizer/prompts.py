# summarizer/prompts.py

# Prompt para el rol "system" del modelo
SUMMARIZE_PROMPT_SYSTEM = """
Eres un asistente experto en resumir noticias en español.
Recibes artículos con título y cuerpo, y tu tarea es generar un resumen claro, conciso y coherente.
Evita repetir información, no agregues opiniones, y mantén el lenguaje formal.
"""

# Prompt para el rol "user" del modelo
# Se utiliza str.format para insertar título y cuerpo del artículo
SUMMARIZE_PROMPT_USER = """
Título del artículo:
{titulo}

Cuerpo del artículo:
{cuerpo}

Por favor, genera un resumen breve y coherente en español (unas 2-5 frases máximo).
"""
