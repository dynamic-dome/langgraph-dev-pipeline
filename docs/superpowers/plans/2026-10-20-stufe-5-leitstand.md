# Lab 2 · Stufe 5 (Leitstand) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Eine lokale Weboberfläche zeigt jeden Lauf als Ablaufdiagramm mit dem Knoten, an dem er gerade steht. Dort
beantwortet Dominic alle vier Haltepunkte (Fragen, Spec-, Plan-Freigabe, Eskalation) und startet neue Läufe.

**Architecture:**
- **Einzige Wahrheit ist der Checkpointer.** Der Leitstand liest Zustand und Verlauf jedes Laufs aus
  `data/checkpoints.db`. So sieht er auch Läufe, die über die CLI in einem anderen Prozess laufen.
- **Die Oberfläche fragt einmal je Sekunde nach** (Polling). SSE würde nur Läufe sehen, die in diesem Prozess
  laufen.
- **Läufe, die der Leitstand startet oder fortsetzt**, laufen in einem Hintergrund-Thread des Servers
  (`ausfuehrer.py`). Je Lauf gibt es höchstens einen Thread.
- **Die Antwort an einen Haltepunkt** baut dieselbe Funktion wie in der CLI. Sie wird dafür nach `steuerung.py`
  herausgezogen, damit Browser und Kommandozeile nie verschieden entscheiden.
- **Das Diagramm ist eigenes SVG** aus `graph.get_graph().to_json()`, mit Ebenen-Layout wie der Puls in Lab 1.
  Keine fremde JS-Bibliothek, läuft offline.

**Tech Stack:** FastAPI + uvicorn (Entscheidung im Entwurf), httpx nur für den `TestClient`, Vanilla-JS/SVG/CSS.

**Spec:** `docs/specs/2026-10-19-entwicklungs-pipeline-design.md`. Maßgeblich sind:
- Stufe 5: „Leitstand: lokale Weboberfläche mit Live-Ablaufdiagramm und Freigaben im Browser“
- „Leitstand-Technik: FastAPI + uvicorn … Port wird in portwarts `ports.toml` eingetragen“
- Entscheide Dominic 20.10.:
  - beobachten, freigeben, starten
  - eigenes SVG
  - Befehl + Desktop-Symbol
  - 4b läuft vorher nur bis lauffähig, und A5 wird der gemeinsame Abnahmelauf

## Global Constraints

- **Server bindet nur `127.0.0.1`**, fester Port aus `ports.toml` (eingetragen in Task 6). Ist er belegt: klare
  Meldung, kein Ausweichen auf einen anderen Port.
- **Token:** Jeder Start erzeugt `secrets.token_urlsafe(24)`.
  - Die Seite wird über `/?token=…` geöffnet.
  - Jede API-Anfrage braucht den Header `X-Leitstand-Token`, sonst 403.
  - Zusätzlich muss der `Host` genau `127.0.0.1:<port>` sein.
  - Gibt es einen `Origin`, muss er `http://127.0.0.1:<port>` sein, sonst 403.
  - Grund: Ohne das könnte jede offene Webseite per Anfrage an 127.0.0.1 eine Freigabe auslösen.
- **Der Leitstand ändert nichts außerhalb der Pipeline.** Er startet Läufe, setzt sie fort und liest. Merge, Push
  und Löschen bleiben außen vor.
- **Starten nur für Repos unter Lab 2 mit `entwicklung.toml`** und für Aufgaben aus `aufgaben/<repo>/*.md`. Modell
  und Stufe aus einer festen Auswahl (kein Fable).
- **Testsperre:** In Tests laufen nur Fakes (wie bisher), der Server nur über `TestClient`, nie auf einem echten
  Port.
- Neue Abhängigkeiten nur im venv von Lab 2, Versionen in `requirements.lock` festhalten.

## Review Focus

1. **Anfrage ohne Token, mit falschem Token, fremdem `Origin` oder fremdem `Host`:** 403, nichts passiert. Test in
   Task 4.
2. **Zwei Freigaben kurz hintereinander** (Doppelklick) für denselben Lauf: Die zweite wird abgelehnt (409), solange
   der erste Fortsetzungs-Thread läuft. Test in Task 3.
3. **Eine Antwort, die nicht zum Haltepunkt passt**, oder ein Lauf, der gar nicht wartet: 400 bzw. 409 mit der
   erlaubten Angabe. Kein `Command`. Test in Task 4.
4. **Ein Lauf, den die CLI in einem anderen Prozess ausführt:** Er erscheint mit seinem Stand. Fortsetzen geht nur,
   wenn er an einem Haltepunkt wartet. Test in Task 2 (Thread aus fremdem Checkpointer).
5. **Ein Fehler im Hintergrund-Thread** (Absturz eines Knotens): Er erscheint als Fehler des Laufs in der
   Oberfläche, und der Server läuft weiter. Test in Task 3.

---

### Task 1: Steuerung herausziehen, Abhängigkeiten

**Files:** Create `entwicklung/steuerung.py`, `tests/test_steuerung.py`; Modify `entwicklung/cli.py`,
`pyproject.toml`, `requirements.lock`

**Interfaces:**
- `steuerung.antwort_fuer(punkt: str, entscheidung: str | None, antwort: str | None, hinweis: str | None)
  -> dict | None`. Inhalt wie bisher `cli._antwort_fuer`. Die CLI ruft es auf.
- `steuerung.ERLAUBT_KURZ: dict[str, list[str]]`: je Haltepunkt die erlaubten Entscheidungen bzw. `antwort`, für die
  Oberfläche.
- Abhängigkeiten `fastapi`, `uvicorn`, `httpx` (Test). Installation mit `pip install`, Versionen nach
  `requirements.lock`.

- [ ] Tests:
  - `test_antwort_fuer_je_haltepunkt` (parametrisiert über alle gültigen und ungültigen Kombinationen der vier
    Haltepunkte)
  - CLI-Suite bleibt grün
- [ ] FAIL, Implement, PASS. **Commit.**

### Task 2: Daten für die Oberfläche

**Files:** Create `entwicklung/leitstand/__init__.py`, `entwicklung/leitstand/daten.py`, `tests/test_leitstand_daten.py`

**Interfaces:**
- `graph_daten(graph) -> dict`:
  - `{"knoten": [{id, ebene, spalte, text, haltepunkt: bool, phase}], "kanten": [{von, nach, bedingt, zurueck}]}`
  - Ebenen: längster Weg ab `__start__`, Rückkanten zählen nicht.
  - `phase` ist „planung“, „umsetzung“ oder „pruefung“.
  - `text` kommt aus einer festen Tabelle `KNOTEN_TEXT` (ein Satz je Knoten).
- `lauf_daten(graph, cp, thread_id) -> dict`:
  - `{thread_id, stufe, aufgabe_id, status, wartepunkt, frage (interrupt-Wert oder None), aktiv: [Knoten aus next],
    verlauf: [{knoten, zeit}] (aus get_state_history, älteste zuerst), runde, bericht_pfad}`
  - `frage` wird um die Inhalte von `spec.md`, `plan.md` und den Testdateien ergänzt (gekürzt auf 40 000 Zeichen je
    Datei), damit man im Browser lesen kann, was man freigibt.
- `laeufe(cp, graph_fuer) -> list[dict]`: alle Läufe (Präfix `lauf-`), jüngste zuerst, je `{thread_id, aufgabe_id,
  status, wartepunkt, stufe}`.

- [ ] Tests:
  - `test_graph_daten_ebenen_und_haltepunkte` (S4-Graph: `__start__` Ebene 0, die 4 Haltepunkte markiert, die
    Rückkante `fix_runde → implementieren` als `zurueck`)
  - `test_lauf_daten_wartend` (Fake-Lauf bis `spec_freigabe`: `wartepunkt`, `frage.art`, Inhalt von `spec.md` in
    `frage`, `verlauf` beginnt mit `vorbereiten`)
  - `test_lauf_daten_fertig` (Status, Bericht)
  - `test_laeufe_liste_ueber_stufen`
  - `test_lauf_aus_anderem_prozess` (Thread mit eigenem SqliteSaver auf dieselbe Datei geschrieben, über einen
    zweiten gelesen)
- [ ] FAIL, Implement, PASS. **Commit.**

### Task 3: Ausführer im Hintergrund

**Files:** Create `entwicklung/leitstand/ausfuehrer.py`, `tests/test_leitstand_ausfuehrer.py`

**Interfaces:**
- `class Ausfuehrer(abh, cp)` mit:
  - `starte(repo, aufgabe_id, stufe, modell, pruefer_modell) -> str`: legt die `thread_id` mit
    `freie_thread_id` an, startet einen Thread mit `graph.invoke(eingabe, cfg)`, gibt die `thread_id` zurück.
  - `fortsetzen(thread_id, antwort: dict) -> None`: wirft `Belegt`, wenn für den Lauf ein Thread läuft, und
    `WartetNicht`, wenn er an keinem Haltepunkt steht.
  - `zustand(thread_id) -> {"laeuft": bool, "fehler": str | None}`
  - `warte(thread_id, timeout)` (für Tests)
- Fehler im Thread werden gefangen und in `zustand` abgelegt, nie nach außen geworfen.

- [ ] Tests (Fakes aus `tests/test_graph_s4.py`):
  - `test_starten_bis_fragen`
  - `test_fortsetzen_bis_spec_freigabe`
  - `test_doppeltes_fortsetzen_belegt` (Fake-Planer blockiert per `threading.Event`)
  - `test_fortsetzen_ohne_wartepunkt` (`WartetNicht`)
  - `test_fehler_im_thread_wird_zustand` (Fake-Testlauf `abh.tests` wirft `RuntimeError` in der Probe; das fängt
    kein Agenten-Schutz ab, der Graph bricht ab, der Ausführer meldet `fehler`, der Server läuft weiter)
- [ ] FAIL, Implement, PASS. **Commit.**

### Task 4: Server und CLI-Befehl

**Files:** Create `entwicklung/leitstand/server.py`, `tests/test_leitstand_server.py`; Modify `entwicklung/cli.py`

**Interfaces:**
- `baue_app(abh, cp, token: str, port: int) -> FastAPI`. Endpunkte:

  | Methode und Pfad | Zweck |
  |---|---|
  | `GET /` | `index.html`, nur mit `?token=` |
  | `GET /api/graph?stufe=4` | `graph_daten` |
  | `GET /api/laeufe` | Liste |
  | `GET /api/laeufe/{tid}` | `lauf_daten` + `ausfuehrer.zustand` |
  | `GET /api/start-optionen` | Repos, Aufgaben, Modelle, Stufen |
  | `POST /api/laeufe` | `{repo, aufgabe, stufe, modell, pruefer_modell}` → 201 `{thread_id}` |
  | `POST /api/laeufe/{tid}/antwort` | `{entscheidung?, antwort?, hinweis?}` → 202. Antwortet 400 (passt nicht, mit `erlaubt`), 409 (wartet nicht oder belegt) |
  | `/static/…` | Dateien der Oberfläche |
- Eine Middleware prüft Token, `Host` und `Origin` für alles außer `/static` (dort nur `Host`).
- CLI `leitstand [--port P] [--kein-browser]`:
  - erzeugt das Token, startet uvicorn auf `127.0.0.1`
  - öffnet `http://127.0.0.1:P/?token=…` mit `webbrowser`
  - Standard-Port aus `ports.toml` (Task 6)

- [ ] Tests mit `TestClient`:
  - `test_ohne_token_403`
  - `test_falscher_host_oder_origin_403`
  - `test_start_und_antwort_ueber_api` (bis `spec_freigabe`, freigeben, `plan_freigabe`)
  - `test_unpassende_antwort_400`
  - `test_lauf_wartet_nicht_409`
  - `test_start_nur_bekannte_repos_und_aufgaben` (Pfad-Tricks wie `../` → 400)
  - `test_kein_fable`
- [ ] FAIL, Implement, PASS. **Commit.**

### Task 5: Oberfläche

**Files:** Create `entwicklung/leitstand/static/index.html`, `app.js`, `stil.css`

- **Aufbau:**
  - Links die Liste der Läufe (Status-Symbol, Aufgabe, Haltepunkt), oben ein Knopf „Neuer Lauf“.
  - In der Mitte das SVG-Diagramm des gewählten Laufs:
    - Knoten nach Phase eingefärbt
    - Haltepunkte als Raute
    - aktive Knoten pulsieren
    - schon gelaufene Knoten gefüllt
    - Rückkanten gestrichelt
  - Rechts die Details:
    - Status und Runde
    - je Haltepunkt das passende Formular: Fragen mit Textfeld; Spec-Freigabe mit aufklappbarer Spec, Tests und
      Prüfpunkten, Knöpfe freigeben / ändern / Tests nachbessern / abbrechen und Hinweisfeld; Plan-Freigabe mit
      Plan; Eskalation mit Befunden und weiter / annehmen / abbrechen
    - dazu der Verlauf mit Uhrzeiten
- Dunkles Leitstand-Design wie das Dashboard-Muster im Workspace. Keine Schrift vom Netz, Systemschriften.
- Abfrage einmal je Sekunde. Knöpfe sind gesperrt, solange eine Antwort unterwegs ist.

- [ ] Prüfen im echten Browser (Playwright-MCP, Screenshots nach `%TEMP%`) gegen einen Server mit Fake-Abhängigkeiten
  (`docs/lernpfad/leitstand_demo.py`, startet mit Fakes auf einem Temp-Datenordner):
  - Liste
  - Diagramm mit aktivem Knoten
  - alle vier Haltepunkt-Formulare
  - Start eines Laufs
  - eine abgelehnte Antwort zeigt den Grund
  - Konsole ohne Fehler
- [ ] **Commit.**

### Task 6: Port, Desktop-Symbol, Doku

- [ ] Freien Port mit `portwart frei 8790-8799` bestimmen und in `portwart/ports.toml` als Eintrag
  `projekt = "langgraph-lab-2"`, `zweck = "Leitstand"` eintragen. Commit in portwart `main`: eine reine
  Datenzeile, Merge nicht nötig. Danach `portwart pruefen` ausführen.
- [ ] `leitstand.cmd` im Projekt (startet `pythonw -m entwicklung leitstand`) und das Desktop-Symbol „Leitstand“
  (Verknüpfung per PowerShell `WScript.Shell`, wie der Puls).
- [ ] HOW-TO-USE: Abschnitt Leitstand. **Commit.**

### Task 7: Abnahme mit A5 im Leitstand, Lernnotizen, Codex, Gate

- [ ] **Step 1:** Leitstand starten, `A5` im Browser starten. Fragen, Spec- und Plan-Freigabe gibt **Dominic im
  Browser**. Vorher lese ich Spec, Tests und Plan und gebe ihm meine Einschätzung. Gemergt wird erst nach dem Gate.
- [ ] **Step 2:** Lernnotizen:
  - `docs/lernpfad/04b-plan-freigabe.md` (aus dem 4b-Plan, Task 5)
  - `docs/lernpfad/05-leitstand.md`: Checkpointer als Schnittstelle zwischen Prozessen, `Command(resume)` aus einer
    UI, Token gegen fremde Webseiten, `get_graph()` als Daten
- [ ] **Step 3:** Codex-Verifier (`high`) über die Diffs von 4b und 5, Befunde per TDD, Ledger nach `docs/`.
  **STUFEN-GATE (4b und 5).**
