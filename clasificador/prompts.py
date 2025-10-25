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
