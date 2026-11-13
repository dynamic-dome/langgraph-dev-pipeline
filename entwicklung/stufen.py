"""Modellstufen (Stufe 6b-2): je Rolle und Komplexität ein Modell und eine Reasoning-Stufe.

Die Komplexität schätzen beide Modellfamilien (Claude schreibt die Spec, Codex prüft sie); es gilt die höhere
Schätzung, Dominic kann sie an der Plan-Freigabe ändern. Sie ist der einzige Regler: Implementierer und Prüfer der
Umsetzung ziehen Modell und Effort aus dieser Tabelle. Vor der Schätzung (klären, Spec, Tests, Plan) gelten feste
Stufen. Entscheide Dominic 20.10.: sonnet implementiert, opus prüft, haiku nur als bewusstes Experiment (Startwahl),
Fable bleibt Berater auf Klick. Codex bleibt auf high: codex-cli 0.163.0 nahm auch einen erfundenen Wert („ultra“)
ohne Fehler an, dass höhere Werte wirken, ist nicht belegt.
"""
KOMPLEXITAETEN = ("einfach", "mittel", "schwer")
STANDARD = "mittel"

STUFEN_TABELLE = {  # (Modell, Effort); Modell None: Codex mit seinem Standardmodell
    "implementierer": {"einfach": ("sonnet", "medium"), "mittel": ("sonnet", "high"), "schwer": ("opus", "high")},
    "pruefer": {"einfach": ("opus", "high"), "mittel": ("opus", "high"), "schwer": ("opus", "xhigh")},
    "codex": {k: (None, "high") for k in KOMPLEXITAETEN},
}
PLANUNG_STUFEN = {"planer": ("sonnet", "high"), "spec_pruefer": ("opus", "high"), "codex": (None, "high")}
STANDARD_TIMEOUT = 600
TIMEOUT_OPUS_IMPLEMENTIERER = 900
TIMEOUT_XHIGH = 1200  # opus mit xhigh braucht deutlich länger
START_FELD = {"implementierer": "modell", "pruefer": "pruefer_modell"}  # ausdrückliche Startwahl schlägt die Tabelle


def stufe_fuer(rolle: str, komplexitaet: str | None) -> tuple[str | None, str]:
    return STUFEN_TABELLE[rolle][komplexitaet if komplexitaet in KOMPLEXITAETEN else STANDARD]


def hoechste(*werte) -> str:
    """Die höchste gültige Schätzung (einfach < mittel < schwer); ohne gültige gilt mittel."""
    gueltig = [w for w in werte if w in KOMPLEXITAETEN]
    return max(gueltig, key=KOMPLEXITAETEN.index) if gueltig else STANDARD


def stufe_im_lauf(state, rolle: str) -> dict:
    """Modell, Effort und Timeout für eine Rolle in diesem Lauf (Startwahl des Modells gewinnt, Effort nicht)."""
    modell, effort = stufe_fuer(rolle, state.get("komplexitaet"))
    gewaehlt = state.get(START_FELD.get(rolle, ""))
    if gewaehlt and gewaehlt != "auto":
        modell = gewaehlt
    timeout = STANDARD_TIMEOUT
    if effort == "xhigh":
        timeout = TIMEOUT_XHIGH
    elif rolle == "implementierer" and modell == "opus":
        timeout = TIMEOUT_OPUS_IMPLEMENTIERER
    return {"modell": modell, "effort": effort, "timeout": timeout}
