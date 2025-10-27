def format_duration_hms(sec: float) -> str:
    """
    Convierte segundos a un string "Hh Mm Ss" para logs.

    - Redondea hacia abajo los segundos (p. ej., 9.8 -> 9s).
    - Omite horas si son 0; omite minutos si son 0 y hay horas=0; siempre muestra segundos.
    - Útil para imprimir tiempos transcurridos y ETA.

    Args:
        sec: Duración en segundos (puede ser float).

    Returns:
        Cadena en formato compacto, p. ej. "2h 3m 4s", "5m 0s", "7s".

    Ejemplos:
        >>> format_duration_hms(0)
        '0s'
        >>> format_duration_hms(125)
        '2m 5s'
        >>> format_duration_hms(7322)
        '2h 2m 2s'
    """
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    if h: return f"{h}h {m}m {s}s"
    if m: return f"{m}m {s}s"
    return f"{s}s"