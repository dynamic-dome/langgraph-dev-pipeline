# Lab 2 · Stufe 2 (parallele Prüfungen) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Nach dem Testlauf prüfen vier Prüfer **parallel** das Ergebnis des Implementierers: Funktion
(deterministisch), Security und Clean Code (`claude -p`, nur lesend) sowie Codex (`codex exec -s read-only`).
`befunde_sammeln` schickt ihre Berichte durch den fusion-harness-Filter und meldet, ob eine Fix-Runde nötig wäre.
Noch ohne Schleife, nur Bericht. Die Pipeline baut damit portwart-Aufgabe A2.

**Architecture:**
- `tests_ausfuehren` fächert per bedingter Kante mit vier `Send` an vier verschiedene Knoten auf.
- Jeder Prüfer hängt einen Bericht an `pruefberichte` an (Reducer `operator.add`).
- `befunde_sammeln` wartet auf alle vier (ein Superstep), filtert und dedupliziert.
- Prüfer-Adapter stecken wie der Implementierer hinter `Abhaengigkeiten` und sind in Tests gesperrt.

**Tech Stack:** wie Stufe 1. Neu genutzt werden `codex exec` (installierte Version) und `claude -p --json-schema`.

**Spec:** `docs/specs/2026-10-19-entwicklungs-pipeline-design.md` (Stufe 2, Randbedingungen „Prüfer“, „Funktion“,
„Was eine Fix-Runde auslöst“).

## Global Constraints

- Alle aus Stufe 1 gelten weiter (Pfade, Isolation, kein Fable, kein Push, Worktree ohne `--force`).
- A1 ist seit 19.10. lokal per Fast-Forward in `portwart/main` (Entscheid Dominic). A2 startet von dort.
- **Prüfer lesen nur:**
  - claude-Prüfer: `--restricted --tools Read,Glob,Grep` (kein Bash, kein Write/Edit), `cwd` = Worktree.
  - Codex: `-s read-only -c approval_policy="never" -c model_reasoning_effort="high"`, Diff und geänderte Dateien
    eingebettet.
  - Nach den Prüfern: Der Worktree muss unverändert sein (`geaenderte_dateien == []`) und die Nachkontrolle der
    geschützten Repos sauber. Sonst Status `grenzverletzung`.
- Prüferberichte folgen `<fusion-harness>/prompts/REVIEW_SCHEMA.json`. Gefiltert wird per
  Subprozess `python <fusion-harness>/fusion_harness.py --json befunde <bericht> --repo <worktree>
  --rev <sicherung> --changed <dateien>`. fusion-harness wird nie verändert.
- **Fix-Runde nötig** (in Stufe 2 nur im Bericht und im Exit-Code):
  - Funktion rot, oder
  - mindestens ein Befund im Topf `candidates` mit Schwere `blocker` oder `major`.
- Modelle: Prüfer `sonnet` (CLI `--pruefer-modell haiku|sonnet|opus`); Codex wie konfiguriert. Kein Fable.
- Ein Prüfer, der scheitert (Timeout, kein Schema, rc≠0), ist ein Eintrag „nicht verwertbar“ im Bericht, kein
  Absturz und **kein** PASS.
- Regression: Bei Aufgabe An laufen die Akzeptanztests aller Aufgaben A1…An des Repos mit.

## Review Focus

1. **Ein Prüfer schreibt in den Worktree** (oder die Nachkontrolle schlägt danach an): `grenzverletzung`, Befunde
   bleiben im Bericht. Test in Task 6.
2. **Ein Prüfer liefert Unsinn** (kein JSON, falsches Schema, leere Antwort): „nicht verwertbar“, kein PASS und
   kein stilles Weglassen. Tests in Tasks 4 und 5.
3. **Ein Befund zitiert Code, den es nicht gibt:** landet in `quote_missing` und löst keine Fix-Runde aus. Test in
   Task 5 mit dem echten Filter.
4. **Ein A1-Akzeptanztest bricht durch A2:** Regressionslauf rot, Funktion meldet einen Befund. Test in Task 3.
5. **Zwei Prüfer melden denselben Befund:** Er erscheint einmal, mit beiden Prüfern genannt. Test in Task 5.

---

### Task 1: Spike — Prüfer-Aufrufe gegen die echten Programme

**Files:** Create `docs/spike-2026-10-19-pruefer.md`. Kein Produktcode.

- [ ] **Step 1:** Temp-Repo mit einer Datei, die einen absichtlichen Fehler enthält.
  - `claude -p --restricted --tools Read,Glob,Grep --permission-prompts none --json-schema <REVIEW_SCHEMA>
    --output-format json` mit `cwd` = Repo. Prüfen: In welchem Feld steht das strukturierte Ergebnis? Ist es
    schema-gültig? Hat der Agent versucht zu schreiben?
- [ ] **Step 2:** `codex exec` per Python-`subprocess` (nicht Git Bash), mit Prompt per stdin, `-o <datei>` und
  `--output-schema`. Prüfen: `shutil.which("codex")`, rc, Inhalt der `-o`-Datei, Dauer, unveränderter Worktree.
- [ ] **Step 3:** Ergebnis, Flag-Satz und Fallen dokumentieren. **Commit** `docs: Spike Prüfer-Aufrufe`.

### Task 2: Aufgabe A2 mit Akzeptanztests

**Files:** Create `aufgaben/portwart/A2.md`, `aufgaben/portwart/A2/test_akzeptanz_a2.py`

**Vertrag A2 (steht so in `A2.md`):**
- **`portwart/lauschen.py`:**
  - `lauschende_ports(netstat_text: str) -> set[int]`: Zeilen mit Protokoll `TCP` oder `TCPv6`
    (Groß/Klein egal). Ein Port lauscht, wenn die Gegenadresse auf `:0` endet (`0.0.0.0:0`, `[::]:0`, `*:0`). Das
    gilt unabhängig von Sprache und Codepage des Statusworts. Der Port ist die Zahl nach dem letzten `:` der lokalen
    Adresse. Alle anderen Zeilen (UDP, Kopfzeilen, Verbindungen) werden ignoriert.
  - `lies_netstat() -> str`: `netstat -an` über `shutil.which`. Die Bytes werden mit `errors="replace"`
    dekodiert. Fehlt netstat oder scheitert der Aufruf, wird `LauschFehler` (Unterklasse von `RuntimeError`)
    geworfen.
- **`portwart/abgleich.py`:**
  - `Abgleich`: frozen dataclass mit `belegt`, `frei` und `unbekannt` (je `list[int]`, sortiert, ohne Wiederholung).
  - `abgleich(eintraege, lauschend, bereich=(1024, 49151)) -> Abgleich`:
    - `belegt` = eingetragen und lauscht
    - `frei` = eingetragen, lauscht nicht
    - `unbekannt` = lauscht, nicht eingetragen, liegt im Bereich
    - `bereich` filtert nur `unbekannt`.
- **CLI** `python -m portwart abgleich [--datei PFAD] [--netstat-datei PFAD] [--alle]`:
  - Ausgabe: eine Zeile je Port, erst `belegt`, dann `frei`, dann `unbekannt`, jeweils nach Port aufsteigend.
    Formate: `belegt 8766 wiki-inselwelt`, `frei 8792 langgraph-lab`, `unbekannt 9000`. Bei mehreren Projekten
    werden sie sortiert mit `, ` verbunden.
  - Exit-Codes: 0, wenn nichts unbekannt ist; 1, wenn mindestens ein Port unbekannt ist; 2 mit `Fehler: <grund>`
    auf stderr bei `ListenFehler`, `LauschFehler` oder fehlender netstat-Datei.
  - `--netstat-datei`: die Datei wird als Bytes gelesen statt netstat zu starten (cp850 erlaubt).
  - `--alle`: Bereich 1–65535.
  - `pruefen` aus A1 bleibt unverändert.

- [ ] **Step 1:** Etwa 15 Akzeptanztests. Sie importieren nur innerhalb der Testfunktionen (Regel aus Stufe 1).
  Abgedeckt werden:
  - deutsche netstat-Ausgabe mit cp850-Byte für „Ö“ (echter Mitschnitt-Ausschnitt) und englische Ausgabe
  - IPv6
  - eine bestehende Verbindung wird ignoriert, UDP wird ignoriert
  - alle drei Kategorien
  - der Bereich schließt 135 und 49664 aus, `--alle` nimmt sie mit
  - doppelt eingetragene Projekte
  - Exit-Codes 0, 1 und 2, fehlende netstat-Datei
  - `lies_netstat` ohne netstat (monkeypatch `shutil.which` → None) ergibt `LauschFehler`
- [ ] **Step 2:** Gegen `portwart/main` (A1) prüfen: A2 ist komplett rot, A1 bleibt grün. **Commit.**

### Task 3: Regression und Diff im Testlauf

**Files:** Modify `entwicklung/testlauf.py`, `entwicklung/graph.py` (vorbereiten), `entwicklung/worktree.py`;
Tests in `tests/test_testlauf.py`, `tests/test_worktree.py`

**Interfaces:**
- `fuehre_tests_aus(worktree, konfig, akzeptanz_dirs: list[Path], timeout=300) -> dict`:
  - Bisher `akzeptanz_dir`, jetzt eine Liste. Alle `*.py` der Liste kommen nach `tests/_akzeptanz/`.
  - Kommt ein Dateiname doppelt vor, gibt es `ValueError`.
  - `erwartet` = Summe der Erwartungen; ist eine davon unbekannt, ist auch die Summe unbekannt (`None`).
- `vorbereiten`:
  - `akzeptanz_dirs` = Ordner aller Aufgaben `aufgaben/<repo>/A<k>/` mit k ≤ n (Ziffern numerisch sortiert).
  - Merkt `basis` = HEAD des neuen Worktrees.
- `worktree.diff(worktree: Path, basis: str, ziel: str) -> str`: `git diff basis..ziel`.

- [ ] Tests:
  - `test_mehrere_akzeptanzordner` (Summe, erwartet)
  - `test_doppelter_dateiname_valueerror`
  - `test_regression_rot` (zweiter Ordner rot, also nicht grün)
  - `test_vorbereiten_sammelt_a1_bis_an`
  - `test_diff`
- [ ] FAIL, Implement, PASS. **Commit.**

### Task 4: Prüfer-Adapter

**Files:** Create `entwicklung/pruefer.py`, `tests/test_pruefer.py`; Modify `tests/conftest.py` (Sperre)

**Interfaces:**
- `ROLLEN = {"security": …, "clean_code": …, "codex": …}`: Fokus-Text je Rolle (deutsch).
- `pruefer_prompt(rolle, aufgabe_text, diff, dateien: dict[str, str]) -> str`. Inhalt:
  - Aufgabe, Diff, volle geänderte Dateien (zusammen höchstens 60 000 Zeichen, dann gekürzt mit Hinweis)
  - Schema-Pflicht
  - `quote` wörtlich aus der Datei, `path` relativ zum Repo
  - keine Stilfragen außer bei Clean Code mit `kind: style`
- `claude_pruefer(rolle, prompt, worktree, modell="sonnet", timeout=600, runner=None) -> dict`
- `codex_pruefer(prompt, worktree, timeout=900, runner=None) -> dict`
- Beide liefern `{"pruefer": rolle, "ok": bool, "bericht": dict | None, "fehler": str | None, "dauer_s": float}`.
  `ok` ist nur wahr, wenn `bericht` die Pflichtfelder des Schemas hat.
- `funktion_bericht(testergebnis: dict) -> dict`:
  - deterministisch, im Schema-Format, `pruefer: "funktion"`, `ok: True`
  - Befunde (Schwere `blocker`, `kind: bug`, `path: "tests"`, `status: executed`) für:
    rote oder fehlende Akzeptanztests (gesammelt ≠ erwartet), rote eigene Tests, rc≠0
  - `verdict: PASS`, wenn `testergebnis["gruen"]` gilt
- Testsperre: Mit `runner=None` und `agenten._TESTSPERRE` wird `EchterAgentImTest` geworfen.

- [ ] Tests:
  - Flags des claude-Prüfers: `--restricted`, `--tools Read,Glob,Grep`, `--json-schema` mit dem Schema, kein
    Write/Bash
  - Flags des Codex-Aufrufs: `-s read-only`, effort high, `--output-schema`, `-o`
  - Ausgabe ohne Schema, leer, Timeout oder rc≠0 ergibt `ok=False`
  - Kürzung bei 60 000 Zeichen
  - `funktion_bericht` grün / rot / fehlende Akzeptanz / rc≠0
  - Testsperre greift für beide Adapter
- [ ] FAIL, Implement (Flag-Satz nach Spike Task 1), PASS. **Commit.**

### Task 5: Befunde sammeln

**Files:** Create `entwicklung/befunde.py`, `tests/test_befunde.py`

**Interfaces:**
- `filtere(bericht: dict, worktree: Path, rev: str, geaendert: list[str]) -> dict`: ruft fusion-harness (Pfad wie in
  Global Constraints) per Subprozess mit `--json` auf und gibt dessen Töpfe zurück (`candidates`, `quote_missing`,
  `side`, `speculation`, `out_of_scope`, `not_checkable`, `duplicates`). Ist der Bericht nicht verwertbar (rc 4)
  oder liefert der Subprozess kein JSON, gibt es `ValueError`.
- `sammle(pruefberichte: list[dict], worktree, rev, geaendert) -> dict` mit den Feldern:
  - `befunde`: Liste von `{pruefer: [..], topf, severity, kind, path, line, claim}`; Funktion-Befunde mit
    `topf: "deterministisch"`, ohne Filter
  - `nicht_verwertbar`: `[{"pruefer", "fehler"}]`
  - `fix_noetig`: bool, Regel aus Global Constraints
  - Gleich sind zwei Befunde, wenn `(path, line, claim.lower())` übereinstimmen; dann erscheinen sie einmal mit
    allen Prüfern.

- [ ] Tests mit dem **echten** Filter gegen ein Mini-Repo in tmp_path:
  - Zitat vorhanden ergibt `candidates`
  - erfundenes Zitat ergibt `quote_missing`
  - `minor` ergibt `side` und keine Fix-Runde
  - kaputter Bericht ergibt `nicht_verwertbar`
  - zwei Prüfer mit demselben Befund ergeben einen Eintrag mit zwei Prüfern
  - roter Funktion-Bericht ergibt `fix_noetig`
- [ ] FAIL, Implement, PASS. **Commit.**

### Task 6: Graph S2 mit Send, Bericht, CLI

**Files:** Modify `entwicklung/state.py`, `graph.py`, `bericht.py`, `cli.py`; Create `tests/test_graph_s2.py`

**Interfaces:**
- State neu:
  - `basis`, `akzeptanz_dirs`
  - `pruefberichte: Annotated[list[dict], operator.add]`
  - `befunde`, `nicht_verwertbar`, `fix_noetig`, `pruefer_modell`
- `baue_graph_s2(abh=None, checkpointer=None)` mit derselben Strecke wie S1. Nach `tests_ausfuehren` geht eine
  bedingte Kante `zu_pruefern` → `[Send("pruefen_funktion", …), Send("pruefen_security", …),
  Send("pruefen_clean_code", …), Send("pruefen_codex", …)]` mit Payload `{worktree, aufgabe_text, diff, dateien,
  testergebnis, pruefer_modell}`. Danach `befunde_sammeln` (Nachkontrolle Worktree + geschützte Repos, `sammle`)
  → `bericht`.
- `Abhaengigkeiten` neu: `pruefer` (`claude_pruefer`), `codex` (`codex_pruefer`).
- Bericht: neue Abschnitte „Prüfer“ (je Prüfer: ok / nicht verwertbar, Dauer, Zahl der Befunde) und „Befunde“
  (nach Topf, auslösende zuerst), dazu die Zeile „Fix-Runde nötig: ja/nein“.
- CLI:
  - `lauf … [--stufe 1|2]` (Standard 2), `--pruefer-modell`
  - Exit 0 nur bei `gruen` und nicht `fix_noetig`
  - `--live` zeigt die vier Prüfer, sobald sie fertig sind
- `baue_graph_s1` bleibt unverändert lauffähig.

- [ ] Tests mit Fakes (Implementierer, Prüfer, Codex) und echtem Testlauf und Filter:
  - `test_vier_pruefer_laufen` (vier Berichte, Reihenfolge egal)
  - `test_befund_mit_zitat_loest_fix_aus`
  - `test_pruefer_schreibt_ist_grenzverletzung`
  - `test_pruefer_kaputt_nicht_verwertbar`
  - `test_grenzverletzung_ueberspringt_pruefer`
  - `test_cli_stufe_1_weiter_lauffaehig`
  - `test_cli_exit_bei_fix_noetig`
- [ ] FAIL, Implement, PASS, `sqlite-schema-guard`. **Commit.**

### Task 7: Live-Lauf A2, Lernnotiz 02, Codex, Gate

- [ ] **Step 1:** `python -m entwicklung lauf --repo portwart --aufgabe A2 --live` (sonnet). Erwartet:
  - Akzeptanz A1 und A2 grün
  - vier Prüferberichte, davon höchstens Codex nicht verwertbar
  - die Prüfer laufen gleichzeitig: ihre Zeitstempel in `--live` liegen dicht beieinander
- [ ] **Step 2:** Von Hand nachprüfen:
  - `python -m portwart abgleich` gegen das echte netstat (zeigt z. B. 8770 und 8792)
  - Worktree und Hauptrepo unverändert
  - Befunde an der Quelle prüfen
- [ ] **Step 3:** Lernnotiz `docs/lernpfad/02-pruefer-send.md`. Inhalt:
  - Send an verschiedene Ziele
  - Reducer
  - Superstep als Warte-Punkt
  - warum Funktion kein LLM ist
  - Filter mit Quellenprüfung
  - was die Prüfer im echten Lauf fanden
- [ ] **Step 4:** Commit, Codex-Verifier (`high`) über den Stufen-Diff, Befunde per TDD. Ledger nach `docs/`.
  **STUFEN-GATE.**
