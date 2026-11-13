# Lab 2 · Stufe 6a (Fable-Berater an den Haltepunkten) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** An jedem Haltepunkt gibt es im Leitstand (und in der CLI) einen Knopf **„Fable fragen“**. Fable liest,
was Dominic freigeben soll, und das Repo, und liefert:
- eine Empfehlung mit Begründung
- eine Einschätzung jedes Prüfpunkts (echt, klein oder falscher Alarm)
- das vorausgefüllte Formular

Ein Klick „Empfehlung übernehmen“ sendet die Antwort. **Fable berät, Dominic entscheidet** (Entscheid 20.10.).

**Architecture:**
- **`berater.py`** enthält Prompt, Schema und Prüfung des Rats und übersetzt ihn in die Antwort an den Haltepunkt.
  Für die Übersetzung nutzt es `steuerung.antwort_fuer`, also dieselbe Regel wie Knopf und CLI.
- **Der Aufruf** läuft über `strukturiert.claude_strukturiert` mit `--model fable`, nur lesend, `cwd` = Worktree.
  Danach folgt eine Nachkontrolle wie bei den Planungsagenten.
- **Im Leitstand** läuft ein Rat in einem Hintergrund-Thread (1 bis 3 Minuten). Er ist an Haltepunkt und
  `checkpoint_id` gebunden. Ändert sich der Stand, gilt er als veraltet und lässt sich nicht mehr übernehmen.
- **Jeder Rat wird abgelegt** unter `berichte/<lauf>/rat-<haltepunkt>-<n>.json` und erscheint im Bericht. So bleibt
  nachvollziehbar, wo Fable beraten hat und ob Dominic gefolgt ist.

**Tech Stack:** wie Stufe 5.

**Spec:** `docs/specs/2026-10-19-entwicklungs-pipeline-design.md` (Stufe 6 „Modellstufen“). Entscheide Dominic
20.10.:
- Hilfe-Knopf mit Fable an den Freigabe-Punkten
- Fable berät, Dominic klickt
- 6a (Knopf) vor 6b (Modellstufen, Kosten, Wiederaufnahme, Prozesssperre, Schiedsrichter)

## Global Constraints

- **Fable nur hier und nur auf Klick.** Ein Klick ergibt genau einen Aufruf, nie im Hintergrund oder automatisch.
  Implementierer, Prüfer und Planungsagenten bleiben ohne Fable. Konstante `BERATER_MODELL = "fable"`, Timeout
  900 s.
- **Fable liest nur** (`--restricted --tools Read,Glob,Grep`, `cwd` = Worktree). Danach `_sauber`-Nachkontrolle:
  Worktree und geschützte Repos unverändert, sonst ist der Rat ungültig („Grenzverletzung beim Rat“).
- **Ein Rat ist nur gültig** für den Haltepunkt und die `checkpoint_id`, für die er erstellt wurde. Übernehmen
  sendet genau diese beiden mit, der Server prüft sie wie in Stufe 5. Ein veralteter Rat ist sichtbar markiert, sein
  Knopf gesperrt.
- **Der Rat muss eine gültige Antwort ergeben** (`steuerung.antwort_fuer` liefert nicht `None`). Sonst wird er als
  „nicht verwertbar“ angezeigt und nicht übernehmbar.
- Je Lauf höchstens ein Rat gleichzeitig (Doppelklick: 409).
- Testsperre wie bisher: In Tests ist Fable ein Fake, `claude_strukturiert` ohne Runner wirft `EchterAgentImTest`.

## Review Focus

1. **Fable empfiehlt etwas, das am Haltepunkt nicht erlaubt ist** (z. B. `weiter` an der Spec-Freigabe, `aendern`
   ohne Hinweis): „nicht verwertbar“, kein Knopf zum Übernehmen. Test in Task 1.
2. **Der Stand ändert sich, während Fable denkt** (Dominic antwortet selbst, anderer Tab): Der Rat kommt als
   „veraltet“ an, Übernehmen gibt 409. Test in Task 2.
3. **Fable schreibt trotz Lesewerkzeugen etwas:** Der Rat ist ungültig und wird gemeldet. Test in Task 1.
4. **Rat bei `tests_nachbessern`:** Der vorausgefüllte Hinweis enthält die konkreten Prüfpunkte, weil der
   Test-Schreiber die Prüfpunkte sonst nicht sieht (Lehre aus A5). Test in Task 1 (Prompt-Inhalt).
5. **Text von Fable in der Oberfläche:** nur per `textContent`. Browser-Prüfung in Task 3.

---

### Task 1: Berater (Prompt, Schema, Prüfung, Aufruf)

**Files:** Create `entwicklung/berater.py`, `tests/test_berater.py`; Modify `entwicklung/graph.py`
(`Abhaengigkeiten.berater = claude_strukturiert`)

**Interfaces:**
- `RAT_SCHEMA = _objekt(entscheidung=_TEXT, text=_TEXT, begruendung=_TEXT, sicherheit=enum hoch|mittel|niedrig,
  punkte=_liste(_objekt(aussage=_TEXT, einschaetzung=enum echt|klein|falscher_alarm, warum=_TEXT)))`.
  - `entscheidung`: an `fragen` `antwort` oder `abbrechen`, sonst die erlaubten Entscheidungen.
  - `text`: die Antwort bzw. der Hinweis, sonst `""`.
- `berater_prompt(punkt: str, frage: dict, werte: dict) -> str`. Enthält:
  - Wunsch, Klärung, Spec, Tests und Plan (aus `frage`/`werte`, gekürzt auf je 40 000 Zeichen)
  - Prüfpunkte und Probe
  - die erlaubten Entscheidungen samt Bedeutung
  - Abschnitt **„Wissen über die Pipeline“**:
    - Akzeptanztests liegen beim Lauf in `tests/_akzeptanz/`, `parents[2]` ist das Repo
    - `aendern` erzeugt Spec und danach Tests neu
    - `tests_nachbessern` behält die Spec, der Test-Schreiber sieht aber **keine** Prüfpunkte, also müssen sie
      konkret in den Hinweis
    - ein Test, der bei jeder Umsetzung scheitert, führt sicher in die Eskalation
    - Freigeben ist richtig, wenn nur `minor`-Punkte bleiben
  - Auftrag: im Repo nachsehen statt raten, jeden Prüfpunkt einschätzen, Antwort- oder Hinweistext fertig formulieren
- `rat_pruefen(punkt: str, rat: dict) -> tuple[dict | None, str | None]`: `(antwort, None)` über
  `steuerung.antwort_fuer` (an `fragen` mit `antwort=text`), sonst `(None, grund)`.
- `hole_rat(abh, punkt, frage, werte, worktree, sauber: Callable[[], list[str]]) -> dict`. Ergebnis
  `{ok, rat, antwort, fehler, dauer_s}`. Ruft `abh.berater("berater", prompt, worktree, RAT_SCHEMA,
  modell=BERATER_MODELL, timeout=900)`, danach `sauber()`.

- [ ] Tests:
  - `test_prompt_enthaelt_material_und_wissen` (Spec, Testtext, Prüfpunkte, „tests/_akzeptanz“, „keine Prüfpunkte“)
  - `test_rat_pruefen_gueltig_je_haltepunkt` (parametrisiert, vier Haltepunkte)
  - `test_rat_pruefen_ungueltig` (`weiter` an der Spec-Freigabe, `aendern` ohne Text, leere Antwort an `fragen`)
  - `test_hole_rat_nutzt_fable_und_liest_nur` (Fake sieht `modell="fable"`; Fake schreibt in den Worktree, dann
    `ok False` mit „Grenzverletzung“)
  - `test_rat_schema_streng`
- [ ] FAIL, Implement, PASS. **Commit.**

### Task 2: Rat im Leitstand-Server und in der CLI

**Files:** Modify `entwicklung/leitstand/ausfuehrer.py` (Rat-Threads), `entwicklung/leitstand/server.py`,
`entwicklung/cli.py`, `entwicklung/bericht.py`; Tests in `tests/test_leitstand_rat.py`, `tests/test_cli_s4.py`

**Interfaces:**
- `Ausfuehrer.frage_rat(thread_id) -> None`:
  - liest den Stand (Haltepunkt, `checkpoint_id`, Frage, Werte, Worktree), startet einen Thread
  - legt das Ergebnis unter `berichte/<lauf_id>/rat-<haltepunkt>-<n>.json` ab
  - wirft `Belegt`, wenn schon ein Rat läuft, `WartetNicht`, wenn kein Haltepunkt
- `Ausfuehrer.rat(thread_id) -> dict | None`: `{zustand: laeuft|fertig|fehler, haltepunkt, checkpoint_id, rat,
  antwort, fehler, veraltet: bool}`. `veraltet`, wenn Haltepunkt oder `checkpoint_id` nicht mehr dem aktuellen
  Stand entsprechen.
- Endpunkte (mit Token wie alle `/api`):
  - `POST /api/laeufe/{tid}/rat` → 202, bei laufendem Rat 409, ohne Haltepunkt 409
  - `GET /api/laeufe/{tid}/rat` → obiges Dict oder 404
- Übernehmen braucht keinen eigenen Endpunkt. Der Browser schickt `rat.antwort` mit `haltepunkt` und
  `checkpoint_id` des Rats an `/antwort`, die Prüfung aus Stufe 5 greift.
- CLI: `python -m entwicklung rat [--thread ID]` holt den Rat für den wartenden Lauf und gibt ihn aus:
  - Empfehlung, Sicherheit, Begründung, Punkte
  - den fertigen `fortsetzen`-Befehl
  - blockiert bis fertig, Exit 0 bzw. 1 bei Fehler
- Bericht: Abschnitt „Berater (Fable)“ mit je Rat Haltepunkt, Empfehlung, Sicherheit und Datei.

- [ ] Tests (Fake-Berater):
  - `test_rat_bis_fertig_und_uebernehmen` (Rat an der Spec-Freigabe, Übernehmen über `/antwort`, Lauf an der
    Plan-Freigabe)
  - `test_rat_veraltet_nach_eigener_antwort` (Rat starten, Dominic antwortet vorher selbst, Rat `veraltet True`,
    Übernehmen 409)
  - `test_doppelter_rat_409`
  - `test_rat_ohne_haltepunkt_409`
  - `test_rat_ohne_token_403`
  - `test_rat_wird_abgelegt_und_im_bericht`
  - `test_cli_rat` (Fake, Ausgabe enthält Empfehlung und Befehl)
- [ ] FAIL, Implement, PASS. **Commit.**

### Task 3: Knopf in der Oberfläche

**Files:** Modify `entwicklung/leitstand/static/app.js`, `stil.css`, `docs/lernpfad/leitstand_demo.py`
(Fake-Fable mit kurzer Denkpause)

- In jedem Haltepunkt-Formular der Knopf **„🧠 Fable fragen“**. Solange der Rat läuft:
  - „Fable denkt … (1–3 min)“ mit verstrichener Zeit
  - der Knopf ist gesperrt
- Die Rat-Karte zeigt:
  - Empfehlung als Marke (z. B. „Freigeben“), Sicherheit, Begründung
  - die Punkte mit Einschätzung (echt, klein, falscher Alarm)
  - Antwort- oder Hinweistext vorausgefüllt im Textfeld, damit Dominic ihn ändern kann
- Knöpfe der Rat-Karte:
  - **„Empfehlung übernehmen“** sendet `rat.antwort` mit Haltepunkt und `checkpoint_id` des Rats
  - Bei veraltetem oder nicht verwertbarem Rat ist der Knopf gesperrt und der Grund steht daneben
- Der Rat bleibt beim Neuladen sichtbar, weil er über `GET …/rat` geholt wird.
- [ ] Browser-Prüfung (Playwright, Demo):
  - Rat an Fragen, Spec-, Plan-Freigabe und Eskalation
  - Übernehmen
  - veralteter Rat
  - Konsole ohne Fehler
  - **Testfenster danach schließen**
- [ ] **Commit.**

### Task 4: Abnahme mit A6, Lernnotiz, Codex, Gate

- [ ] **Step 1:** Wunsch `aufgaben/portwart/A6.md`: `drift` soll Ordner ausschließen können (z. B. Berichte und
  Daten), weil der erste echte Einsatz 201 von 204 Funden aus Berichten lieferte. Wie, bleibt offen (Liste in
  `ports.toml`, Option, Standardausschlüsse). **Commit.**
- [ ] **Step 2:** Dominic startet A6 im Leitstand und nutzt an jedem Haltepunkt zuerst „Fable fragen“. Ich lese
  parallel und vergleiche Fables Urteil mit meinem. Gemergt wird erst nach dem Gate.
- [ ] **Step 3:** Lernnotiz `docs/lernpfad/06a-fable-berater.md`. Inhalt:
  - ein teures Modell als Berater statt als Arbeiter
  - Rat an einen Stand gebunden (`checkpoint_id`)
  - warum Fable nicht selbst freigibt
  - Vergleich Fable mit meinem Urteil am echten Lauf
- [ ] **Step 4:** Codex-Verifier (`high`), Befunde per TDD, Ledger nach `docs/`. **STUFEN-GATE.**
