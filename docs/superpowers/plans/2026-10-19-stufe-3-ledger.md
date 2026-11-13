# SDD ledger — plan: docs/superpowers/plans/2026-10-19-stufe-3-fix-schleife.md

Pre-flight: T1 speicher -> T4 cli; T2 reducer/fix_prompt -> T3 graph; T3 graph -> T4 cli. Konsistent.
Ruling: A2-Lauf 20261019-220447 gruen, aber fix_noetig (major/test-gap) -> nicht gemergt; A2 wird mit Stufe 3 erneut gebaut (Merge-Freigabe Dominic: gruen ohne Fix-Bedarf).
Task 1: complete (commits 5d70b66..d5e5276, tests: .venv/Scripts/python.exe -m pytest -q → 138 passed in 120.05s (0:02:00))
Task 2: complete (commits d5e5276..9cdafdf, tests: .venv/Scripts/python.exe -m pytest -q → 141 passed in 125.92s (0:02:05))
Task 3: Ruling: eskalation stellt genau ein interrupt je Durchlauf und laeuft bei ungueltiger Antwort ueber eine Kante zu sich selbst zurueck — gemessen: zweites interrupt im selben Knoten laesst get_state().next leer (LangGraph 1.2.10), wartender Lauf saehe fertig aus — Kosten falls falsch: keine.
Task 3: Ruling: Command(resume=None) stuerzt in LangGraph 1.2.10 ab (UnboundLocalError in _loop._first); CLI schickt immer ein dict, Testfall None gestrichen und dokumentiert. resume={} zaehlt nicht als Antwort (interrupt feuert mit Originalfrage).
Task 3: Ruling: geaenderte_dateien jetzt kumulativ seit basis (worktree.dateien_seit), Pruefer-Diff/Filter gegen HEAD statt sicherung (Runde ohne Aenderung haette sonst basis genutzt) — Kosten falls falsch: keine.
Task 3: complete (commits 9cdafdf..daaad39, tests: .venv/Scripts/python.exe -m pytest -q → 153 passed in 235.68s (0:03:55))
Task 4: Ruling: S2-CLI-Tests ausdruecklich auf --stufe 2 (Standard ist jetzt 3). Endstand nach Lauf immer aus dem Checkpointer (get_state + offene interrupts), damit live und still gleich ausgewertet werden.
Task 4: complete (commits daaad39..387026d, tests: .venv/Scripts/python.exe -m pytest -q → 162 passed in 362.12s (0:06:02))
Task 5: A3 + Akzeptanztests committet (aufgaben/portwart/A3); gegen main mit A2: A3 25/26 rot (Regressionstest gruen), A1 19/19, A2 16/16.
Task 6 Step 1: A2 mit Stufe 3 (lauf-20261019-225129): Runde 0 gruen, 1 ausloesender Befund (clean_code major/test-gap: lies_netstat-Garantie ungetestet) -> Fix-Runde 1: +tests/test_lauschen.py (9 Tests, u. a. which verboten) -> gruen 63/63, Akzeptanz 35/35, 0 ausloesend. Per Fast-Forward nach portwart/main (2353b83), Freigabe Dominic 19.10.
Task 6 Step 2: A3 Abnahmelauf (lauf-20261019-225712): Runden 0-2 je gruen, ausloesend codex (-1-5; '--' und lange Ziffernfolge) und clean_code (netstat-Lesecode doppelt) -> Eskalation, Dominic: weiter -> Runde 3 gruen 96/96, Akzeptanz 61/61, neuer clean_code major (main() argv-Sonderfall) -> Eskalation, Dominic: annehmen (🟡). Nicht gemergt (Gate).
Task 6: Ruling: Lernnotiz nennt recursion_limit 10007 (LangGraph 1.2.10, _internal/_config.py, je Aufruf) statt der Tutorial-Zahl 25 — gemessen im installierten Paket — Kosten falls falsch: eine Zeile Doku.
Task 6 Step 3: Lernnotiz 03 + HOW-TO-USE Stufe 3 committet (8f8a866).
Final: Codex-Verifier (high) ueber 5d70b66..8f8a866: 6 Befunde (3 major, 3 minor), alle bestaetigt und behoben in b66e2bd:
Final: fixed S3-002 wartende_laeufe nahm next statt offenem interrupt — test_geplante_eskalation_ohne_interrupt_wartet_nicht RED→GREEN
Final: fixed S3-003 aufraeumen entfernte Worktree eines wartenden Laufs — test_aufraeumen_behaelt_wartenden_lauf RED→GREEN
Final: fixed S3-001 thread_id nicht atomar (zwei Laeufe je Sekunde) — Tabelle reservierung (PRIMARY KEY) in checkpoints.db, test_freie_thread_id_reserviert_ohne_checkpoint RED→GREEN
Final: fixed S3-004 Fix-Runde mit fruehem Abbruch zeigte alte Tests/Befunde — test_abbruch_in_fix_runde_zeigt_keine_alten_ergebnisse RED→GREEN
Final: fixed S3-005/006 A3-Akzeptanz ohne -5-10 (CLI) und ohne Standardpfad lies_netstat — 26→28 Tests; Gegenprobe: Runde-0-Stand d1b3140 faellt nur an -5-10, faule Variante nur am Standardpfad; angenommener Stand lauf/20261019-225712 28/28, main 27/28 rot
Final: Ruling: Lernnotiz zu Falle 1 nachgemessen (20.10.): nach zweitem interrupt ist next leer, tasks zeigt das interrupt weiter — Text korrigiert, Self-Loop bleibt (next soll stimmen) — Kosten falls falsch: keine
Final: suite 166/166 (344.9 s), sqlite-schema-guard PASS, echte data/checkpoints.db unveraendert
Gate Stufe 3 (20.10., Dominic): abgenommen; A3 per Fast-Forward nach portwart/main (7cea75f, 35 eigene Tests gruen); Fix-Regel jetzt schaerfen, Schiedsrichter-Knoten in Stufe 6.
Nachtrag: Fix-Regel — Clean-Code-major (candidates) loest nur mit zweiter Stimme (security/codex, gleiche Datei, <=3 Zeilen, Topf candidates/side) aus, sonst gebremst (15e413c). Rueckblick auf echte Laeufe (DB-Kopie): A2 R0 bleibt 1, A3 R0/R1 bleiben 1/2, A3 R2/R3 1->0 (A3 waere nach Runde 2 gruen geendet).
Nachtrag: Codex-Verifier (high) 4 Befunde, alle behoben in acf4888: F1 Dublette ohne belegtes Zitat galt als zweite Stimme, F3 Stimme ging bei Dublette mit Funktion verloren — Regel laeuft jetzt auf Rohbefunden vor dem Zusammenfuehren; F2 line None -> TypeError, line 0 bestaetigte — nur int > 0; F4 Lernnotiz zu weit. Tests RED→GREEN, suite 175/175, sqlite-schema-guard PASS.
Ruling: zusammengefuehrte Befunde: gebremst = (einer gebremst) und nicht ausloesend — ein ausloesender Mitbefund (z. B. codex major gleicher Wortlaut) hebt die Bremse auf — Kosten falls falsch: ein Befund falsch markiert, fix_noetig bleibt korrekt.
