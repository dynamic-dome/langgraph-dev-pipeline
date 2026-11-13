"""Daten für den Leitstand: der Graph als Diagramm und jeder Lauf mit seinem Stand.

Einzige Quelle ist der Checkpointer. Deshalb sieht der Leitstand auch Läufe, die die CLI in einem anderen Prozess
ausführt: Beide schreiben in dieselbe `data/checkpoints.db`. Der Graph beschreibt sich selbst
(`get_graph().to_json()`); hier kommen Ebenen und Spalten fürs Zeichnen dazu, wie beim Puls in Lab 1.
"""
from pathlib import Path

from entwicklung.berater import einwaende_fuer
from entwicklung.pfade import berichte_dir
from entwicklung.speicher import PRAEFIX, WARTEPUNKTE, _schluessel, stufe_des_laufs, wartepunkt

MAX_ZEICHEN = 40_000  # je Datei, die der Browser zur Freigabe zeigt

PLANUNG = {"klaeren", "fragen", "stufe_waehlen", "budget_spec", "budget_plan", "spec_schreiben", "akzeptanz_schreiben", "pruefen_spec_claude", "pruefen_spec_codex",
           "spec_pruefung_sammeln", "spec_freigabe", "plan_schreiben", "plan_pruefen", "plan_freigabe"}
PRUEFUNG = {"pruefen_funktion", "pruefen_security", "pruefen_clean_code", "pruefen_codex", "befunde_sammeln"}
ABSCHLUSS = {"budget_abschluss", "gesamtreview", "abschluss_freigabe", "abschluss"}  # Stufe 7

KNOTEN_TEXT = {
    "vorbereiten": "Legt den Worktree an, liest Aufgabe und Zielkonfiguration, merkt den Stand der geschützten Repos.",
    "klaeren": "Ein Agent liest Wunsch und Repo und stellt Rückfragen, falls der Vertrag noch offen ist.",
    "fragen": "Haltepunkt: Die Rückfragen gehen an dich. Deine Antwort geht zurück an den Klärer.",
    "spec_schreiben": "Ein Agent schreibt die Spec (Ziel, Vertrag, Rahmen, Annahmen) und nennt ihre Schnittstellen.",
    "akzeptanz_schreiben": "Ein eigener Agent schreibt aus der Spec die Akzeptanztests; Code prüft sie und die Probe "
                           "gegen main.",
    "pruefen_spec_claude": "Claude prüft Spec und Tests gegen Wunsch und Antworten (nur lesend).",
    "pruefen_spec_codex": "Codex prüft Spec und Tests gegen Wunsch und Antworten (nur lesend).",
    "spec_pruefung_sammeln": "Sammelt beide Spec-Prüfungen und kontrolliert, dass nichts verändert wurde.",
    "spec_freigabe": "Haltepunkt: Du gibst Spec und Tests frei, änderst die Spec oder lässt nur die Tests "
                     "nachbessern.",
    "plan_schreiben": "Ein Agent schreibt den Umsetzungsplan; Code prüft Abdeckung und Rahmen.",
    "plan_pruefen": "Codex prüft den Plan gegen die Spec.",
    "plan_freigabe": "Haltepunkt: Du gibst den Plan frei oder lässt ihn ändern.",
    "umsetzung_starten": "Ab hier sind Spec und Plan die Aufgabe, die erzeugten Tests ihre Akzeptanztests.",
    "stufe_waehlen": "Router: Claude und Codex schätzen die Komplexität, die höhere gilt; sie wählt Modell und Reasoning.",
    "budget_spec": "Haltepunkt Kostenrahmen: Ist die Zahl der Agentenaufrufe erreicht, entscheidest du (mehr oder abbrechen).",
    "budget_plan": "Haltepunkt Kostenrahmen vor dem Plan: mehr Aufrufe erlauben oder abbrechen.",
    "budget_umsetzung": "Haltepunkt Kostenrahmen vor jeder Umsetzung und Fix-Runde: mehr Aufrufe erlauben oder abbrechen.",
    "implementieren": "Der Implementierer (claude -p, nur im Worktree) setzt um; in Fix-Runden mit den Befunden.",
    "grenzen_pruefen": "Nachkontrolle: hat sich außerhalb des Worktrees etwas geändert? Danach Sicherung als Commit.",
    "tests_ausfuehren": "Eigene Tests und abgeschirmte Akzeptanztests (inklusive aller früheren Aufgaben).",
    "pruefen_funktion": "Macht aus dem gezählten Testergebnis Befunde (kein Modell).",
    "pruefen_security": "Security-Prüfer (Claude, nur lesend).",
    "pruefen_clean_code": "Clean-Code-Prüfer (Claude, nur lesend).",
    "pruefen_codex": "Codex prüft die Umsetzung (nur lesend).",
    "befunde_sammeln": "Filtert die Befunde an der Quelle und entscheidet, ob eine Fix-Runde nötig ist.",
    "fix_runde": "Schickt die auslösenden Befunde zurück an den Implementierer.",
    "eskalation": "Haltepunkt: Nach den Fix-Runden entscheidest du: weiter, annehmen oder abbrechen.",
    "budget_abschluss": "Haltepunkt Kostenrahmen vor dem Gesamtreview: mehr Aufrufe erlauben oder abbrechen.",
    "gesamtreview": "Codex (andere Modellfamilie) prüft Spec, Plan und Diff als Ganzes und bewertet die Tür "
                    "(einseitig oder zweiseitig).",
    "abschluss_freigabe": "Haltepunkt: mergen oder nicht mergen. Bei Einwand (major, einseitige Tür, "
                          "unerwartete Skips) nur mit Begründung.",
    "abschluss": "Lokaler Fast-Forward in den Hauptzweig, Akzeptanztests übernehmen, Worktree und Branch "
                 "abbauen. Kein Push.",
    "bericht": "Schreibt den Bericht (Markdown und JSON) nach berichte/.",
}


def _phase(knoten: str) -> str:
    if knoten in PLANUNG:
        return "planung"
    if knoten in PRUEFUNG:
        return "pruefung"
    if knoten in ABSCHLUSS:
        return "abschluss"
    return "rand" if knoten.startswith("__") else "umsetzung"


def graph_daten(graph) -> dict:
    roh = graph.get_graph().to_json()
    ids = [k["id"] for k in roh["nodes"]]
    nach = {i: [] for i in ids}
    for kante in roh["edges"]:
        nach[kante["source"]].append(kante["target"])

    # Rückkanten per Tiefensuche (Muster aus Lab 1): Zeigt eine Kante auf einen Knoten, der gerade auf dem Pfad
    # liegt, schließt sie eine Schleife (fix_runde → implementieren, fragen → klaeren, Kanten zu sich selbst).
    zurueck, auf_pfad, besucht, reihenfolge = set(), set(), set(), []

    def tiefe(knoten):
        besucht.add(knoten)
        auf_pfad.add(knoten)
        for ziel in nach.get(knoten, []):
            if ziel in auf_pfad:
                zurueck.add((knoten, ziel))
            elif ziel not in besucht:
                tiefe(ziel)
        auf_pfad.discard(knoten)
        reihenfolge.append(knoten)

    for start in ["__start__"] + ids:
        if start not in besucht:
            tiefe(start)
    ebene = {i: 0 for i in ids}
    for knoten in reversed(reihenfolge):  # topologische Ordnung ohne Rückkanten: längster Weg ab __start__
        for ziel in nach.get(knoten, []):
            if (knoten, ziel) not in zurueck:
                ebene[ziel] = max(ebene[ziel], ebene[knoten] + 1)
    spalte, belegt = {}, {}
    for i in ids:  # Reihenfolge der Knoten im Graphen, je Ebene von links nach rechts
        spalte[i] = belegt.get(ebene[i], 0)
        belegt[ebene[i]] = spalte[i] + 1

    knoten = [{"id": i, "ebene": ebene[i], "spalte": spalte[i], "text": KNOTEN_TEXT.get(i, ""),
               "haltepunkt": i in WARTEPUNKTE, "phase": _phase(i)} for i in ids]
    kanten = [{"von": k["source"], "nach": k["target"], "bedingt": bool(k.get("conditional")),
               "zurueck": (k["source"], k["target"]) in zurueck,
               # Abbruchwege (Grenzverletzung, Agentenfehler …) gehen fast überall direkt zum Bericht: blass zeichnen
               "abbruch": bool(k.get("conditional")) and k["target"] == "bericht"
                          and k["source"] not in ("befunde_sammeln", "eskalation")} for k in roh["edges"]]
    return {"knoten": knoten, "kanten": kanten}


def _lies(pfad) -> str:
    try:
        text = Path(pfad).read_text(encoding="utf-8")
    except (OSError, TypeError):
        return ""
    return text if len(text) <= MAX_ZEICHEN else text[:MAX_ZEICHEN] + "\n… (gekürzt)"


def _frage(snap, punkt: str | None) -> dict | None:
    """Der interrupt-Wert des Haltepunkts, ergänzt um die Dateien, die Dominic zur Freigabe lesen will."""
    if punkt is None:
        return None
    aufgabe = next((a for a in snap.tasks if a.name == punkt and a.interrupts), None)
    if aufgabe is None:  # Haltepunkt nicht in diesem Schnappschuss (Lauf ist gerade weitergelaufen)
        return None
    wert = aufgabe.interrupts[0].value
    frage = dict(wert) if isinstance(wert, dict) else {"wert": wert}
    if punkt == "spec_freigabe":
        frage["spec_text"] = _lies(frage.get("spec_pfad"))
        ordner = Path(frage.get("akz_ordner") or "")
        frage["tests_text"] = {d.name: _lies(d) for d in sorted(ordner.glob("*.py"))} if ordner.is_dir() else {}
    elif punkt == "plan_freigabe":
        frage["plan_text"] = _lies(frage.get("plan_pfad"))
    return frage


def lauf_daten(graph, cp, thread_id: str) -> dict:
    cfg = {"configurable": {"thread_id": thread_id}}
    snap = graph.get_state(cfg)
    werte = snap.values
    # Haltepunkt aus demselben Schnappschuss wie die Frage: Ein zweites get_state könnte schon weiter sein
    punkt = next((a.name for a in snap.tasks if a.name in WARTEPUNKTE and a.interrupts), None)
    verlauf = [{"schritt": (s.metadata or {}).get("step"), "knoten": list(s.next), "zeit": s.created_at}
               for s in reversed(list(graph.get_state_history(cfg)))
               if s.next and not all(k.startswith("__") for k in s.next)]  # __start__ = Eingabe, kein Schritt
    aktiv = [] if punkt else list(snap.next)
    erledigt = sorted({k for v in verlauf for k in v["knoten"]} - set(aktiv) - ({punkt} if punkt else set()))
    if not snap.next and werte.get("bericht_pfad"):
        erledigt = sorted(set(erledigt) | {"bericht"})
    checkpoint_id = snap.config["configurable"].get("checkpoint_id")
    frage = _frage(snap, punkt)
    einwaende = (einwaende_fuer(punkt, frage, berichte_dir() / werte["lauf_id"], checkpoint_id)
                 if punkt and werte.get("lauf_id") else [])
    return {"thread_id": thread_id, "checkpoint_id": checkpoint_id,
            "stufe": stufe_des_laufs(cp, thread_id), "aufgabe_id": werte.get("aufgabe_id"),
            "status": "wartet" if punkt else (werte.get("status") or ("laeuft" if snap.next else "unbekannt")),
            "wartepunkt": punkt, "frage": frage, "einwaende": einwaende, "aktiv": aktiv, "erledigt": erledigt,
            "verlauf": verlauf, "runde": werte.get("runde"), "max_runden": werte.get("max_runden"),
            "bericht_pfad": werte.get("bericht_pfad"), "worktree": werte.get("worktree"),
            "testergebnis": werte.get("testergebnis"),
            "aufrufe": werte.get("aufrufe") or 0, "budget": werte.get("budget")}


def laeufe(cp, graph_fuer) -> list[dict]:
    ids = {t.config["configurable"]["thread_id"] for t in cp.list(None)}
    liste = []
    for tid in sorted((i for i in ids if i.startswith(PRAEFIX)), key=_schluessel, reverse=True):
        stufe = stufe_des_laufs(cp, tid)
        graph = graph_fuer(stufe)
        punkt = wartepunkt(graph, tid)
        werte = graph.get_state({"configurable": {"thread_id": tid}}).values
        liste.append({"thread_id": tid, "stufe": stufe, "aufgabe_id": werte.get("aufgabe_id"),
                      "status": "wartet" if punkt else (werte.get("status") or "laeuft"), "wartepunkt": punkt})
    return liste
