# Lab 2 · Stufe 6c (Konvergenzlogik der Spec-Runden) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Ab der zweiten Fassung prüfen die Spec-Prüfer gegen die Vorfassung (Diff + alte Punkte) statt von null.
Jeder neue Punkt trägt eine Herkunft, jeder alte einen Status. Ein deterministischer Schritt im Graphen teilt die Punkte
in „lösen eine neue Runde aus“ und „Liste für Dominic“. Nur die erste Gruppe geht an den Spec-Schreiber und
an die Empfehlung der Berater. Der Schreiber prüft bei „ändern“ die ganze Spec gegen die Antworten und baut keine
neuen Sonderregeln an. Je Fassung sind Größe, Annahmen und Tests sichtbar.

**Architecture:**
- **Neues Modul `entwicklung/konvergenz.py`** (reine Funktionen, keine Agenten): Schema der Nachprüfung, Diff,
  Einordnung, Verlaufszeile. Der Graph ruft es auf, die Oberflächen zeigen sein Ergebnis.
- **Nachprüfung** = jede Spec-Prüfung, für die `vorige_fassung` im State steht (nach „ändern“ und nach „Tests
  nachbessern“). Die erste Prüfung bleibt wie bisher (`SPEC_PRUEF_K_SCHEMA`, alle Major lösen aus).
- **Herkunft neuer Punkte:** `aenderung` (durch die letzte Änderung entstanden), `widerspruch` (widerspricht Wunsch
  oder Antworten), `sonstiges` (stand so schon in der Vorfassung). **Status alter Punkte:** `geloest`, `teilweise`,
  `offen`.
- **Regel (`ausloesend`):** neuer Punkt `major` mit Herkunft `aenderung`, `widerspruch` oder unbekannt; alter Punkt
  mit Vorfassung-Schwere `major` und Status `teilweise` oder `offen` (schlechtester Status über die verwertbaren
  Prüfer, fehlende Bewertung = `offen`). Alles andere geht in die `liste`.
- **Codex-Sperre aus 6b-1 bleibt vollständig:** Jeder Codex-Major (auch `sonstiges`) und jeder alte Codex-Punkt, den
  Codex als nicht gelöst meldet, ist ein Einwand. Die Regel steuert Runden, nicht die Sperre.

**Tech Stack:** wie 6b-2 (Python 3.12, LangGraph, SqliteSaver, FastAPI-Leitstand, `difflib` aus der Standardbibliothek).

**Spec:** `docs/specs/2026-10-19-entwicklungs-pipeline-design.md` (Spec-Review-Schleife, Freigaben) und mein
Auftrag zur Konvergenzlogik (drei Bausteine, Akzeptanzkriterien). Entscheide Dominic 21.10.:
- 6c freigegeben, mit vierter Herkunft „alt, nicht gelöst“ (hier: Status alter Punkte).
- Abnahme mit neuer Aufgabe A9 (Untertabellen beim Austragen), nicht mit einer Wiederholung von A8.

**Abweichungen vom Auftrag (bitte bestätigen):**
- Die Regel gilt **ab der ersten Nachprüfung** (Fassung 2), nicht erst ab „Runde 2“. Erst ab dort gibt es eine
  Vorfassung, gegen die man die Herkunft bestimmen kann.
- Nur Spec-Runden. Die Plan-Runden waren in A8 schon nach einem Durchgang durch (5 Aufrufe). Sie folgen nur, wenn eine
  Messung das verlangt.
- Der Spec-Schreiber bekommt ab jetzt nur noch auslösende Punkte, also keine `minor` mehr aus der ersten Prüfung.
  Grund: Jede lokale Korrektur hat in A8 neue Befunde erzeugt. Dein Hinweis bei „ändern“ kann trotzdem alles nennen.

## Global Constraints

- Python nur über `.venv\Scripts\python.exe` (3.12). Keine neue Abhängigkeit (`difflib` ist Standardbibliothek).
- Kein Fable außer den Beratern auf Klick; Implementierer nur über `claude -p`.
- Test-DB-Isolation wie bisher (conftest leitet data/berichte/arbeit auf `tmp_path` um). Vor der ganzen Suite und
  danach Bestand von `data/checkpoints.db` zählen (Ledger-Zeile wie in 6b-2).
- Ganze Suite nur einmal am Ende (dauert ~20 min, Arbeitsspeicher). Zwischendurch gezielte Testdateien.
- Kein Push, kein Merge ohne Dominic. Die A9-Abnahme startet Dominic (oder ich nach seinem ausdrücklichen Ja).
- Konstanten: `HERKUENFTE = ("aenderung", "widerspruch", "sonstiges")`, `STATUS = ("geloest", "teilweise", "offen")`,
  `DIFF_GRENZE = 30000` Zeichen je Diff (Spec, Tests getrennt), danach Zeile `… (Diff gekürzt, N Zeichen fehlen)`.
- Alte State-Schlüssel bleiben lesbar: Läufe ohne `vorige_fassung` verhalten sich wie in 6b-2.

## Review Focus

1. **Prüfer lässt ein altes Punkt-`nr` aus oder erfindet eins:** Fehlend zählt `offen`, unbekannte `nr` werden
   ignoriert. Kein Absturz, kein stilles „gelöst“ → `test_alter_punkt_ohne_bewertung_ist_offen`,
   `test_unbekannte_nr_wird_ignoriert` (Task 1).
2. **Prüfer liefert keine oder eine falsche Herkunft** (alter Prompt, Fake, Codex weicht ab): Ein Major ohne gültige
   Herkunft löst aus und wird nicht versteckt → `test_major_ohne_herkunft_loest_aus` (Task 1).
3. **Ein Prüfer ist nicht verwertbar** (`ok: False`): Er zählt weder für den Status noch als „fehlende Bewertung“,
   sonst wäre jeder alte Punkt `offen` → `test_nicht_verwertbarer_pruefer_zaehlt_nicht` (Task 1).
4. **„Tests nachbessern“ zwischen zwei Spec-Fassungen:** Die Nachprüfung vergleicht dann mit den vorigen Tests, die
   Spec-Diff ist leer, der Fassungszähler bleibt → `test_nachbessern_prueft_gegen_vorige_tests` (Task 2).
5. **Riesige Spec (A8: 21,7 KB) mit großem Diff:** Der Prompt bleibt begrenzt → `test_diff_wird_gekuerzt` (Task 1).

---

### Task 1: Modul `konvergenz` (Schema, Diff, Einordnung, Verlauf)

**Files:**
- Create: `entwicklung/konvergenz.py`
- Test: `tests/test_konvergenz.py`

**Interfaces:**
- Consumes: `planung._objekt`, `planung._liste`, `planung._TEXT`, `planung.SPEC_PRUEF_K_SCHEMA`
- Produces:
  - `NACHPRUEF_SCHEMA: dict`: wie `SPEC_PRUEF_K_SCHEMA`, aber jedes Element von `punkte` hat zusätzlich
    `herkunft` (enum `HERKUENFTE`), dazu `alte_punkte: [{nr: integer, status: enum STATUS, grund: string}]`. Streng
    (alle Felder Pflicht), weil Codex `--output-schema` das verlangt.
  - `diff_text(alt: str, neu: str, name: str) -> str`: `difflib.unified_diff` mit `fromfile=f"{name} (vorher)"`,
    `tofile=f"{name} (jetzt)"`, gekürzt auf `DIFF_GRENZE`; ohne Änderung genau `f"{name}: unverändert"`.
  - `nachpruef_text(vorige: dict, spec: str, tests: dict[str, str]) -> str`: Prompt-Abschnitt mit Diff der Spec,
    Diff je Testdatei (neue/entfallene Dateien gegen leeren Text), den alten Punkten als
    `{nr}. [{pruefer}, {schwere}] {aussage}` und dem Auftrag (siehe Step 3).
  - `einordnen(pruefungen: list[dict], vorige_punkte: list[dict] | None) -> dict` mit
    `{"ausloesend": [...], "liste": [...], "alte": [...]}`. Neue Punkte: `{pruefer, schwere, aussage, herkunft}`.
    Alte: `{nr, pruefer, schwere, aussage, status, bewertet: {pruefer: status}}`. `vorige_punkte is None` = erste
    Prüfung: alle Major lösen aus, Herkunft `"erstpruefung"`.
  - `nummeriert(punkte: list[dict]) -> list[dict]`: dieselben Punkte mit `nr` ab 1 (so werden sie zu `vorige_punkte`).
  - `verlauf_eintrag(spec_runde: int, nachgebessert: bool, spec: str, annahmen: list, tests: list[str],
    einordnung: dict) -> dict` = `{"fassung": spec_runde + 1, "nachgebessert", "zeichen": len(spec),
    "annahmen": len(annahmen), "tests": len(tests), "ausloesend": n, "liste": n}`.

- [ ] **Step 1: Failing tests schreiben** (`tests/test_konvergenz.py`, nur reine Funktionen, keine Agenten)

```python
A = {"pruefer": "claude", "ok": True}
ALT = [{"nr": 1, "pruefer": "codex", "schwere": "major", "aussage": "Reload fehlt"},
       {"nr": 2, "pruefer": "claude", "schwere": "minor", "aussage": "Meldung unklar"}]

def test_erste_pruefung_alle_major_loesen_aus():
    e = einordnen([{**A, "punkte": [{"schwere": "major", "aussage": "x"}, {"schwere": "minor", "aussage": "y"}]}], None)
    assert [p["aussage"] for p in e["ausloesend"]] == ["x"] and [p["aussage"] for p in e["liste"]] == ["y"]
    assert e["ausloesend"][0]["herkunft"] == "erstpruefung" and e["alte"] == []

def test_sonstiges_major_geht_in_die_liste():
    e = einordnen([{**A, "punkte": [{"schwere": "major", "aussage": "alt übersehen", "herkunft": "sonstiges"}],
                    "alte_punkte": []}], [])
    assert e["ausloesend"] == [] and e["liste"][0]["herkunft"] == "sonstiges"

def test_aenderung_und_widerspruch_loesen_aus(): ...   # je ein major, beide in ausloesend
def test_major_ohne_herkunft_loest_aus(): ...          # herkunft fehlt bzw. "quatsch" → ausloesend, herkunft "unbekannt"

def test_alter_major_teilweise_loest_aus():
    e = einordnen([{**A, "punkte": [], "alte_punkte": [{"nr": 1, "status": "teilweise", "grund": "nur Pfad A"},
                                                       {"nr": 2, "status": "offen", "grund": ""}]}], ALT)
    assert [p["nr"] for p in e["ausloesend"]] == [1]       # nr 2 ist minor → liste
    assert [p["nr"] for p in e["liste"]] == [2]

def test_schlechtester_status_gilt():
    claude = {**A, "punkte": [], "alte_punkte": [{"nr": 1, "status": "geloest", "grund": ""}]}
    codex = {"pruefer": "codex", "ok": True, "punkte": [], "alte_punkte": [{"nr": 1, "status": "offen", "grund": ""}]}
    alt = einordnen([claude, codex], ALT[:1])["alte"][0]
    assert alt["status"] == "offen" and alt["bewertet"] == {"claude": "geloest", "codex": "offen"}

def test_alter_punkt_ohne_bewertung_ist_offen(): ...   # alte_punkte=[] → nr 1 status "offen", ausloesend
def test_unbekannte_nr_wird_ignoriert(): ...           # nr 99 → kein Fehler, nicht in "alte"
def test_nicht_verwertbarer_pruefer_zaehlt_nicht():    # codex ok False, claude sagt geloest → status geloest
    ...
def test_alle_geloest_nichts_loest_aus(): ...

def test_diff_unveraendert():
    assert diff_text("a\n", "a\n", "spec") == "spec: unverändert"

def test_diff_wird_gekuerzt():
    d = diff_text("", "x" * 100 + "\n" * 40000, "spec")
    assert len(d) <= DIFF_GRENZE + 80 and "Diff gekürzt" in d

def test_nachpruef_text_nennt_alte_punkte_und_diffs():
    t = nachpruef_text({"spec": "a\n", "tests": {"t.py": "x = 1\n"}, "punkte": ALT}, "b\n", {"t.py": "x = 2\n"})
    assert "1. [codex, major] Reload fehlt" in t and "-a" in t and "+b" in t and "+x = 2" in t

def test_nachpruef_schema_streng():
    item = NACHPRUEF_SCHEMA["properties"]["punkte"]["items"]
    assert item["required"] == ["schwere", "aussage", "herkunft"]
    assert set(NACHPRUEF_SCHEMA["required"]) >= {"verdict", "punkte", "alte_punkte", "komplexitaet"}

def test_verlauf_eintrag(): ...   # fassung = spec_runde + 1, zeichen = len(spec), Zählwerte
```

- [ ] **Step 2: Rot sehen**

Run: `.venv\Scripts\python.exe -m pytest tests/test_konvergenz.py -q`
Expected: FAIL (`ModuleNotFoundError: entwicklung.konvergenz`)

- [ ] **Step 3: `entwicklung/konvergenz.py` schreiben**

Auftrag im `nachpruef_text` (wörtlich, das ist der Kern der Diff-Prüfung):

```text
## Nachprüfung (Vorfassung liegt vor)
Prüfe nicht von vorn. Beantworte zuerst für jeden alten Punkt in `alte_punkte`, ob er in der neuen Fassung
`geloest`, `teilweise` oder `offen` ist (`grund`: ein Satz). Melde danach in `punkte` nur, was neu ist, mit
`herkunft`: `aenderung`, wenn die Stelle im Diff oben steht oder von ihm abhängt; `widerspruch`, wenn die Spec
dem Wunsch oder einer Antwort von Dominic widerspricht; `sonstiges` für alles, was schon in der Vorfassung so stand.
```

`einordnen`: Status-Rangfolge `geloest < teilweise < offen`; nur Prüfungen mit `ok` zählen; ohne verwertbare Prüfung
bleibt jeder alte Punkt `offen`.

- [ ] **Step 4: Grün**

Run: `.venv\Scripts\python.exe -m pytest tests/test_konvergenz.py -q` → alle passed

- [ ] **Step 5: Commit**

```bash
git add entwicklung/konvergenz.py tests/test_konvergenz.py
git commit -m "feat: Modul konvergenz (Nachprüf-Schema, Diff, Einordnung, Verlauf)"
```

---

### Task 2: Graph nutzt die Nachprüfung (State, Knoten, Prompts)

**Files:**
- Modify: `entwicklung/state.py` (Planung-Block)
- Modify: `entwicklung/graph_s4.py` (`spec_schreiben`, `nach_akzeptanz`, `_spec_pruefung`, `spec_pruefung_sammeln`,
  `spec_freigabe`, `codex_einwaende`)
- Modify: `entwicklung/planung.py` (`spec_prompt`, `klaer_prompt`)
- Test: `tests/test_graph_s6c.py` (neu, Fixtures und `Planer` aus `tests/test_graph_s4.py` importieren)

**Interfaces:**
- Consumes: alles aus Task 1
- Produces (State, von Task 3 gelesen):
  - `vorige_fassung: dict | None` = `{"spec": str, "tests": dict[str, str], "punkte": list[dict]}` (nummeriert)
  - `spec_einordnung: dict` (Ergebnis von `einordnen`)
  - `spec_verlauf: Annotated[list[dict], operator.add]` (eine Zeile je Prüfung)
  - interrupt `spec_freigabe` zusätzlich: `"einordnung": spec_einordnung`, `"verlauf": spec_verlauf`,
    `"nachpruefung": bool`. `pruefpunkte` bleibt (alle neuen Punkte, jetzt mit `herkunft`).
  - `codex_einwaende(punkte, alte=None) -> list[str]`: zusätzlich je alter Punkt mit `pruefer == "codex"`,
    `schwere == "major"` und `bewertet["codex"] in ("teilweise", "offen")`:
    `f"Codex (GPT) meldet major weiter {status}: {aussage}"`.

- [ ] **Step 1: Failing tests schreiben** (`tests/test_graph_s6c.py`; Ablauf per `Planer`-Listen: erste Prüfung mit
  Major → `aendern` → zweite Prüfung im `NACHPRUEF_SCHEMA`-Format)

  - `test_erste_pruefung_unveraendert`: ohne Vorfassung bekommt `spec_pruefer` kein „Nachprüfung“ im Prompt, das
    interrupt hat `nachpruefung is False` und `einordnung["ausloesend"]` = die Major.
  - `test_nachpruefung_nach_aendern`: nach `aendern` enthält der zweite `spec_pruefer`- und `spec_codex`-Prompt
    „## Nachprüfung“, den Spec-Diff und „1. [codex, major] …“; interrupt `nachpruefung is True`,
    `verlauf` hat 2 Zeilen mit `fassung` 1 und 2.
  - `test_schreiber_bekommt_nur_ausloesende`: zweite Prüfung meldet einen `aenderung`-Major und einen
    `sonstiges`-Major. Nach erneutem `aendern` steht im dritten `spec_schreiben`-Prompt nur der `aenderung`-Punkt.
  - `test_alter_codex_punkt_offen_bleibt_einwand`: Codex meldet Punkt 1 `offen` → `freigeben` ohne `begruendung`
    wird abgewiesen (`halt_hinweis` enthält „meldet major weiter offen“).
  - `test_sonstiges_codex_major_bleibt_einwand`: die Sperre aus 6b-1 gilt auch für `sonstiges`.
  - `test_nachbessern_prueft_gegen_vorige_tests`: `tests_nachbessern` → Prüfprompt enthält „spec: unverändert“ und
    einen Test-Diff; `verlauf[-1]["nachgebessert"] is True`, `fassung` bleibt 1.
  - `test_alter_lauf_ohne_vorige_fassung`: State ohne die neuen Schlüssel (wie 6b-2) läuft bis `spec_freigabe`
    ohne KeyError.
  - `test_spec_prompt_bremse`: `spec_prompt(..., vorige_spec="x", ...)` enthält „Gesamtsicht“ und „keine neue
    Sonderregel“; ohne Vorfassung steht die Ablehnungs-Regel für Grenzfälle trotzdem drin.

- [ ] **Step 2: Rot sehen**

Run: `.venv\Scripts\python.exe -m pytest tests/test_graph_s6c.py -q` → FAIL

- [ ] **Step 3: Umsetzen**

  - `spec_schreiben` (bei `neu`): `vorige_fassung = {"spec": state["spec"], "tests": {Name: Inhalt der akz_dateien},
    "punkte": nummeriert(state["spec_einordnung"]["ausloesend"])}`. Dieselbe Liste `ausloesend` geht als
    `pruefpunkte` in `spec_prompt`. Fehlt `spec_einordnung` (alter Lauf), gilt `pruefpunkte(...)` wie bisher.
  - `spec_freigabe` bei `tests_nachbessern`: `vorige_fassung` genauso setzen (Spec gleich, Tests alt).
  - `nach_akzeptanz`: mit `vorige_fassung` hängt `nachpruef_text(...)` an `spec_pruef_prompt` an, im `auftrag`
    `"nachpruefung": True`; `_spec_pruefung` nimmt dann `NACHPRUEF_SCHEMA`, sonst `SPEC_PRUEF_K_SCHEMA`, und reicht
    `alte_punkte` in den Prüfbericht durch.
  - `spec_pruefung_sammeln`: nach `_sauber` `spec_einordnung = einordnen(state["spec_pruefungen"],
    vorige["punkte"] if vorige else None)` und eine `spec_verlauf`-Zeile (`nachgebessert = freigabe ==
    "tests_nachbessern"`). Hier und nicht in `spec_freigabe`: Dieser Knoten läuft je Prüfung genau einmal, das
    interrupt dagegen bei jeder ungültigen Antwort erneut.
  - `spec_prompt`: immer die Zeile „Grenzfälle, die nur mit einer Sonderregel lösbar wären, lehnst du mit klarer
    Meldung ab und nennst das in `annahmen`.“ Mit Vorfassung zusätzlich: „Gesamtsicht: Lies die ganze vorige Fassung
    gegen Wunsch und Antworten. Löse jeden Punkt bevorzugt durch Streichen, Vereinfachen oder Ablehnen, keine neue
    Sonderregel. Die Spec wird nur länger, wenn ein Punkt es verlangt.“
  - `klaer_prompt`: Voreinstellung bei Grenzfall-Fragen „ablehnen mit klarer Meldung“.

- [ ] **Step 4: Grün, Nachbarn prüfen**

Run: `.venv\Scripts\python.exe -m pytest tests/test_graph_s6c.py tests/test_graph_s4.py tests/test_planung.py tests/test_konvergenz.py -q`
Expected: alle passed (bestehende s4-Tests unverändert grün)

- [ ] **Step 5: Commit**

```bash
git add entwicklung/state.py entwicklung/graph_s4.py entwicklung/planung.py tests/test_graph_s6c.py
git commit -m "feat: Spec-Nachprüfung gegen die Vorfassung, Einordnung und Zuschnitt-Bremse im Graphen"
```

---

### Task 3: Oberflächen zeigen die Einordnung (CLI, Leitstand, Berater, Bericht)

**Files:**
- Modify: `entwicklung/cli.py` (Anzeige `spec_freigabe`)
- Modify: `entwicklung/leitstand/static/app.js` (Karte Spec-Freigabe), ggf. `entwicklung/leitstand/daten.py`
- Modify: `entwicklung/berater.py` (`_material` für `spec_freigabe`)
- Modify: `entwicklung/bericht.py` (Verlauf je Fassung)
- Modify: `docs/lernpfad/leitstand_demo.py` (Szenario mit zweiter Fassung)
- Test: `tests/test_cli_s4.py`, `tests/test_berater.py`, `tests/test_leitstand_daten.py`, Bericht-Test dort, wo
  `bericht.py` heute getestet wird

**Interfaces:**
- Consumes: interrupt-Felder `einordnung`, `verlauf`, `nachpruefung` und State `spec_verlauf` aus Task 2
- Produces: nichts für spätere Tasks

- [ ] **Step 1: Failing tests**

  - CLI: bei `nachpruefung` drei Blöcke „Lösen eine neue Runde aus:“, „Liste für dich (keine neue Runde nötig):“,
    „Alte Punkte:“ mit `[{status}] {aussage}`; dazu eine Zeile je Verlauf
    `Fassung {f}: {zeichen} Zeichen, {annahmen} Annahmen, {tests} Tests, {ausloesend} auslösend` (bei `nachgebessert`
    mit Zusatz „(Tests nachgebessert)“). Ohne `nachpruefung` Ausgabe wie bisher.
  - Berater: `berater_prompt("spec_freigabe", frage_mit_einordnung, werte)` enthält die beiden Gruppen und den Satz
    „Ab Fassung 2 empfiehlst du `aendern` nur, wenn ein Punkt unter „Lösen eine neue Runde aus“ echt ist. Die Liste
    allein ist kein Grund für eine neue Runde; nenne sie in `begruendung`.“ Ohne Einordnung bleibt der Prompt wie
    bisher (bestehender Test).
  - Bericht: Abschnitt „Spec-Verlauf“ mit denselben Zeilen wie die CLI.
  - Leitstand-Daten: `frage` reicht `einordnung` und `verlauf` unverändert durch (falls `daten._frage` filtert).

- [ ] **Step 2: Rot sehen** (die vier Testdateien gezielt)

- [ ] **Step 3: Umsetzen.** `app.js`: Karte „Spec-Freigabe“ zeigt bei `f.nachpruefung` statt einer `punkteListe`
  die drei Gruppen (Herkunft bzw. Status als Präfix) und den Verlauf als kleine Tabelle. Alle Texte über `el(..., {text})`
  (kein `innerHTML`, die Demo enthält einen XSS-Hinweistext).

- [ ] **Step 4: Grün** (die vier Testdateien) **und Browser-Prüfung**: `leitstand_demo.py --port 8795`, Lauf bis zur
  zweiten Spec-Freigabe; prüfen: drei Gruppen, Verlauf mit 2 Zeilen, Freigeben trotz Codex-Einwand verlangt
  Begründung. Port vorher prüfen, `127.0.0.1`, Demo danach beenden. Ergebnis als Ledger-Zeile.

- [ ] **Step 5: Commit**

```bash
git add entwicklung/cli.py entwicklung/leitstand/static/app.js entwicklung/berater.py entwicklung/bericht.py docs/lernpfad/leitstand_demo.py tests/...
git commit -m "feat: Einordnung der Spec-Punkte und Verlauf in CLI, Leitstand, Rat und Bericht"
```

---

### Task 4: Ganze Suite, A9, Abnahme, Lernnotiz

**Files:**
- Create: `aufgaben/portwart/A9.md`
- Create: `docs/lernpfad/06c-konvergenz.md`
- Modify: `docs/superpowers/plans/2026-10-21-stufe-6c-ledger.md` (beim Ausführen angelegt)

- [ ] **Step 1: Ganze Suite** mit Bestandszählung vorher/nachher (checkpoints, writes, berichte, arbeit, portwart
  `git status`). Run: `.venv\Scripts\python.exe -m pytest -q` → alle passed, keine Warnungen.

- [ ] **Step 2: A9-Wunsch schreiben und von Dominic bestätigen lassen** (Muster A8, nur der Wunsch, Tests entstehen
  aus der Spec). Entwurf:

```markdown
# A9: Austragen mit Untertabellen (Wunsch)

`portwart austragen <name>` entfernt heute nur die Kopfzeile `[[port]]` und ihre Schlüssel. Hat der Eintrag
Untertabellen (z. B. `[port.meta]` oder `[[port.sub]]`), bleiben sie stehen und hängen sich still an den Eintrag
davor. Ich möchte, dass der ganze Eintrag samt seinen Untertabellen verschwindet und alles andere bleibt, wie es ist.
Kann portwart nicht sicher erkennen, was zum Eintrag gehört, soll es ablehnen, mit einer klaren Meldung, statt zu raten.
```

- [ ] **Step 3: A9-Abnahme mit `auto`** (Dominic startet oder sagt ausdrücklich ja). Messen und in die Lernnotiz:
  Spec-Fassungen, Aufrufe gesamt und in der Spec-Phase, je Nachprüfung Anzahl `aenderung` / `widerspruch` /
  `sonstiges` / alte Punkte je Status, ob jede Prüfung gültige Herkunft-Labels geliefert hat, Spec-Zeichen je Fassung.
  Vergleich mit A8 (4 Fassungen, 29 Aufrufe, 21,7 KB). **Kriterium:** höchstens 2 Spec-Fassungen bis zur Freigabe
  UND Labels in jeder Nachprüfung vollständig. Ehrlich: Ein Lauf ist eine Stichprobe, keine Statistik. Merge nur
  mit Dominic.

- [ ] **Step 4: Lernnotiz `06c-konvergenz.md`** im Stil von 06b2: was gebaut, LangGraph-Lernstoff (warum die
  Einordnung im Fan-in-Knoten und nicht hinter dem interrupt sitzt; Regel im Graphen vs. Bitte im Prompt),
  Vorher/Nachher-Tabelle, „Selbst prüfen“ mit 3 Fragen.

- [ ] **Step 5: Codex-Verifier (high, read-only)** über den Stufen-Diff, Befunde an der Quelle prüfen, beheben,
  Ledger. Danach Gate durch Dominic.

```bash
git add aufgaben/portwart/A9.md docs/lernpfad/06c-konvergenz.md docs/superpowers/plans/2026-10-21-stufe-6c-ledger.md
git commit -m "docs: A9, Lernnotiz 6c und Ledger"
```
