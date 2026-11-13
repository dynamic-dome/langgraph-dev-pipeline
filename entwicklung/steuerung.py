"""Antworten an die Haltepunkte, gemeinsam für Kommandozeile und Leitstand.

Beide bauen die Antwort mit derselben Funktion. So kann der Browser nie etwas freigeben, was die CLI ablehnen würde,
und umgekehrt. `None` heißt „nicht angegeben“, ein leerer Text „leer angegeben“ (und ist ungültig).
"""
from entwicklung.graph import BUDGET_ENTSCHEIDUNGEN, BUDGET_PUNKTE, ENTSCHEIDUNGEN
from entwicklung.graph_s4 import ABSCHLUSS_ENTSCHEIDUNGEN, DURCHLASS, FREIGABEN, MIT_HINWEIS, PLAN_FREIGABEN
from entwicklung.stufen import KOMPLEXITAETEN

ERLAUBT_KURZ = {  # für die Oberfläche: welche Knöpfe es je Haltepunkt gibt
    "fragen": ["antwort", "abbrechen"],
    "spec_freigabe": list(FREIGABEN),
    "plan_freigabe": list(PLAN_FREIGABEN),
    "eskalation": list(ENTSCHEIDUNGEN),
    "abschluss_freigabe": list(ABSCHLUSS_ENTSCHEIDUNGEN),  # Stufe 7
    **{p: list(BUDGET_ENTSCHEIDUNGEN) for p in BUDGET_PUNKTE},  # Kostenrahmen (6b-2)
}
# DURCHLASS kommt aus graph_s4: freigeben, annehmen, mergen; trotz Einwand nur mit Begründung (6b-1, Stufe 7)


def antwort_fuer(punkt: str, entscheidung: str | None, antwort: str | None, hinweis: str | None,
                 begruendung: str | None = None, komplexitaet: str | None = None) -> dict | None:
    """Die Antwort für den Haltepunkt, oder None, wenn die Angaben nicht dazu passen.

    Eine Begründung (Freigeben trotz Einwand) reist nur mit, wenn sie Text hat. Eine Komplexität (6b-2) gilt nur
    beim Freigeben des Plans."""
    ergebnis = _antwort(punkt, entscheidung, antwort, hinweis)
    if ergebnis is not None and komplexitaet is not None:
        if punkt != "plan_freigabe" or entscheidung != "freigeben" or komplexitaet not in KOMPLEXITAETEN:
            return None
        ergebnis = {**ergebnis, "komplexitaet": komplexitaet}
    grund = (begruendung or "").strip()
    return {**ergebnis, "begruendung": grund} if ergebnis is not None and grund else ergebnis


def einwand_fehlt(punkt: str, antwort: dict, einwaende: list[str]) -> str | None:
    """Fehlertext, wenn eine Durchlass-Entscheidung trotz Einwand ohne Begründung kommt, sonst None.

    Gleiche Regel für Leitstand und CLI. Gegenstimmen der anderen Modellfamilie werden nicht still überstimmt
    (Lehre A6)."""
    if antwort.get("entscheidung") not in DURCHLASS or not einwaende:
        return None
    if str(antwort.get("begruendung") or "").strip():
        return None
    return (f"{antwort['entscheidung']} an {punkt} trotz Einwand braucht eine begruendung. Einwände: "
            + "; ".join(einwaende))


def _antwort(punkt: str, entscheidung: str | None, antwort: str | None, hinweis: str | None) -> dict | None:
    text, notiz = (antwort or "").strip(), (hinweis or "").strip()
    if punkt == "fragen" and hinweis is None:
        if text and entscheidung is None:
            return {"antwort": text}
        if entscheidung == "abbrechen" and antwort is None:
            return {"entscheidung": "abbrechen"}
    erlaubt = {"spec_freigabe": FREIGABEN, "plan_freigabe": PLAN_FREIGABEN}.get(punkt, ())
    if entscheidung in erlaubt and antwort is None:
        if entscheidung in MIT_HINWEIS:
            return {"entscheidung": entscheidung, "hinweis": notiz} if notiz else None
        if hinweis is None:
            return {"entscheidung": entscheidung}
    if punkt == "eskalation" and entscheidung in ENTSCHEIDUNGEN and antwort is None and hinweis is None:
        return {"entscheidung": entscheidung}
    if (punkt == "abschluss_freigabe" and entscheidung in ABSCHLUSS_ENTSCHEIDUNGEN and antwort is None
            and hinweis is None):
        return {"entscheidung": entscheidung}
    if punkt in BUDGET_PUNKTE and entscheidung in BUDGET_ENTSCHEIDUNGEN and antwort is None and hinweis is None:
        return {"entscheidung": entscheidung}
    return None
