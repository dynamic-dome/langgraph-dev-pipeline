# SDD ledger — plan: docs/superpowers/plans/2026-10-19-stufe-2-pruefungen.md

Pre-flight: T3 fuehre_tests_aus(akzeptanz_dirs) -> T6 graph; T4 pruefer-Adapter + funktion_bericht -> T5 sammle -> T6; T1-Spike kann Flags in T4 aendern. Konsistent.
Ruling: A1 per Fast-Forward in portwart/main (431be14), Entscheid Dominic 19.10.
Task 1: complete (commits 9d87776..013354a, tests: .venv/Scripts/python.exe -m pytest -q → 77 passed in 72.01s (0:01:12))
Task 2: Ruling: test_pruefen_aus_a1_unveraendert ist gegen main bereits gruen (bewusster Regressionstest), A2 sonst 14/15 rot, A1 19/19 gruen — Kosten falls falsch: keine.
Task 2: complete (commits 013354a..a49834c, tests: .venv/Scripts/python.exe -m pytest -q → 77 passed in 69.89s (0:01:09))
Task 3: complete (commits a49834c..e5baa41, tests: .venv/Scripts/python.exe -m pytest -q → 82 passed in 75.69s (0:01:15))
Task 4: Ruling: Testsperre der Pruefer nutzt agenten._TESTSPERRE/EchterAgentImTest mit (conftest unveraendert) — eine Sperre fuer alle echten Agenten — Kosten falls falsch: keine.
Task 4: complete (commits e5baa41..ab22507, tests: .venv/Scripts/python.exe -m pytest -q → 105 passed in 81.05s (0:01:21))
Task 5: Ruling: sammle() liefert zusaetzlich nicht_pruefbar (not_checkable der Pruefer) und je Befund ausloesend — fuer Bericht und Stufe 3 — Kosten falls falsch: keine.
Task 5: complete (commits ab22507..c29023c, tests: .venv/Scripts/python.exe -m pytest -q → 117 passed in 82.06s (0:01:22))
Task 6: Ruling: tests_ausfuehren (S2) vergleicht danach die geschuetzten Repos erneut (Testcode des Agenten laeuft dort) -> grenzverletzung "Testlauf: ..." und keine Pruefer; Snapshot stand_vor_pruefern inkl. Worktree fuer die Pruefer-Nachkontrolle — schliesst einen Teil der bekannten Luecke — Kosten falls falsch: keine.
Task 6: Ruling: S1-CLI-Tests explizit auf --stufe 1 gesetzt (Standard ist jetzt 2, sonst wuerde die Testsperre der echten Pruefer greifen).
Task 6: complete (commits c29023c..3204fd1, tests: .venv/Scripts/python.exe -m pytest -q → 128 passed in 124.79s (0:02:04))
Task 7: Live-Lauf A2 (20261019-211528) gruen 53/53, Akzeptanz 34/34 (A1+A2), 4 Pruefer parallel (Start 49,2 s, Ende = Start + Dauer), 6 minor-Befunde, keine Fix-Runde; Befund netstat-datei "" an der Quelle bestaetigt; abgleich gegen echtes netstat: 25 unbekannte Ports.
Final review: Codex-Verifier (high), 5 Befunde, alle an der Quelle geprueft und echt.
Final: fixed Testcode veraendert Worktree nach Sicherung — test_testcode_veraendert_worktree RED→GREEN
Final: fixed Filter-Timeout bricht Graph ab — test_filter_timeout_ist_nicht_verwertbar RED→GREEN
Final: fixed vom Filter verworfener Bericht als PASS angezeigt, schema_ok zu flach — test_vom_filter_verworfener_bericht_ist_nicht_pass, test_schema_ok_streng RED→GREEN
Final: fixed A2-Akzeptanz: which-Patch umgehbar, lies_netstat ungetestet — PATH-Isolation + Ersatz-netstat.bat (2 neue Tests); Pipeline-Ergebnis A2 besteht 36/36; suite 134/134
Task 7: complete (commits 3204fd1..dffade0, tests: .venv/Scripts/python.exe -m pytest -q → 134 passed in 130.59s (0:02:10))
