# Lab 2 · Stufe 6b-2 (Modellstufen mit Reasoning, Kostenrahmen) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Eine Tabelle legt je Rolle und Komplexität Modell und Reasoning-Stufe fest. Die Komplexität schätzen beide
Modellfamilien (Claude-Spec-Schreiber und Codex-Spec-Prüfer), es gilt die höhere. Dominic kann sie an der
Plan-Freigabe ändern; sie ist der einzige Regler. Jeder Lauf hat einen Kostenrahmen in Agentenaufrufen und hält am
Haltepunkt `budget`, wenn er erreicht ist. Fable und Astra beraten auf derselben Reasoning-Stufe, und Astra bekommt
den bestehenden Code des Ziel-Repos.

**Architecture:**
- **Tabelle `STUFEN_TABELLE`** in `entwicklung/stufen.py` (neu):

  | Rolle | einfach | mittel | schwer |
  |---|---|---|---|
  | `implementierer` | sonnet · medium | sonnet · high | opus · high |
  | `pruefer` (Security, Clean Code) | opus · high | opus · high | opus · xhigh |
  | `codex` (Prüfer Umsetzung) | – · high | – · high | – · high |

  `stufe_fuer(rolle, komplexitaet) -> (modell | None, effort)`.
- **Vor der Schätzung feste Stufen** (`PLANUNG_STUFEN`): Klärer, Spec-Schreiber, Akzeptanz-Schreiber und Plan-Schreiber
  laufen auf sonnet · high, der Claude-Spec-Prüfer auf opus · high, Codex-Spec- und Plan-Prüfer auf high.
- **Schätzung durch beide Familien:** `SPEC_SCHEMA` bekommt `komplexitaet` und `komplexitaet_grund`, ebenso
  `SPEC_PRUEF_SCHEMA` (für beide Spec-Prüfer gleich; zählt wird die Codex-Schätzung). Der Knoten `stufe_waehlen`
  (Router) zwischen `spec_freigabe` und `plan_schreiben` setzt `komplexitaet = max(claude, codex)` nach
  `einfach < mittel < schwer` und merkt sich beide Werte. Fehlt die Codex-Schätzung (Codex gescheitert), gilt die
  Claude-Schätzung, versehen mit diesem Hinweis.
- **Bestätigung:** Die Plan-Freigabe zeigt beide Schätzungen, das Ergebnis und die Zeilen der Tabelle. Die Antwort
  darf `komplexitaet` mitbringen, `umsetzung_starten` übernimmt sie. Implementierer und Prüfer der Umsetzung und der
  Fix-Runden ziehen Modell und Effort aus der Tabelle.
- **haiku nur als Experiment:** Ein beim Start ausdrücklich gewähltes Implementierer-Modell (`--modell haiku` usw.)
  überschreibt die Spalte Modell des Implementierers, nicht den Effort. Der Standard heißt `auto`.
- **Kostenrahmen:** Jeder Knoten, der einen Agenten aufruft, meldet `aufrufe: <n>`. Der Additions-Reducer zählt auch
  die parallelen Send-Knoten richtig. Wächter-Knoten stehen vor `spec_schreiben`, `plan_schreiben` und
  `implementieren`. Bei `aufrufe >= budget` folgt ein interrupt `budget` mit `mehr` (+`BUDGET_SCHRITT`) oder
  `abbrechen`. Berater zählen nicht in den Rahmen, sie stehen getrennt im Bericht.
- **Berater:** `BERATER_EFFORT = "high"` für Fable (`--effort high`) und Astra (`model_reasoning_effort="high"`).
- **Astra-Kontext** und die Kleinigkeiten aus 6b-1 wie zuvor geplant.

**Tech Stack:** wie 6b-1.

**Spec:** `docs/specs/2026-10-19-entwicklungs-pipeline-design.md`, Stufe 6 (Router-Knoten, Budget im State;
Kostenrahmen in Agentenaufrufen). Entscheide Dominic vom 20.10.:
- Zuschnitt in drei Teile.
- Der Agent schätzt, Dominic bestätigt; geschätzt wird mit beiden Familien, es gilt die vorsichtigere Schätzung.
- Kostenrahmen in Aufrufen.
- Reasoning-Stufe je Rolle und Komplexität.
- sonnet implementiert, opus prüft.
- haiku nur als bewusstes Experiment.
- Fable bleibt Berater auf Klick.
- Die Komplexität ist der einzige Regler an der Plan-Freigabe.

## Global Constraints

- **Effort-Werte:** Claude `low | medium | high | xhigh | max` (laut `claude --help`), verwendet werden nur `medium`,
  `high` und `xhigh`. Codex bleibt auf `high`. Gemessen am 20.10.: codex-cli 0.163.0 nimmt auch den erfundenen Wert
  `ultra` ohne Fehler an, dass `xhigh` wirkt, ist also nicht belegt.
- **Timeouts:** opus · xhigh bekommt `PRUEFER_TIMEOUT_XHIGH = 1200` s statt 600, der Implementierer mit opus 900 s.
- **Modelle:** `MODELLE_START = ["auto", "haiku", "sonnet", "opus"]`, kein Fable. `KOMPLEXITAETEN = ("einfach",
  "mittel", "schwer")`.
- **Rahmen:** `BUDGET = 40` je Lauf, `BUDGET_SCHRITT = 20`. Gezählt werden Aufrufe von `implementierer`, `pruefer`,
  `codex`, `planer` und `planer_codex`, auch gescheiterte. `pruefen_funktion` zählt nicht.
- **Haltepunkt `budget`:** genau ein interrupt je Durchlauf, eine ungültige Antwort führt über die Kante zurück, im
  Leitstand an die `checkpoint_id` gebunden.
- **Alte Läufe:** Ohne `budget` gibt es keinen Rahmen. Ohne `komplexitaet` gilt `mittel`. Ohne `aufrufe` zählt der
  Lauf ab 0.
- Tests nur mit Fakes (alle Fakes nehmen `effort=None` an), Isolation wie bisher, vor pytest `sqlite-schema-guard`.
  Kein Commit in Lab 2 während eines echten Laufs.

## Review Focus

1. **Parallele Prüfer und der Reducer:** Die Summe der `aufrufe` stimmt (3 Agenten je Prüfrunde). Test in Task 2.
2. **`mehr` an `budget`, dann wieder erreicht:** Der Lauf hält erneut an. Test in Task 2.
3. **Eine ungültige `komplexitaet` in der Plan-Antwort** (`extrem`, `opus`) macht die Antwort ungültig, der Lauf
   wartet erneut. Test in Task 1.
4. **Uneinige Schätzungen** (Claude einfach, Codex schwer) ergeben schwer: opus · high für den Implementierer,
   opus · xhigh für die Prüfer. Die Uneinigkeit steht im Haltepunkt. Test in Task 1.
5. **Start mit `--modell haiku`:** Der Implementierer läuft auf haiku mit dem Effort der Tabelle, die Prüfer bleiben
   nach Tabelle. Test in Task 1.

---

### Task 1: Tabelle, Schätzung beider Familien, Router, Bestätigung, Effort für Implementierer und Prüfer

**Files:** Create `entwicklung/stufen.py`. Modify:
- `entwicklung/planung.py` (beide Schemas, `spec_prompt` und `spec_pruef_prompt`: je ein Satz zu den Stufen)
- `entwicklung/agenten.py` (Implementierer mit `effort`)
- `entwicklung/pruefer.py` (Prüfer mit `effort`, Timeout)
- `entwicklung/graph.py` (Implementierer und Prüfer lesen die Tabelle)
- `entwicklung/graph_s4.py` (`stufe_waehlen`, Plan-Freigabe, Planungsstufen)
- `entwicklung/state.py`, `entwicklung/steuerung.py`, `entwicklung/cli.py`, `entwicklung/leitstand/server.py`,
  `entwicklung/bericht.py`

Test `tests/test_stufen.py` (neu), `tests/test_graph_s4.py`, `tests/test_graph_s3.py`, `tests/test_steuerung.py`,
`tests/test_cli_s4.py`, `tests/test_agenten.py`, `tests/test_pruefer.py`.

**Interfaces (Produces):**
- `stufen.KOMPLEXITAETEN`, `STUFEN_TABELLE`, `PLANUNG_STUFEN`, `stufe_fuer(rolle, komplexitaet)`, `hoechste(*werte)`
  (`None` wird übergangen, ohne Wert gilt `mittel`).
- Die Stufe-3-Graphen (ohne Spec) nutzen `mittel`, ein Startmodell gilt wie bisher.
- `agenten.implementierer(..., effort=None)` und `pruefer.claude_pruefer(..., effort=None, timeout=...)` hängen
  `--effort` an, wenn gesetzt.
- State: `komplexitaet`, `komplexitaet_claude`, `komplexitaet_codex`, `komplexitaet_grund`, `aufrufe`, `budget`.
- `steuerung.antwort_fuer(..., komplexitaet=None)` ist nur an `plan_freigabe` mit `freigeben` erlaubt.
- CLI `lauf --modell auto|haiku|sonnet|opus` (Standard `auto`), `fortsetzen --komplexitaet`. Server `Start.modell`
  darf `auto` sein, `Antwort.komplexitaet`.
- Bericht: Abschnitt „Modellstufen“ mit Schätzung Claude und Codex, Ergebnis, ob Dominic sie geändert hat, und
  Modell plus Effort je Rolle.

- [ ] **Step 1: Failing tests**
  - `test_stufe_fuer_tabelle` (alle Zellen) und `test_hoechste`.
  - `test_router_nimmt_hoehere_schaetzung` (Review Focus 4): Claude einfach, Codex schwer ergibt schwer. Der
    Implementierer-Fake sieht `modell="opus", effort="high"`, die Prüfer-Fakes sehen `opus` und `xhigh`.
  - `test_router_ohne_codex_schaetzung`: Codex scheitert, es gilt Claudes Schätzung mit Hinweis.
  - `test_plan_freigabe_komplexitaet_aendern`: Mit `{"entscheidung": "freigeben", "komplexitaet": "einfach"}` läuft
    der Implementierer auf sonnet · medium.
  - `test_plan_freigabe_ungueltige_komplexitaet` (Review Focus 3).
  - `test_startmodell_haiku_nur_implementierer` (Review Focus 5).
  - `test_planung_feste_stufen`: Spec-Schreiber sonnet · high, Claude-Spec-Prüfer opus · high.
  - `test_implementierer_und_pruefer_effort_im_befehl` (Fake-Runner prüft `cmd`).
  - `test_cli_auto_und_fortsetzen_komplexitaet` und `test_bericht_modellstufen`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implementieren. Der Fake `SPEC` und die Fakes für die Spec-Prüfer in den
  Tests bekommen `komplexitaet: "mittel"`. **Step 4:** Die genannten Dateien → PASS; Suite grün.
- [ ] **Step 5:** Commit `feat: Modellstufen mit Reasoning – Tabelle, Schätzung beider Familien, Router`.

### Task 2: Kostenrahmen in Agentenaufrufen, Haltepunkt `budget`

**Files:** Modify `entwicklung/state.py` (`aufrufe: Annotated[int, operator.add]`), `entwicklung/graph.py`,
`entwicklung/graph_s4.py`, `entwicklung/speicher.py` (`WARTEPUNKTE` + `budget`), `entwicklung/steuerung.py`,
`entwicklung/cli.py`, `entwicklung/leitstand/daten.py`, `entwicklung/bericht.py`. Test `tests/test_graph_s4.py`,
`tests/test_graph_s3.py`, `tests/test_cli_s4.py`, `tests/test_steuerung.py`.

**Interfaces (Produces):**
- `graph.BUDGET` und `graph.BUDGET_SCHRITT`. `ERLAUBT_KURZ["budget"] = ["mehr", "abbrechen"]`.
- Wächter-Knoten `budget_spec`, `budget_plan` und `budget_umsetzung` teilen sich eine Funktion. Bei Halt folgt
  `interrupt({"art": "budget", "aufrufe", "budget", "naechster", "erlaubt", "hinweis"})`. `mehr` erhöht den
  Rahmen um `BUDGET_SCHRITT`, `abbrechen` setzt `status = "abgebrochen"` und führt zum Bericht. Unter dem Rahmen
  geht es mit `{}` weiter.
- `vorbereiten` übernimmt `budget` aus der Eingabe (Standard `BUDGET`). In Stufe 3 gibt es nur
  `budget_umsetzung`.
- CLI `lauf --budget N`, `fortsetzen --entscheidung mehr|abbrechen`. Bericht: „Agentenaufrufe: N von M; Berater: F×
  Fable, A× Astra“.

- [ ] **Step 1: Failing tests**
  - `test_aufrufe_zaehlen_parallel` (Review Focus 1): Ein grüner Lauf in Stufe 4 ergibt genau 11 (klären 1, Spec 1,
    Akzeptanz 1, Spec-Prüfer 2, Plan 1, Plan-Prüfung 1, Implementierer 1, Prüfer 3).
  - `test_budget_haelt_an_und_mehr` (Review Focus 2): `budget=11`, Fix-Runde nötig, also Halt vor der Fix-Runde.
    `BUDGET_SCHRITT` ist im Test auf 4 gesetzt. `mehr` hebt auf 15, eine Runde läuft (15), dann folgt ein erneuter
    Halt.
  - `test_budget_abbrechen_schreibt_bericht`.
  - `test_budget_ungueltige_antwort_haelt_erneut`.
  - `test_alter_lauf_ohne_budget_laeuft`.
  - `test_s3_budget_vor_implementieren`.
  - `test_cli_budget` und `test_bericht_aufrufe_und_berater`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implementieren. **Step 4:** PASS; Suite grün.
- [ ] **Step 5:** Commit `feat: Kostenrahmen in Agentenaufrufen mit Haltepunkt budget`.

### Task 3: Berater auf gleicher Reasoning-Stufe, Astra-Kontext, Kleinigkeiten aus 6b-1

**Files:** Modify `entwicklung/strukturiert.py` (`effort` in beiden Aufrufen; die Planungsagenten nutzen das auch
für `PLANUNG_STUFEN`), `entwicklung/berater.py`, `entwicklung/bericht.py` (`JSON_FELDER` + `einwand_freigaben`,
`aufrufe`, `budget`, `komplexitaet*`). Test `tests/test_strukturiert.py`, `tests/test_berater.py`,
`tests/test_cli_s4.py`.

**Interfaces (Produces):**
- `claude_strukturiert(..., effort=None)` gibt `--effort` weiter, `codex_strukturiert(..., effort="high")` setzt den
  Effort.
- `berater.BERATER_EFFORT = "high"`, an beide Berater weitergereicht.
- `quelldateien` hängt `git ls-files "*.py"` des Worktrees an (erst Code, dann `tests/`, nie `tests/_akzeptanz/`).
  Der Vermerk zählt in `MAX_QUELLEN` mit.

- [ ] **Step 1: Failing tests**
  - `test_claude_effort_im_befehl` und `test_codex_effort_im_befehl`.
  - `test_hole_rat_gleiche_stufe`.
  - `test_quelldateien_repo_code_an_rueckfragen`.
  - `test_quelldateien_grenze_mit_vermerk` (F-005).
  - `test_bericht_json_einwand_freigaben` (F-004).
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implementieren. **Step 4:** PASS; Suite grün.
- [ ] **Step 5:** Commit `feat: Berater auf gleicher Reasoning-Stufe, Astra sieht den Repo-Code; 6b-1-Kleinigkeiten`.

### Task 4: Oberfläche, Demo, Doku, Abnahme an A8

**Files:** Modify `entwicklung/leitstand/static/app.js` and `stil.css`, `docs/lernpfad/leitstand_demo.py`,
`HOW-TO-USE.md`. Create `docs/lernpfad/06b2-modellstufen-kosten.md` und `aufgaben/portwart/A8.md`.

**Was die Oberfläche bekommt:**
- Startformular: Modell `auto` als Standard, Feld „Rahmen (Aufrufe)“.
- Plan-Freigabe: Schätzung Claude und Codex, Ergebnis, Auswahl der Komplexität, Tabelle mit Modell und Effort je
  Rolle für die gewählte Stufe.
- Formular `budget`. Kopfzeile „Aufrufe N/M“.

**Was die Demo bekommt:** uneinige Fake-Schätzungen und einen kleinen Rahmen.

- [ ] **Step 1: Browser-Prüfung an der Demo (8795)**, mit Strg+F5:
  - Die Plan-Freigabe zeigt beide Schätzungen und die Uneinigkeit.
  - Ein Wechsel der Komplexität aktualisiert die Tabelle.
  - Das Freigeben schickt `komplexitaet`.
  - `budget` erscheint, „Mehr erlauben“ läuft weiter.
  - Agententext (Gründe) erscheint per `textContent`.

  Danach Testfenster schließen und Demo beenden.
- [ ] **Step 2:** Den A8-Wunsch schreiben: `portwart austragen <name>`. **Wortlaut bestätigt Dominic.**
- [ ] **Step 3: Abnahme.** Dominic startet A8 mit `auto`. Ich halte fest:
  - Schätzung Claude und Codex
  - Ergebnis und ob Dominic es geändert hat
  - Modell und Effort je Rolle
  - Aufrufe gegenüber dem Rahmen
  - Dauer und Ergebnis

  Danach Lernnotiz und Ledger, Codex-Verifier (high), Gate.
