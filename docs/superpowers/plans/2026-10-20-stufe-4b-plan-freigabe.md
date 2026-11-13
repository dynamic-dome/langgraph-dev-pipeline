# Lab 2 · Stufe 4b (Plan, Plan-Prüfung, Plan-Freigabe; Tests nachbessern) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Nach der Spec-Freigabe schreibt ein Agent einen Umsetzungsplan. Code und Codex prüfen ihn gegen die Spec,
Dominic gibt ihn frei, und der Implementierer bekommt Spec und Plan. An der Spec-Freigabe kommt ein dritter Weg
dazu: **nur die Tests nachbessern**. Dabei bleibt die Spec, wie sie ist, und der Test-Schreiber bekommt Dominics
Hinweis und seine vorige Fassung.

**Architecture:**
- `baue_graph_s4` wird erweitert (kein eigener Bauplan für 4a). `--stufe 4` meint danach die Pipeline mit
  Plan-Phase.
- Neuer Haltepunkt `plan_freigabe` nach dem Muster der anderen.
- Der Plan-Schreiber liefert JSON wie alle Planungsagenten. Code legt den Plan als `berichte/<lauf>/plan.md` ab und
  prüft ihn deterministisch (`pruefe_plan`). Codex prüft ihn inhaltlich.

**Tech Stack:** wie Stufe 4a.

**Spec:** `docs/specs/2026-10-19-entwicklungs-pipeline-design.md`. Maßgeblich sind:
- Ziel-Ablauf: `plan_schreiben → plan_pruefen (gegen Spec und Anforderungen) → plan_freigabe ⏸`
- „Freigaben immer per interrupt“
- Gate 4a (20.10.): weiter mit 4b, dazu der Weg „nur Tests nachbessern“, Übungsaufgabe A5

## Global Constraints

- Alle Regeln aus Stufe 1 bis 4a gelten weiter.
- Plan-Schreiber und Plan-Prüfer lesen nur (`strukturiert.py`), danach `_sauber`.
- Der Plan-Prüfer ist **Codex allein** (`-s read-only`, `high`). Die Spec hatte zwei Prüfer, der Plan bekommt einen,
  weil Code die Abdeckung schon deterministisch prüft.
- `pruefe_plan` liefert Gründe, sie **blockieren nicht**. Sie stehen in der Plan-Freigabe als Punkte „Code“ neben
  denen von Codex. Dominic entscheidet.
- Antworten:

  | Haltepunkt | gültige Antwort |
  |---|---|
  | `spec_freigabe` | wie bisher, dazu `{"entscheidung": "tests_nachbessern", "hinweis": "<nicht leer>"}` |
  | `plan_freigabe` | `{"entscheidung": "freigeben"}`, `{"entscheidung": "aendern", "hinweis": "<nicht leer>"}`, `{"entscheidung": "abbrechen"}` |

  Alles andere hält erneut an.
- Der Implementierer bekommt als `aufgabe_text` die Spec, dann `## Plan` und den Plan. Testcode bekommt er nie.
- Regression: Nach einem Merge gehören die erzeugten Tests nach `aufgaben/<repo>/<id>/`, sonst laufen sie bei
  späteren Aufgaben nicht mit. In Stufe 4b macht das ein Task von Hand für A4; automatisch wird es in Stufe 7
  (Abschluss).

## Review Focus

1. **`tests_nachbessern` ohne Hinweis oder an der Plan-Freigabe:** Der Lauf hält erneut an, oder die CLI nennt das
   Erlaubte mit Exit 3. Tests in Task 2 und 3.
2. **`aendern` an der Plan-Freigabe** schreibt nur den Plan neu. Spec, Tests und Probe bleiben, und die
   Plan-Prüfungen sind frisch. Test in Task 2.
3. **`tests_nachbessern`** lässt Spec und `spec_runde` unverändert. Der Test-Schreiber sieht Hinweis und vorige
   Fassung, die Spec-Prüfung läuft neu, und die Freigabe kommt wieder. Test in Task 2.
4. **Der Plan nennt Dateien außerhalb des Rahmens** (`ports.toml`, `tests/_akzeptanz/…`, `..`, absolut) oder lässt
   eine Schnittstelle der Spec aus: Der Grund steht in der Freigabe. Test in Task 1.
5. **Fix-Runden** bekommen Spec und Plan, ohne Testcode aus den Dateien. Test in Task 2.

---

### Task 1: Planungsbausteine für den Plan

**Files:** Modify `entwicklung/planung.py`; Tests in `tests/test_planung.py`

**Interfaces:**
- `PLAN_SCHEMA = _objekt(plan=_TEXT, dateien=_liste(_TEXT))`. `dateien` sind die Pfade, die der Plan anlegen oder
  ändern will, relativ zum Repo.
- `plan_prompt(spec, schnittstellen, aenderung: str | None, voriger_plan: str | None, pruefpunkte: list) -> str`.
  Der Plan ist Markdown:
  - je Schritt eine Überschrift mit Dateien, Test zuerst (TDD), dann Umsetzung
  - jede Schnittstelle der Spec kommt vor
  - nichts außerhalb des Rahmens der Spec
- `plan_pruef_prompt(spec, plan, dateien) -> str`. Fragen: Deckt der Plan jeden Teil des Vertrags ab? Hält er den
  Rahmen ein? Würde ein Implementierer, der ihm folgt, die Spec erfüllen? Schema `SPEC_PRUEF_SCHEMA`.
- `pruefe_plan(plan: str, dateien: list[str], schnittstellen: list[dict]) -> list[str]`. Gründe:
  - leerer Plan
  - Name einer Schnittstelle kommt im Plan nicht vor (`modul` als letzter Teil oder Pfad `portwart/drift.py`, jeder
    Name als Wort)
  - Datei absolut, mit `..`, unter `tests/_akzeptanz/`, oder `ports.toml`
- `akzeptanz_prompt(spec, schnittstellen, aufgabe_id, gruende, vorige: dict[str, str] | None = None,
  hinweis: str | None = None)`: vorige Fassung und Hinweis als eigene Abschnitte, mit Vorrang für den Hinweis.
- `lege_plan_ab(ordner: Path, plan: str) -> Path` schreibt `plan.md` über `pruefe_schreibziel`.

- [ ] Tests:
  - `test_pruefe_plan_ok`
  - `test_plan_ohne_schnittstelle`
  - `test_plan_dateien_ausserhalb_des_rahmens` (parametrisiert: `ports.toml`, `tests/_akzeptanz/x.py`,
    `../x.py`, `C:/x.py`)
  - `test_plan_prompts` (Änderung, voriger Plan, Prüfpunkte, Schnittstellen enthalten)
  - `test_akzeptanz_prompt_nachbessern` (vorige Fassung und Hinweis enthalten)
  - `test_plan_schema_streng` (in den bestehenden Parametrisierungen ergänzen)
- [ ] FAIL, Implement, PASS. **Commit.**

### Task 2: Graph mit Plan-Phase und Tests nachbessern

**Files:** Modify `entwicklung/graph_s4.py`, `entwicklung/state.py`, `entwicklung/speicher.py`;
Tests in `tests/test_graph_s4.py`, `tests/test_speicher.py`

**Interfaces:**
- `speicher.WARTEPUNKTE` um `"plan_freigabe"` erweitern.
- State neu: `plan: str`, `plan_dateien: list[str]`, `plan_runde: int`, `plan_aenderung: str | None`,
  `plan_gruende: list[str]`, `plan_pruefungen: Annotated[list[dict], sammeln_oder_leeren]`,
  `plan_freigabe: str | None`, `akz_hinweis: str | None`.
- Ablauf:

  ```
  … spec_freigabe ⏸ ─ freigeben         → plan_schreiben → plan_pruefen (Codex) → plan_freigabe ⏸
                     ─ tests_nachbessern → akzeptanz_schreiben (Hinweis + vorige Fassung) → … → spec_freigabe
  plan_freigabe ⏸ ─ freigeben → umsetzung_starten → implementieren …
                  ─ aendern   → plan_schreiben (Hinweis + Prüfpunkte, plan_runde + 1)
                  ─ abbrechen → bericht
  ```
- `plan_schreiben`:
  - Agent aufrufen (Name `plan_schreiben`)
  - `pruefe_plan`, Ergebnis nach `plan_gruende`
  - `lege_plan_ab`
  - `plan_pruefungen: LEEREN`
- `plan_pruefen`: Codex mit dem Namen `plan_codex`, dann `_sauber`. Ergebnis in `plan_pruefungen`.
- `plan_freigabe`:
  - `interrupt({"art": "plan_freigabe", "plan_pfad", "dateien", "pruefpunkte": Code-Gründe als `{"pruefer": "code",
    "schwere": "major"}` + Codex-Punkte, "plan_runde", "hinweis"})`
  - setzt `plan_freigabe`
- `umsetzung_starten`: `aufgabe_text = spec + "\n\n## Plan\n\n" + plan`.
- `spec_freigabe` mit `tests_nachbessern`:
  - setzt `akz_hinweis` und `akz_versuch 0`
  - leert `spec_pruefungen`
  - `spec_runde` bleibt
  - → `akzeptanz_schreiben`. Dort gehen Hinweis und `akz_dateien` als vorige Fassung in den Prompt.

- [ ] Tests (bestehende S4-Tests, die freigeben, gehen künftig über die Plan-Freigabe. Ein Helfer
  `_bis_umsetzung(graph)` gibt Spec und Plan frei):
  - `test_spec_freigeben_dann_plan_freigabe` (`next == ("plan_freigabe",)`, `plan.md` liegt unter berichte,
    Codex-Prüfung da)
  - `test_plan_freigeben_dann_umsetzung` (Implementierer-Prompt enthält Spec und Plan, kein Testcode)
  - `test_plan_aendern_nur_plan_neu` (Spec-, Test- und Probe-Felder unverändert, `plan_runde 1`, Hinweis im Prompt)
  - `test_plan_gruende_in_der_freigabe` (Plan ohne Schnittstelle: Punkt „code“ in der Freigabe, kein Abbruch)
  - `test_tests_nachbessern` (Spec und `spec_runde` gleich, Hinweis und vorige Fassung im zweiten Test-Prompt,
    `spec_pruefungen` frisch, wieder an `spec_freigabe`)
  - `test_ungueltig_an_plan_freigabe_haelt_erneut` (parametrisiert: `{}`, `aendern` ohne Hinweis,
    `tests_nachbessern`)
  - `test_fix_prompt_enthaelt_plan`
  - `test_abbrechen_an_plan_freigabe`
  - `test_wartepunkt_plan_freigabe` in `test_speicher.py`
- [ ] FAIL, Implement, PASS. **Commit.**

### Task 3: CLI und Bericht

**Files:** Modify `entwicklung/cli.py`, `entwicklung/bericht.py`, `HOW-TO-USE.md`; Tests in `tests/test_cli_s4.py`

**Interfaces:**
- `--entscheidung` kennt zusätzlich `tests_nachbessern`.
- `_antwort_fuer`:
  - an `spec_freigabe`: `tests_nachbessern` nur mit `--hinweis`
  - an `plan_freigabe`: `freigeben`, `abbrechen` oder `aendern` mit `--hinweis`
  - sonst die erlaubten Angaben mit Exit 3
- `ERLAUBT["plan_freigabe"]`, und `ERLAUBT["spec_freigabe"]` um die Zeile `tests_nachbessern` erweitert.
- `_zeige_halt` für die Plan-Freigabe: Pfad von `plan.md`, geplante Dateien, Punkte (Code und Codex), Runde.
- `_detail` für `plan_schreiben` („Plan · N Dateien · M Gründe“), `plan_pruefen`, `plan_freigabe`.
- Bericht: Abschnitt „Plan“ (Pfad, Runden, Dateien, Punkte, Freigabe). JSON um die Plan-Felder.

- [ ] Tests:
  - `test_fortsetzen_bis_plan_freigabe_und_umsetzung`
  - `test_tests_nachbessern_ueber_cli` (ohne Hinweis Exit 3, mit Hinweis wieder Spec-Freigabe)
  - `test_falsche_angabe_an_plan_freigabe`
  - `test_live_zeigt_plan_phase`
  - `test_bericht_mit_plan`
- [ ] FAIL, Implement, PASS, `sqlite-schema-guard`, ganze Suite. **Commit.**

### Task 4: A4-Tests in die Regression, Wunsch A5

**Files:** Create `aufgaben/portwart/A4/test_akzeptanz_a4.py`, `aufgaben/portwart/A5.md`

- [ ] **Step 1:** `berichte/20261020-120157/akzeptanz/A4/test_akzeptanz_a4.py` nach `aufgaben/portwart/A4/`
  kopieren.
  - Ausnahme: `test_durchsuche_symlink_auf_ordner_nicht_verfolgt` braucht einen echten Ordner-Symlink und springt
    hier aus. Ohne Wissen, wie die Umsetzung Symlinks erkennt, lässt er sich nicht simulieren.
  - Ich streiche ihn deshalb, mit Vermerk im Kopf der Datei und im Ledger.
  - Ein übersprungener Test in der Regression würde jede spätere Aufgabe rot machen (Funktionsprüfung).
- [ ] **Step 2:** Prüfen, dass die Datei gegen `portwart/main` grün ist (alle Tests, 0 übersprungen) und A1 bis A3
  grün bleiben.
- [ ] **Step 3:** `aufgaben/portwart/A5.md` als Wunsch in 4 bis 6 Sätzen:
  - Jeder Eintrag in `ports.toml` darf einen Pfad zu seinem Projektordner haben.
  - `drift` nutzt diesen Pfad, statt den Ordnernamen unter einer Wurzel zu suchen.
  - Bestehende Listen ohne Pfad gelten weiter.
  - Bewusst offen bleiben: relativ wozu, Pflicht oder nicht, was `pruefen` mit doppelten Pfaden macht, ob WURZEL
    optional wird.
- [ ] **Commit.**

### Task 5: Live A5, Lernnotiz, Codex, Gate

- [ ] **Step 1:** `lauf --repo portwart --aufgabe A5 --live`. Fragen, Spec- und Plan-Freigabe beantwortet Dominic;
  ich lese Spec, Tests und Plan vorher und gebe ihm meine Einschätzung. Gemergt wird erst nach dem Gate.
- [ ] **Step 2:** Lernnotiz `docs/lernpfad/04b-plan-freigabe.md`. Inhalt:
  - vier Haltepunkte und wie die Antworten zum richtigen gelangen
  - Freigabe als Weiche mit drei oder vier Wegen
  - deterministische Plan-Prüfung neben der Modellprüfung
  - warum erzeugte Tests in die Regression gehören
  - was der echte Lauf zeigte
- [ ] **Step 3:** Codex-Verifier (`high`) über den Stufen-Diff, Befunde per TDD, Ledger nach `docs/`.
  **STUFEN-GATE.**
