"""Demo ohne Abo: ein kompletter Lauf an examples/portwart mit Fake-Agenten.

    python -m entwicklung demo                 Leitstand auf 127.0.0.1 (Standard 8795), Lauf D1 startet von selbst
    python -m entwicklung demo --durchlauf     ohne Browser: alle Haltepunkte automatisch bis zum lokalen Merge

Alles Bleibende entsteht in einem neuen Temp-Ordner (kurzlebige Hilfsordner des Testlaufs legt Python wie
immer im allgemeinen Temp-Verzeichnis an und räumt sie selbst weg): ein frisches Git-Repo aus examples/portwart, die Aufgabe D1 („Einträge je
Projekt zählen“), Datenbank, Berichte und Worktrees. Die Fakes liefern feste, plausible Antworten (Spec, Tests, Plan,
Code, Prüfberichte, Gesamtreview); der Graph, die Nachkontrolle, der Testlauf mit abgeschirmten Akzeptanztests, der
Befund-Filter, die Haltepunkte und der Fast-Forward-Merge sind echt. Echte Agenten sind gesperrt (agenten._TESTSPERRE).
"""
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from entwicklung import agenten
from entwicklung.graph import Abhaengigkeiten
from entwicklung.pfade import projekt_dir

BEISPIEL = "examples/portwart"
AUFGABE = "D1"
WUNSCH = """# D1: Einträge je Projekt zählen

Ich möchte sehen, wie viele Ports jedes Projekt in ports.toml belegt. Eine Funktion reicht, die CLI kommt später.
"""
SPEC = {"spec": """# D1: Einträge je Projekt zählen

## Ziel
Für eine portwart-Liste (Text im Format von ports.toml) die Zahl der Einträge je Projekt liefern.

## Vertrag
`portwart.anzahl.je_projekt(text: str) -> dict[str, int]`
- Schlüssel: Projektname aus `projekt`, Wert: Zahl der `[[port]]`-Einträge dieses Projekts.
- Sortiert nach Projektname (Einfügereihenfolge des dict).
- Leerer Text oder keine Einträge: `{}`.

## Rahmen
Nur das neue Modul `portwart/anzahl.py` und sein Test; nichts Bestehendes ändern.
""", "schnittstellen": [{"modul": "portwart.anzahl", "namen": ["je_projekt"]}],
        "annahmen": ["Ungültiges TOML muss nicht abgefangen werden (Folgeaufgabe)."],
        "komplexitaet": "einfach", "komplexitaet_grund": "eine Funktion, ein Modul"}
TEST = '''def test_zaehlt_je_projekt():
    from portwart.anzahl import je_projekt
    text = '[[port]]\\nport = 1\\nprojekt = "b"\\n\\n[[port]]\\nport = 2\\nprojekt = "a"\\n\\n[[port]]\\nport = 3\\nprojekt = "b"\\n'
    assert je_projekt(text) == {"a": 1, "b": 2}
    assert list(je_projekt(text)) == ["a", "b"]


def test_leer():
    from portwart.anzahl import je_projekt
    assert je_projekt("") == {}
'''
PLAN = {"plan": "# Plan D1\n\n## Schritt 1: Test zuerst\n`tests/test_anzahl.py` mit zwei Fällen (Zählen, leer).\n\n"
                "## Schritt 2: portwart/anzahl.py\n`tomllib.loads`, `Counter` über `projekt`, nach Namen sortiert.\n",
        "dateien": ["portwart/anzahl.py", "tests/test_anzahl.py"]}
PRUEF_OK = {"verdict": "PASS", "punkte": [], "komplexitaet": "einfach", "komplexitaet_grund": "(Demo) eine Funktion"}
GESAMT_OK = {"verdict": "PASS", "zusammenfassung": "(Demo) Der Diff erfüllt die Spec; nur ein neues Modul mit Test.",
             "spec_erfuellt": True, "restpunkte": [],
             "tuer": {"urteil": "zweiseitig", "radius": "Modul", "begruendung": "(Demo) nur neuer Code",
                      "faelle": [], "selbstbewertung_stimmt": True}}
CODE = '''"""Einträge je Projekt zählen (Aufgabe D1, gebaut in der Demo der Entwicklungs-Pipeline)."""
import tomllib
from collections import Counter


def je_projekt(text: str) -> dict[str, int]:
    zaehler = Counter(e.get("projekt", "") for e in tomllib.loads(text).get("port", []))
    return dict(sorted(zaehler.items()))
'''
EIGENER_TEST = '''from portwart.anzahl import je_projekt


def test_je_projekt():
    assert je_projekt('[[port]]\\nport = 1\\nprojekt = "x"\\n') == {"x": 1}
'''
PRUEFBERICHT = {"verdict": "PASS", "findings": [], "not_checkable": []}
ANTWORTEN = {"klaeren": {"klar": True, "verstaendnis": "(Demo) Zahl der Einträge je Projekt", "fragen": []},
             "spec_schreiben": SPEC, "akzeptanz_schreiben": {"dateien": [{"name": "test_akzeptanz_d1.py",
                                                                          "inhalt": TEST}]},
             "spec_pruefer": PRUEF_OK, "spec_codex": PRUEF_OK, "plan_schreiben": PLAN, "plan_codex": PRUEF_OK,
             "gesamtreview": GESAMT_OK}
RAT = {"fragen": "antwort", "spec_freigabe": "freigeben", "plan_freigabe": "freigeben", "eskalation": "annehmen"}


def temp_ordner() -> Path:
    return Path(tempfile.mkdtemp(prefix="lab2-demo-"))


def _git(cwd: Path, *args: str) -> None:
    subprocess.run([shutil.which("git") or "git", *args], cwd=cwd, check=True, capture_output=True)


def baue_umgebung(ziel: Path) -> tuple[Path, Path]:
    """Frisches Git-Repo ziel/portwart aus examples/portwart und ziel/aufgaben/portwart/D1.md."""
    repo = ziel / "portwart"
    shutil.copytree(projekt_dir() / BEISPIEL, repo, ignore=shutil.ignore_patterns("__pycache__", "*.pyc",
                                                                                  ".pytest_cache"))
    (repo / "entwicklung.toml").write_text(
        f'python = "{Path(sys.executable).as_posix()}"\ntestbefehl = ["-m", "pytest", "-q"]\n', encoding="utf-8")
    dateien = sorted(p.relative_to(repo).as_posix() for p in repo.rglob("*") if p.is_file())
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "add", "--", *dateien)
    _git(repo, "-c", "user.name=demo", "-c", "user.email=demo@example.invalid", "commit", "-q", "-m",
         "portwart (Beispiel, Stand nach A9)")
    aufgaben = ziel / "aufgaben"
    (aufgaben / "portwart").mkdir(parents=True)
    (aufgaben / "portwart" / f"{AUFGABE}.md").write_text(WUNSCH, encoding="utf-8")
    return repo, aufgaben


class _Fakes:
    """Feste Antworten statt claude -p und codex exec; `pause` lässt die Knoten im Leitstand sichtbar wandern."""

    def __init__(self, pause: float = 0.0):
        self.pause = pause

    def _warte(self):
        if self.pause:
            time.sleep(self.pause)

    def planer(self, name, prompt, cwd, schema, modell=None, timeout=600, effort=None, runner=None):
        self._warte()
        return {"name": name, "ok": True, "daten": ANTWORTEN[name], "fehler": None, "dauer_s": self.pause}

    def planer_codex(self, name, prompt, cwd, schema, timeout=900, effort=None, runner=None):
        return self.planer(name, prompt, cwd, schema)

    def implementierer(self, prompt, wt, python, modell="sonnet", timeout=600, effort=None, runner=None):
        self._warte()
        (wt / "portwart" / "anzahl.py").write_text(CODE, encoding="utf-8")
        (wt / "tests" / "test_anzahl.py").write_text(EIGENER_TEST, encoding="utf-8")
        return {"ok": True, "zusammenfassung": "(Demo) portwart/anzahl.py mit Test", "rc": 0, "dauer_s": self.pause,
                "fehler": None, "turns": 3, "verweigerungen": []}

    def pruefer(self, rolle, prompt, wt, modell="sonnet", timeout=600, effort=None, runner=None):
        self._warte()
        return {"pruefer": rolle, "ok": True, "bericht": PRUEFBERICHT, "fehler": None, "dauer_s": self.pause}

    def codex(self, prompt, wt, timeout=900, effort=None, runner=None):
        return self.pruefer("codex", prompt, wt)

    def berater(self, name, prompt, cwd, schema, modell=None, timeout=600, effort=None, runner=None):
        """Rat nur zur Anschauung: je Haltepunkt eine erlaubte Entscheidung."""
        self._warte()
        punkt = next((p for p in RAT if f"an diesem Haltepunkt ({p})" in prompt), "spec_freigabe")
        entscheidung = RAT[punkt]
        daten = {"entscheidung": entscheidung, "text": "(Demo) ja" if entscheidung == "antwort" else "",
                 "begruendung": f"(Demo) Für {punkt} wäre „{entscheidung}“ plausibel.", "sicherheit": "mittel",
                 "punkte": []}
        return {"name": name, "ok": True, "daten": daten, "fehler": None, "dauer_s": self.pause}

    def berater_astra(self, name, prompt, cwd, schema, timeout=900, effort=None, runner=None):
        return self.berater(name, prompt, cwd, schema)


def abhaengigkeiten(aufgaben: Path, pause: float = 0.0) -> Abhaengigkeiten:
    agenten._TESTSPERRE = True  # nur Fakes: ein echter Agent würde hier abbrechen statt zu starten
    f = _Fakes(pause)
    return Abhaengigkeiten(implementierer=f.implementierer, pruefer=f.pruefer, codex=f.codex, planer=f.planer,
                           planer_codex=f.planer_codex, berater=f.berater, berater_astra=f.berater_astra,
                           aufgaben_dir=aufgaben, weitere_geschuetzte=[])


def _antwort(frage: dict) -> dict:
    """Was ein Mensch in der Demo antworten würde: freigeben und mergen, bei Einwand mit Begründung."""
    art = frage.get("art", "eskalation")
    antwort = {"fragen": {"antwort": "(Demo) ja"}, "budget": {"entscheidung": "mehr"},
               "eskalation": {"entscheidung": "annehmen"},
               "abschluss_freigabe": {"entscheidung": "mergen"}}.get(art, {"entscheidung": "freigeben"})
    if frage.get("einwaende"):
        antwort = {**antwort, "begruendung": "(Demo) Einwand gelesen"}
    return antwort


def durchlauf(ziel: Path, ausgabe=None) -> dict:
    """Lauf D1 ohne Browser bis zum Ende. Gibt den Endstand zurück, dazu `haltepunkte`: [(art, entscheidung)]."""
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.types import Command

    from entwicklung.graph_s4 import baue_graph_s4
    repo, aufgaben = baue_umgebung(ziel)
    graph = baue_graph_s4(abhaengigkeiten(aufgaben), checkpointer=InMemorySaver())
    cfg = {"configurable": {"thread_id": "demo"}}
    erg = graph.invoke({"repo": str(repo), "aufgabe_id": AUFGABE}, cfg)
    halte = []
    while erg.get("__interrupt__"):
        frage = erg["__interrupt__"][0].value
        antwort = _antwort(frage)
        halte.append((frage.get("art", "eskalation"), antwort.get("entscheidung") or "antwort"))
        if ausgabe:
            ausgabe(f"⏸ {halte[-1][0]:<19} → {halte[-1][1]}")
        erg = graph.invoke(Command(resume=antwort), cfg)
    return {**graph.get_state(cfg).values, "haltepunkte": halte}
