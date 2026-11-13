# Lab 2 · Stufe 7 (Gesamtreview, Abschluss-Freigabe, lokaler Merge) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Ein grüner oder angenommener Lauf endet nicht mehr im Bericht, sondern läuft über ein Gesamtreview zu einem
letzten Haltepunkt `abschluss_freigabe`. Dort entscheidet Dominic `mergen` oder `nicht_mergen`. Bei `mergen` führt die
Pipeline den Branch lokal per Fast-Forward in den Hauptzweig des Ziel-Repos, übernimmt die erzeugten Akzeptanztests
nach `aufgaben/<repo>/<id>/` und baut den Worktree ab. Danach ist die Pipeline einmal komplett.

**Architecture:**
- **Neue Knoten in `graph_s4`** (Stufe 3 bleibt unverändert): `budget_abschluss` (vierter Wächter des Kostenrahmens)
  → `gesamtreview` → `abschluss_freigabe` ⏸ → `abschluss` → `bericht`.
- **Wann:** `befunde_sammeln` ohne Fix-Bedarf mit Status `gruen` und `eskalation` mit `annehmen` gehen künftig zu
  `budget_abschluss` statt zu `bericht`. Rot, Grenzverletzung, Agentenfehler und Abbruch gehen wie bisher zum Bericht.
- **Gesamtreview durch Codex (GPT), nicht durch Claude.** Spec, Plan und Code stammen aus der Claude-Familie. Das
  letzte Urteil vor dem Merge soll die andere Familie fällen, wie die Sperre aus 6b-1. Codex kann unter Windows nicht
  lesen (Spike 19.10.), deshalb kommen Spec, Plan, der Diff `basis..HEAD`, die Befunde der letzten Runde, das
  Testergebnis und die Liste offener Punkte in den Prompt (`GESAMT_GRENZE = 200_000` Zeichen; der Verifier 6c lief mit
  390 000 Zeichen). Schema `GESAMT_SCHEMA = {verdict: PASS|FAIL, zusammenfassung, spec_erfuellt: bool,
  restpunkte: [{schwere: major|minor, aussage}]}`.
- **Sperre:** Jeder `restpunkt` `major` des Gesamtreviews ist ein Einwand. `mergen` ist eine Durchlass-Entscheidung
  (`DURCHLASS` bekommt `mergen`) und braucht dann eine Begründung. Ein gescheitertes Gesamtreview (Codex nicht
  verwertbar) ist ebenfalls ein Einwand: „Gesamtreview fehlt“.
- **Lokaler Merge** (`worktree.merge_ff(repo, branch, basis) -> str`): nur, wenn im Ziel-Repo derselbe Zweig
  ausgecheckt ist wie beim Start, der Stand sauber ist (`stand(repo)` leer) und `HEAD == basis` gilt. Dann
  `git merge --ff-only lauf/<id>`. Sonst kein Merge, sondern Status `merge_abgelehnt` mit Grund; Branch und Worktree
  bleiben. Kein Merge-Commit, kein Rebase, kein `--force`, kein Push.
- **Weil Fast-Forward:** Der gemergte Stand ist genau der Stand, den `tests_ausfuehren` geprüft hat. Ein zweiter
  Testlauf auf `main` entfällt.
- **Akzeptanztests übernehmen:** `berichte/<lauf>/akzeptanz/<id>/*.py` → `aufgaben/<repo>/<id>/` (nur anlegen, nie
  überschreiben; existiert der Ordner schon, kein Kopieren und Hinweis). Nicht committen: Das macht Dominic bzw. die
  Sitzung danach. Die Datei liegt nach dem letzten Agentenknoten, also nach jeder Nachkontrolle.
- **Aufräumen nach dem Merge:** `worktree.entfernen` (ohne `--force`) und `git branch -d lauf/<id>` (gemergt, also
  sicher). Scheitert einer davon, bleibt es stehen, und der Bericht nennt den Grund.
- **Kein Rat an `abschluss_freigabe` und `budget_abschluss`** (`OHNE_RAT`). Am Abschluss entscheidet Dominic, das
  Gesamtreview ist schon die Zweitmeinung.

**Tech Stack:** wie 6c.

**Spec:** `docs/specs/2026-10-19-entwicklungs-pipeline-design.md`, Ziel-Ablauf „→ gesamtreview → abschluss_freigabe ⏸
→ lokal mergen + Bericht“, Stufe 7, Nicht-Ziele („Die Pipeline merged höchstens lokal und nur nach Freigabe“). Entscheide
Dominic 21.10.: Stufe 7 vor 6d; Gate 6c.

**Bitte bestätigen (Entwurfsentscheidungen):**
1. Gesamtreview durch **Codex** statt Claude (andere Familie, gleiche Sperrlogik wie 6b-1).
2. **Nur Fast-Forward.** Ist der Hauptzweig inzwischen weitergelaufen, mergt die Pipeline nicht, sondern meldet es.
3. Übernommene Tests werden **nicht automatisch committet**.
4. Nach dem Merge Worktree abbauen und Branch löschen (`-d`).
5. Nicht im Umfang: **abgelöste ältere Akzeptanztests** (A8 → A9 heute). Ändert eine Aufgabe bewusst ein früheres
   Verhalten, wird ein alter Akzeptanztest rot, und die Fix-Schleife kann ihn nicht erfüllen. Das löst Stufe 7 nicht.
   Es landet in der Eskalation, und Dominic entscheidet. Kandidat für später: Die Spec nennt abgelöste Tests, und der
   Testlauf lässt genau diese weg.

## Global Constraints

- Python nur über `.venv\Scripts\python.exe` (3.12). Keine neue Abhängigkeit.
- Kein Push, kein Merge außer dem Fast-Forward nach `mergen` im Haltepunkt. Worktrees nur per `git worktree remove`.
- Test-DB-Isolation wie bisher. Alle Git-Tests auf Mini-Repos unter `tmp_path` (Fixture `umgebung` aus test_graph_s1).
- Ganze Suite nur am Ende, mit Bestandszählung vorher und nachher. **Kein Schreiben in Lab 2, solange ein echter Lauf
  läuft** (Lehre 6c: grenzverletzung).
- Konstanten: `ABSCHLUSS_ENTSCHEIDUNGEN = ("mergen", "nicht_mergen")`, `BUDGET_PUNKTE` + `"budget_abschluss"`,
  `WARTEPUNKTE` + `"abschluss_freigabe"`, `"budget_abschluss"`, `GESAMT_GRENZE = 200_000`.
- Neue Status: `merge_abgelehnt`. Bestehende Status bleiben (`gruen`, `angenommen`, …). Das Ergebnis des Abschlusses
  steht in `abschluss: {entscheidung, merge_commit, uebernommen: [Pfade], aufgeraeumt: bool, grund}`.

## Review Focus

1. **Ziel-Repo hat inzwischen uncommittete Änderungen oder einen anderen Zweig:** kein Merge, `merge_abgelehnt` mit
   Grund, Repo unverändert → `test_merge_abgelehnt_bei_schmutzigem_repo`, `..._bei_anderem_zweig` (Task 1).
2. **Hauptzweig ist weitergelaufen** (`HEAD != basis`): kein Merge, keine Teilübernahme der Tests →
   `test_merge_abgelehnt_wenn_main_weiter` (Task 1/2).
3. **Codex scheitert beim Gesamtreview:** `mergen` braucht eine Begründung, nicht stilles Durchwinken →
   `test_gesamtreview_fehlt_ist_einwand` (Task 2).
4. **Aufgaben-Ordner existiert schon** (zweiter Lauf derselben Aufgabe): nie überschreiben →
   `test_uebernahme_ueberschreibt_nicht` (Task 1).
5. **Ungültige Antwort am Abschluss:** Ein erneutes interrupt im selben Knoten, kein Merge →
   `test_abschluss_ungueltige_antwort` (Task 2).

---

### Task 1: Werkzeuge für den Abschluss (`worktree.merge_ff`, Übernahme der Tests)

**Files:**
- Modify: `entwicklung/worktree.py`
- Create: `entwicklung/abschluss.py` (Gesamtreview-Prompt, Schema, Übernahme, Einwände; keine Agenten)
- Test: `tests/test_abschluss.py`

**Interfaces:**
- Produces:
  - `worktree.merge_ff(repo: Path, branch: str, basis: str, zweig: str) -> str`: neuer HEAD; wirft `WorktreeFehler`
    mit Grund (`"Ziel-Repo nicht sauber: …"`, `"anderer Zweig ausgecheckt: X statt Y"`,
    `"Hauptzweig ist weitergelaufen (HEAD abc1234 statt Basis def5678)"`, Git-Fehlertext).
  - `worktree.zweig(repo) -> str` (aktueller Zweig); `vorbereiten` merkt ihn sich im State als `zielzweig`.
  - `worktree.branch_loeschen(repo, branch) -> None` (`git branch -d`).
  - `abschluss.GESAMT_SCHEMA`, `abschluss.gesamt_prompt(state: dict, diff: str) -> str`.
  - `abschluss.uebernimm_tests(quelle: Path, ziel: Path) -> list[Path]` (wirft `FileExistsError`, wenn `ziel` existiert).
  - `abschluss.einwaende(gesamt: dict | None) -> list[str]`: `"Gesamtreview (Codex) meldet major: …"` je Restpunkt;
    `["Gesamtreview fehlt: <fehler>"]`, wenn es nicht verwertbar ist.

- [ ] **Step 1: Failing tests** (Mini-Repos unter `tmp_path`): `test_merge_ff_fast_forward` (main zeigt danach auf den
  Branch-Kopf, Arbeitsbaum gleich), `test_merge_abgelehnt_bei_schmutzigem_repo`, `test_merge_abgelehnt_bei_anderem_zweig`,
  `test_merge_abgelehnt_wenn_main_weiter` (Repo jeweils unverändert: HEAD und `stand`), `test_uebernahme_kopiert_nur_py`,
  `test_uebernahme_ueberschreibt_nicht`, `test_einwaende_major_und_fehlend`, `test_gesamt_prompt_kuerzt` (bleibt unter
  `GESAMT_GRENZE` + Marke „gekürzt“), `test_gesamt_schema_streng`.
- [ ] **Step 2: Rot sehen**, **Step 3: umsetzen**, **Step 4: grün** (`pytest tests/test_abschluss.py tests/test_worktree.py`)
- [ ] **Step 5: Commit** `feat: Werkzeuge für den Abschluss (Fast-Forward-Merge, Übernahme der Akzeptanztests)`

---

### Task 2: Graph — Kostenrahmen, Gesamtreview, Abschluss-Freigabe, Merge

**Files:**
- Modify: `entwicklung/graph_s4.py` (Knoten, Kanten), `entwicklung/graph.py` (`BUDGET_PUNKTE`, `umsetzung_s3` bekommt
  `ziel_gruen: str = "bericht"` für die beiden Kanten), `entwicklung/state.py`, `entwicklung/speicher.py`
  (`WARTEPUNKTE`), `entwicklung/steuerung.py` (`ERLAUBT_KURZ`, `DURCHLASS`, `_antwort`)
- Test: `tests/test_graph_s7.py`

**Interfaces:**
- Consumes: alles aus Task 1; `planer_codex` aus `Abhaengigkeiten` (Name `"gesamtreview"`, Effort `high`).
- Produces: State `zielzweig`, `gesamtreview: dict | None` (`{ok, daten, fehler}`), `abschluss: dict`; interrupt
  `abschluss_freigabe` mit `{art, branch, diffstat, tests, gesamtreview, einwaende, offene_befunde, uebernahme_ziel,
  erlaubt, hinweis}`.

- [ ] **Step 1: Failing tests** (Fakes wie in test_graph_s4, Ziel-Repo unter `tmp_path`):
  - `test_gruen_haelt_an_abschluss`: grüner Lauf hält an `abschluss_freigabe` statt zu enden; der Prompt von
    `gesamtreview` enthält Spec, Plan und Diff.
  - `test_mergen_fast_forward_und_uebernahme`: `mergen` → main zeigt auf den Lauf-Kopf, `aufgaben/mini/M2/` enthält
    die Testdatei, Worktree weg, Branch weg, Bericht mit Abschnitt „Abschluss“.
  - `test_nicht_mergen_laesst_alles_stehen`: Branch und Worktree bleiben, main unverändert, keine Übernahme.
  - `test_gesamtreview_major_braucht_begruendung` und `test_gesamtreview_fehlt_ist_einwand` (Codex `None`).
  - `test_angenommen_geht_auch_zum_abschluss`: Eskalation `annehmen` → `abschluss_freigabe`.
  - `test_rot_und_abbruch_enden_wie_bisher`.
  - `test_merge_abgelehnt_wenn_main_weiter`: zwischen Freigabe und Antwort einen Commit auf main → Status
    `merge_abgelehnt`, nichts übernommen, Branch und Worktree bleiben.
  - `test_budget_abschluss_haelt`: Rahmen erreicht → Halt `budget_abschluss` vor dem Gesamtreview.
  - `test_abschluss_ungueltige_antwort`.
  - `test_stufe3_unveraendert`: `baue_graph_s3` endet weiter im Bericht (bestehende s3-Tests bleiben grün).
- [ ] **Step 2: Rot sehen**, **Step 3: umsetzen**, **Step 4: grün** (s7 + s4 + s3 + steuerung + speicher)
- [ ] **Step 5: Commit** `feat: Gesamtreview, Abschluss-Freigabe und lokaler Merge im Graphen`

---

### Task 3: Oberflächen (CLI, Leitstand, Bericht)

**Files:** `entwicklung/cli.py` (Anzeige `abschluss_freigabe`, `fortsetzen --entscheidung mergen|nicht_mergen`),
`entwicklung/leitstand/static/app.js` (Karte), Knotentexte und Phase der neuen Knoten im Leitstand,
`entwicklung/bericht.py` (Abschnitt „Abschluss“, `JSON_FELDER` + `gesamtreview`, `abschluss`, `zielzweig`),
`entwicklung/berater.py` (`OHNE_RAT`), `docs/lernpfad/leitstand_demo.py` (Lauf bis zum Abschluss)
**Tests:** `tests/test_cli_s4.py` (neuer Test bis zum Merge über die CLI), `tests/test_leitstand_*.py` (Knotentexte,
409 für Rat am Abschluss, Antwort `mergen` mit Einwand ohne Begründung → 400), Bericht-Test.

- [ ] Steps wie gewohnt: Rot, umsetzen, grün, **Browser-Prüfung der Demo** (Karte zeigt Gesamtreview, Restpunkte,
  Branch, Diffstat; Mergen trotz Einwand verlangt Begründung; nach Mergen Bericht mit Abschnitt „Abschluss“), Commit
  `feat: Abschluss-Freigabe in CLI, Leitstand und Bericht`.

---

### Task 4: Ganze Suite, Abnahme A10, Lernnotiz, Verifier, Gate

- [ ] **Step 1:** ganze Suite mit Bestandszählung vorher/nachher.
- [ ] **Step 2: Codex-Verifier** (high, read-only) über den Stufen-Diff; Befunde an der Quelle prüfen, mit Test vorher
  beheben, Suite erneut.
- [ ] **Step 3: A10-Wunsch** (die Folgeaufgabe aus A9) von Dominic bestätigen lassen. Entwurf:
  „`portwart austragen` lehnt heute eine Datei ab, wenn in den übrigen Einträgen ein Wert `nan` steht (zwei `nan` sind
  nie gleich). Und eine Untertabellen-Kopfzeile ohne Werte wie `["port".meta]` hinter dem Eintrag bleibt stehen. Beides
  soll richtig behandelt werden: `nan` gilt als unverändert, und eine solche Kopfzeile wird abgelehnt, statt stehen zu
  bleiben.“
- [ ] **Step 4: A10-Abnahme bis zum Merge** (Dominic startet oder sagt ja): Lauf mit `auto`, am Abschluss `mergen`.
  Belege: main per Fast-Forward, `aufgaben/portwart/A10/` angelegt, Worktree und Branch weg, A1–A10 gegen main grün.
- [ ] **Step 5: Lernnotiz `07-abschluss.md`** (Lernstoff: letzter Haltepunkt mit Seiteneffekt nach der Freigabe; warum
  Fast-Forward die zweite Testrunde erspart; warum die andere Familie das letzte Wort hat), Ledger, Gate durch Dominic.

---

## Nachtrag 2026-10-24: Merge-Danger-Zeile und Skip-Prüfung im Freigabebericht

> Nur Plan-Ergänzung, noch nichts gebaut. Stufe 7 ist weiter Dominics Lernstufe und wird von ihm geführt. Der Nachtrag
> ändert nichts an den Entscheidungen 1–5 oben. Die Entwurfsentscheidungen 6–8 sind **zu bestätigen**, bevor Task 1
> beginnt. Entstanden ohne Eingriff in `entwicklung/`, `tests/` oder `aufgaben/`.

**Herkunft:** eine eigene Analyse öffentlicher Skill-Sammlungen vom 20.10. (Übernahme „Tür/Radius-Zeile“, dazu der
Absatz zu `implement-spec`: Tests mit git-ignorierten Daten laufen im Worktree still als SKIP durch). Vorbild: gzif
Phase 4 Schritt 5 (Skill `gzif-pipeline`, Commit `25254d0`): eine Zeile `Tür: einseitig|zweiseitig · Radius: <ein Wort>`,
feste Liste einseitiger Fälle, der Verifier prüft das Urteil des Autors.

### Zusätzliche Entwurfsentscheidungen (bestätigt 2026-10-25, siehe Bestätigung unten)

6. **Merge-Danger-Zeile im Abschluss-Haltepunkt.** Die Karte `abschluss_freigabe` und der Abschnitt „Abschluss“ im Bericht
   bekommen eine Zeile `Tür: einseitig|zweiseitig · Radius: <ein Wort>` plus, bei „einseitig“, die Liste der
   betroffenen Fälle. **Selbstbewertung** = deterministisches Mindesturteil der Pipeline aus dem Diff `basis..HEAD`
   (Muster unten), nicht ein Urteil des Implementierers. Der Implementierer-Prompt bleibt unverändert, sonst müssten
   die Tests der Stufen 1–6 und die Akzeptanzläufe nachgezogen werden. **Gegenprüfung durch Codex im Gesamtreview**
   (dieselbe Anfrage, kein zweiter Aufruf): Codex bekommt die Selbstbewertung im Prompt und urteilt unabhängig. Es gilt
   das **strengere** Urteil. „Zweiseitig, klein“ ist das am wenigsten belastbare Urteil und bekommt im Prompt
   ausdrücklich die Anweisung, es zu widerlegen.
7. **Einseitig ist ein Einwand.** Wie ein `major`-Restpunkt: `mergen` braucht dann eine Begründung (`DURCHLASS`). Der
   lokale Fast-Forward selbst ist zweiseitig (der Branch bleibt bis `branch -d`, `git reset` stellt `main` wieder her,
   solange nichts gepusht ist). Einseitig wird es nur durch den **Inhalt** des Diffs.
8. **Skip-Prüfung der Worktree-Tests.** `testlauf._zaehle` liefert `uebersprungen` schon je Lauf (eigene Tests und
   Akzeptanztests). Neu: Der Abschluss-Haltepunkt zeigt die Zahlen beider Läufe in einer Zeile
   (`Tests: n bestanden · m übersprungen`). **`uebersprungen > 0` ist ein Einwand** („Tests übersprungen: unerwartete
   Skips sind eine Lücke, kein Bestehen“), `mergen` braucht dann eine Begründung. Alternative, falls echte, gewollte Skips
   im Zielrepo vorkommen: die Skip-Zahl einmal in `vorbereiten` auf dem Hauptzweig messen und nur die Abweichung nach
   oben als Einwand werten. Standard bleibt die einfache Regel, weil `portwart` und alle bisherigen Aufgaben ohne Skips
   laufen. Hintergrund: Akzeptanztests importieren den Zielcode erst in der Testfunktion, ein git-ignoriertes Fixture
   fehlt im Worktree dagegen lautlos.

**Bestätigung 2026-10-25 (Owner):** Die Entwurfsentscheidungen 6 bis 8
sind bestätigt, „ja“, umzusetzen wie im Bogen empfohlen. Damit ist die Bedingung „vor Task 1 bestätigen“ erfüllt.
- (6) Tür-Selbstbewertung deterministisch aus dem Diff plus Codex-Gegenprüfung, das strengere Urteil gilt. Codex-Gegenprüfung bleibt, weil sich eine Diff-Heuristik austricksen lässt.
- (7) Einseitig ist ein Einwand mit Begründungspflicht.
- (8) `uebersprungen > 0` ist ein Einwand, **mit einer Ausnahme laut Empfehlung im Bogen**: dokumentierte, begründete Plattform-Skips (etwa `skipif` für eine fehlende Plattform) dürfen den Einwand nicht auslösen, sonst blockieren legitime Tests. Wie ein Skip als „dokumentiert und begründet“ gilt (Markierung im Skip-Grund oder die Basismessung aus der Alternative oben), legt der Bau in Task 1 fest und hält es hier nach.
- Der Bau selbst (Task 1 bis 4) ist weiter Dominics Lernstufe; er startet sie selbst. Dieser Nachtrag und die Bestätigung ändern weder `entwicklung/` noch `tests/` noch `aufgaben/`.

### Feste Liste einseitiger Fälle (Muster auf dem Diff, `abschluss.EINSEITIG_FAELLE`)

| Fall | Erkennung im Diff `basis..HEAD` |
|---|---|
| Schema-Migration | Dateien unter `migrations/`, `*.sql`, SQL-DDL (`ALTER`, `DROP`, `CREATE` auf Tabellen) in hinzugefügten Zeilen |
| Löschen von Daten oder Dateien | gelöschte Dateien (`D` in `--name-status`), `rmtree`, `unlink`, `os.remove`, SQL-Löschbefehle in hinzugefügten Zeilen |
| Veröffentlichen | `git push`, `deploy`, `publish`, `twine`, `npm publish`, `gh release` in hinzugefügten Zeilen oder Dateien unter `.github/workflows/` |
| Schreiben in eine Produktions-DB | `sqlite3.connect` oder SQL-Schreibbefehle auf einen Pfad außerhalb von `tmp_path`/Test-Override; `*.db`, `*.sqlite` im Diff |
| Rechte, Konten, Secrets | `chmod`, `icacls`, `setx`, Dateien `.env`, `*.pem`, `*.key`, Token-Muster in hinzugefügten Zeilen |

Die Muster sind absichtlich grob (lieber ein Fehlalarm, den Codex entkräftet, als ein übersehener Fall). Treffer in
`tests/`, die nur Testdaten in `tmp_path` anlegen, entkräftet Codex, nicht das Muster.

### Änderungen an den Tasks

- **Task 1** (`entwicklung/abschluss.py`, `tests/test_abschluss.py`):
  - `EINSEITIG_FAELLE` (Tabelle oben als Regex-Liste) und `abschluss.tuer_selbst(diff: str, name_status: str) -> dict`
    mit `{urteil: "einseitig"|"zweiseitig", radius: str, faelle: [str]}`. Radius als ein Wort aus
    `Datei | Modul | Repo | System`: eine Datei im Diff → `Datei`, ein Ordner → `Modul`, mehrere Ordner → `Repo`,
    einseitiger Fall außerhalb des Repos → `System`.
  - `GESAMT_SCHEMA` erweitert um `tuer: {urteil: einseitig|zweiseitig, radius, begruendung, faelle: [str],
    selbstbewertung_stimmt: bool}`; `gesamt_prompt` nimmt die Selbstbewertung auf und fordert die Gegenprüfung.
  - `abschluss.tuer_endgueltig(selbst: dict, gesamt: dict | None) -> dict`: das strengere Urteil gewinnt; fehlt Codex,
    gilt die Selbstbewertung (und `einwaende` meldet ohnehin „Gesamtreview fehlt“).
  - `abschluss.einwaende` ergänzt: `"Tür einseitig: <Fälle>"` und `"Tests übersprungen: <n>"`.
  - Neue Tests: `test_tuer_selbst_erkennt_migration_loeschen_push_db_secret` (je ein Mini-Diff je Fall),
    `test_tuer_selbst_zweiseitig_bei_reinem_code`, `test_tuer_strengeres_urteil_gewinnt`,
    `test_tuer_codex_fehlt_selbstbewertung_gilt`, `test_einwand_einseitig_und_skips`, `test_gesamt_schema_tuer_streng`.
- **Task 2** (`graph_s4.py`, `state.py`, `steuerung.py`): Der Interrupt-Payload von `abschluss_freigabe` bekommt `tuer`
  (`{urteil, radius, faelle, selbst, codex}`) und `tests_zeile` (bestanden/übersprungen beider Läufe). State-Feld `tuer`,
  das Ergebnis steht in `abschluss`. Neue Tests: `test_einseitige_tuer_braucht_begruendung`, `test_skips_sind_einwand`,
  `test_tuer_im_payload_der_freigabe`.
- **Task 3** (`bericht.py`, `cli.py`, `leitstand/static/app.js`): Zeile `Tür: … · Radius: …` direkt unter der Überschrift
  der Karte und im Bericht-Abschnitt „Abschluss“; bei „einseitig“ rot mit Fallliste, bei Uneinigkeit (Selbstbewertung
  und Codex verschieden) beide Urteile nebeneinander. Die Browser-Prüfung der Demo bekommt einen einseitigen Lauf dazu.
- **Task 4:** Review-Fokus-Punkte 6 und 7 (unten). A10-Abnahme: zusätzlich ein Probelauf mit künstlich eingestreutem
  einseitigem Fall (z. B. `rmtree` in einer Hilfsfunktion): Die Karte zeigt „einseitig“, `mergen` ohne Begründung
  → 400. Lernnotiz `07-abschluss.md` um den Abschnitt „Warum der Autor seine eigene Tür nicht allein bewertet“ ergänzen.

### Review Focus (Ergänzung)

6. **Selbstbewertung „zweiseitig“, Codex sagt „einseitig“:** das strengere Urteil gilt, beide stehen im Bericht →
   `test_tuer_strengeres_urteil_gewinnt`.
7. **Lautlose Skips im Worktree:** `uebersprungen > 0` erscheint als Einwand, nicht nur als Zahl im Bericht →
   `test_skips_sind_einwand`.

### Nicht im Umfang

- Eine zweite Skip-Messung auf dem Hauptzweig (nur als Alternative in Entscheidung 8).
- Änderungen am Implementierer-Prompt.
- Tür-Bewertung für Läufe, die rot, abgebrochen oder mit Grenzverletzung enden (sie erreichen den Abschluss nicht).

**Festlegung 2026-11-13 (Bau Stufe 7, Follow-up zu Entscheidung 8):** Ein Skip gilt als dokumentiert und begründet,
wenn sein Grund mit `plattform:` beginnt (z. B. `pytest.mark.skipif(sys.platform != "win32", reason="plattform: nur
Windows")`). `testlauf` sammelt dafür die Skip-Gründe beider Läufe aus dem JUnit-XML (`skip_gruende`). Jeder andere
Skip ist ein Einwand („Tests übersprungen: n ohne Plattform-Begründung“). Fehlen die Gründe (ältere Läufe), zählt
jeder Skip als undokumentiert. Grund für die Marke statt der Basismessung: kein zweiter Testlauf auf dem Hauptzweig,
und der Grund steht sichtbar im Testcode. Der Test `test_skips_sind_einwand` bekommt den Zwilling
`test_plattform_skip_ist_kein_einwand`.
