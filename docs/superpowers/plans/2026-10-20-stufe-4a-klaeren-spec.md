# Lab 2 · Stufe 4a (klären, Spec, Akzeptanztests aus der Spec) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Vor dem Implementieren steht eine Planungsphase. Die Pipeline bekommt nur noch einen kurzen **Wunsch**
(`aufgaben/portwart/A4.md`) und läuft so:
- Sie stellt Dominic Rückfragen.
- Sie schreibt eine Spec.
- Ein eigener Agent schreibt aus der Spec die Akzeptanztests.
- Code prüft diese Tests, und Codex und Claude prüfen Spec und Tests.
- Dominic gibt die Spec frei.
- Danach läuft Stufe 3 unverändert, mit der Spec als Aufgabe.

**Architecture:**
- Neuer Graph `baue_graph_s4` in `entwicklung/graph_s4.py`. Er setzt vor `implementieren` die Planungsknoten und
  übernimmt die Bausteine von Stufe 3 unverändert.
- Zwei neue Haltepunkte per `interrupt` (`fragen`, `spec_freigabe`) neben `eskalation`, alle mit dem Muster aus
  Stufe 3: ein interrupt je Durchlauf, Kante zu sich selbst bei ungültiger Antwort.
- Alle Planungsagenten lesen nur und liefern ihr Ergebnis als JSON (`--json-schema`). Dateien schreibt nur
  Pipeline-Code, und zwar nach `berichte/<lauf_id>/`, außerhalb des Worktrees.

**Tech Stack:** wie Stufe 3 (LangGraph 1.2.10, SqliteSaver, `claude -p`, `codex exec`), dazu `ast` aus der
Standardbibliothek für die Testprüfung.

**Spec:** `docs/specs/2026-10-19-entwicklungs-pipeline-design.md`. Maßgeblich sind:
- Stufe 4 in der Tabelle
- „Ab Stufe 4 entstehen Kriterien und Akzeptanztests aus der Spec, und zwar durch einen eigenen Agenten“
- „Freigaben immer per interrupt“

Entscheide Dominic 20.10.: Stufe 4 wird in 4a (dieser Plan) und 4b (Plan und Plan-Prüfung) geteilt. Akzeptanztests
schreibt ein eigener Agent, mit den Sicherungen dieses Plans.

## Global Constraints

- Alle Regeln aus Stufe 1 bis 3 gelten weiter. Fix-Regel mit zweiter Stimme gilt (Gate 20.10.).
- Planungsagenten (Klärer, Spec-Schreiber, Test-Schreiber, Spec-Prüfer):
  - `claude -p --restricted --tools Read,Glob,Grep --json-schema …`
  - `cwd` = Worktree (noch Stand `main`), Modell `sonnet`
  - Codex als Spec-Prüfer: `-s read-only`, `--output-schema`, `high`
  - Nach jedem Planungsagenten: Worktree unverändert (`geaenderte_dateien == []`) und geschützte Repos sauber,
    sonst `grenzverletzung`
- `MAX_KLAERUNGEN = 3` Fragerunden. Danach schreibt der Spec-Schreiber offene Punkte als Annahmen in die Spec.
- `AKZ_VERSUCHE = 2`. Scheitert die Testprüfung zweimal, endet der Lauf mit dem Status `akzeptanz_fehler`.
- Akzeptanztests eines Laufs liegen unter `berichte/<lauf_id>/akzeptanz/<aufgabe_id>/test_akzeptanz_<id klein>.py`,
  die Spec unter `berichte/<lauf_id>/spec.md`. Der Implementierer sieht beides nie. Sein Prompt enthält nur die Spec,
  die Tests kommen erst im Testlauf in den Worktree und werden danach wieder entfernt (wie bisher).
- Regression: Zum Testlauf gehören die Akzeptanzordner A1…A(n−1) aus `aufgaben/` und der erzeugte Ordner.
- Antworten an die Haltepunkte:

  | Haltepunkt | gültige Antwort |
  |---|---|
  | `fragen` | `{"antwort": "<nicht leer>"}` oder `{"entscheidung": "abbrechen"}` |
  | `spec_freigabe` | `{"entscheidung": "freigeben"}`, `{"entscheidung": "aendern", "hinweis": "<nicht leer>"}`, `{"entscheidung": "abbrechen"}` |
  | `eskalation` | wie Stufe 3 |

  Alles andere hält erneut an, mit Hinweis.
- Neue Status: `akzeptanz_fehler` (⚠). `abgebrochen` gilt auch für einen Abbruch in der Planung.
- Exit-Code 3, solange ein Lauf an irgendeinem Haltepunkt wartet.
- Kein Fable. Kein Push. Merge nach `portwart/main` nur nach Dominics Zustimmung beim Gate.

## Review Focus

1. **Der Test-Agent schreibt Tests, die gegen `main` schon grün sind** und damit nichts prüfen. Die Probe verlangt
   mindestens einen roten Akzeptanztest. Grüne Tests zeigt die Freigabe namentlich an. Test in Task 4.
2. **Der Test-Agent importiert Zielcode auf Modulebene oder Namen, die nicht in der Spec stehen.**
   `pruefe_akzeptanz` lehnt das ab, dann folgt ein zweiter Versuch mit den Gründen, dann `akzeptanz_fehler`.
   Tests in Task 2 und 4.
3. **Leere oder unpassende Antwort an einen Haltepunkt** (`--antwort ""`, `aendern` ohne Hinweis, `--antwort` an
   die Freigabe): Der Lauf hält erneut an, oder die CLI meldet, was dort erlaubt ist. Nichts wird entschieden.
   Tests in Task 4 und 5.
4. **Ein Planungsagent verändert trotz Lesewerkzeugen den Worktree oder ein geschütztes Repo:** `grenzverletzung`,
   kein Implementierer. Test in Task 4.
5. **Die erzeugten Tests sickern zum Implementierer durch:** Sein Prompt enthält keinen Testcode, und im Worktree
   liegt vor `tests_ausfuehren` keine Akzeptanzdatei. Test in Task 4.

---

### Task 1: Agenten mit JSON-Ergebnis

**Files:** Create `entwicklung/strukturiert.py`, `tests/test_strukturiert.py`

**Interfaces:**
- `claude_strukturiert(name: str, prompt: str, cwd: Path, schema: dict, modell: str = "sonnet",
  timeout: int = 600, runner=None) -> dict`. Flags wie `pruefer.claude_pruefer`, mit `--json-schema
  json.dumps(schema)`. Ergebnis `{"name", "ok", "daten", "fehler", "dauer_s"}`; `daten` = `structured_output`.
- `codex_strukturiert(name, prompt, cwd, schema: dict, timeout: int = 900, runner=None) -> dict`: Schema in eine
  Temp-Datei für `--output-schema`, sonst wie `pruefer.codex_pruefer`.
- Beide nutzen `pruefer._runner` (Testsperre) und `pruefer._umgebung` (ohne API-Keys). `pruefer.py` bleibt
  unverändert.

- [ ] Tests mit Fake-Runner:
  - `test_claude_strukturiert_liefert_daten` (Kommando enthält `--restricted`, `--tools Read,Glob,Grep`, Schema)
  - `test_claude_strukturiert_fehlerfaelle` (rc≠0, `is_error`, kein JSON, Timeout ergeben `ok False` mit Grund)
  - `test_codex_strukturiert_liest_ausgabedatei`
  - `test_testsperre_gilt` (ohne runner: `EchterAgentImTest`)
- [ ] FAIL, Implement, PASS. **Commit.**

### Task 2: Planungsbausteine (Schemas, Prompts, Testprüfung)

**Files:** Create `entwicklung/planung.py`, `tests/test_planung.py`

**Interfaces:**
- Schemas (dicts):
  - `KLAER_SCHEMA`: `{klar: bool, verstaendnis: str, fragen: [str]}`
  - `SPEC_SCHEMA`: `{spec: str (Markdown), schnittstellen: [{modul: str, namen: [str]}], annahmen: [str]}`
  - `AKZEPTANZ_SCHEMA`: `{dateien: [{name: str, inhalt: str}]}`
  - `SPEC_PRUEF_SCHEMA`: `{verdict: "PASS"|"FAIL", punkte: [{schwere: "major"|"minor", aussage: str}]}`
- Prompts (deutsch, je eine Funktion → `str`):
  - `klaer_prompt(wunsch, klaerung: list[dict], runde, max_runden)`
  - `spec_prompt(wunsch, klaerung, aenderung: str | None, vorige_spec: str | None, pruefpunkte: list)`. Die Spec
    hat die Abschnitte von `A3.md`: Ziel, Vertrag (Module, Funktionen, CLI, Exit-Codes, Fehler), Rahmen, Annahmen.
  - `akzeptanz_prompt(spec, schnittstellen, aufgabe_id, gruende: list[str])`. Regeln:
    - Imports des Zielcodes nur in Testfunktionen und nur aus den Schnittstellen
    - CLI über `subprocess` mit `python -m portwart`, `REPO = Path(__file__).resolve().parents[2]`
    - nur `tmp_path`, kein echtes netstat, kein Netz
    - 10 bis 30 Tests, Dateiname `test_akzeptanz_<id klein>.py`
  - `spec_pruef_prompt(wunsch, klaerung, spec, tests: dict[str, str])`: prüft Spec gegen Wunsch und Antworten
    sowie Tests gegen die Spec.
- `pruefe_akzeptanz(dateien: list[dict], schnittstellen: list[dict], aufgabe_id: str) -> list[str]`: Gründe, leer =
  in Ordnung. Regeln per `ast`:
  - genau eine Datei mit dem erwarteten Namen, gültiges Python
  - Imports auf Modulebene nur aus der Standardbibliothek (`sys.stdlib_module_names`) und `pytest`
  - in Funktionen nur `from portwart.<m> import <n>` mit `(m, n)` aus den Schnittstellen
  - mindestens 1 Testfunktion
- `lege_ab(ordner: Path, spec: str, dateien: list[dict], aufgabe_id: str) -> Path`: schreibt `spec.md` und
  `akzeptanz/<aufgabe_id>/…`, gibt den Akzeptanzordner zurück. Nur über `pfade.pruefe_schreibziel`.

- [ ] Tests:
  - `test_pruefe_akzeptanz_ok`
  - `test_import_auf_modulebene_abgelehnt`
  - `test_name_ausserhalb_der_spec_abgelehnt`
  - `test_falscher_dateiname_und_syntaxfehler`
  - `test_ohne_testfunktion_abgelehnt`
  - `test_lege_ab_nur_unter_berichte`
  - `test_prompts_enthalten_regeln` (akzeptanz_prompt nennt die Schnittstellen; spec_prompt enthält Antworten und
    Hinweis)
- [ ] FAIL, Implement, PASS. **Commit.**

### Task 3: State und mehrere Haltepunkte im Speicher

**Files:** Modify `entwicklung/state.py`, `entwicklung/speicher.py`; Tests in `tests/test_state.py`,
`tests/test_speicher.py`

**Interfaces:**
- State neu:
  - `wunsch: str`, `klaerung: Annotated[list[dict], operator.add]` (je Runde `{fragen, antwort}`)
  - `klaer_runde: int`, `offene_fragen: list[str]`, `verstaendnis: str`
  - `spec: str`, `schnittstellen: list[dict]`, `annahmen: list[str]`, `spec_runde: int`,
    `spec_aenderung: str | None`
  - `akz_versuch: int`, `akz_gruende: list[str]`, `akz_dateien: list[dict]`, `akz_ordner: str`,
    `akz_probe: dict` (`{erwartet, bestanden, gruen_gegen_main: [Testnamen]}`)
  - `spec_pruefungen: Annotated[list[dict], sammeln_oder_leeren]`, `halt_hinweis: str`
- `speicher.WARTEPUNKTE = ("fragen", "spec_freigabe", "eskalation")`
- `speicher.wartepunkt(graph, thread_id) -> str | None`: Name der Aufgabe mit offenem interrupt
- `wartende_laeufe(cp, graph_fuer: Callable[[int], graph]) -> list[str]`: baut den Graphen je Thread nach
  `metadata["stufe"]` (fehlt die Angabe: 3).
- Aufrufer (`cli._fortsetzen`, `cli._wartende_worktrees`) werden angepasst.

- [ ] Tests:
  - `test_wartepunkt_nennt_haltepunkt` (Mini-Graph mit `fragen`)
  - `test_wartende_laeufe_ueber_stufen` (je ein Thread mit Stufe 3 und Stufe 4 wartet, beide gefunden)
  - bestehende `test_speicher.py` angepasst und grün
- [ ] FAIL, Implement, PASS. **Commit.**

### Task 4: Graph S4 (Planungsphase)

**Files:** Create `entwicklung/graph_s4.py`, `tests/test_graph_s4.py`; Modify `entwicklung/graph.py`
(`Abhaengigkeiten` um `planer = claude_strukturiert`, `planer_codex = codex_strukturiert`)

**Interfaces:**
- `baue_graph_s4(abh=None, checkpointer=None)`. Ablauf:

  ```
  vorbereiten → klaeren ─(Fragen, klaer_runde < MAX)→ fragen ⏸ → klaeren
                        └(klar oder MAX erreicht)→ spec_schreiben → akzeptanz_schreiben ⇄ (pruefe_akzeptanz, Probe)
  → Send: pruefen_spec_claude | pruefen_spec_codex → spec_freigabe ⏸
       freigeben → umsetzung_starten → implementieren … (Stufe 3 unverändert)
       aendern   → spec_schreiben (Hinweis + Prüfpunkte, spec_runde + 1)
       abbrechen → bericht
  ```
- `vorbereiten` wie bisher, setzt dazu `wunsch` = Aufgabendatei, `klaer_runde 0`, `spec_runde 0`, `akz_versuch 0`.
  Die Akzeptanzordner sind nur A1…A(n−1).
- Jeder Planungsknoten ruft danach `_planung_sauber(state)` auf (Worktree unverändert, geschützte Repos sauber).
  Verstoß: `status grenzverletzung` → `bericht`. Ein gescheiterter Agent (`ok False`) ergibt `status agent_fehler`
  → `bericht`.
- `akzeptanz_schreiben`:
  - Agent aufrufen, dann `pruefe_akzeptanz`
  - bei Fehlern: `akz_versuch + 1`, Gründe merken, erneut (höchstens `AKZ_VERSUCHE`), sonst `akzeptanz_fehler`
  - sonst `lege_ab` und Probe mit `abh.tests(worktree, konfig, [akz_ordner])`
  - die Probe verlangt `akzeptanz.gesammelt == erwartet > 0` und `bestanden < erwartet`; sonst zählt sie als
    Fehlversuch mit Grund
  - grün gegen main gebliebene Tests stehen in `akz_probe.gruen_gegen_main` (aus der JUnit-Auswertung, Ruling
    erlaubt: nur die Zahl, falls Namen nicht ohne Umbau zu haben sind)
- `spec_freigabe`: `interrupt({"art": "spec_freigabe", "spec_pfad", "akz_ordner", "annahmen",
  "tests": [Testnamen], "probe", "pruefpunkte", "hinweis"})`.
  - Die Prüfpunkte der Spec-Prüfer lösen **keine** automatische Überarbeitung aus. Sie stehen in der Freigabe, und
    Dominic entscheidet (`aendern` gibt sie mit seinem Hinweis an den Spec-Schreiber).
  - Begründung: Eine Schleife ohne Menschen hatten wir in Stufe 3. Hier soll der Mensch die Spec verantworten.
- `umsetzung_starten`: `aufgabe_text = spec`, `akzeptanz_dirs = A1…A(n−1) + [akz_ordner]`, `runde 0`,
  `max_runden`. → `implementieren`.

- [ ] Tests mit Fakes (Planer liefert je `name` eine Antwortliste; Implementierer, Prüfer wie in S3):
  - `test_klar_ohne_fragen_bis_freigabe` (`next == ("spec_freigabe",)`, Spec-Datei liegt unter berichte)
  - `test_fragen_schleife` (zwei Fragerunden, Antworten im Spec-Prompt)
  - `test_max_klaerungen_dann_spec`
  - `test_leere_antwort_haelt_erneut` (an `fragen` und an `spec_freigabe`, inklusive `aendern` ohne Hinweis)
  - `test_freigeben_dann_umsetzung_gruen` (Implementierer-Prompt enthält die Spec, aber keinen Testcode; erzeugte
    Tests im Testlauf; Regression A1…A(n−1))
  - `test_aendern_schreibt_spec_neu` (Hinweis im Prompt, `spec_pruefungen` frisch)
  - `test_import_auf_modulebene_zweiter_versuch_dann_fehler` (Status `akzeptanz_fehler`)
  - `test_probe_gegen_main_gruen_zaehlt_als_fehlversuch`
  - `test_planer_schreibt_ist_grenzverletzung` (Fake schreibt in den Worktree; kein Implementierer-Aufruf)
  - `test_abbrechen_an_fragen_und_freigabe`
  - `test_keine_akzeptanzdatei_im_worktree_vor_testlauf`
- [ ] FAIL, Implement, PASS. **Commit.**

### Task 5: CLI und Bericht

**Files:** Modify `entwicklung/cli.py`, `entwicklung/bericht.py`, `HOW-TO-USE.md`; Tests in `tests/test_cli_s4.py`

**Interfaces:**
- `lauf … --stufe 1|2|3|4`, Standard jetzt 4 (Hinweis in HOW-TO-USE: A1–A3 sind Verträge mit eigenen Tests; für
  sie `--stufe 3`).
- `fortsetzen [--entscheidung weiter|annehmen|abbrechen|freigeben|aendern] [--antwort TEXT] [--hinweis TEXT]
  [--thread ID] [--live]`:
  - Die CLI liest den Wartepunkt des Laufs und prüft, ob die Angaben dazu passen.
  - Passen sie nicht, meldet sie die erlaubten Angaben für diesen Wartepunkt mit Exit 1, ohne `Command`.
  - Der Graph wird nach `metadata.stufe` des Threads gebaut.
- Anzeige bei Halt (`_zeige_halt`, je Art):
  - Fragen: nummeriert
  - Freigabe: Pfad der Spec, Annahmen, Testnamen, Probe („x von y rot gegen main; grün: …“), Prüfpunkte
  - Eskalation wie bisher
  - Dazu immer der passende Fortsetzungsbefehl
- Bericht: Abschnitte „Klärung“ (Fragen und Antworten), „Spec“ (Pfad, Runden, Annahmen), „Akzeptanztests aus der
  Spec“ (Pfad, Versuche, Probe), „Spec-Prüfung“. `SYMBOL["akzeptanz_fehler"] = "⚠"`. JSON um die neuen Felder.

- [ ] Tests:
  - `test_lauf_s4_haelt_an_fragen_exit_3`
  - `test_fortsetzen_antwort_dann_freigabe`
  - `test_fortsetzen_falsche_angabe_fuer_wartepunkt` (`--antwort` an der Freigabe; `--entscheidung freigeben` an
    den Fragen)
  - `test_fortsetzen_stufe_3_lauf_weiter_moeglich`
  - `test_bericht_s4_abschnitte`
- [ ] FAIL, Implement, PASS, `sqlite-schema-guard`, ganze Suite. **Commit.**

### Task 6: Wunsch A4, Live, Lernnotiz, Codex, Gate

- [ ] **Step 1:** `aufgaben/portwart/A4.md` als Wunsch in 4 bis 6 Sätzen, **ohne** Vertrag und ohne Testordner.
  Inhalt: Projektordner nur lesend nach Port-Angaben durchsuchen (z. B. `--port 8766`, `PORT=8766`, `:8766`,
  `port = 8766`) und mit `ports.toml` vergleichen. Gemeldet werden Ports, die im Code stehen, aber nicht in der Liste,
  und eingetragene Projekte, deren Code einen anderen Port nennt. Dateiarten, Kommentare, Ausgabeformat und
  Exit-Codes bleiben bewusst offen, damit `klaeren` echte Fragen hat. **Commit.**
- [ ] **Step 2:** `lauf --repo portwart --aufgabe A4 --live`. Die Fragen und die Spec-Freigabe beantwortet
  **Dominic** mit `fortsetzen`, ich zeige ihm die Befehle. Danach läuft die Umsetzung mit Fix-Schleife. Gemergt
  wird erst nach dem Gate.
- [ ] **Step 3:** Lernnotiz `docs/lernpfad/04-klaeren-spec.md`. Inhalt:
  - mehrere Haltepunkte in einem Lauf, und wie `fortsetzen` den richtigen erkennt
  - Fragen-Schleife mit dem Menschen
  - warum Planungsagenten nur JSON liefern und Code die Dateien schreibt
  - die Sicherungen der erzeugten Tests: Prüfung per `ast`, Probe rot gegen main, Prüfer, Freigabe
  - was im echten Lauf gefragt und gefunden wurde
- [ ] **Step 4:** Codex-Verifier (`high`) über den Stufen-Diff, Befunde per TDD, Ledger nach `docs/`.
  **STUFEN-GATE.**
