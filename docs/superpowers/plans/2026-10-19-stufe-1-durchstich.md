# Lab 2 · Stufe 1 (Durchstich) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Die erste echte Pipeline: Aufgabe → Implementierer (`claude -p --restricted` im Worktree) → Nachkontrolle
→ Tests inklusive unabhängiger Akzeptanztests → Bericht. Damit baut die Pipeline portwart-Aufgabe A1 selbst.

**Architecture:**
- Paket `entwicklung` mit einem LangGraph-Graphen `baue_graph_s1`.
- Alles Externe (Implementierer, git, Testlauf) steckt hinter einem `Abhaengigkeiten`-Objekt. Tests reichen Fakes
  herein, und eine `BaseException`-Sperre verhindert echte Agenten in Tests (Muster aus `langgraph-lab`).
- Zielrepo portwart ist ein eigenes git-Repo. Je Lauf entsteht ein Worktree unter `arbeit/`.

**Tech Stack:** Python 3.12 (uv-venv), langgraph 1.2.10, langgraph-checkpoint-sqlite 3.1.2, pytest; git; Claude Code
2.1.303 (`claude -p`).

**Spec:** `docs/specs/2026-10-19-entwicklungs-pipeline-design.md`

## Global Constraints

- Projektordner `langgraph-lab-2`, eigenes git-Repo (lokal, kein Remote). Python nur über
  `.venv\Scripts\python.exe`.
- `.gitignore`: `.venv/`, `data/`, `berichte/`, `arbeit/`, `portwart/`, `privat/`, `__pycache__/`, `.pytest_cache/`,
  `.superpowers/`.
- Schreiben nur unter `langgraph-lab-2\{data,berichte,arbeit}` oder im Temp-Ordner (lazy Pfade mit Guard wie in
  `langgraph-lab/oekopuls/pfade.py`). Ins portwart-Hauptrepo schreibt nur das Grundgerüst in Task 2 (von Hand).
- Implementierer-Aufruf (sofern der Spike in Task 3 es bestätigt):
  - `claude -p --model <m> --restricted --permission-prompts none --tools Read Edit Write Glob Grep Bash`
  - `--allowedTools "Bash(<python> -m pytest:*)"`
  - `cwd` = Worktree, Prompt per stdin (UTF-8), API-Keys aus der Umgebung entfernen, Timeout 600 s
- Nachkontrolle nach jedem Agentenaufruf: `git status --porcelain` im portwart-Hauptrepo und in Lab 2 muss gleich
  bleiben (bis auf `arbeit/`). Sonst Abbruch mit Status `grenzverletzung`.
- Akzeptanztests liegen in `langgraph-lab-2/aufgaben/portwart/A1/` und **nicht** im portwart-Repo. Sie werden erst
  zum Testlauf in den Worktree kopiert (`tests/_akzeptanz/`) und danach wieder entfernt.
- Kein Push, kein Merge in Stufe 1. Der Worktree bleibt nach dem Lauf zur Ansicht stehen; Aufräumen über
  `python -m entwicklung aufraeumen`.
- Modelle: Implementierer `sonnet` (Standard), kein Fable.
- Test-DB-Isolation wie in Lab 1, inklusive `sqlite-schema-guard` vor dem ersten pytest.

## Review Focus

1. **Agent schreibt außerhalb des Worktrees** (z. B. ins portwart-Hauptrepo): Die Nachkontrolle meldet
   `grenzverletzung`, die Tests laufen nicht, der Bericht nennt die Pfade. Test in Task 4.
2. **Agent ändert oder löscht die Akzeptanztests:** Sie werden vor jedem Testlauf frisch kopiert. Eigene Änderungen
   des Agenten unter `tests/_akzeptanz/` werden überschrieben. Test in Task 5.
3. **pytest sammelt 0 Tests** (z. B. Importfehler): Das gilt als `fehlgeschlagen`, nicht als grün. Test in Task 5.
4. **Implementierer hängt oder bricht ab** (Timeout, rc≠0, keine Ausgabe): Das ist ein Befund `agent_fehler`, kein
   Absturz des Graphen. Der Worktree bleibt zur Ansicht. Test in Task 6.
5. **Worktree-Name existiert schon** (zweiter Lauf derselben Sekunde): Es wird ein Suffix angehängt, nichts
   überschrieben. Test in Task 4.

---

### Task 1: Projekt-Setup, Pfade, Isolation

**Files:** Create `pyproject.toml`, `.gitignore`, `CLAUDE.md` (≤ 40 Zeilen), `HOW-TO-USE.md`,
`entwicklung/__init__.py`, `entwicklung/pfade.py`, `tests/conftest.py`, `tests/test_pfade.py`

**Interfaces:**
- `pfade.projekt_dir()`, `data_dir()`, `berichte_dir()`, `arbeit_dir()`, `checkpoint_db_pfad()`, `pruefe_schreibziel(p)`
- Umgebungsvariablen `ENTWICKLUNG_DATA_DIR`, `ENTWICKLUNG_BERICHTE_DIR`, `ENTWICKLUNG_ARBEIT_DIR`

- [ ] **Step 1:** `git init`, `uv venv --python 3.12 .venv`, Abhängigkeiten installieren, `requirements.lock`.
- [ ] **Step 2: Failing tests** analog zu `langgraph-lab/tests/test_pfade.py`:
  - Override per Umgebungsvariable
  - Verbot für die Datenordner anderer eigener Projekte
  - Ziel nur im Projekt oder Temp-Ordner
  - Checkpoint-DB liegt in `data_dir()`
- [ ] **Step 3: Implement.** Die conftest leitet alle drei Ordner auf `tmp_path` um, mit Hard-Guards und
  Vorher/Nachher-Prüfung der echten `data/checkpoints.db` inklusive `-wal`/`-shm`. Dazu kommt die Testsperre für
  echte Agenten aus Task 6, vorbereitet als `monkeypatch.setattr(agenten, "_TESTSPERRE", True)`.
- [ ] **Step 4:** Tests grün, `sqlite-schema-guard` PASS. **Commit** `feat: Lab-2-Gerüst, Pfade mit Guards, Test-Isolation`

### Task 2: portwart-Grundgerüst und Aufgabe A1 mit Akzeptanztests

**Files:**
- portwart-Repo (`langgraph-lab-2/portwart/`, eigenes `git init`): `pyproject.toml`, `portwart/__init__.py` (leer bis
  auf Docstring), `tests/__init__.py`, `tests/test_platzhalter.py` (ein grüner Platzhaltertest), `ports.toml`
  (Beispiel mit echten Ports, darunter 8770 doppelt), `entwicklung.toml`, `README.md`
- Lab 2: `aufgaben/portwart/A1.md`, `aufgaben/portwart/A1/test_akzeptanz_a1.py`

**Interfaces (Vertrag A1, steht wörtlich in `A1.md`):**
- `ports.toml`: Liste `[[port]]` mit `port` (int 1–65535), `projekt` (str), `zweck` (str, optional)
- `portwart.liste.lade(pfad) -> list[Eintrag]`. `Eintrag` ist eine frozen dataclass mit `port`, `projekt`, `zweck`.
  Wirft `ListenFehler` (Unterklasse von `ValueError`) bei kaputtem TOML, fehlendem Feld oder Port außerhalb 1–65535.
- `portwart.liste.doppelte(eintraege) -> dict[int, list[str]]`: nur Ports mit mehr als einem Projekt, Projekte
  sortiert.
- CLI `python -m portwart pruefen [--datei PFAD]` (Standard `ports.toml` im aktuellen Ordner):
  - Exit 0 mit „keine doppelten Ports“, wenn alles passt
  - Exit 1 mit einer Zeile je Kollision im Format `Port 8770 doppelt: job-radar, tool-tracker`
  - Exit 2 mit `Fehler: <grund>` bei einem `ListenFehler`
- `entwicklung.toml`: `python = "<absoluter Pfad zu langgraph-lab-2/.venv/Scripts/python.exe>"`,
  `testbefehl = ["-m", "pytest", "-q"]`

- [ ] **Step 1:** Gerüst anlegen. Der Platzhaltertest ist grün, erster Commit im portwart-Repo.
- [ ] **Step 2:** `test_akzeptanz_a1.py` schreiben, mit 8–12 Tests zum Vertrag: Laden, Doppelte, Grenzwerte
  0/65536, fehlendes Feld, kaputtes TOML, alle drei CLI-Exit-Codes, Ausgabeformat. Diese Tests müssen gegen das leere
  portwart **rot** sein. Prüfen: In den Worktree kopiert und ausgeführt schlagen alle fehl (ImportError zählt).
- [ ] **Step 3: Commit** in Lab 2 `feat: Aufgabe A1 mit unabhängigen Akzeptanztests`

### Task 3: Spike — claude --restricted gegen das echte Programm

**Files:** Create `docs/spike-2026-10-19-restricted.md` (Ergebnis). Kein Produktcode.

- [ ] **Step 1:** Temporäres git-Repo mit Worktree in `%TEMP%`. Darin einen echten Aufruf mit den Flags aus den
  Global Constraints starten. Auftrag: (a) `hallo.py` anlegen, (b) pytest ausführen, (c) eine Datei **außerhalb** des
  Worktrees anlegen, (d) `git commit` ausführen, (e) `curl` aufrufen.
- [ ] **Step 2:** Ergebnis an Dateien und git prüfen, nicht an der Selbstauskunft des Agenten: (a) und (b) erlaubt,
  (c), (d) und (e) verweigert. Ausgabeformat, Laufzeit und rc notieren.
- [ ] **Step 3:** Weicht etwas ab, den Flag-Satz anpassen und erneut prüfen. Lässt sich (c) nicht verhindern, als
  Ruling festhalten: Dann trägt die Nachkontrolle allein, und Dominic wird beim Stufen-Gate informiert.
- [ ] **Step 4: Commit** `docs: Spike claude --restricted`

### Task 4: Worktree und Nachkontrolle

**Files:** Create `entwicklung/worktree.py`, `tests/test_worktree.py`

**Interfaces:**
- `anlegen(repo: Path, lauf_id: str) -> Path`: `git worktree add -b lauf/<lauf_id> <arbeit_dir>/<reponame>-<lauf_id>`,
  bei Namenskonflikt Suffix `-2`, `-3` …
- `stand(repo: Path) -> list[str]`: sortierte Zeilen von `git status --porcelain=v1 -uall`
- `geaenderte_dateien(worktree: Path) -> list[str]`: relativ zum Worktree
- `grenzverletzungen(vorher: dict[str, list[str]], nachher: dict[str, list[str]]) -> list[str]`: Sätze je Repo mit neuen
  oder geänderten Pfaden, Pfade unter `arbeit/` ausgenommen
- `entfernen(repo: Path, worktree: Path) -> None`: `git worktree remove --force` plus Branch löschen; nie `rm -rf`

- [ ] **Step 1: Failing tests** mit echten git-Repos in `tmp_path`:
  - Anlegen und Datei schreiben, dann zeigt `geaenderte_dateien` die Datei
  - Zweiter Lauf mit gleicher ID bekommt Suffix (Review Focus 5)
  - Eine Datei im Hauptrepo nach `vorher` ergibt eine Grenzverletzung (Review Focus 1)
  - Entfernen räumt Worktree und Branch weg
- [ ] **Step 2–4:** FAIL, Implement (git per `shutil.which("git")`, `encoding="utf-8"`), PASS. **Commit.**

### Task 5: Testlauf mit Akzeptanztests

**Files:** Create `entwicklung/konfig.py`, `entwicklung/testlauf.py`, `tests/test_testlauf.py`

**Interfaces:**
- `lade_zielkonfig(repo: Path) -> dict` mit `python` (Pfad) und `testbefehl` (list[str]); fehlt die Datei:
  `ValueError` mit Hinweis
- `fuehre_tests_aus(worktree: Path, konfig: dict, akzeptanz_dir: Path | None, timeout: int = 300) -> dict`:
  - kopiert `akzeptanz_dir/*.py` frisch nach `worktree/tests/_akzeptanz/` und überschreibt dabei vorhandene
  - führt `[python, *testbefehl, "--junitxml", <tmp>]` im Worktree aus
  - wertet die JUnit-XML aus
  - liefert `{gesammelt, bestanden, fehlgeschlagen, fehler, akzeptanz: {gesammelt, bestanden}, gruen: bool, auszug}`
  - entfernt `tests/_akzeptanz/` danach wieder
  - `gruen` gilt nur, wenn mehr als 0 gesammelt, 0 fehlgeschlagen, 0 Fehler und mindestens 1 Akzeptanztest gelaufen
- `auszug` sind die letzten 40 Zeilen der Ausgabe.

- [ ] **Step 1: Failing tests** mit einem Mini-Repo in `tmp_path` und dem Lab-2-venv als Python:
  - grüne Tests ergeben `gruen`
  - ein roter Akzeptanztest ergibt kein `gruen`
  - Importfehler ergibt 0 gesammelt, kein `gruen` (Review Focus 3)
  - eine vom „Agenten“ veränderte Akzeptanzdatei wird überschrieben (Review Focus 2)
  - `_akzeptanz` ist nach dem Lauf entfernt
- [ ] **Step 2–4:** FAIL, Implement, PASS. **Commit.**

### Task 6: Implementierer-Adapter

**Files:** Create `entwicklung/agenten.py`, `tests/test_agenten.py`

**Interfaces:**
- `class EchterAgentImTest(BaseException)`, `_TESTSPERRE = False`
- `implementierer_prompt(aufgabe_text: str, testbefehl_text: str) -> str`: deutsch. Inhalt:
  - Aufgabe umsetzen, eigene Tests schreiben, Tests ausführen
  - nichts außerhalb des Arbeitsordners ändern, kein git
  - am Ende eine kurze Zusammenfassung
- `claude_implementierer(prompt: str, worktree: Path, python: str, modell: str = "sonnet", timeout: int = 600, runner=None) -> dict`:
  - Flags laut Global Constraints, angepasst nach dem Spike-Ergebnis
  - liefert `{ok: bool, zusammenfassung: str, rc: int, dauer_s: float, fehler: str | None}`
  - Timeout, OSError oder leere Ausgabe ergeben `ok=False` mit `fehler`, keine Exception (Review Focus 4)
  - `runner=None` und `_TESTSPERRE` ergeben `EchterAgentImTest`

- [ ] **Step 1: Failing tests:**
  - `test_befehl_gehaertet` (Fake-Runner prüft Flags, cwd, stdin, env ohne API-Keys)
  - `test_timeout_ok_false`
  - `test_leere_ausgabe_ok_false`
  - `test_testsperre`
- [ ] **Step 2–4:** FAIL, Implement, PASS. **Commit.**

### Task 7: Graph S1, Bericht, CLI, Lernnotiz, Live-Lauf A1

**Files:** Create `entwicklung/state.py`, `entwicklung/graph.py`, `entwicklung/bericht.py`, `entwicklung/cli.py`,
`entwicklung/__main__.py`, `tests/test_graph_s1.py`, `tests/test_cli.py`, `docs/lernpfad/01-durchstich.md`

**Interfaces:**
- `Abhaengigkeiten` (dataclass) mit Standardwerten auf die echten Funktionen:
  - `implementierer`: Signatur wie `claude_implementierer`
  - `tests`: wie `fuehre_tests_aus`
  - `worktree_anlegen`, `stand`
- `baue_graph_s1(abh=None, checkpointer=None)` mit den Knoten:
  - `vorbereiten`: Aufgabe aus `aufgaben/<repo>/<id>.md` laden, Zielkonfig lesen, Stand vorher von portwart-Repo und
    Lab 2, Worktree anlegen
  - `implementieren`
  - `grenzen_pruefen`: bedingte Kante, bei Verletzung direkt zum Bericht
  - `tests_ausfuehren`
  - `bericht`
- State-Felder:
  - `repo`, `aufgabe_id`, `aufgabe_text`, `konfig`, `lauf_id`, `worktree`, `stand_vorher`
  - `agent`, `grenzverletzungen`, `testergebnis`, `geaenderte_dateien`
  - `status` (`gruen` | `rot` | `grenzverletzung` | `agent_fehler`), `bericht_pfad`
- Bericht `berichte/<lauf_id>.md` und `.json`: Aufgabe, Status, geänderte Dateien, Testzahlen (eigene und Akzeptanz),
  Agenten-Zusammenfassung, Testauszug, Worktree-Pfad.
- CLI:
  - `python -m entwicklung lauf --repo portwart --aufgabe A1 [--modell sonnet] [--live]`. `--repo` ist ein Pfad oder
    ein Name unter `langgraph-lab-2/`; `--live` streamt die Knoten wie im Puls.
  - `python -m entwicklung aufraeumen [--alle]` entfernt alte Worktrees.

- [ ] **Step 1: Failing tests** mit Fake-Implementierer, der in den Worktree schreibt:
  - `test_gruen`: Fake schreibt korrekten Code, Status `gruen`
  - `test_rot`: Akzeptanztest rot
  - `test_grenzverletzung`: Fake schreibt ins Hauptrepo, Status `grenzverletzung`, Tests liefen nicht
  - `test_agent_fehler`: Fake liefert `ok=False`, Status `agent_fehler`
  - `test_cli_lauf`
- [ ] **Step 2–4:** FAIL, Implement, PASS, `sqlite-schema-guard`.
- [ ] **Step 5: Live-Lauf A1** mit echtem Implementierer (`sonnet`). Erwartet: Status `gruen`, alle Akzeptanztests
  bestanden. Das Ergebnis wird im Worktree selbst nachgeprüft: `pytest` von Hand, `python -m portwart pruefen` auf
  dem Beispiel meldet 8770. Außerdem wird kontrolliert, dass das portwart-Hauptrepo unverändert ist.
- [ ] **Step 6: Lernnotiz 01** am echten Code und Lauf: Agent als Knoten mit Schreibrechten, warum Worktree, zwei
  Sperren, warum Akzeptanztests unabhängig sein müssen, `gruen` ist erst gruen, wenn gezählt wurde.
- [ ] **Step 7: Commit**, Codex-Verifier (`high`), Befunde an der Quelle prüfen und mit TDD beheben. **STUFEN-GATE.**
