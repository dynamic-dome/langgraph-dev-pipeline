"""Leitstand mit Fake-Agenten ausprobieren, ohne echte Agenten und ohne echte Daten.

    .venv\\Scripts\\python.exe docs\\lernpfad\\leitstand_demo.py [--port 8795]

Legt alles in einem Temp-Ordner an (Datenbank, Berichte, Worktrees, ein Mini-Repo `mini` mit Wunsch M2) und
startet den Leitstand auf 127.0.0.1 mit dem Token „demo“. Die Fakes stammen aus den Tests und warten je Aufruf
etwas, damit man die aktiven Knoten im Diagramm wandern sieht. Echte Agenten sind gesperrt (Testsperre).
"""
import argparse
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

PROJEKT = Path(__file__).resolve().parents[2]
TEMP = Path(tempfile.mkdtemp(prefix="leitstand-demo-"))
for name in ("DATA", "BERICHTE", "ARBEIT"):  # vor jedem Import von entwicklung: alles in den Temp-Ordner
    os.environ[f"ENTWICKLUNG_{name}_DIR"] = str(TEMP / name.lower())
    (TEMP / name.lower()).mkdir()
sys.path.insert(0, str(PROJEKT))

from entwicklung import agenten  # noqa: E402
from entwicklung.graph import Abhaengigkeiten  # noqa: E402
from entwicklung.leitstand.server import baue_app  # noqa: E402
from entwicklung.speicher import oeffne_checkpointer  # noqa: E402
from tests.test_graph_s2 import _codex, _pruefer  # noqa: E402
from tests.test_graph_s3 import RICHTIG, Implementierer  # noqa: E402
from tests.test_graph_s4 import CODEX_MAJOR, FRAGEN, GESAMT_OK, KLAR, PRUEF_OK, SPEC, Planer  # noqa: E402

agenten._TESTSPERRE = True  # nur Fakes


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def mini_repo() -> tuple[Path, Path]:
    repo = TEMP / "mini"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "demo@lab2")
    _git(repo, "config", "user.name", "demo")
    (repo / "README.md").write_text("mini\n", encoding="utf-8")
    (repo / "entwicklung.toml").write_text(
        f'python = "{Path(sys.executable).as_posix()}"\ntestbefehl = ["-m", "pytest", "-q"]\n', encoding="utf-8")
    _git(repo, "add", "README.md", "entwicklung.toml")
    _git(repo, "commit", "-q", "-m", "init")
    aufgaben = TEMP / "aufgaben" / "mini"
    aufgaben.mkdir(parents=True)
    (aufgaben / "M2.md").write_text("# M2: plus\nplus soll addieren.\n", encoding="utf-8")
    return repo, TEMP / "aufgaben"


DEMO_RAT = {  # je Haltepunkt ein plausibler Rat, damit man Karte, Vorausfüllen und Übernehmen sieht
    "fragen": ("antwort", "Ja, auch negative Zahlen."),
    "spec_freigabe": ("tests_nachbessern", "FABLE-HINWEIS: Test für große Zahlen ergänzen."),
    "plan_freigabe": ("aendern", "Bitte erst den Test für große Zahlen, dann die Umsetzung."),
    "eskalation": ("annehmen", ""),
}


def fake_fable(name, prompt, cwd, schema, modell="sonnet", timeout=600, effort=None, runner=None):
    """Fake-Fable für die Demo: denkt 4 s und rät je Haltepunkt (aus dem Prompt erkannt)."""
    time.sleep(4)
    punkt = next(p for p in DEMO_RAT if f"an diesem Haltepunkt ({p})" in prompt)
    entscheidung, text = DEMO_RAT[punkt]
    daten = {"entscheidung": entscheidung, "text": text, "sicherheit": "mittel",
             "begruendung": f"(Demo) Für {punkt} wäre „{entscheidung}“ plausibel; ein echter Rat käme von Fable.",
             "punkte": [{"aussage": "Beispielpunkt", "warum": "nur Demo", "einschaetzung": "klein"}]}
    return {"name": name, "ok": True, "daten": daten, "fehler": None, "dauer_s": 4.0}


DEMO_RAT_ASTRA = {  # Astra widerspricht Fable an Spec und Plan: so sieht man „uneinig“ und den Einwand-Kasten
    "fragen": ("antwort", "Ja, auch negative Zahlen; große Zahlen ohne Grenze."),
    "spec_freigabe": ("aendern", "Den Satz zur Idempotenz streichen. <img src=x onerror=console.log('XSS')>"),
    "plan_freigabe": ("freigeben", ""),
    "eskalation": ("weiter", ""),
}


def fake_astra(name, prompt, cwd, schema, timeout=900, effort=None, runner=None):
    """Fake-Astra (Codex) für die Demo: denkt 6 s und widerspricht Fable an der Spec."""
    time.sleep(6)
    punkt = next(p for p in DEMO_RAT_ASTRA if f"an diesem Haltepunkt ({p})" in prompt)
    entscheidung, text = DEMO_RAT_ASTRA[punkt]
    daten = {"entscheidung": entscheidung, "text": text, "sicherheit": "hoch",
             "begruendung": f"(Demo) Für {punkt} rät Astra zu „{entscheidung}“. Ein echter Rat käme von Codex.",
             "punkte": [{"aussage": "Idempotenz-Satz widerspricht der ./-Regel", "warum": "nur Demo",
                         "einschaetzung": "echt"}]}
    return {"name": name, "ok": True, "daten": daten, "fehler": None, "dauer_s": 6.0}


# Nachprüfung (6c): Nach „Spec ändern“ zeigt die zweite Fassung beide Gruppen, den Verlauf und den Einwand
# „Codex meldet major weiter teilweise“.
GELOEST = {"nr": 1, "status": "geloest", "grund": "(Demo) erledigt"}
NACH_CODEX = {"verdict": "FAIL", "komplexitaet": "schwer", "komplexitaet_grund": "(Demo)",
              "punkte": [{"schwere": "minor", "aussage": "(Demo) Formulierung holpert", "herkunft": "sonstiges"}],
              "alte_punkte": [{"nr": 1, "status": "teilweise", "grund": "(Demo) nur halb gestrichen"}]}
NACH_CLAUDE = {"verdict": "FAIL", "alte_punkte": [GELOEST],
               "punkte": [{"schwere": "major", "aussage": "(Demo) stand schon in Fassung 1", "herkunft": "sonstiges"}]}


# Stufe 7: Das erste Gesamtreview widerspricht der Selbstbewertung (Tür einseitig) → Einwand am Abschluss, mergen
# nur mit Begründung. Spätere Läufe bekommen ein sauberes Gesamtreview.
GESAMT_EINSEITIG = {**GESAMT_OK, "zusammenfassung": "(Demo) erfüllt die Spec, löscht aber eine Datei",
                    "tuer": {"urteil": "einseitig", "radius": "Repo", "begruendung": "(Demo) löscht Dateien",
                             "faelle": ["Löschen von Daten oder Dateien: (Demo) mathe.py"],
                             "selbstbewertung_stimmt": False}}


class LangsamerPlaner(Planer):
    def __call__(self, *args, **kwargs):
        time.sleep(1.5)
        return super().__call__(*args, **kwargs)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8795)
    args = parser.parse_args()
    repo, aufgaben = mini_repo()
    # Codex-major (Einwand) und uneinige Schätzung: Claude „einfach“, Codex „schwer“ → schwer (Modellstufen 6b-2)
    planer = LangsamerPlaner(klaeren=[FRAGEN, KLAR], spec_schreiben=[{**SPEC, "komplexitaet": "einfach",
                                                                       "komplexitaet_grund": "(Demo) eine Funktion"}],
                             spec_codex=[{**CODEX_MAJOR, "komplexitaet": "schwer"}, NACH_CODEX,
                                         {**NACH_CODEX, "punkte": [], "alte_punkte": [GELOEST]}],
                             spec_pruefer=[PRUEF_OK, NACH_CLAUDE], gesamtreview=[GESAMT_EINSEITIG, GESAMT_OK])
    abh = Abhaengigkeiten(implementierer=Implementierer(RICHTIG), pruefer=_pruefer(), codex=_codex(),
                          planer=planer, planer_codex=planer.codex, berater=fake_fable,
                          berater_astra=fake_astra, aufgaben_dir=aufgaben,
                          weitere_geschuetzte=[])
    app = baue_app(abh, oeffne_checkpointer(), "demo", args.port, repos_dir=TEMP, demo=True)
    print(f"Leitstand-Demo: http://127.0.0.1:{args.port}/?token=demo  (Daten in {TEMP})", flush=True)
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
