"""Konvergenz der Spec-Runden (ab Stufe 6c): Nachprüfung gegen die Vorfassung statt Neuprüfung von null.

A8 (21.10.) brauchte vier Spec-Fassungen. Die Befunde entstanden meist erst durch die vorige Korrektur, und die
Prüfer prüften jede Fassung von vorn. Ab der zweiten Fassung bekommen sie deshalb den Diff und die alten Punkte.
Jeder neue Punkt trägt eine Herkunft, jeder alte einen Status. `einordnen` entscheidet danach deterministisch, was
eine neue Runde auslöst. Die Regel sitzt im Graphen und nicht nur im Prompt: Eine Regel im Werkzeug ist eine Garantie,
eine Regel im Prompt nur eine Bitte. Die Codex-Sperre aus 6b-1 bleibt davon unberührt (graph_s4.codex_einwaende).
"""
import difflib

from entwicklung.planung import SPEC_PRUEF_K_SCHEMA, _TEXT, _liste, _objekt

HERKUENFTE = ("aenderung", "widerspruch", "sonstiges")
STATUS = ("geloest", "teilweise", "offen")  # Rangfolge: der schlechteste Status über die Prüfer gilt
DIFF_GRENZE = 30000  # Zeichen je Diff; A8 hatte eine Spec von 21,7 KB

NACHPRUEF_SCHEMA = _objekt(**{
    **SPEC_PRUEF_K_SCHEMA["properties"],
    "punkte": _liste(_objekt(schwere={"type": "string", "enum": ["major", "minor"]}, aussage=_TEXT,
                             herkunft={"type": "string", "enum": list(HERKUENFTE)})),
    "alte_punkte": _liste(_objekt(nr={"type": "integer"}, status={"type": "string", "enum": list(STATUS)},
                                  grund=_TEXT)),
})

AUFTRAG = """## Nachprüfung (Vorfassung liegt vor)
Prüfe nicht von vorn. Beantworte zuerst für jeden alten Punkt in `alte_punkte`, ob er in der neuen Fassung
`geloest`, `teilweise` oder `offen` ist (`grund`: ein Satz). Melde danach in `punkte` nur, was neu ist, mit
`herkunft`: `aenderung`, wenn die Stelle im Diff oben steht oder von ihm abhängt; `widerspruch`, wenn die Spec
dem Wunsch oder einer Antwort von Dominic widerspricht; `sonstiges` für alles, was schon in der Vorfassung so stand.
"""


def diff_text(alt: str, neu: str, name: str) -> str:
    if alt == neu:
        return f"{name}: unverändert"
    text = "".join(difflib.unified_diff(alt.splitlines(keepends=True), neu.splitlines(keepends=True),
                                        fromfile=f"{name} (vorher)", tofile=f"{name} (jetzt)"))
    if len(text) > DIFF_GRENZE:
        text = text[:DIFF_GRENZE] + f"\n… (Diff gekürzt, {len(text) - DIFF_GRENZE} Zeichen fehlen)"
    return text


def _punkt_zeile(p: dict) -> str:
    return f"{p['nr']}. [{p.get('pruefer', '?')}, {p['schwere']}] {p['aussage']}"


def nachpruef_text(vorige: dict, spec: str, tests: dict[str, str]) -> str:
    alte_tests = vorige.get("tests") or {}
    diffs = [diff_text(alte_tests.get(n, ""), tests.get(n, ""), n) for n in sorted(set(alte_tests) | set(tests))]
    return "\n".join([
        "## Diff der Spec zur Vorfassung", "```diff", diff_text(vorige.get("spec") or "", spec, "spec"), "```",
        "## Diff der Akzeptanztests zur Vorfassung", "```diff", "\n".join(diffs) or "(keine Tests)", "```",
        "## Alte Punkte (zur Vorfassung)", "\n".join(_punkt_zeile(p) for p in vorige.get("punkte") or []) or "(keine)",
        "", AUFTRAG])


def nummeriert(punkte: list[dict]) -> list[dict]:
    return [{**p, "nr": i} for i, p in enumerate(punkte, 1)]


def _status(eintrag: dict) -> str:
    s = eintrag.get("status")
    return s if s in STATUS else "offen"  # unbekannter Status zählt nicht als gelöst


def einordnen(pruefungen: list[dict], vorige_punkte: list[dict] | None) -> dict:
    """{"ausloesend", "liste", "alte"}. vorige_punkte None = erste Prüfung: jeder Major löst aus wie bisher."""
    verwertbar = [p for p in pruefungen or [] if p.get("ok")]
    neu = []
    for p in verwertbar:
        for punkt in p.get("punkte") or []:
            h = "erstpruefung" if vorige_punkte is None else punkt.get("herkunft")
            neu.append({"pruefer": p["pruefer"], "schwere": punkt.get("schwere"), "aussage": punkt.get("aussage"),
                        "herkunft": h if h == "erstpruefung" or h in HERKUENFTE else "unbekannt"})
    alte = []
    for alt in vorige_punkte or []:
        bewertet = {}
        for p in verwertbar:
            treffer = [e for e in p.get("alte_punkte") or []
                       if isinstance(e, dict) and type(e.get("nr")) is int and e["nr"] == alt["nr"]]
            bewertet[p["pruefer"]] = _status(treffer[0]) if treffer else "offen"  # ausgelassen = nicht gelöst
        status = max(bewertet.values(), key=STATUS.index) if bewertet else "offen"
        alte.append({"nr": alt["nr"], "pruefer": alt.get("pruefer"), "schwere": alt["schwere"],
                     "aussage": alt["aussage"], "status": status, "bewertet": bewertet,
                     "nur_sperre": bool(alt.get("nur_sperre"))})
    # nur_sperre: ein Codex-Major von der Liste, der nur für die Sperre mitreist (Codex-Verifier 6c, V1)
    loest_aus = ([p for p in neu if p["schwere"] == "major" and p["herkunft"] != "sonstiges"]
                 + [a for a in alte if a["schwere"] == "major" and a["status"] != "geloest" and not a["nur_sperre"]])
    liste = [p for p in [*neu, *alte] if not any(p is q for q in loest_aus)]
    return {"ausloesend": loest_aus, "liste": liste, "alte": alte}


def verlauf_eintrag(spec_runde: int, nachgebessert: bool, spec: str, annahmen: list, tests: list[str],
                    einordnung: dict) -> dict:
    return {"fassung": spec_runde + 1, "nachgebessert": nachgebessert, "zeichen": len(spec),
            "annahmen": len(annahmen), "tests": len(tests), "ausloesend": len(einordnung["ausloesend"]),
            "liste": len(einordnung["liste"])}


def punkt_zeile(p: dict) -> str:
    """Eine Zeile für CLI, Bericht und Rat: neue Punkte mit Herkunft, alte mit ihrem Status."""
    marke = f"alt {p['status']}" if "status" in p else p.get("herkunft", "?")
    return f"[{p.get('pruefer', '?')}, {p.get('schwere')}, {marke}] {p.get('aussage')}"


def verlauf_zeile(v: dict) -> str:
    return (f"Fassung {v['fassung']}: {v['zeichen']} Zeichen, {v['annahmen']} Annahmen, {v['tests']} Tests, "
            f"{v['ausloesend']} auslösend, {v['liste']} auf der Liste"
            + (" (Tests nachgebessert)" if v.get("nachgebessert") else ""))
