# SDD ledger — plan: docs/superpowers/plans/2026-10-20-stufe-5-leitstand.md

Setup: Arbeit auf main von Lab 2 wie bisher; Spec docs/specs/2026-10-19-entwicklungs-pipeline-design.md. Ziel laut Dominic: lauffähiger Prototyp, später von der Pipeline selbst erweiterbar.
Pre-flight: T1 steuerung.antwort_fuer -> T4 Server + CLI; T2 daten (graph_daten, lauf_daten, laeufe) -> T4/T5; T3 Ausfuehrer -> T4; T4 API -> T5 Oberfläche; T6 Port -> T4 CLI-Standardport. Konsistent.
Task 1: Ruling: venv ohne pip (uv) — Installation per uv pip install; fastapi zog opentelemetry-api mit (im Lock vermerkt) — Kosten falls falsch: keine
Task 1: complete (commits b329feb..6d91e57, tests: .venv/Scripts/python.exe -m pytest -q tests/test_steuerung.py tests/test_cli_s4.py → 38 passed in 61.99s (0:01:01))
Task 2: Ruling: Verlauf aus get_state_history (next je Checkpoint mit Zeitstempel = Start eines Schritts), ohne den Eingabe-Checkpoint __start__ — Kosten falls falsch: Dauer je Knoten nur indirekt
Task 2: complete (commits 6d91e57..d98baac, tests: .venv/Scripts/python.exe -m pytest -q tests/test_leitstand_daten.py → 5 passed in 13.67s)
Task 3: Ruling: Leitstand startet nur Stufe 3 und 4 (nur sie haben Gedächtnis und Haltepunkte); Graphen eigene Tabelle statt cli.STUFEN (sonst Importkreis cli ↔ leitstand) — Kosten falls falsch: keine
Task 3: complete (commits d98baac..0252307, tests: .venv/Scripts/python.exe -m pytest -q tests/test_leitstand_ausfuehrer.py → 5 passed in 9.54s)
Task 4: Ruling: baue_app bekommt repos_dir (Standard Lab-2-Ordner), damit Tests Temp-Repos nutzen; /docs und /openapi abgeschaltet (keine unnötige Angriffsfläche); unbekannter Lauf 404, wartet nicht oder belegt 409 — Kosten falls falsch: keine
Task 4: complete (commits 0252307..0409eb3, tests: .venv/Scripts/python.exe -m pytest -q tests/test_leitstand_server.py tests/test_steuerung.py → 42 passed in 15.55s)
Task 5: Browser-Prüfung (Playwright, Demo mit Fakes, Port 8795): Start, Rückfragen (leere Antwort abgelehnt), Spec-Freigabe (ändern ohne Hinweis abgelehnt), Plan-Freigabe, Umsetzung bis 🟢, Stufe-3-Lauf bis Eskalation, Annehmen → 🟡; F5; Konsole ohne Fehler. Screenshots %TEMP%/leitstand_*.png.
Task 5: Ruling: Token nur für /api verlangt, Seite und Dateien frei — Neuladen (F5) gab sonst 403, weil das Token aus der Adresszeile entfernt wird; Seite enthält keine Daten, alle Daten und Aktionen über /api mit Token-Header; Host-/Origin-Prüfung gilt weiter überall — Kosten falls falsch: wer den Port kennt, sieht eine leere Oberfläche
Task 5: Ruling: Abbruchkanten (bedingt → bericht, außer von befunde_sammeln/eskalation) blass; „gegangen“ aus aufeinanderfolgenden Verlaufsschritten statt „beide Enden erledigt“ — sonst leuchteten nie gegangene Abbruchwege
Task 5: Ruling: replaceChildren macht aus null den Text „null“ — Helfer fuelle() filtert; Meldung zur vorigen Antwort wird beim neuen Haltepunkt gelöscht
Task 5: complete (commits 0409eb3..6f9f746, tests: .venv/Scripts/python.exe -m pytest -q tests/test_leitstand_server.py tests/test_leitstand_daten.py tests/test_leitstand_ausfuehrer.py → 25 passed in 39.51s)
Task 6: Port per portwart frei 8790-8799 → 8790, eingetragen in portwart/ports.toml (portwart main baf8a50); Desktop-Symbol Leitstand.lnk → leitstand.cmd (minimiert, Fenster schließen beendet Server). Rauchtest echter Leitstand: Seite 200, API ohne Token 403, fremde Herkunft 403, echte Läufe A4/A3/A2 gelistet, A4 im Diagramm mit Verlauf.
Task 6: Ruling: Server in sichtbarem, minimiertem Fenster statt unsichtbar (pythonw) — so lässt er sich ohne Taskmanager beenden — Kosten falls falsch: ein Fenster in der Taskleiste
Task 6: Ruling: „angenommen“ in der Oberfläche bernsteinfarben (wie 🟡) statt rot — Kosten falls falsch: keine
Task 6: complete (commits 6f9f746..e2d15ec, tests: .venv/Scripts/python.exe -m pytest -q tests/test_leitstand_server.py → 15 passed in 15.02s)
Vor Abnahme: suite 335/335 (736 s), echte DB unberührt, git sauber.
Final: Codex-Verifier (high) über 7280314..01f44f8 (4b + 5): 9 Befunde. Behoben in 1875b30:
Final: fixed L2-002 veraltete Freigabe (zweiter Tab) traf den nächsten Haltepunkt — Antwort trägt haltepunkt + checkpoint_id, Server 409 bei Abweichung; test_veraltete_antwort_409 RED→GREEN, im Browser bestätigt
Final: fixed L2-003 Laufwechsel während Klick — Antwort an den angezeigten Lauf, verspätete Detailantworten verworfen, Formular beim Wechsel sofort weg (Browser; Server-Prüfung aus L2-002 sichert zusätzlich)
Final: fixed L2-004 Junction/Symlink unter Lab 2 auf Repo außerhalb — nicht angeboten, Start 400; test_junction_ausserhalb_wird_nicht_angeboten RED→GREEN
Final: fixed L2-005 Läufe aus 4a ohne plan_runde — test_alter_lauf_ohne_plan_runde RED→GREEN
Final: fixed L2-006 Test band echten Socket — Fake-Socket per monkeypatch
Final: fixed L2-007 Haltepunkt und Frage aus zwei Schnappschüssen (500 beim Wechsel) — test_checkpoint_id_und_frage_aus_einem_schnappschuss RED→GREEN
Final: Ruling: L2-001 (CLI und Leitstand setzen denselben Lauf gleichzeitig fort) nicht behoben — braucht Sperre über Prozessgrenzen, gehört zu Stufe 6 (Wiederaufnahme); Einzelnutzer — Kosten falls falsch: doppelte Ausführung im selben Worktree
Final: Ruling: L2-009 --port darf vom Eintrag abweichen — gewollt (belegter Port, Tests) — Kosten falls falsch: keine
Final: minor (deferred): L2-008 nach gescheitertem tests_nachbessern bleiben Testordner/Probe der vorigen Fassung als Ergebnisfelder
Final: suite 339/339 (795 s), echte DB unberührt.
Nachtrag (Dominic 20.10.): Demo-Leitstand im sichtbaren Playwright-Fenster für echten Lauf gehalten — Verbindungsverlust jetzt als deutlicher Hinweis mit gesperrten Knöpfen, Demo unübersehbar gekennzeichnet (/api/info, test_info_kennzeichnet_demo), Testfenster nach Prüfungen schließen (Memory).
Task 7: Abnahme A5 im Leitstand (lauf-20261020-164410): 5 Fragen (Antwort 3 von Dominic geändert: pfad-fehlt als Befund), Spec Fassung 1 mit kaputtem Test (Claude+Codex) → aendern, Fassung 2 freigegeben, Plan freigegeben, Umsetzung R0 grün + 1 auslösend (PermissionError beim Iterieren) → R1 grün, 232 Tests, Akzeptanz 123/123. Echteinsatz: 0,4 s, pfad-fehlt korrekt, 201/204 unbekannt aus berichte/docs (A6: Ausschlüsse). Lernnotizen 04b + 05 committet.
Gate 4b+5 (20.10., Dominic): abgenommen; A5 per Fast-Forward nach portwart/main (db49f35, 109 eigene Tests grün); A5-Akzeptanztests unverändert nach aufgaben/portwart/A5/ (A1–A5 gegen main 123/123, 0 übersprungen). Weiter: Stufe 6 mit Hilfe-Knopf (Fable an den Haltepunkten).
