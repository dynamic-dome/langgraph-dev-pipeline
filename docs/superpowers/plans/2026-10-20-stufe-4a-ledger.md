# SDD ledger — plan: docs/superpowers/plans/2026-10-20-stufe-4a-klaeren-spec.md

Setup: Arbeit auf main von Lab 2 wie in Stufe 1–3 (Lernrepo, kein Remote); Spec docs/specs/2026-10-19-entwicklungs-pipeline-design.md gelesen.
Pre-flight: T1 strukturiert (claude_strukturiert/codex_strukturiert) -> T4 Abhaengigkeiten.planer/planer_codex: Signatur (name, prompt, cwd, schema, …) gleich. T2 planung (Schemas, Prompts, pruefe_akzeptanz, lege_ab) -> T4 Knoten. T3 state/speicher (WARTEPUNKTE, wartepunkt, wartende_laeufe(cp, graph_fuer)) -> T4 Graph, T5 CLI (fortsetzen nach metadata.stufe, _wartende_worktrees). Konsistent.
Task 1: complete (commits 63ccd6a..77e13f9, tests: .venv/Scripts/python.exe -m pytest -q tests/test_strukturiert.py tests/test_pruefer.py → 43 passed in 1.91s)
Task 2: Ruling: schnittstellen.modul ist der volle Modulname (portwart.drift) statt relativ zum Paket — Prüfung bleibt repo-unabhängig; Test angepasst — Kosten falls falsch: keine
Task 2: complete (commits 77e13f9..8df8235, tests: .venv/Scripts/python.exe -m pytest -q tests/test_planung.py tests/test_strukturiert.py → 33 passed in 5.72s)
Task 3: Ruling: stufe_des_laufs als eigene öffentliche Funktion in speicher (vom Plan nicht genannt) — CLI braucht die Stufe auch zum Fortsetzen; cli._graph_fuer baut je Stufe einmal — Kosten falls falsch: keine
Task 3: complete (commits 8df8235..e7bc692, tests: .venv/Scripts/python.exe -m pytest -q tests/test_speicher.py tests/test_state.py tests/test_cli_s3.py → 20 passed in 139.11s (0:02:19))
Task 4: Ruling: eigene Felder freigabe (statt entscheidung) und planung_fehler (statt agent) — sonst zeigte der Bericht „Entscheidung an der Eskalation: freigeben“ bzw. einen Klärer-Fehler als Implementierer-Fehler — Kosten falls falsch: keine
Task 4: Ruling: akz_probe zählt nur ({erwartet, gesammelt, bestanden}), keine Namen der gegen main grünen Tests — Testlauf liefert keine Namen (Plan erlaubte das); Testnamen der Datei per ast in der Freigabe — Kosten falls falsch: Dominic sieht nicht, welche Tests schon grün sind
Task 4: Ruling: Umsetzungsteil von S3 als graph.umsetzung_s3(g, bausteine) herausgezogen, S3 und S4 nutzen ihn — S3-Tests grün — Kosten falls falsch: keine
Task 4: Ruling: Planungsagenten nutzen state.pruefer_modell (Standard sonnet) — kein eigener CLI-Schalter — Kosten falls falsch: ein Schalter mehr später
Task 4: Ruling: resume={} feuert die Originalfrage ohne Hinweis (LangGraph 1.2.10, wie Stufe 3); Tests prüfen den Hinweis nur bei echten ungültigen Antworten
Task 4: Ruling: bericht._liste verträgt None (Lauf endet in der Planung, vor geaenderte_dateien) — vorgezogen aus Task 5, weil der Bericht sonst abstürzt
Task 4: Mutationsprobe: Probe-Prüfung abgeschaltet → test_probe… rot; erzeugter Ordner nicht im Testlauf → test_freigeben… rot; zurückgesetzt.
Task 4: complete (commits e7bc692..95a4c1c, tests: .venv/Scripts/python.exe -m pytest -q tests/test_graph_s4.py tests/test_graph_s3.py → 35 passed in 301.99s (0:05:01))
Task 5: Ruling: S3-CLI-Tests ausdrücklich auf --stufe 3 (Standard ist jetzt 4; ohne Angabe griff die Testsperre gegen echte Planungsagenten) — wie bei Stufe 2 — Kosten falls falsch: keine
Task 5: Ruling: zusätzlicher Test test_fortsetzen_ohne_angabe und test_akzeptanz_fehler_symbol; Live-Meldung „⏸ wartet auf dich“ statt „auf deine Entscheidung“ (auch Fragen) — Kosten falls falsch: keine
Task 5: complete (commits 95a4c1c..10835b9, tests: .venv/Scripts/python.exe -m pytest -q → 240 passed in 697.21s (0:11:37))
Task 6 Step 1: Wunsch A4 committet (655d681).
Task 6 Step 2: Live A4 lauf-20261020-120157: klaeren 5 Fragen (Zuordnung Ordner=Projekt, Dateien, Muster, Abweichung, Ausgabe/Exit) → Dominic: Voreinstellungen, + arbeit/.pytest_cache; Pfad je Eintrag später (A5). Spec 3 Module/10 Annahmen, 26 Tests, Probe „25 von 26 rot“ (falsch, s. u.), Spec-Prüfer claude 4 / codex 5 Punkte, alle minor. Dominic: freigeben. Umsetzung: R0 Akz 88/89 + codex 4 → R1 → R2 nur noch der übersprungene Symlink-Test → Eskalation, Dominic: annehmen (🟡).
Task 6: Ruling: Live-Anzeige stürzte an pruefen_spec_* ab (KeyError, Zweig pruefen_* zu weit) — behoben mit test_live_zeigt_planung (9b6aa0a); abgebrochener Lauf per invoke(None) aus dem Checkpoint wieder aufgenommen, vorher an DB-Kopie mit gesperrten Agenten geprüft (Writes der Spec-Prüfer wiederverwendet, kein Agent neu)
Task 6: Ruling: erste Probe der Wiederaufnahme schrieb einen falschen grenzverletzung-Bericht in die echten berichte/ (nur data umgeleitet) — eigenes Artefakt nach %TEMP%/lab2_probe_bericht verschoben; Grenzverletzung kam von meiner Korrektur in Lab 2 während der Pause (Commit stellte sauberen Stand her)
Task 6: Ruling: übersprungene Akzeptanztests: Testlauf zählt akzeptanz.uebersprungen, Funktionsprüfer nennt sie, Probe lehnt Tests mit Skip ab, Test-Prompt verbietet skip/skipif (monkeypatch statt Skip) — Lauf hatte 2 Fix-Runden an einem unbehebbaren Skip verbraucht — Kosten falls falsch: plattformabhängige Tests müssen simuliert werden
Final: Codex-Verifier (high) über 63ccd6a..e02d819: 9 Befunde (6 major, 3 minor). Behoben in 0a48daa:
Final: fixed F4 Setup-Fehler galt in der Probe als rot — test_setup_fehler_im_akzeptanztest_gezaehlt, test_probe_setup_fehler_zaehlt_als_fehlversuch RED→GREEN
Final: fixed F5 Probe lief im Worktree des Implementierers — Probe in git-archive-Kopie (worktree.exportiere), test_probe_laeuft_ausserhalb_des_worktrees RED→GREEN
Final: fixed F1 erzeugte Tests unter berichte/ (git-ignoriert) veränderbar — sha256 bei umsetzung_starten, Vergleich vor jedem tests_ausfuehren, test_veraenderte_erzeugte_tests_sind_grenzverletzung RED→GREEN
Final: fixed F2 importlib/__import__/eval/.__globals__ umgingen die Importprüfung — test_dynamische_zugriffe_abgelehnt (6 Fälle) RED→GREEN
Final: fixed F7 alte akz-Felder nach aendern — test_aendern_mit_gescheiterten_tests_laesst_keine_alten_stehen RED→GREEN
Final: fixed F8 ungültige Angabe an fortsetzen gab Exit 1 statt 3 (Plan: 3 solange wartend) — CLI-Tests angepasst RED→GREEN
Final: Ruling: F3 (Import in Hilfsfunktion, auf Modulebene mit try/except aufgerufen) nicht behoben — verlangt absichtliche Trickserei eines mitarbeitenden Agenten, Dominic sieht die Tests — Kosten falls falsch: Zielcode läuft schon beim Sammeln
Final: Ruling: F6 (Fix-Prompt enthält Testauszug mit assert-Zeilen) bleibt — seit Stufe 3 so gewollt (Auszug wie im CI, Testdateien selbst unsichtbar) — Kosten falls falsch: Implementierer sieht einzelne erwartete Werte
Final: Ruling: F9 (keine Namen der gegen main grünen Tests) bleibt wie in Task 4 entschieden — Testlauf liefert nur Zahlen — Kosten falls falsch: Dominic sucht den grünen Test selbst
Final: minor (deferred): Live-Anzeige zeigt beim Wiederaufnehmen „✓ __metadata__“-Zeilen (gecachte Writes)
Final: minor (deferred): ausgeführter Testcode des Implementierers kann die erzeugten Tests unter berichte/ lesen (erst Sandbox verhindert das)
Final: suite 256/256 (543 s), sqlite-schema-guard PASS, echte data/checkpoints.db zuletzt 12:50:51 (= annehmen-Bericht), von den Suiten unberührt.
Task 6: Echteinsatz drift (lesend, Worktree-Code, echte ports.toml): über den ganzen Arbeitsordner nach 180 s abgebrochen (zu groß, Spec ohne Vorgabe zu Größe/Laufzeit, Klärer fragte nicht danach); eingetragene Projekte (job-radar, tool-tracker …) liegen nicht unter dem durchsuchten Ordner → bestätigt A5 (Pfad je Eintrag).
Gate Stufe 4a (20.10., Dominic): abgenommen; A4 per Fast-Forward nach portwart/main (72f9042, 78 eigene Tests grün); weiter mit 4b (Plan, Plan-Prüfung, Freigabe, dazu Weg „nur Tests nachbessern“), Übungsaufgabe A5.
