# SDD ledger — plan: docs/superpowers/plans/2026-10-20-stufe-6a-fable-berater.md

Setup: Arbeit auf main von Lab 2 wie bisher; Spec docs/specs/2026-10-19-entwicklungs-pipeline-design.md; Entscheide Dominic 20.10. (Fable berät, Dominic klickt; 6a vor 6b). CLI-Alias --model fable vorhanden (claude --help).
Pre-flight: T1 berater (RAT_SCHEMA, berater_prompt, rat_pruefen, hole_rat, Abhaengigkeiten.berater) -> T2 Ausfuehrer.frage_rat/rat, Endpunkte, CLI rat, Bericht; T2 Endpunkte -> T3 Oberfläche. Konsistent.
Task 1: Ruling: hole_rat liefert zusätzlich grund (Rat geliefert, aber am Haltepunkt nicht verwertbar) neben fehler (kein Rat) — Oberfläche muss beides unterscheiden — Kosten falls falsch: keine
Task 1: complete (commits aecb94e..43ca61b, tests: .venv/Scripts/python.exe -m pytest -q tests/test_berater.py → 17 passed in 0.61s)
Task 2: Ruling: Nachkontrolle als graph_s4.planung_sauber herausgezogen (Planung und Berater nutzen sie); rat_fuer_lauf gemeinsam für Leitstand (Thread) und CLI (blockierend) — Kosten falls falsch: keine
Task 2: Ruling: CLI-Testfall statt in test_cli_s4.py in test_leitstand_rat.py (gemeinsamer Fake-Fable) — Kosten falls falsch: keine
Task 2: complete (commits 43ca61b..b0dbbf2, tests: .venv/Scripts/python.exe -m pytest -q tests/test_leitstand_rat.py tests/test_berater.py tests/test_leitstand_server.py → 43 passed in 50.10s)
Task 3: Browser-Prüfung (Demo, Fake-Fable 4 s): Rat an fragen (Antwort vorausgefüllt, übernommen), spec (Freigeben, übernommen), plan (Ändern + Hinweis vorausgefüllt, Dominic-Klick „Freigeben“ dagegen), Lauf grün, Konsole ohne Fehler, Testfenster geschlossen.
Task 3: Ruling: Rat zu einem anderen Haltepunkt wird nicht angezeigt (nur „veraltet“ bei gleichem Haltepunkt mit anderem Stand) — sonst stand der Rat der Rückfragen an der Spec-Freigabe; GET /rat ohne Rat 204 statt 404 (kein Konsolenfehler) — Kosten falls falsch: keine
Task 3: Ruling: Eskalation im Browser nicht eigens durchgespielt (Formular-Code gemeinsam, Rat-Karte identisch; Server-Test deckt Haltepunkte ab) — Kosten falls falsch: Darstellungsfehler nur an der Eskalation
Task 3: complete (commits b0dbbf2..0abaf74, tests: .venv/Scripts/python.exe -m pytest -q tests/test_leitstand_rat.py tests/test_leitstand_server.py → 26 passed in 45.56s)
Final: Codex-Verifier (high) über aecb94e..415a863: 8 Befunde (alle major), behoben in 011d499:
Final: fixed F-008 Fable sah an Plan-Freigabe weder Spec noch Tests, an Eskalation weder Spec noch Plan — test_plan_und_eskalation_sehen_spec_tests_plan RED→GREEN
Final: fixed F-003 Rat-Thread band sich an späteren Stand — rat_fuer_lauf(erwartet=…), test_rat_bindet_sich_nicht_an_spaeteren_stand RED→GREEN
Final: fixed F-005 Nachkontrolle übersah tests/_akzeptanz/ — planung_sauber über alle Status-Einträge, test_nachkontrolle_sieht_akzeptanzordner RED→GREEN
Final: fixed F-001/F-002 CLI-Übernahmebefehl ungebunden und nicht shell-sicher — --haltepunkt/--stand in fortsetzen, PowerShell-Quoting mit einfachen Anführungszeichen; test_cli_rat_befehl_gebunden_und_shell_sicher, test_fortsetzen_mit_falschem_haltepunkt_oder_stand RED→GREEN
Final: fixed F-006 „Empfehlung übernehmen“ ignorierte eigene Textänderung — mitEigenemText (Browser: geänderte Antwort im Checkpointer bestätigt)
Final: fixed F-007 Knopf verschwand beim Laufwechsel — Rat-Schlüssel mit Lauf, Haltepunkt und Platz (Browser: Knopf an jedem Haltepunkt)
Final: fixed F-004 (teilweise) Rat-Dateien atomar mit open('x'); Ruling: gleichzeitige Räte aus CLI und Leitstand nicht gesperrt — Sperre über Prozessgrenzen in 6b — Kosten falls falsch: doppelter Fable-Aufruf
Final: suite 370 passed in 633.67s (0:10:33)
Task 4: Abnahme A6 (lauf-20261020-184036) im Leitstand mit Fable an jedem Haltepunkt: fragen antwort (73 s, lade()-Fallstrick), Spec 1 tests_nachbessern (110 s, unerfüllbarer Test ././a), Spec 2 freigeben (144 s, Idempotenz-Widerspruch als klein herabgestuft — falsch), Plan freigeben (52 s), Eskalation annehmen (35 s). Umsetzung: R0 Leerraum-Befund (echt), R1+R2 Idempotenz-Widerspruch aus der Spec (Codex major) → Eskalation, Dominic: annehmen 🟡. 346 Tests, Akzeptanz 198/198.
Task 4: Lehre (Dominic): gleiche Modellfamilie, gleicher blinder Fleck — Codex (GPT) meldete major, Claude-Prüfer/Fable/ich stuften herab. Nächste Priorität: Zweitmeinung aus der GPT-Familie („Astra fragen“) und Freigabe, die Familien-Uneinigkeit nicht still übergeht. Lernnotiz 06a committet.
Gate 6a (20.10., Dominic): abgenommen; A6 per Fast-Forward nach portwart/main (efa9d63, 148 eigene Tests grün); A6-Tests unverändert nach aufgaben/portwart/A6/ (A1–A6 gegen main 198/198). Weiter: Stufe 6b-1 Familien-Zweitmeinung (Astra = Codex-Standardmodell gpt-6.1-sol, high), Uneinigkeit als Halt mit Begründung, Frühabbruch bei wiederkehrendem Befund.
