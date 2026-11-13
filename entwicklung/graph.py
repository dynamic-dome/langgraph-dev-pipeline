"""Der Entwicklungs-Graph.

Stufe 1 (Durchstich):
    vorbereiten → implementieren → grenzen_pruefen ─┬→ tests_ausfuehren → bericht
                                                     └→ bericht   (Grenzverletzung oder Agentenfehler)

Stufe 2 (parallele Prüfungen):
    … → tests_ausfuehren ─┬→ Send ×4: pruefen_funktion | pruefen_security | pruefen_clean_code | pruefen_codex
                           │      (ein Superstep, laufen gleichzeitig; Reducer sammelt in pruefberichte)
                           │   → befunde_sammeln (Nachkontrolle, fusion-harness-Filter) → bericht
                           └→ bericht   (Testcode hat in ein geschütztes Repo geschrieben)

Stufe 3 (Fix-Schleife):
    … → befunde_sammeln ─┬→ bericht                      (nichts auslösend, oder Grenzverletzung/Agentenfehler)
                         ├→ fix_runde → implementieren → …  (Runde < max_runden)  ↺
                         └→ eskalation ⏸ (interrupt) ─┬→ fix_runde  (weiter: eine Runde mehr)
                                                      └→ bericht    (annehmen / abbrechen)

Alles, was nach außen greift (Implementierer, Testlauf, git), kommt über Abhaengigkeiten herein. Tests reichen
Fakes hinein; der echte Implementierer ist in Tests zusätzlich gesperrt (agenten._TESTSPERRE).
"""
import contextvars
import functools
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send, interrupt

from entwicklung import worktree as wt_modul
from entwicklung.agenten import claude_implementierer, fix_prompt, implementierer_prompt
from entwicklung.befunde import sammle
from entwicklung.bericht import schreibe_bericht, tests_zeile
from entwicklung.konfig import lade_zielkonfig
from entwicklung.pfade import projekt_dir
from entwicklung.pruefer import claude_pruefer, codex_pruefer, funktion_bericht, pruefer_prompt
from entwicklung.state import LEEREN, EntwicklungState
from entwicklung.stufen import stufe_im_lauf
from entwicklung.strukturiert import claude_strukturiert, codex_strukturiert
from entwicklung.testlauf import fuehre_tests_aus


# ---------------------------------------------------------------------------------------------- Zähler (6b-2)
# Jeder Agentenaufruf ruft zaehle(); gezaehlt() legt um einen Knoten einen Zähler und meldet die Summe als
# „aufrufe“. Ein Additions-Reducer im State zählt so auch parallele Send-Knoten richtig (jeder Thread hat seinen
# eigenen Kontext). Knoten ohne Agenten melden nichts.
_ZAEHLER: contextvars.ContextVar = contextvars.ContextVar("aufrufe", default=None)


def zaehle() -> None:
    zaehler = _ZAEHLER.get()
    if zaehler is not None:
        zaehler[0] += 1


def gezaehlt(knoten):
    @functools.wraps(knoten)  # behält die Annotation: Send-Knoten mit „auftrag: dict“ bekommen weiter den Auftrag
    def mit_zaehler(eingabe):
        zaehler = [0]
        marke = _ZAEHLER.set(zaehler)
        try:
            update = knoten(eingabe)
        finally:
            _ZAEHLER.reset(marke)
        return {**(update or {}), "aufrufe": zaehler[0]} if zaehler[0] else update
    return mit_zaehler


@dataclass
class Abhaengigkeiten:
    implementierer: Callable = claude_implementierer
    tests: Callable = fuehre_tests_aus
    worktree_anlegen: Callable = wt_modul.anlegen
    stand: Callable = wt_modul.stand
    jetzt: Callable[[], datetime] = datetime.now
    aufgaben_dir: Path | None = None  # Standard: <projekt>/aufgaben
    weitere_geschuetzte: list[Path] | None = None  # neben dem Zielrepo; Standard: Lab 2 selbst
    pruefer: Callable = claude_pruefer  # Security und Clean Code
    codex: Callable = codex_pruefer
    planer: Callable = claude_strukturiert  # ab Stufe 4: Klärer, Spec-, Test-Schreiber, Spec-Prüfer (nur lesend)
    planer_codex: Callable = codex_strukturiert
    berater: Callable = claude_strukturiert  # ab Stufe 6a: Fable berät an den Haltepunkten, nur auf Klick
    berater_astra: Callable = codex_strukturiert  # ab 6b-1: Astra (GPT-Familie) als Gegenstimme, nur auf Klick


def _geschuetzte(abh: Abhaengigkeiten, repo: Path) -> dict[str, Path]:
    weitere = [projekt_dir()] if abh.weitere_geschuetzte is None else abh.weitere_geschuetzte
    return {p.name: p for p in [repo, *weitere]}


def _akzeptanz_dirs(aufgaben_repo: Path, aufgabe_id: str) -> list[Path]:
    """Akzeptanzordner dieser Aufgabe und aller früheren gleicher Reihe (A1 … An), für die Regression."""
    treffer = re.fullmatch(r"([A-Za-z]+)(\d+)", aufgabe_id)
    if not treffer:
        eigener = aufgaben_repo / aufgabe_id
        return [eigener] if eigener.is_dir() else []
    praefix, nummer = treffer.group(1), int(treffer.group(2))
    gefunden = []
    for ordner in aufgaben_repo.iterdir():
        t = re.fullmatch(rf"{praefix}(\d+)", ordner.name)
        if ordner.is_dir() and t and int(t.group(1)) <= nummer:
            gefunden.append((int(t.group(1)), ordner))
    return [ordner for _, ordner in sorted(gefunden)]


def _bausteine_s1(abh: Abhaengigkeiten):
    aufgaben_dir = abh.aufgaben_dir or projekt_dir() / "aufgaben"

    def vorbereiten(state: EntwicklungState) -> dict:
        repo = Path(state["repo"]).resolve()
        aufgabe = aufgaben_dir / repo.name / f"{state['aufgabe_id']}.md"
        if not aufgabe.is_file():
            raise FileNotFoundError(f"Aufgabe {state['aufgabe_id']} fehlt: {aufgabe}")
        konfig = lade_zielkonfig(repo)  # aus dem Hauptrepo, nie aus dem Worktree
        stand_vorher = {name: abh.stand(p) for name, p in _geschuetzte(abh, repo).items()}
        wt = abh.worktree_anlegen(repo, abh.jetzt().strftime("%Y%m%d-%H%M%S"))
        return {"aufgabe_text": aufgabe.read_text(encoding="utf-8"),
                "akzeptanz_dirs": [str(d) for d in _akzeptanz_dirs(aufgabe.parent, state["aufgabe_id"])],
                "basis": wt_modul.kopf(wt),
                "konfig": konfig, "stand_vorher": stand_vorher, "worktree": str(wt),
                "lauf_id": wt.name[len(repo.name) + 1:],
                "modell": state.get("modell") or "auto"}  # auto: Tabelle (stufen.py), sonst Startwahl

    def implementieren(state: EntwicklungState) -> dict:
        konfig = state["konfig"]
        testbefehl = " ".join([konfig["python"], *konfig["testbefehl"]])
        if state.get("runde"):  # Fix-Runde: Befunde der Vorrunde beheben, im selben Worktree
            auftrag = state["fix_auftrag"]
            prompt = fix_prompt(state["aufgabe_text"], state["runde"], auftrag["befunde"], auftrag["testauszug"],
                                testbefehl)
        else:
            prompt = implementierer_prompt(state["aufgabe_text"], testbefehl)
        try:
            st = stufe_im_lauf(state, "implementierer")
            zaehle()
            agent = abh.implementierer(prompt, Path(state["worktree"]), konfig["python"], modell=st["modell"],
                                       effort=st["effort"], timeout=st["timeout"])
        except Exception as e:  # Agent ist ein Befund, kein Absturz des Graphen
            agent = {"ok": False, "zusammenfassung": "", "rc": None, "dauer_s": 0.0, "turns": None,
                     "verweigerungen": [], "fehler": f"{type(e).__name__}: {e}"}
        return {"agent": agent}

    def grenzen_pruefen(state: EntwicklungState) -> dict:
        repo = Path(state["repo"]).resolve()
        nachher = {name: abh.stand(p) for name, p in _geschuetzte(abh, repo).items()}
        verletzungen = wt_modul.grenzverletzungen(state["stand_vorher"], nachher)
        wt = Path(state["worktree"])
        # Per .gitignore versteckt: würde getestet, aber nicht gesichert (und beim Aufräumen gelöscht).
        verletzungen += [f"Worktree: {p} per .gitignore versteckt, nicht gesichert"
                         for p in wt_modul.versteckte_dateien(wt)]
        art = f"Fix-Runde {state['runde']}" if state.get("runde") else "Implementierer"
        sicherung = wt_modul.sichern(wt, f"lauf {state['lauf_id']}: {art} "
                                         f"({stufe_im_lauf(state, 'implementierer')['modell']})")
        geaendert = wt_modul.dateien_seit(wt, state["basis"])  # über alle Runden, für Prüfer und Bericht
        update = {"grenzverletzungen": verletzungen, "geaenderte_dateien": geaendert, "sicherung": sicherung}
        if verletzungen:
            update["status"] = "grenzverletzung"
        elif not state["agent"]["ok"]:
            update["status"] = "agent_fehler"
        return update

    def nach_grenzen(state: EntwicklungState) -> str:
        return "bericht" if state.get("status") else "tests_ausfuehren"

    def tests_ausfuehren(state: EntwicklungState) -> dict:
        dirs = [Path(d) for d in state.get("akzeptanz_dirs") or []]
        ergebnis = abh.tests(Path(state["worktree"]), state["konfig"], dirs)
        return {"testergebnis": ergebnis, "status": "gruen" if ergebnis["gruen"] else "rot"}

    def bericht(state: EntwicklungState) -> dict:
        return {"bericht_pfad": str(schreibe_bericht(state))}

    return vorbereiten, implementieren, grenzen_pruefen, nach_grenzen, tests_ausfuehren, bericht


def baue_graph_s1(abh: Abhaengigkeiten | None = None, checkpointer=None):
    vorbereiten, implementieren, grenzen_pruefen, nach_grenzen, tests_ausfuehren, bericht = \
        _bausteine_s1(abh or Abhaengigkeiten())
    g = StateGraph(EntwicklungState)
    g.add_node("vorbereiten", vorbereiten)
    g.add_node("implementieren", implementieren)
    g.add_node("grenzen_pruefen", grenzen_pruefen)
    g.add_node("tests_ausfuehren", tests_ausfuehren)
    g.add_node("bericht", bericht)
    g.add_edge(START, "vorbereiten")
    g.add_edge("vorbereiten", "implementieren")
    g.add_edge("implementieren", "grenzen_pruefen")
    g.add_conditional_edges("grenzen_pruefen", nach_grenzen, ["tests_ausfuehren", "bericht"])
    g.add_edge("tests_ausfuehren", "bericht")
    g.add_edge("bericht", END)
    return g.compile(checkpointer=checkpointer)


# ---------------------------------------------------------------------------------------------- Stufe 2

PRUEFER_KNOTEN = ("pruefen_funktion", "pruefen_security", "pruefen_clean_code", "pruefen_codex")


def _nicht_verwertbar(name: str, e: Exception) -> dict:
    return {"pruefer": name, "ok": False, "bericht": None, "fehler": f"{type(e).__name__}: {e}", "dauer_s": 0.0}


def _bausteine_s2(abh: Abhaengigkeiten):
    vorbereiten, implementieren, grenzen_pruefen, nach_grenzen, tests_s1, bericht = _bausteine_s1(abh)

    def _geschuetzt_jetzt(state) -> dict[str, list[str]]:
        repo = Path(state["repo"]).resolve()
        return {name: abh.stand(p) for name, p in _geschuetzte(abh, repo).items()}

    def tests_ausfuehren(state: EntwicklungState) -> dict:
        update = tests_s1(state)
        # Beim Testlauf läuft Code des Agenten: geschützte Repos danach erneut vergleichen.
        jetzt = _geschuetzt_jetzt(state)
        verletzungen = [f"Testlauf: {v}" for v in wt_modul.grenzverletzungen(state["stand_vorher"], jetzt)]
        # Nach der Sicherung muss der Worktree sauber bleiben, sonst lesen die Prüfer anderen Code als den,
        # gegen den der Filter ihre Zitate prüft (Codex S2, Befund 1).
        verletzungen += [f"Testlauf: Worktree: {p} verändert"
                         for p in wt_modul.geaenderte_dateien(Path(state["worktree"]))]
        if verletzungen:
            update.update(grenzverletzungen=state["grenzverletzungen"] + verletzungen, status="grenzverletzung")
        update["stand_vor_pruefern"] = {**jetzt, "worktree": wt_modul.stand(Path(state["worktree"]))}
        return update

    def zu_pruefern(state: EntwicklungState):
        """Bedingte Kante mit Send: vier Aufträge an vier verschiedene Knoten, oder direkt zum Bericht."""
        if state.get("status") == "grenzverletzung":
            return "bericht"
        wt = Path(state["worktree"])
        diff = wt_modul.diff(wt, state["basis"], wt_modul.kopf(wt))  # Stand aller Runden
        dateien = {}
        for pfad in state.get("geaenderte_dateien") or []:
            datei = wt / pfad
            if datei.is_file():
                dateien[pfad] = datei.read_text(encoding="utf-8", errors="replace")
        auftrag = {"worktree": state["worktree"], "aufgabe_text": state["aufgabe_text"], "diff": diff,
                   "dateien": dateien, "testergebnis": state["testergebnis"],
                   "stufe": stufe_im_lauf(state, "pruefer")}
        return [Send(knoten, auftrag) for knoten in PRUEFER_KNOTEN]

    # Die Prüfer bekommen den Send-Auftrag, nicht den State (Annotation dict: LangGraph filtert nichts weg).
    def pruefen_funktion(auftrag: dict) -> dict:
        return {"pruefberichte": [funktion_bericht(auftrag["testergebnis"])]}

    def _claude_rolle(rolle: str):
        def pruefen(auftrag: dict) -> dict:
            prompt = pruefer_prompt(rolle, auftrag["aufgabe_text"], auftrag["diff"], auftrag["dateien"])
            try:
                st = auftrag["stufe"]
                zaehle()
                ergebnis = abh.pruefer(rolle, prompt, Path(auftrag["worktree"]), modell=st["modell"],
                                       effort=st["effort"], timeout=st["timeout"])
            except Exception as e:  # ein Prüfer ist ein Befund, kein Absturz des Graphen
                ergebnis = _nicht_verwertbar(rolle, e)
            return {"pruefberichte": [ergebnis]}
        return pruefen

    def pruefen_codex(auftrag: dict) -> dict:
        prompt = pruefer_prompt("codex", auftrag["aufgabe_text"], auftrag["diff"], auftrag["dateien"])
        try:
            zaehle()
            ergebnis = abh.codex(prompt, Path(auftrag["worktree"]))
        except Exception as e:
            ergebnis = _nicht_verwertbar("codex", e)
        return {"pruefberichte": [ergebnis]}

    def befunde_sammeln(state: EntwicklungState) -> dict:
        wt = Path(state["worktree"])
        vorher = state["stand_vor_pruefern"]
        nachher = {**_geschuetzt_jetzt(state), "worktree": wt_modul.stand(wt)}
        verletzungen = [f"Prüfer: {v}" for v in wt_modul.grenzverletzungen(vorher, nachher)]
        gesammelt = sammle(state["pruefberichte"], wt, wt_modul.kopf(wt), state.get("geaenderte_dateien") or [])
        if verletzungen:
            gesammelt.update(grenzverletzungen=state["grenzverletzungen"] + verletzungen, status="grenzverletzung")
        return gesammelt

    return (vorbereiten, implementieren, grenzen_pruefen, nach_grenzen, tests_ausfuehren, zu_pruefern,
            pruefen_funktion, _claude_rolle("security"), _claude_rolle("clean_code"), pruefen_codex,
            befunde_sammeln, bericht)


def baue_graph_s2(abh: Abhaengigkeiten | None = None, checkpointer=None):
    (vorbereiten, implementieren, grenzen_pruefen, nach_grenzen, tests_ausfuehren, zu_pruefern, pruefen_funktion,
     pruefen_security, pruefen_clean_code, pruefen_codex, befunde_sammeln, bericht) = \
        _bausteine_s2(abh or Abhaengigkeiten())
    g = StateGraph(EntwicklungState)
    for name, knoten in (("vorbereiten", vorbereiten), ("implementieren", implementieren),
                         ("grenzen_pruefen", grenzen_pruefen), ("tests_ausfuehren", tests_ausfuehren),
                         ("pruefen_funktion", pruefen_funktion), ("pruefen_security", pruefen_security),
                         ("pruefen_clean_code", pruefen_clean_code), ("pruefen_codex", pruefen_codex),
                         ("befunde_sammeln", befunde_sammeln), ("bericht", bericht)):
        g.add_node(name, knoten)
    g.add_edge(START, "vorbereiten")
    g.add_edge("vorbereiten", "implementieren")
    g.add_edge("implementieren", "grenzen_pruefen")
    g.add_conditional_edges("grenzen_pruefen", nach_grenzen, ["tests_ausfuehren", "bericht"])
    g.add_conditional_edges("tests_ausfuehren", zu_pruefern, [*PRUEFER_KNOTEN, "bericht"])
    for knoten in PRUEFER_KNOTEN:
        g.add_edge(knoten, "befunde_sammeln")  # Fan-in: befunde_sammeln läuft einmal, nach allen vier
    g.add_edge("befunde_sammeln", "bericht")
    g.add_edge("bericht", END)
    return g.compile(checkpointer=checkpointer)


# ---------------------------------------------------------------------------------------------- Stufe 3

MAX_RUNDEN = 2
ENTSCHEIDUNGEN = ("weiter", "annehmen", "abbrechen")
BUDGET = 40  # Agentenaufrufe je Lauf (Entwurf: „höchstens eine feste Zahl von Agentenaufrufen“)
BUDGET_SCHRITT = 20
BUDGET_PUNKTE = ("budget_spec", "budget_plan", "budget_umsetzung", "budget_abschluss")  # budget_abschluss: Stufe 7
BUDGET_ENTSCHEIDUNGEN = ("mehr", "abbrechen")


def budget_knoten(naechster):
    """Wächter vor einer teuren Schleife: Ist der Rahmen erreicht, entscheidet Dominic (mehr oder abbrechen).

    Genau ein interrupt je Durchlauf; eine ungültige Antwort läuft über die Kante zurück in denselben Knoten,
    ebenso „mehr“, wenn der erhöhte Rahmen noch erreicht ist (Codex 6b-2). `naechster` ist ein Knotenname oder eine
    Funktion state -> Knotenname (budget_spec führt nach „Tests nachbessern“ zu akzeptanz_schreiben).
    Ohne budget (Läufe vor 6b-2) gibt es keinen Rahmen."""
    def knoten(state) -> dict:
        rahmen = state.get("budget")
        aufrufe = state.get("aufrufe") or 0
        if not rahmen or aufrufe < rahmen:
            return {}
        ziel = naechster(state) if callable(naechster) else naechster
        antwort = interrupt({"art": "budget", "aufrufe": aufrufe, "budget": rahmen,
                             "naechster": ziel, "schritt": BUDGET_SCHRITT, "erlaubt": list(BUDGET_ENTSCHEIDUNGEN),
                             "hinweis": state.get("budget_hinweis") or ""})
        entscheidung = antwort.get("entscheidung") if isinstance(antwort, dict) else None
        if entscheidung == "mehr":
            neu = rahmen + BUDGET_SCHRITT
            if aufrufe >= neu:
                return {"budget": neu, "budget_hinweis": f"noch über dem Rahmen: {aufrufe} Aufrufe bei Rahmen {neu}"}
            return {"budget": neu, "budget_hinweis": ""}
        if entscheidung == "abbrechen":
            return {"status": "abgebrochen", "budget_hinweis": ""}
        return {"budget_hinweis": f"ungültige Antwort {antwort!r}, erlaubt: {{'entscheidung': 'mehr' | 'abbrechen'}}"}
    return knoten


def nach_budget(punkt: str, naechster):
    def kante(state) -> str:
        if state.get("budget_hinweis"):
            return punkt
        if state.get("status") == "abgebrochen":
            return "bericht"
        return naechster(state) if callable(naechster) else naechster
    return kante


def befund_schluessel(b: dict) -> str:
    """Wer, wo, welche Art. Zeile und Wortlaut bleiben draußen: Beide ändern sich nach jedem Fix."""
    return f"{'+'.join(sorted(b['pruefer']))}|{b['path']}|{b['kind']}"


def wiederkehrend(runden: list[dict]) -> list[str]:
    """Schlüssel, die in den letzten beiden Runden direkt nacheinander auslösten (Stufe 6b-1, Lehre A6).

    Ein Prüfer, der denselben Befund nach einem Fix wieder meldet, meldet ihn meist auch nach dem nächsten (A6: ein
    Widerspruch in der Spec, den keine Umsetzung erfüllen kann). Dann fragt der Lauf Dominic, statt eine Runde zu
    vergeuden."""
    if len(runden) < 2 or runden[-1].get("runde") != (runden[-2].get("runde") or 0) + 1:
        return []
    return sorted(set(runden[-2].get("schluessel") or []) & set(runden[-1].get("schluessel") or []))


def _bausteine_s3(abh: Abhaengigkeiten):
    (vorbereiten_s1, implementieren, grenzen_pruefen, nach_grenzen, tests_ausfuehren, zu_pruefern, pruefen_funktion,
     pruefen_security, pruefen_clean_code, pruefen_codex, befunde_sammeln_s2, bericht) = _bausteine_s2(abh)

    def vorbereiten(state: EntwicklungState) -> dict:
        maximum = state.get("max_runden")
        rahmen = state.get("budget")
        return {**vorbereiten_s1(state), "runde": 0, "max_runden": MAX_RUNDEN if maximum is None else maximum,
                "budget": BUDGET if rahmen is None else rahmen, "budget_hinweis": ""}

    def befunde_sammeln(state: EntwicklungState) -> dict:
        update = befunde_sammeln_s2(state)
        status = update.get("status") or state.get("status")
        update["runden"] = [{"runde": state["runde"], "status": status, "tests": tests_zeile(state["testergebnis"]),
                             "befunde": len(update["befunde"]),
                             "ausloesend": sum(b["ausloesend"] for b in update["befunde"]),
                             # nur Prüfer-Urteile: rote Tests sind gemessen, dort hilft die Fix-Runde mit Testauszug
                             "schluessel": sorted({befund_schluessel(b) for b in update["befunde"]
                                                   if b["ausloesend"] and b["topf"] != "deterministisch"})}]
        return update

    def nach_befunden(state: EntwicklungState) -> str:
        """Die Abbruchbedingung steht im State: runde und max_runden. Ohne sie wäre der Zyklus endlos."""
        if state.get("status") in ("grenzverletzung", "agent_fehler") or not state["fix_noetig"]:
            return "bericht"
        if wiederkehrend(state.get("runden") or []):
            return "eskalation"  # Frühabbruch: derselbe Befund zweimal nacheinander
        return "fix_runde" if state["runde"] < state["max_runden"] else "eskalation"

    def fix_runde(state: EntwicklungState) -> dict:
        t = state["testergebnis"]
        # Ergebnisse der Vorrunde zurücksetzen: Bricht die neue Runde vor dem Testlauf ab, zeigte der Bericht sonst
        # alte Tests und Befunde als Ergebnis des neuen Codes. Die Vorrunde bleibt in runden.
        return {"runde": state["runde"] + 1,
                "pruefberichte": LEEREN,  # Reducer leert: die neue Runde sammelt frisch
                "fix_auftrag": {"befunde": [b for b in state["befunde"] if b["ausloesend"]],
                                "testauszug": None if t["gruen"] else t["auszug"]},
                "status": None, "testergebnis": None, "befunde": [], "nicht_verwertbar": [], "nicht_pruefbar": [],
                "fix_noetig": False}

    def eskalation(state: EntwicklungState) -> dict:
        """Notausgang: Nach max_runden entscheidet Dominic, nicht das Modell.

        Genau ein interrupt je Durchlauf. Eine ungültige Antwort läuft über die Kante zurück in diesen Knoten,
        statt ein zweites interrupt im selben Knoten zu stellen: Dann zeigte get_state().next in LangGraph 1.2.10
        nichts mehr an, und ein wartender Lauf sähe aus wie ein fertiger (gemessen 19.10.).
        """
        wieder = wiederkehrend(state.get("runden") or []) if state.get("fix_noetig") else []
        frage = (f"Derselbe Befund kam in zwei Runden nacheinander ({', '.join(wieder)}). Eine weitere Runde hilft "
                 f"vermutlich nicht. Wie weiter?" if wieder else
                 f"Nach {state['runde']} Fix-Runde(n) sind noch Befunde offen. Wie weiter?")
        antwort = interrupt({"frage": frage, "wiederkehrend": wieder,
                             "runde": state["runde"], "max_runden": state["max_runden"],
                             "ausloesend": [b for b in state["befunde"] if b["ausloesend"]],
                             "tests": tests_zeile(state["testergebnis"]), "erlaubt": list(ENTSCHEIDUNGEN),
                             "hinweis": state.get("eskalation_hinweis") or ""})
        if not (isinstance(antwort, dict) and antwort.get("entscheidung") in ENTSCHEIDUNGEN):
            return {"entscheidung": None,
                    "eskalation_hinweis": f"ungültige Antwort {antwort!r}, erlaubt: "
                                          f"{{'entscheidung': {' | '.join(ENTSCHEIDUNGEN)}}}"}
        entscheidung = antwort["entscheidung"]
        einwand = {}
        einwaende = antwort.get("einwaende")
        if (entscheidung == "annehmen" and isinstance(einwaende, list) and einwaende
                and all(isinstance(e, str) for e in einwaende)):
            # Einwände der Berater bringt der Server mit; hier nur ablegen (gesperrt wird in steuerung.einwand_fehlt)
            einwand = {"einwand_freigaben": (state.get("einwand_freigaben") or []) + [
                {"haltepunkt": "eskalation", "entscheidung": entscheidung, "einwaende": list(dict.fromkeys(einwaende)),
                 "begruendung": str(antwort.get("begruendung") or "").strip()}]}
        if entscheidung == "weiter":
            return {"entscheidung": entscheidung, "eskalation_hinweis": "", "max_runden": state["max_runden"] + 1}
        return {"entscheidung": entscheidung, "eskalation_hinweis": "", **einwand,
                "status": "angenommen" if entscheidung == "annehmen" else "abgebrochen"}

    def nach_eskalation(state: EntwicklungState) -> str:
        if state.get("entscheidung") is None:
            return "eskalation"  # ungültig: noch einmal fragen
        return "fix_runde" if state["entscheidung"] == "weiter" else "bericht"

    return (vorbereiten, implementieren, grenzen_pruefen, nach_grenzen, tests_ausfuehren, zu_pruefern,
            pruefen_funktion, pruefen_security, pruefen_clean_code, pruefen_codex, befunde_sammeln, nach_befunden,
            fix_runde, eskalation, nach_eskalation, bericht)


def umsetzung_s3(g: StateGraph, bausteine: tuple, ziel_gruen: str = "bericht") -> None:
    """Knoten und Kanten der Umsetzung ab implementieren bis bericht (Stufe 3). Stufe 4 setzt davor die Planung.

    `ziel_gruen`: wohin ein grüner Lauf ohne Fix-Bedarf und ein an der Eskalation angenommener gehen (Stufe 7:
    budget_abschluss vor dem Gesamtreview). Rot, Grenzverletzung, Agentenfehler und Abbruch enden im Bericht."""
    (_vorbereiten, implementieren, grenzen_pruefen, nach_grenzen, tests_ausfuehren, zu_pruefern, pruefen_funktion,
     pruefen_security, pruefen_clean_code, pruefen_codex, befunde_sammeln, nach_befunden, fix_runde, eskalation,
     nach_eskalation, bericht) = bausteine
    for name, knoten in (("implementieren", implementieren),
                         ("grenzen_pruefen", grenzen_pruefen), ("tests_ausfuehren", tests_ausfuehren),
                         ("pruefen_funktion", pruefen_funktion), ("pruefen_security", pruefen_security),
                         ("pruefen_clean_code", pruefen_clean_code), ("pruefen_codex", pruefen_codex),
                         ("befunde_sammeln", befunde_sammeln), ("fix_runde", fix_runde),
                         ("eskalation", eskalation), ("bericht", bericht),
                         ("budget_umsetzung", budget_knoten("implementieren"))):
        g.add_node(name, gezaehlt(knoten))
    g.add_conditional_edges("budget_umsetzung", nach_budget("budget_umsetzung", "implementieren"),
                            ["budget_umsetzung", "implementieren", "bericht"])
    g.add_edge("implementieren", "grenzen_pruefen")
    g.add_conditional_edges("grenzen_pruefen", nach_grenzen, ["tests_ausfuehren", "bericht"])
    g.add_conditional_edges("tests_ausfuehren", zu_pruefern, [*PRUEFER_KNOTEN, "bericht"])
    for knoten in PRUEFER_KNOTEN:
        g.add_edge(knoten, "befunde_sammeln")

    def nach_befunden_ziel(state) -> str:
        ziel = nach_befunden(state)
        gruen = state.get("status") == "gruen" and not state.get("fix_noetig")
        return ziel_gruen if ziel == "bericht" and gruen else ziel

    def nach_eskalation_ziel(state) -> str:
        ziel = nach_eskalation(state)
        return ziel_gruen if ziel == "bericht" and state.get("status") == "angenommen" else ziel

    ende = list(dict.fromkeys(["bericht", ziel_gruen]))
    g.add_conditional_edges("befunde_sammeln", nach_befunden_ziel, [*ende, "fix_runde", "eskalation"])
    g.add_edge("fix_runde", "budget_umsetzung")  # die Rückkante (über den Kostenrahmen): hier entsteht der Zyklus
    g.add_conditional_edges("eskalation", nach_eskalation_ziel, ["eskalation", "fix_runde", *ende])
    g.add_edge("bericht", END)


def baue_graph_s3(abh: Abhaengigkeiten | None = None, checkpointer=None):
    """Braucht einen Checkpointer: Ohne ihn kann eskalation zwar anhalten, aber nie fortgesetzt werden."""
    bausteine = _bausteine_s3(abh or Abhaengigkeiten())
    g = StateGraph(EntwicklungState)
    g.add_node("vorbereiten", bausteine[0])
    umsetzung_s3(g, bausteine)
    g.add_edge(START, "vorbereiten")
    g.add_edge("vorbereiten", "budget_umsetzung")
    return g.compile(checkpointer=checkpointer)
