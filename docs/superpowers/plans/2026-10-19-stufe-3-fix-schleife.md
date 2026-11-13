# Lab 2 · Stufe 3 (Fix-Schleife und Eskalation) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Ist nach `befunde_sammeln` eine Fix-Runde nötig, geht die Arbeit mit den auslösenden Befunden zurück an
den Implementierer. Das geschieht im selben Worktree, höchstens 2 Runden. Danach hält der Graph per `interrupt` an,
und Dominic entscheidet: `weiter` (eine Runde mehr), `annehmen` (so lassen) oder `abbrechen`.

**Architecture:**
- `baue_graph_s3` erweitert S2 um den Zyklus `befunde_sammeln → fix_runde → implementieren → … → befunde_sammeln`
  und den Knoten `eskalation` mit `interrupt`.
- Ein `SqliteSaver` unter `data/checkpoints.db` hält den Lauf über das Anhalten hinweg. Muster aus Lab 1, aber
  ohne Merker-Datei: `fortsetzen` findet den wartenden Lauf über den Checkpointer.
- `pruefberichte` bekommt einen eigenen Reducer, der je Runde geleert werden kann.

**Tech Stack:** wie Stufe 2, dazu `langgraph-checkpoint-sqlite` (schon installiert).

**Spec:** `docs/specs/2026-10-19-entwicklungs-pipeline-design.md` (Stufe 3, „Rundenlimit N = 2“, „Was eine Fix-Runde
auslöst“, „Freigaben immer per interrupt“).

## Global Constraints

- Alle Regeln aus Stufe 1 und 2 gelten weiter.
- `MAX_RUNDEN = 2` Fix-Runden; per CLI `--max-runden` (0–5) überschreibbar.
- Antwort an `eskalation`: `{"entscheidung": "weiter" | "annehmen" | "abbrechen"}`. Alles andere (auch `{}`) führt
  erneut zu `interrupt`, nie zu einer stillen Entscheidung (Lehre aus Lab 1). Das Modell gibt sich nie selbst frei.
- **Fix-Auftrag an den Implementierer:**
  - Aufgabe
  - Rundennummer
  - auslösende Befunde (Prüfer, Datei:Zeile, Aussage)
  - bei roten Tests der Testauszug, so wie ihn ein Entwickler im CI sähe; die Akzeptanztest-Dateien selbst bleiben
    unsichtbar
  - Hinweis: weiter im bestehenden Worktree, nicht von vorn
- Eine Fix-Runde mit `grenzverletzung` oder `agent_fehler` beendet den Lauf sofort (Bericht) ohne weitere Runde.
- Status am Ende:
  - `gruen`: Tests grün, keine Fix-Runde nötig
  - `rot`
  - `grenzverletzung`
  - `agent_fehler`
  - `angenommen`: Dominic nimmt den Stand trotz offener Befunde an
  - `abgebrochen`
- Exit-Code 0 nur bei `gruen`; 3 bei „wartet auf Entscheidung“.
- Checkpoint-DB nur über `pfade.checkpoint_db_pfad()`; Tests laufen mit umgeleitetem `data_dir` (conftest) und
  prüfen die echte DB vorher/nachher (besteht seit Stufe 1). Vor dem ersten pytest `sqlite-schema-guard`.

## Review Focus

1. **Endlosschleife:** Nach `max_runden` Fix-Runden kommt immer `eskalation`; `weiter` erlaubt genau eine Runde mehr.
   Test in Task 3.
2. **Leere oder falsche Antwort beim Fortsetzen** (`{}`, `"ja"`, unbekannte Entscheidung): Der Graph hält erneut an,
   nichts wird entschieden. Test in Task 3.
3. **Prüfberichte der Vorrunde mischen sich in die neue Runde:** Der Reducer leert sie am Rundenbeginn; die
   Befunde einer Runde stammen nur aus ihr. Test in Task 2/3.
4. **`fortsetzen`, wenn kein Lauf wartet oder der Lauf schon fertig ist:** klare Meldung, Exit 1, keine Änderung.
   Test in Task 4.
5. **Fix-Runde schreibt außerhalb oder bricht ab:** sofort Bericht, keine weitere Runde, Worktree bleibt
   gesichert. Test in Task 3.

---

### Task 1: Gedächtnis (Checkpointer)

**Files:** Create `entwicklung/speicher.py`, `tests/test_speicher.py`

**Interfaces:**
- `oeffne_checkpointer() -> SqliteSaver`: Pfad `pfade.checkpoint_db_pfad()`, `check_same_thread=False`.
- `freie_thread_id(cp, jetzt) -> str`: `"lauf-JJJJMMTT-HHMMSS"`, bei Kollision `-2`, `-3` …
- `wartende_laeufe(cp, graph) -> list[str]`: thread_ids, deren nächster Schritt `eskalation` ist, jüngste zuerst
  (Sortierung mit numerischem Suffix).

- [ ] Tests:
  - `test_db_liegt_im_umgeleiteten_data_dir`
  - `test_freie_thread_id_kollision`
  - `test_wartende_laeufe` (mit einem Mini-Graphen mit `interrupt` in tmp)
- [ ] FAIL, Implement, PASS. **Commit.**

### Task 2: Reducer, State, Fix-Auftrag

**Files:** Modify `entwicklung/state.py`, `entwicklung/agenten.py`; Tests in `tests/test_state.py`,
`tests/test_agenten.py`

**Interfaces:**
- `LEEREN = None`. `sammeln_oder_leeren(alt: list, neu: list | None) -> list`: `None` gibt `[]` zurück, sonst
  `alt + neu`. `pruefberichte: Annotated[list[dict], sammeln_oder_leeren]`.
- State neu:
  - `runde: int` (0 = erste Umsetzung)
  - `max_runden: int`
  - `runden: Annotated[list[dict], operator.add]` mit je Runde `{runde, status, tests, befunde, ausloesend}`
  - `entscheidung: str | None`
- `fix_prompt(aufgabe_text, runde, befunde: list[dict], testauszug: str | None, testbefehl_text) -> str`: deutsch,
  enthält Aufgabe, Runde, jeden auslösenden Befund als `- [prüfer] pfad:zeile — aussage`, den Testauszug (falls
  vorhanden), den Testbefehl und die Regeln aus `implementierer_prompt`.

- [ ] Tests:
  - `test_reducer_sammelt_und_leert`
  - `test_fix_prompt_enthaelt_befunde_und_auszug`
  - `test_fix_prompt_ohne_auszug`
- [ ] FAIL, Implement, PASS. **Commit.**

### Task 3: Graph S3

**Files:** Modify `entwicklung/graph.py`; Create `tests/test_graph_s3.py`

**Interfaces:**
- `baue_graph_s3(abh=None, checkpointer=None)`. Verlauf: wie S2 bis `befunde_sammeln`, dann die bedingte Kante
  `nach_befunden`:
  - `status` ist `grenzverletzung` oder `agent_fehler` → `bericht`
  - nicht `fix_noetig` → `bericht`
  - `runde < max_runden` → `fix_runde`
  - sonst → `eskalation`
- `fix_runde`:
  - `runde + 1`, `pruefberichte: None` (leeren)
  - merkt `fix_auftrag` = auslösende Befunde und Testauszug (falls Funktion rot)
  - entfernt `status`, damit die neue Runde ihn neu setzt
  - → `implementieren`
- `implementieren` nutzt ab `runde ≥ 1` den `fix_prompt`.
- `grenzen_pruefen` sichert mit der Nachricht `lauf <id>: Fix-Runde <k> (<modell>)`.
- `befunde_sammeln` hängt eine Zeile an `runden` an.
- `eskalation`:
  - `interrupt({"frage", "runde", "max_runden", "ausloesend": [...], "tests": tests_zeile})`
  - gültige Antwort ergibt `entscheidung`
  - `weiter`: `max_runden + 1`, → `fix_runde`
  - `annehmen`: `status = "angenommen"`, → `bericht`
  - `abbrechen`: `status = "abgebrochen"`, → `bericht`
- `baue_graph_s1/s2` bleiben unverändert lauffähig.

- [ ] Tests mit Fakes (Implementierer lernt pro Runde dazu, Prüfer zählt Runden):
  - `test_ohne_befunde_keine_runde`
  - `test_fix_runde_behebt` (Runde 1 roter Akzeptanztest → Runde 2 grün; `runden` hat 2 Einträge; Fix-Prompt
    enthielt den Testauszug)
  - `test_pruefberichte_je_runde_frisch` (4 Berichte im Endstand, nicht 8)
  - `test_eskalation_nach_max_runden` (`next == ("eskalation",)`, Implementierer genau 3× aufgerufen)
  - `test_weiter_gibt_eine_runde` (danach erneut Eskalation)
  - `test_annehmen` / `test_abbrechen` (Status, Bericht)
  - `test_ungueltige_antwort_haelt_erneut` (`{}`, `{"entscheidung": "ja"}`)
  - `test_grenzverletzung_in_fix_runde_beendet`
  - `test_max_runden_0_eskaliert_sofort`
- [ ] FAIL, Implement, PASS. **Commit.**

### Task 4: CLI und Bericht

**Files:** Modify `entwicklung/cli.py`, `entwicklung/bericht.py`; Tests in `tests/test_cli_s3.py`

**Interfaces:**
- `lauf … [--stufe 1|2|3]`, Standard 3, dazu `--max-runden` (Standard 2).
  - Stufe 3 öffnet den Checkpointer, `thread_id = freie_thread_id(...)`, `metadata.stufe`.
  - Hält der Lauf an: Frage, auslösende Befunde und Fortsetzungsbefehl ausgeben, Exit 3.
- `fortsetzen --entscheidung weiter|annehmen|abbrechen [--thread ID]`:
  - ohne `--thread` der jüngste wartende Lauf
  - kein wartender Lauf: Meldung, Exit 1
  - sonst `Command(resume={"entscheidung": …})`, live oder still wie beim Start (`--live`)
- Bericht: Abschnitt „Runden“ (eine Zeile je Runde) und ggf. „Entscheidung: …“. JSON um `runden`, `entscheidung`,
  `max_runden` erweitert.

- [ ] Tests:
  - `test_lauf_haelt_an_exit_3`
  - `test_fortsetzen_annehmen`
  - `test_fortsetzen_ohne_wartenden_lauf`
  - `test_fortsetzen_mit_thread`
  - `test_stufe_2_weiter_lauffaehig`
- [ ] FAIL, Implement, PASS, `sqlite-schema-guard`. **Commit.**

### Task 5: Aufgabe A3

**Files:** Create `aufgaben/portwart/A3.md`, `aufgaben/portwart/A3/test_akzeptanz_a3.py`

**Vertrag A3:**
- `portwart/frei.py`: `freie_ports(eintraege, lauschend, von: int, bis: int) -> list[int]` gibt aufsteigend alle
  Ports im Bereich zurück, die weder eingetragen sind noch lauschen.
  `BereichsFehler(ValueError)` bei `von > bis` oder Grenzen außerhalb 1–65535.
- CLI `python -m portwart frei VON-BIS [--anzahl N] [--datei] [--netstat-datei]`:
  - gibt die ersten N freien Ports aus (Standard 1), je Zeile einer, Exit 0
  - kein freier Port: `kein freier Port in VON-BIS`, Exit 1
  - kaputter Bereich (Format, Grenzen), `ListenFehler` oder `LauschFehler`: `Fehler: …` auf stderr, Exit 2
  - `--anzahl` < 1 ist ein Fehler (Exit 2)
  - `pruefen` und `abgleich` bleiben unverändert
- [ ] Etwa 12 Akzeptanztests (Imports in den Funktionen). Rot gegen `main` ohne A3, A1 und A2 grün.
  **Commit.**

### Task 6: Live, Lernnotiz, Codex, Gate

- [ ] **Step 1:** `lauf --repo portwart --aufgabe A2 --live` mit Stufe 3. Erwartet: Der Befund aus Lauf
  20261019-220447 (oder ein neuer) löst eine Fix-Runde aus, danach ist alles grün ohne Fix-Bedarf.
  - Ist das Ergebnis grün und ohne Fix-Bedarf: per Fast-Forward nach `portwart/main` mergen (Freigabe Dominic
    19.10.).
  - Sonst eskaliert der Lauf; ich zeige ihn Dominic.
- [ ] **Step 2:** `lauf --aufgabe A3 --live` als Abnahmelauf der Stufe. Ergebnis von Hand prüfen. Gemergt wird erst
  nach Dominics Zustimmung beim Gate.
- [ ] **Step 3:** Lernnotiz `docs/lernpfad/03-fix-schleife.md`. Inhalt:
  - Zyklus mit Abbruchbedingung im State
  - Reducer mit Leeren
  - interrupt als Notausgang
  - Checkpointer als Voraussetzung
  - fortsetzen ohne Merker
  - echte Runden aus dem Lauf
- [ ] **Step 4:** Commit, Codex-Verifier (`high`), Befunde per TDD, Ledger nach `docs/`. **STUFEN-GATE.**
