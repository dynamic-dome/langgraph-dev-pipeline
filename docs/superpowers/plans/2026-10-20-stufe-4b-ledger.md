# SDD ledger — plan: docs/superpowers/plans/2026-10-20-stufe-4b-plan-freigabe.md

Setup: Arbeit auf main von Lab 2 wie in Stufe 1–4a; Spec docs/specs/2026-10-19-entwicklungs-pipeline-design.md.
Pre-flight: T1 planung (PLAN_SCHEMA, plan_prompt, plan_pruef_prompt, pruefe_plan, akzeptanz_prompt(vorige, hinweis), lege_plan_ab) -> T2 Graph; T2 (WARTEPUNKTE plan_freigabe, State-Felder, Freigabe-Antworten) -> T3 CLI; T4 A4-Regression -> T5 Live A5. Konsistent.
Task 1: complete (commits 7280314..185a306, tests: .venv/Scripts/python.exe -m pytest -q tests/test_planung.py → 35 passed in 7.71s)
Task 2: Ruling: test_fix_prompt_enthaelt_plan prüft nicht „kein assert im Fix-Prompt“ — der Testauszug mit assert-Zeilen ist seit Stufe 3 gewollt (Ruling F6 aus 4a) — Kosten falls falsch: keine
Task 2: Ruling: scheitert der Plan-Prüfer (Codex), blockiert das nicht: Eintrag „nicht verwertbar“ in der Plan-Freigabe; nur eine Grenzverletzung beendet den Lauf — wie die Spec-Prüfer — Kosten falls falsch: Plan ohne inhaltliche Prüfung freigegeben, Dominic sieht es
Task 2: Ruling: CLI-Tests aus 4a (spec freigeben → Umsetzung) sind bis Task 3 rot; Task-2-Abschluss läuft über Graph-/Speicher-Tests
Task 2: complete (commits 185a306..ced400f, tests: .venv/Scripts/python.exe -m pytest -q tests/test_graph_s4.py tests/test_speicher.py tests/test_graph_s3.py → 60 passed in 301.83s (0:05:01))
Ruling: Reihenfolge (Dominic 20.10.): 4b nur bis lauffähig (Task 3+4), dann Leitstand (Stufe 5); Task 5 (Live A5, Lernnotiz, Codex, Gate) läuft danach im Leitstand als gemeinsame Abnahme von 4b und 5
Task 3: complete (commits ced400f..758db36, tests: .venv/Scripts/python.exe -m pytest -q → 283 passed in 658.64s (0:10:58))
Task 4: Ruling: test_durchsuche_symlink_auf_ordner_nicht_verfolgt beim Übernehmen nach aufgaben/portwart/A4/ gestrichen (Vermerk im Dateikopf) — braucht echten Ordner-Symlink (WinError 1314), Skip in der Regression machte jede spätere Aufgabe rot — Kosten falls falsch: Symlink-Verhalten von drift ohne Regressionstest
Task 4: Probe: A1–A4 gegen Kopie von portwart/main (72f9042) mit dem Pipeline-Testlauf: grün, Akzeptanz 88/88, 0 übersprungen, 0 Fehler.
Task 4: complete (commits 758db36..46a6f29, tests: .venv/Scripts/python.exe -m pytest -q tests/test_graph_s4.py -k freigeben_dann_umsetzung → 2 passed, 37 deselected in 18.57s)
