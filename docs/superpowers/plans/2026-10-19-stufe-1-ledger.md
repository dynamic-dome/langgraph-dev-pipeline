# SDD ledger — plan: docs/superpowers/plans/2026-10-19-stufe-1-durchstich.md

Pre-flight: T4 worktree/stand -> T7 vorbereiten; T5 fuehre_tests_aus -> T7; T6 claude_implementierer -> T7: Signaturen konsistent. T3 Spike kann Flags in T6 aendern (Ruling dann im Ledger).
Task 1: Ruling: Testsperre fuer echte Agenten kommt erst mit agenten.py in Task 6 in die conftest (Modul existiert vorher nicht) — kein Risiko, vor Task 6 gibt es keinen Agentenaufruf — Kosten falls falsch: keine.
Task 1: complete (commits 06e6d60..edfc59f, tests: .venv/Scripts/python.exe -m pytest -q → 13 passed in 5.38s)
Task 2: Ruling: Hook blockt `git worktree remove --force` — Pipeline committet das Implementierer-Ergebnis selbst auf lauf/<id> (Agent bleibt ohne git), entfernen() ohne --force, Branch bleibt als Sicherung; gemessen: ignorierte Caches blockieren remove ohne force nicht — Kosten falls falsch: Worktree-Reste von Hand aufraeumen.
Task 2: Ruling: .gitignore-Eintraege auf Wurzel verankert (/portwart/ statt portwart/), sonst war aufgaben/portwart ignoriert. portwart-Grundgeruest liegt im eigenen Repo (64d9d4a); Akzeptanztests 19/19 rot gegen leeres portwart verifiziert.
Task 2: complete (commits edfc59f..06256ed, tests: .venv/Scripts/python.exe -m pytest -q → 13 passed in 0.12s)
Task 3: Ruling: Flag-Satz ergaenzt um --strict-mcp-config, --permission-mode acceptEdits, --output-format json, --max-turns 30 (Plan nannte nur Kern) — gemessen in 2 Laeufen, siehe docs/spike — Kosten falls falsch: Agent bricht frueh ab (max-turns) -> agent_fehler im Bericht.
Task 3: Ruling: Luecke "ausgefuehrter Testcode schreibt ueberall" bestaetigt (aussen2.txt existiert); Nachkontrolle traegt nur fuer portwart+Lab2; Dominic hat Sandbox auf spaeter gelegt -> beim Stufen-Gate prominent melden, nicht stoppen — Kosten falls falsch: Agent-Fehler koennte ausserhalb schreiben, unbemerkt.
Task 3: complete (commits 06256ed..3fd14b0, tests: .venv/Scripts/python.exe -m pytest -q → 13 passed in 0.11s)
Task 4: Ruling: stand() nimmt Inhalts-Hash mit auf und grenzverletzungen() meldet auch verschwundene Eintraege (Plan: nur neue/geaenderte) — sonst bleibt eine zweite Aenderung an einer schon dirty Datei unsichtbar — Kosten falls falsch: keine. Zusaetzlich sichern() (Ruling Task 2) und Guard: entfernen nur unter arbeit_dir.
Task 4: complete (commits 3fd14b0..0f2c610, tests: .venv/Scripts/python.exe -m pytest -q → 24 passed in 3.68s)
Task 5: Ruling: gruen verlangt zusaetzlich akzeptanz.bestanden == akzeptanz.gesammelt (ist durch fehlgeschlagen==0 schon impliziert, aber explizit) und Testlauf haengt -p no:cacheprovider + PYTHONDONTWRITEBYTECODE an (sonst ist der Worktree nicht ohne --force entfernbar) — Kosten falls falsch: Zielrepos ohne pytest brauchen spaeter einen anderen Testlauf.
Task 5: complete (commits 0f2c610..eb936d7, tests: .venv/Scripts/python.exe -m pytest -q → 38 passed in 32.19s)
Task 6: Ruling: Rueckgabe zusaetzlich turns + verweigerungen (aus permission_denials), MAX_TURNS 60 statt 30 aus dem Spike (A1 braucht mehr Runden als der Spike) — Kosten falls falsch: laengere Laufzeit bis agent_fehler.
Task 6: complete (commits eb936d7..efb16ad, tests: .venv/Scripts/python.exe -m pytest -q → 46 passed in 43.62s)
Task 7: Ruling: Abhaengigkeiten zusaetzlich jetzt/aufgaben_dir/weitere_geschuetzte (Tests brauchen festen Zeitpunkt und eigene Aufgaben) — Kosten falls falsch: keine.
Task 7: Ruling: Live-Lauf 1 (20261019-201510) endete mit grenzverletzung, Ursache war meine eigene HOW-TO-USE-Aenderung waehrend des Laufs (Nachkontrolle korrekt); Lauf 2 (20261019-201746) gruen 32/32, Akzeptanz 19/19, von Hand nachgeprueft. Dazu Fix: verweigerte Befehle im Bericht auf 1. Zeile/120 Zeichen gekuerzt (TDD).
Task 7: complete (commits efb16ad..e7f9e11, tests: .venv/Scripts/python.exe -m pytest -q → 61 passed in 30.88s)
Final review: Codex-Verifier (high), 8 Befunde, alle an der Quelle geprueft.
Final: fixed Akzeptanz durch conftest/pytest.ini des Agenten abwaehlbar — test_conftest_des_agenten_waehlt_keine_akzeptanztests_ab, test_pytest_ini_des_agenten_wirkt_nicht_auf_akzeptanz, test_weniger_akzeptanztests_als_erwartet_nicht_gruen RED→GREEN
Final: fixed pytest-Exit-Code ignoriert — test_exitcode_zaehlt RED→GREEN
Final: fixed Agent rc!=0 mit JSON galt als ok — test_rc_ungleich_null_ok_false RED→GREEN
Final: fixed per .gitignore versteckte Dateien (nicht gesichert, beim Aufraeumen geloescht) — test_versteckte_dateien, test_entfernen_verweigert_versteckte_dateien, test_per_gitignore_versteckte_datei_ist_grenzverletzung RED→GREEN
Final: fixed Test legte echten arbeit/ an, Guard blind fuer neuen leeren Ordner — test_standard_im_projekt umgebaut, conftest _ordnerstand None statt {}
Final: fixed arbeit/-Ausnahme galt auch im Zielrepo — test_arbeit_ordner_im_zielrepo_ist_nicht_ausgenommen RED→GREEN
Final: fixed Pfad-Guard erlaubte ganzes Projekt — test_im_projekt_nur_data_berichte_arbeit RED→GREEN; suite 77/77
Final: Ruling: Nachkontrolle sieht ignorierte Bereiche (data/berichte/.venv) nicht — erreichbar nur ueber ausgefuehrten Code = bekannte Sandbox-Luecke, dokumentiert im Spike — Kosten falls falsch: unbemerktes Ueberschreiben von Laufausgaben; wieder vorlegen mit Checkpoint-DB in Stufe 6.
Final: Ruling: Akzeptanztests muessen Zielcode in der Testfunktion importieren (sonst erwartet=None -> nie gruen) — Regel in CLAUDE.md + testlauf.py — Kosten falls falsch: neue Aufgaben-Tests muessen so geschrieben werden.
