"""State des Entwicklungs-Graphen. Jeder Knoten liefert nur die Felder, die er ändert (Teil-Update)."""
import operator
from typing import Annotated, TypedDict

LEEREN = None  # als Update an pruefberichte: Liste leeren (Beginn einer Fix-Runde)


def sammeln_oder_leeren(alt: list | None, neu: list | None) -> list:
    """Reducer: hängt an wie operator.add, aber LEEREN (None) setzt die Liste zurück.

    operator.add kann nur wachsen. In der Fix-Schleife sollen die Befunde einer Runde nur aus dieser Runde stammen,
    deshalb braucht es einen Reducer, der auch leeren kann.
    """
    if neu is LEEREN:
        return []
    return (alt or []) + neu


class EntwicklungState(TypedDict, total=False):
    # Eingabe
    repo: str  # Pfad zum Hauptrepo des Ziels
    aufgabe_id: str
    modell: str
    # vorbereiten
    aufgabe_text: str
    akzeptanz_dirs: list[str]  # diese Aufgabe und alle früheren (Regression)
    basis: str  # Commit, von dem der Worktree abzweigt
    konfig: dict
    lauf_id: str
    worktree: str
    stand_vorher: dict[str, list[str]]
    # implementieren
    agent: dict
    # grenzen_pruefen
    grenzverletzungen: list[str]
    geaenderte_dateien: list[str]
    sicherung: str | None  # Commit auf lauf/<id>
    # Planung (ab Stufe 4)
    wunsch: str  # die Aufgabendatei als Wunsch; aufgabe_text wird erst nach der Freigabe die Spec
    klaerung: Annotated[list[dict], operator.add]  # je Runde {fragen, antwort}
    klaer_runde: int
    offene_fragen: list[str]
    verstaendnis: str
    spec: str
    schnittstellen: list[dict]  # {modul, namen}: was die Akzeptanztests importieren dürfen
    annahmen: list[str]
    spec_runde: int
    spec_aenderung: str | None  # Hinweis von Dominic bei „aendern“
    akz_versuch: int
    akz_gruende: list[str]  # warum der vorige Versuch abgelehnt wurde
    akz_dateien: list[dict]  # {name, inhalt}
    akz_ordner: str  # berichte/<lauf_id>/akzeptanz/<aufgabe_id>
    akz_probe: dict | None  # {erwartet, gesammelt, bestanden, uebersprungen, fehler}
    akz_hashes: dict[str, str]  # sha256 je erzeugter Testdatei bei der Freigabe
    spec_pruefungen: Annotated[list[dict], sammeln_oder_leeren]
    # Konvergenz (ab 6c): Nachprüfung gegen die Vorfassung
    vorige_fassung: dict | None  # {spec, tests: {name: inhalt}, punkte: nummeriert}, was der Schreiber bekam
    spec_einordnung: dict | None  # konvergenz.einordnen: {ausloesend, liste, alte}
    spec_verlauf: Annotated[list[dict], operator.add]  # eine Zeile je Spec-Prüfung, wächst nur
    halt_hinweis: str  # an fragen/spec_freigabe: warum noch einmal gefragt wird
    freigabe: str | None  # Dominics Entscheidung an spec_freigabe (getrennt von entscheidung der Eskalation)
    akz_hinweis: str | None  # „tests_nachbessern“: Dominics Hinweis an den Test-Schreiber
    # Plan (ab Stufe 4b)
    plan: str
    plan_dateien: list[str]
    plan_runde: int
    plan_aenderung: str | None
    plan_gruende: list[str]  # aus pruefe_plan (Code), blockieren nicht
    plan_pruefungen: Annotated[list[dict], sammeln_oder_leeren]
    plan_freigabe: str | None
    # Modellstufen (ab 6b-2)
    komplexitaet: str | None  # gilt für die Umsetzung (einfach | mittel | schwer)
    komplexitaet_vorschlag: str | None  # was der Router vorschlug (höhere Schätzung)
    komplexitaet_claude: str | None
    komplexitaet_codex: str | None
    komplexitaet_grund: str
    komplexitaet_hinweis: str
    einwand_freigaben: list[dict]  # ab 6b-1: freigegeben trotz Einwand {haltepunkt, entscheidung, einwaende, begruendung}
    planung_fehler: str | None  # welcher Planungsagent scheiterte und warum
    # tests_ausfuehren
    testergebnis: dict | None
    stand_vor_pruefern: dict[str, list[str]]  # ab Stufe 2: Worktree und geschützte Repos vor den Prüfern
    # Prüfer (ab Stufe 2): jeder Send-Knoten hängt seinen Bericht an, der Reducer sammelt
    pruefer_modell: str
    pruefberichte: Annotated[list[dict], sammeln_oder_leeren]
    # befunde_sammeln
    befunde: list[dict]
    nicht_verwertbar: list[dict]
    nicht_pruefbar: list[dict]
    fix_noetig: bool
    befund_filter: str  # fusion-harness | eingebaut (…)
    # Fix-Schleife (ab Stufe 3)
    runde: int  # 0 = erste Umsetzung, 1.. = Fix-Runden
    max_runden: int
    fix_auftrag: dict  # auslösende Befunde und Testauszug für die nächste Runde
    runden: Annotated[list[dict], operator.add]  # eine Zeile je Runde, wächst nur
    # Kostenrahmen (ab 6b-2): Agentenaufrufe je Lauf; jeder aufrufende Knoten meldet seine Zahl, der Reducer addiert
    aufrufe: Annotated[int, operator.add]
    budget: int | None
    budget_hinweis: str
    entscheidung: str | None  # Antwort an der Eskalation
    eskalation_hinweis: str  # nach einer ungültigen Antwort: was erlaubt ist
    # Abschluss (ab Stufe 7)
    zielzweig: str  # Zweig des Ziel-Repos beim Start; gemergt wird nur dorthin
    gesamtreview: dict | None  # {ok, daten (GESAMT_SCHEMA), fehler} von Codex
    tuer: dict | None  # abschluss.tuer_endgueltig: {urteil, radius, faelle, selbst, codex, uneinig}
    geprueft_kopf: str  # Commit, den Tests und Gesamtreview gesehen haben; nur er wird gemergt
    abschluss_entscheidung: str | None  # mergen | nicht_mergen
    abschluss_hinweis: str
    abschluss: dict  # {entscheidung, merge_commit, uebernommen, aufgeraeumt, grund}
    # Ergebnis
    status: str | None  # gruen | rot | grenzverletzung | agent_fehler | angenommen | abgebrochen | merge_abgelehnt
    bericht_pfad: str
