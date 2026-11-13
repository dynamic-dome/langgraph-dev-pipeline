# Lab 2 · Stufe 6b-1 (Familien-Zweitmeinung) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Eine Gegenstimme aus der GPT-Familie kann nicht mehr still überstimmt werden. Dazu gehören vier Teile:
- Neben „Fable fragen“ gibt es **„Astra fragen“** (Codex) und **„Beide fragen“** mit der Anzeige einig/uneinig.
- Liegt ein **Einwand der anderen Familie** vor, gibt Freigeben nur mit einer Begründung frei, die im Bericht landet.
- Die Fix-Schleife **bricht früh ab**, wenn derselbe Befund in zwei Runden nacheinander auslöst.
- Fables Wissensblock lernt die Lehre aus A6.

**Architecture:**
- **Harte Sperre im Graphen:** Meldet der Codex-Prüfer an der Spec- oder Plan-Freigabe einen Punkt `major`, nimmt
  der Knoten `freigeben` nur mit `begruendung` an. Das braucht keinen Berater-Klick und hätte A6 abgefangen. Eine
  Sperre im Werkzeug ist eine Garantie, eine Regel in der Oberfläche nur eine Bitte (L71).
- **Sperre über die Räte:** Die Berater laufen außerhalb des Graphen. Ihre Einwände errechnet `berater.einwaende_fuer`
  aus den abgelegten Rat-Dateien des aktuellen Stands. Server und CLI prüfen sie mit derselben Regel
  (`steuerung.einwand_fehlt`) und geben Einwände und Begründung in der Antwort an den Graphen weiter. Dort landen sie
  im State (`einwand_freigaben`) und im Bericht.
- **Astra** ist `codex_strukturiert`: Standardmodell, `high`, read-only. Dazu derselbe Prompt und dasselbe Schema
  wie bei Fable. Codex kann hier keine Prozesse starten und also keine Dateien selbst lesen (`CreateProcessAsUserW`).
  Deshalb bettet der Prompt die relevanten Quelldateien aus dem Worktree ein.
- **Frühabbruch:** Jede Runde in `runden` merkt sich die Schlüssel ihrer auslösenden Befunde. Wiederholt sich ein
  Schlüssel in zwei Runden nacheinander, geht `nach_befunden` sofort zur Eskalation und nicht in die nächste
  Fix-Runde.

**Tech Stack:** wie Stufe 6a.

**Spec:** `docs/specs/2026-10-19-entwicklungs-pipeline-design.md` (Stufe 6). Lehre und Entscheide stehen in
`docs/lernpfad/06a-fable-berater.md` („gleiche Familie, gleicher blinder Fleck“). Entscheide Dominic vom 20.10.:
- Astra ist das Codex-Standardmodell.
- „Beide fragen“ zeigt einig/uneinig.
- Uneinigkeit hält an. Freigeben trotz Einwand verlangt eine Begründung, die im Bericht landet.
- Vorbelegt wird die vorsichtigere Empfehlung.
- Frühabbruch bei wiederkehrendem Befund.
- Im Wissensblock: Ein Spec-Widerspruch ist nie harmlos.

## Global Constraints

- **Berater nur auf Klick.** Ein Klick ergibt einen Aufruf je gefragtem Berater, „Beide“ also zwei. Es gibt nie
  einen automatischen oder Hintergrund-Rat. Fable bleibt `BERATER_MODELL = "fable"`. Astra ruft `codex exec` ohne
  `-m` auf (Standardmodell), mit `model_reasoning_effort="high"`, `-s read-only`, Timeout 900 s.
- **Astra sieht nur, was eingebettet ist:** Eingebettet werden ausschließlich Dateien innerhalb des Worktrees.
  Pfade, die nach `resolve()` außerhalb liegen, werden übersprungen, das gilt auch für Pfade, die ein Agent geliefert
  hat. Insgesamt höchstens `MAX_QUELLEN = 60_000` Zeichen.
- **Einwände errechnet der Server selbst.** Was der Browser als Einwand mitschickt, wird ignoriert. Eine Begründung
  aus Leerzeichen ist keine Begründung.
- **Die Sperre gilt nur für Durchlass-Entscheidungen** `DURCHLASS = {"freigeben", "annehmen"}`. `aendern`,
  `tests_nachbessern`, `weiter` und `abbrechen` brauchen nie eine Begründung.
- **Vorsichts-Reihenfolge** (erst nachbessern, dann verwerfen, dann durchlassen):
  `VORSICHT = {"spec_freigabe": ["aendern", "tests_nachbessern", "abbrechen", "freigeben"], "plan_freigabe":
  ["aendern", "abbrechen", "freigeben"], "eskalation": ["weiter", "abbrechen", "annehmen"]}`.
- **Alte Daten bleiben lesbar:** Rat-Dateien aus 6a (ohne `wer`) gelten als Fable. Läufe ohne `einwand_freigaben`
  stürzen nicht ab.
- Solange ein echter Lauf aktiv ist, wird Lab 2 nicht geändert. Vor jedem pytest läuft
  `python ~/.claude/skills/sqlite-schema-guard/scan.py .`, die conftest-Umleitung bleibt.
- In Tests sind alle Berater Fakes. `codex_strukturiert` und `claude_strukturiert` ohne Runner werfen
  `EchterAgentImTest`.

## Review Focus

1. **Ein Agent liefert `plan_dateien` mit `../`** oder einem absoluten Pfad (`C:/Users/<name>/.ssh/…`):
   `quelldateien` überspringt ihn, und nichts davon steht im Astra-Prompt. Test in Task 3.
2. **Der Browser schickt gefälschte `einwaende` mit oder eine Begründung aus Leerzeichen:** Der Server rechnet
   selbst und antwortet mit 400 samt Liste der Einwände. Test in Task 4.
3. **Ein Rat für einen früheren Stand** (gleicher Haltepunkt, alte `checkpoint_id`, z. B. Spec-Fassung 1) darf an
   Fassung 2 keinen Einwand erzeugen. Test in Task 4.
4. **Bei „Beide fragen“ scheitert ein Berater** (Codex-Timeout): Der andere Rat erscheint, ein Vergleich entfällt,
   und der Fehler erzeugt keine Sperre. Test in Task 4.
5. **„weiter“ nach einem Frühabbruch:** Kehrt derselbe Befund in der nächsten Runde zurück, wird wieder eskaliert;
   ein anderer Befund läuft normal. Test in Task 2.

---

### Task 1: Codex-Einwand sperrt Freigeben ohne Begründung (Graph, Steuerung, CLI, Bericht)

**Files:** Modify `entwicklung/graph_s4.py`, `entwicklung/graph.py` (Eskalation), `entwicklung/state.py`,
`entwicklung/steuerung.py`, `entwicklung/cli.py`, `entwicklung/bericht.py`. Test `tests/test_graph_s4.py`,
`tests/test_steuerung.py`, `tests/test_cli_s4.py`, `tests/test_leitstand_rat.py` (prüft heute den
Berater-Abschnitt des Berichts).

**Interfaces (Produces):**
- `graph_s4.codex_einwaende(pruefpunkte: list[dict]) -> list[str]`: je Punkt mit `pruefer == "codex"` und
  `schwere == "major"` die Zeile `"Codex (GPT) meldet major: <aussage>"`.
- Die Interrupt-Werte von `spec_freigabe` und `plan_freigabe` erhalten das Feld `"einwaende": codex_einwaende(...)`.
- Die Antwort an die Haltepunkte erlaubt zusätzlich `begruendung: str` und `einwaende: list[str]`. Die bisherigen
  Felder bleiben unverändert.
- Neues State-Feld `einwand_freigaben: list[dict]` mit Einträgen `{"haltepunkt", "entscheidung", "einwaende",
  "begruendung"}`. Es ist kein Reducer: Der Knoten schreibt `(state.get(...) or []) + [eintrag]`.
- `steuerung.DURCHLASS`, `steuerung.antwort_fuer(punkt, entscheidung, antwort, hinweis, begruendung=None)`: Mit
  nichtleerer Begründung (nach strip) bekommt das Ergebnis `"begruendung"`.
- `steuerung.einwand_fehlt(punkt: str, antwort: dict, einwaende: list[str]) -> str | None` liefert den Fehlertext,
  wenn `antwort["entscheidung"]` in `DURCHLASS` liegt, Einwände vorliegen und keine Begründung da ist. Sonst `None`.

- [ ] **Step 1: Failing tests**
  - `test_spec_freigabe_codex_major_braucht_begruendung`: Fake-Codex meldet `major`. `freigeben` ohne Begründung
    lässt den Lauf wieder an `spec_freigabe` warten. `halt_hinweis` enthält „begruendung“ und „Codex“. Danach geht
    `{"entscheidung": "freigeben", "begruendung": "Widerspruch geprüft: …"}` weiter zu `plan_schreiben`.
    `einwand_freigaben[0]` enthält Haltepunkt, Einwände und Begründung.
  - `test_plan_freigabe_codex_major_braucht_begruendung`: dasselbe an der Plan-Freigabe.
  - `test_codex_minor_und_claude_major_sperren_nicht`: Ein Claude-`major` und ein Codex-`minor` lassen
    `freigeben` ohne Begründung durch. Die Sperre gilt der anderen Familie, nicht jeder Stimme.
  - `test_aendern_trotz_codex_major_ohne_begruendung`: `aendern` mit Hinweis geht wie bisher.
  - `test_eskalation_annehmen_speichert_einwand`: `annehmen` mit `begruendung` und `einwaende` erzeugt einen Eintrag
    in `einwand_freigaben`. Ohne Einwände entsteht kein Eintrag.
  - `test_antwort_fuer_begruendung` und `test_einwand_fehlt`: Eine Begründung aus Leerzeichen zählt als fehlend.
    `aendern` und `abbrechen` geben `None`.
  - `test_cli_fortsetzen_braucht_begruendung`: `fortsetzen --entscheidung freigeben` ohne Begründung bei einem
    Codex-`major` gibt Exit 3 und nennt den Einwand. Mit `--begruendung '…'` läuft der Lauf weiter.
  - `test_bericht_freigaben_trotz_einwand`: Der Abschnitt „## Freigaben trotz Einwand“ listet Haltepunkt,
    Einwände und Begründung. Ein State ohne das Feld ergibt keinen Abschnitt und keinen Absturz.
- [ ] **Step 2:** Run → FAIL (fehlende Namen bzw. Freigabe geht ohne Begründung durch).
- [ ] **Step 3: Implementieren.**
  - `spec_freigabe` und `plan_freigabe` prüfen nach `_freigabe_antwort` die Sperre mit `codex_einwaende` und den
    `einwaende` aus der Antwort. Die Antwort-Einwände sind nur als `list[str]` gültig, alles andere gilt als leer.
    Eine fehlende Begründung ist eine ungültige Antwort: `halt_hinweis` erklärt sie, die Kante führt zurück in
    denselben Knoten, es gibt kein zweites interrupt.
  - `eskalation` übernimmt `begruendung` und `einwaende`, ohne selbst zu sperren. Ihre Einwände kommen aus den Räten
    (Task 4).
  - In der CLI kommt `--begruendung` zu `fortsetzen` hinzu. Die Einwände dafür kommen in diesem Task aus
    `frage["einwaende"]`; Task 4 ergänzt die aus den Räten.
- [ ] **Step 4:** Run `tests/test_graph_s4.py tests/test_steuerung.py tests/test_cli_s4.py tests/test_leitstand_rat.py` → PASS. Danach die ganze Suite → grün.
- [ ] **Step 5:** Commit `feat: Codex-Einwand sperrt Freigeben ohne Begründung`.

### Task 2: Frühabbruch bei wiederkehrendem Befund

**Files:** Modify `entwicklung/graph.py` (Stufe 3: `befunde_sammeln`, `nach_befunden`, `eskalation`), Test
`tests/test_graph_s3.py`.

**Interfaces (Produces):**
- `graph.befund_schluessel(b: dict) -> str` erzeugt `"<pruefer sortiert, mit + verbunden>|<path>|<kind>"`.
  Zeilennummer und Wortlaut bleiben bewusst draußen: Sie ändern sich nach jedem Fix.
- Die `runden`-Einträge erhalten `"schluessel": sorted({befund_schluessel(b) for auslösende b})`.
- `graph.wiederkehrend(runden: list[dict]) -> list[str]` gibt die Schnittmenge der Schlüssel der letzten beiden
  Einträge zurück. Das gilt nur, wenn deren `runde` direkt aufeinander folgen; sonst `[]`. Alte Einträge ohne
  `schluessel` zählen als leer.
- Der Interrupt-Wert der Eskalation erhält `"wiederkehrend": [...]`. Die Frage lautet dann „Derselbe Befund kam in
  zwei Runden nacheinander (…). Eine weitere Runde hilft vermutlich nicht. Wie weiter?“

- [ ] **Step 1: Failing tests**
  - `test_wiederkehrender_befund_eskaliert_nach_runde_1`: Ein Fake-Codex meldet in Runde 0 und Runde 1 denselben
    Befund (gleicher Pfad und `kind`, andere Zeile, anderer Wortlaut). Bei `max_runden=3` wartet der Lauf nach
    Runde 1 an `eskalation`, und `wiederkehrend` ist nicht leer.
  - `test_anderer_befund_laeuft_weiter`: Runde 1 hat einen anderen Pfad, also folgt eine Fix-Runde wie bisher.
  - `test_weiter_nach_fruehabbruch` (Review Focus 5): Nach `weiter` kehrt der Befund zurück, also wird wieder
    eskaliert. Verschwindet er, endet der Lauf normal.
  - `test_wiederkehrend_alte_runden_ohne_schluessel`: Es entsteht kein Fehler, das Ergebnis ist `[]`.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** In `nach_befunden` die Prüfung `wiederkehrend` vor `runde < max_runden` setzen. Sie greift nur,
  wenn `fix_noetig` gilt.
- [ ] **Step 4:** Run `tests/test_graph_s3.py tests/test_graph_s4.py` → PASS; Suite grün.
- [ ] **Step 5:** Commit `feat: Fix-Schleife eskaliert früh bei wiederkehrendem Befund`.

### Task 3: Astra als zweiter Berater; Vergleich und Wissensblock

**Files:** Modify `entwicklung/berater.py`, `entwicklung/graph.py` (`Abhaengigkeiten.berater_astra: Callable =
codex_strukturiert`), Test `tests/test_berater.py`.

**Interfaces (Produces):**
- `berater.BERATER = ("fable", "astra")`, `ASTRA_TIMEOUT = 900`, `MAX_QUELLEN = 60_000`, `VORSICHT` (siehe
  Constraints).
- `berater.quelldateien(werte: dict, frage: dict, punkt: str, worktree: Path) -> dict[str, str]` bildet die
  Kandidaten in dieser Reihenfolge:
  - die Dateien laut Plan (`frage["dateien"]` an der Plan-Freigabe, sonst `werte["plan_dateien"]`)
  - `werte["geaenderte_dateien"]` an der Eskalation
  - die Module aus `werte["schnittstellen"]`: `"a.b"` wird zu `"a/b.py"`, ein Pfad mit `/` oder `.py` bleibt.

  Ohne Duplikate. Nur bestehende Dateien innerhalb des Worktrees kommen hinein, die Grenze ist `MAX_QUELLEN` mit
  einem Kürzungsvermerk.
- `berater.berater_prompt(punkt, frage, werte, quellen: dict[str, str] | None = None)`:
  - Ohne `quellen` bleibt alles wie heute (Fable liest selbst).
  - Mit `quellen` heißt es statt „Du kannst das Repo … lesen“: „Du kannst keine Dateien lesen. Die relevanten
    Quelldateien stehen unten. Fehlt dir eine, sag es in `begruendung` und senke `sicherheit`.“ Dazu kommt der
    Abschnitt `## Quelldateien (Worktree)`.
- `WISSEN` bekommt zwei neue Punkte, Wortlaut verbindlich:
  - „Ein Widerspruch in der Spec ist nie harmlos: Codex prüft die Umsetzung gegen die Spec und meldet ihn in jeder
    Fix-Runde neu (A6: zwei vergeudete Runden). Empfiehl `aendern` mit dem Satz, der fallen oder umformuliert werden
    soll.“
  - „Ein `major` des Codex-Prüfers (andere Modellfamilie als du) stufst du nur mit Gegenbeleg aus dem Code herab.
    Zitiere ihn. Ohne Beleg ist der Punkt `echt`.“
- `berater.hole_rat(abh, punkt, frage, werte, worktree, sauber, wer: str = "fable") -> dict`:
  - `fable` arbeitet wie bisher.
  - `astra` ruft `abh.berater_astra("berater_astra", prompt_mit_quellen, worktree, RAT_SCHEMA,
    timeout=ASTRA_TIMEOUT)` auf.
  - Das Ergebnis erhält `"wer"`.
- `berater.vergleiche(punkt: str, fable: dict | None, astra: dict | None) -> dict | None` liefert `None`, solange
  nicht beide Räte `ok` sind, eine `antwort` haben und zum selben `(haltepunkt, checkpoint_id)` gehören. Sonst:
  - `{"einig": bool, "vorbelegt": "fable" | "astra", "einwaende": list[str]}`
  - An `fragen` gilt immer `einig=True`, `vorbelegt="fable"`, keine Einwände.
  - Sonst ist `vorbelegt` der Rat, dessen Entscheidung in `VORSICHT[punkt]` weiter vorn steht; bei Gleichstand
    Astra.
- `berater.einwaende_aus_raeten(punkt: str, raete: dict[str, dict]) -> list[str]` sammelt ohne Duplikate:
  - bei Uneinigkeit: „Fable empfiehlt X, Astra Y“
  - wenn Astra `ok` ist und nicht zu `DURCHLASS` rät (nicht an `fragen`): „Astra (GPT) rät zu Y: <erster Satz der
    Begründung>“

  Gescheiterte Räte erzeugen keinen Einwand.

- [ ] **Step 1: Failing tests**
  - `test_quelldateien_bettet_ein_und_bleibt_im_worktree` (Review Focus 1): Die Kandidaten `../draussen.py`, ein
    absoluter Pfad, eine fehlende Datei und `portwart.drift` ergeben genau `{"portwart/drift.py": …}`.
  - `test_quelldateien_kuerzt`.
  - `test_astra_prompt_ohne_lesen_mit_quellen`: Der Prompt enthält den Inhalt der Quelldatei und „keine Dateien
    lesen“, aber nicht „im aktuellen Ordner lesen“.
  - `test_wissen_spec_widerspruch_und_codex_major`.
  - `test_hole_rat_astra`: Der Fake-Astra bekommt `timeout=900` und kein `modell`, das Ergebnis hat
    `wer == "astra"`. Die Grenzverletzung prüft `sauber` wie bei Fable.
  - `test_vergleiche_einig_uneinig_vorsichtiger`: (freigeben, aendern) ergibt `einig=False`, `vorbelegt="astra"`.
    (freigeben, freigeben) ergibt `einig=True`. Bei verschiedenen `checkpoint_id` und einem gescheiterten Rat
    ergibt sich `None`.
  - `test_einwaende_aus_raeten`: Astra rät zu `aendern` und Fable fehlt, das ergibt einen Einwand. Astra gescheitert
    ergibt keinen.
  - `test_testsperre_astra`: `Abhaengigkeiten()` ohne Runner wirft `EchterAgentImTest`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implementieren. **Step 4:** `tests/test_berater.py` → PASS; Suite grün.
- [ ] **Step 5:** Commit `feat: Astra-Berater (Codex) mit eingebetteten Quellen, Vergleich, Wissensblock`.

### Task 4: Ausführer, Server und CLI für zwei Berater; Einwände aus den Räten

**Files:** Modify `entwicklung/leitstand/ausfuehrer.py`, `entwicklung/leitstand/server.py`,
`entwicklung/leitstand/daten.py`, `entwicklung/berater.py`, `entwicklung/cli.py`, `entwicklung/bericht.py`. Test
`tests/test_leitstand_rat.py`, `tests/test_leitstand_server.py`, `tests/test_cli_s4.py`.

**Interfaces (Consumes):** Task 1 (`einwand_fehlt`, `begruendung`, `codex_einwaende`) und Task 3 (`hole_rat(wer)`,
`vergleiche`, `einwaende_aus_raeten`).

**Interfaces (Produces):**
- Rat-Dateien heißen `rat-<haltepunkt>-<wer>-<n>.json` und enthalten das Feld `"wer"`.
- `berater.raete_fuer_stand(ordner: Path, punkt: str, checkpoint_id: str) -> dict[str, dict]` liefert je `wer` den
  neuesten Rat mit genau diesem Haltepunkt und Stand. Alte 6a-Dateien zählen als `fable`.
- `berater.einwaende_fuer(punkt, frage, ordner, checkpoint_id) -> list[str]` ist `frage["einwaende"]` (Codex-Prüfer,
  aus Task 1) plus `einwaende_aus_raeten(...)`, ohne Duplikate.
- `rat_fuer_lauf(abh, graph, thread_id, erwartet=None, wer="fable")`.
- `Ausfuehrer.frage_rat(thread_id, wer="fable")`: höchstens ein Rat je `(Lauf, wer)` gleichzeitig.
- `Ausfuehrer.rat(thread_id)` liefert `{"fable": e|None, "astra": e|None, "vergleich": dict|None}` (jeder Eintrag
  mit `veraltet`) oder `None`, wenn es noch keinen Rat gibt.
- `Ausfuehrer.warte_rat(thread_id, timeout=None)` wartet auf beide.
- `POST /api/laeufe/{tid}/rat?wer=fable|astra|beide`: 202 mit `{"gestartet": [...], "belegt": [...]}`; 409 nur, wenn
  nichts startet; 400 bei unbekanntem `wer`.
- `GET /api/laeufe/{tid}/rat` hat die neue Form oben, sonst 204.
- `lauf_daten` erhält `"einwaende": einwaende_fuer(...)` für den aktuellen Stand.
- `POST …/antwort` nimmt `begruendung` an. Die Einwände errechnet der Server mit `einwaende_fuer`, sonst gibt es
  400 `{"fehler", "einwaende"}`. Bei Durchlass mit Einwänden setzt er `antwort["einwaende"]` selbst.
- `cli rat --wer fable|astra|beide` (Standard `fable`). „beide“ läuft parallel in zwei Threads und gibt beide Räte,
  den Vergleich und den Befehl zum Übernehmen der vorbelegten Empfehlung aus. Liegen Einwände vor und ist die
  Empfehlung ein Durchlass, kommt der Satz „Freigeben trotz Einwand braucht `--begruendung '<dein Grund>'`“ dazu.
  `cli fortsetzen` holt die Einwände über `einwaende_fuer`.
- Der Bericht-Abschnitt heißt „## Berater (Fable, Astra)“, jede Zeile nennt `wer`.

- [ ] **Step 1: Failing tests**
  - `test_beide_fragen_parallel_und_vergleich`: Fake-Fable `freigeben`, Fake-Astra `aendern`. Beide Dateien sind
    abgelegt, `vergleich.einig` ist False, vorbelegt ist Astra.
  - `test_ein_berater_scheitert` (Review Focus 4): Astra wirft eine Ausnahme. Fables Rat ist da, `vergleich` ist
    None, `einwaende` kommen nur aus Codex-Prüfpunkten.
  - `test_server_antwort_einwand_ohne_begruendung_400` (Review Focus 2): Der Browser schickt `einwaende: []` und
    `begruendung: "  "`, Antwort 400 mit Liste. Mit Begründung kommt 202, und der Graph-State enthält die vom
    Server errechneten Einwände.
  - `test_alter_rat_erzeugt_keinen_einwand` (Review Focus 3): Astras Rat zu Spec-Fassung 1 erzeugt an Fassung 2
    (neue `checkpoint_id`) keinen Einwand.
  - `test_rat_doppelklick_je_berater`: Ein zweiter Astra-Klick gibt `belegt: ["astra"]`. Fable startet trotzdem.
  - `test_alte_ratdatei_ohne_wer_gilt_als_fable`.
  - `test_cli_rat_beide` und `test_cli_fortsetzen_einwand_aus_rat`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implementieren. **Step 4:** Die drei Testdateien → PASS; Suite grün.
- [ ] **Step 5:** Commit `feat: Beide fragen in Server und CLI, Einwände aus den Räten`.

### Task 5: Leitstand-Oberfläche und Demo

**Files:** Modify `entwicklung/leitstand/static/app.js`, `stil.css`, `docs/lernpfad/leitstand_demo.py`.

- **Knöpfe:** `🧠 Fable fragen`, `🛰️ Astra fragen`, `⚖️ Beide fragen`. Jeder Knopf ist gesperrt, solange sein
  Berater denkt.
- **Zwei Rat-Karten** nebeneinander, Astras Karte mit dem Untertitel „GPT-Familie, liest nur Eingebettetes“.
- **Leiste über den Karten:**
  - grün „einig: beide empfehlen X“
  - rot „uneinig: Fable X · Astra Y. Vorbelegt ist die vorsichtigere Empfehlung (Y).“
- **Einwand-Kasten:** sichtbar, sobald `lauf.einwaende` nicht leer ist, auch ohne Rat. Er enthält die Liste und das
  Feld `#begruendung`. `freigeben` und `annehmen` bleiben gesperrt, bis das Feld Text hat. `sende` schickt
  `begruendung` mit. „Empfehlung übernehmen“ übernimmt den vorbelegten Rat (`mitEigenemText` wie in 6a).
- **Text von Agenten** nur per `textContent`.
- **Demo:** `DEMO_RAT_ASTRA` widerspricht `DEMO_RAT`, und an der Spec-Freigabe der Demo meldet der Fake-Codex ein
  `major`.

- [ ] **Step 1:** Demo auf Port 8795 starten (rot gestreift DEMO). Im Browser prüfen:
  - Der Einwand-Kasten ist sofort da, Freigeben ist gesperrt.
  - „Beide fragen“ ergibt zwei Karten und die rote Leiste; vorbelegt ist Astras Text.
  - Freigeben mit Begründung geht durch, der Bericht zeigt „Freigaben trotz Einwand“.
  - Ein Agententext `<img src=x onerror=…>` erscheint als Text.

  Die Prüfung läuft mit Screenshots unter `%TEMP%`. **Danach das Testfenster schließen.**
- [ ] **Step 2:** Suite grün. Commit `feat: Leitstand zeigt Fable und Astra, einig/uneinig, Einwand-Kasten`.

### Task 6: Lernnotiz, Anleitung, Abnahme an einer echten Aufgabe

**Files:** Create `docs/lernpfad/06b1-familien-zweitmeinung.md` und `aufgaben/portwart/A7.md`. Modify
`HOW-TO-USE.md` (Abschnitt Leitstand: drei Knöpfe, Einwand, `--begruendung`, `rat --wer`).

- [ ] **Step 1:** Die Lernnotiz enthält:
  - die Idee in einem Satz
  - die harte Sperre gegenüber der Rat-Sperre
  - warum Astra eingebettete Dateien braucht
  - den Frühabbruch-Schlüssel und seinen Preis
  - drei Selbstprüffragen
- [ ] **Step 2:** Den A7-Wunsch schreiben. Vorschlag: `portwart eintragen <name> <port>` als erster schreibender
  Befehl. Er hält Kommentare und Reihenfolge in `ports.toml`, schreibt atomar, lehnt Doppelte und Ports außerhalb
  1–65535 ab. Der Vertrag enthält genug Stellen für Spec-Widersprüche. **Den Wortlaut bestätigt Dominic vor dem
  Lauf.**
- [ ] **Step 3: Abnahme.** Dominic startet A7 im Leitstand und klickt an jedem Haltepunkt „Beide fragen“. Ich halte
  in der Lernnotiz eine Tabelle fest:
  - je Haltepunkt: Fable, Astra, einig?, Dauer
  - was Dominic entschied
  - was wirklich geschah

  Dazu kommt, ob Sperre und Frühabbruch gegriffen haben. Kein Commit in Lab 2, solange der Lauf läuft.
- [ ] **Step 4:** Commit der Doku nach dem Lauf. Codex-Verifier (high) über den ganzen Zweig. Gate mit Dominic.
