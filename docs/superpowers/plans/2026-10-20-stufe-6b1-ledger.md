# SDD ledger — plan: docs/superpowers/plans/2026-10-20-stufe-6b1-familien-zweitmeinung.md

Setup: Arbeit auf main von Lab 2 wie bisher (Freigabe Dominic 20.10.: „Plan ansonsten okay“); kein Lauf aktiv (8790/8795 frei); sqlite-schema-guard PASS.
Pre-flight: T1 codex_einwaende, begruendung, einwand_fehlt, einwand_freigaben -> T4 einwaende_fuer, Server/CLI; T3 hole_rat(wer), vergleiche, einwaende_aus_raeten -> T4; T4 Endpunkte -> T5 Oberfläche. Konsistent.
Pre-flight: Ruling: Dominic 20.10.: Astra-Quellen bleiben eingebettet; Austausch später („Astra liest selbst“, z. B. unter Linux) nur über quelldateien + Abhaengigkeiten.berater_astra — Kosten falls falsch: bei großen Repos sieht Astra zu wenig, bis der Weg gebaut ist.
Task 1: complete (commits f3972d4..f428a7a, tests: pytest -q → 389 passed)
Task 2: Ruling: Frühabbruch nur für Prüfer-Befunde (topf != deterministisch), nicht für rote Tests — gemessene rote Tests kann die Fix-Runde mit Testauszug beheben; bestehende Tests (FALSCH dreimal) verlangen das — Kosten falls falsch: ein wiederholt roter Test kostet weiter bis max_runden Runden.
Task 2: Ruling: kind statt Pfad für den zweiten Befund im Test (ANDERS) — Pfad tests/test_mathe.py wäre evtl. nicht als geändert gefiltert worden — Kosten: keine.
Task 2: complete (commits f428a7a..af8a6c7, tests: pytest tests/test_graph_s3.py tests/test_graph_s4.py → 66 passed; ganze Suite folgt nach Task 3)
Task 3: complete (commits af8a6c7..41aedae, tests: pytest tests/test_berater.py → 27 passed; ganze Suite folgt nach Task 4)
Task 4: Ruling: GET /rat neue Form {fable, astra, vergleich}; bestehende 6a-Tests darauf umgestellt, Dateiname rat-<punkt>-<wer>-<n>.json, CLI-Ausgabe „Fable empfiehlt:“ statt „Empfehlung:“ — Plan legt die Form fest — Kosten: keine (nur interne Nutzer).
Task 4: Ruling: leere Quellen werden Astra ausdrücklich gesagt (test_astra_prompt_ohne_passende_quellen RED→GREEN) — an der Spec-Freigabe gibt es neue Module im Worktree oft noch nicht — Kosten: keine.
Task 4: complete (commits 41aedae..4f11d3a, tests: leitstand_*/cli_s4 → 63 passed, berater → 28 passed; ganze Suite läuft)
Suite nach Task 4: pytest -q → 413 passed (14:29).
Task 5: Browser-Prüfung an der Demo (8795): Einwand-Kasten sofort sichtbar, Freigeben ohne Begründung blockiert, Beide fragen → rote Leiste uneinig, Astra vorbelegt, <img onerror> als Text (0 img), Freigeben mit Begründung → Plan-Freigabe, Bericht „Freigaben trotz Einwand“ mit 3 Einwänden; Konsole 0 Fehler; Testfenster geschlossen, Demo-Prozess beendet. Screenshot %TEMP%/lab2-6b1-uneinig.png.
Task 5: Ruling: Einwand-Kasten in eigenem Platz (#einwandplatz) statt im Formular — sonst baute ein neuer Einwand das Formular neu und Getipptes ginge verloren — Kosten: keine.
Task 5: complete (commits 4f11d3a..01223b2, tests: node --check + Browser-Prüfung; Suite 413 passed)
Task 6: Ruling: Doku vor dem A7-Lauf committet, Abnahme-Tabelle folgt nach dem Lauf; A7-Wortlaut ist Entwurf und braucht Dominics Bestätigung — Kosten: ein weiterer Doku-Commit.
Final review: Codex-Verifier (high, codex exec read-only, Prompt 309k Zeichen) → FAIL, 3 major, 2 minor.
Final: fixed F-001 Fortsetzen nicht atomar an Stand gebunden — test_fortsetzen_nur_fuer_erwarteten_stand RED→GREEN (StandGeaendert unter der Ausführer-Sperre, Server übergibt erwartet).
Final: fixed F-002 Graph prüfte mitgebrachte Einwände nicht — test_mitgebrachte_einwaende_brauchen_begruendung RED→GREEN.
Final: fixed F-003 Vorbelegung behielt Text des schnelleren Beraters — Browser-Demo RED (2×: Fable-Hinweis bei vorbelegt Astra) → GREEN (Astra-Hinweis; eigener Text bleibt); Demo rät jetzt Fable tests_nachbessern mit Hinweis.
Final: fixed (eigener QA-Fund) Browser nahm nach Update altes app.js aus dem Cache — test_seite_und_dateien_ohne_cache RED→GREEN (Cache-Control: no-cache außer /api).
Final: Suite 415/415 nach F-001..F-003 (17:28); danach Server-Tests 19/19 mit Cache-Fix.
Final: minor (deferred): F-004 einwand_freigaben fehlt in JSON_FELDER (nur Markdown-Bericht enthält sie).
Final: minor (deferred): F-005 Kürzungsvermerk überschreitet MAX_QUELLEN um ~60 Zeichen.
Task 6: Abnahme A7 (Lauf 20261020-213457): 🟢 Runde 0, 436/436, Akzeptanz 243/243; 4 Haltepunkte, alle Paare einig; Codex-major an Spec 1 von beiden als echt bestätigt → aendern; Sperre/Frühabbruch nicht ausgelöst (kein Anlass). Gegenprobe selbst: 193 Tests grün, eintragen an Kopie der ports.toml (Eintrag, doppelter Name rc 2, Port 70000 rc 2). Task 6: complete (commit d79635c).
Gate 6b-1 (Dominic 20.10.): A7 per Fast-Forward nach portwart/main (61ad596); A7-Tests in aufgaben/portwart/A7 (291cde9), A1–A7 + eigene gegen main 436/436, 0 übersprungen. Weiter mit Rest von 6b.
