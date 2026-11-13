# Lab 2 · Lernstufe 4a: klären, Spec, Akzeptanztests aus der Spec (mehrere Haltepunkte)

**Ausprobieren:** `.venv\Scripts\python.exe -m entwicklung lauf --repo portwart --aufgabe A4 --live`
(hält zuerst mit Rückfragen an, dann zur Spec-Freigabe, eventuell noch an der Eskalation; jeweils weiter mit
`fortsetzen`, siehe HOW-TO-USE)

## Die Idee in einem Satz

Die Pipeline bekommt keinen fertigen Vertrag mehr, sondern einen **Wunsch** in fünf Sätzen. Daraus macht sie selbst:
Rückfragen an Dominic, eine Spec und Akzeptanztests. Erst wenn Dominic die Spec freigibt, beginnt die Umsetzung aus
Stufe 3, und zwar mit der Spec als Aufgabe.

## Der Ablauf am echten Code

```
vorbereiten → klaeren ─┬→ fragen ⏸ → klaeren                 (Fragen offen, höchstens 3 Runden)
                       └→ spec_schreiben → akzeptanz_schreiben ↺  (abgelehnt: Gründe zurück, höchstens 2 Versuche)
→ Send ×2: pruefen_spec_claude | pruefen_spec_codex → spec_pruefung_sammeln → spec_freigabe ⏸
     freigeben → umsetzung_starten → implementieren → … (Stufe 3 unverändert)
     aendern   → spec_schreiben          abbrechen → bericht
```
`entwicklung/graph_s4.py`. Der Teil ab `implementieren` ist derselbe Code wie in Stufe 3 (`graph.umsetzung_s3`):
Stufe 4 setzt nur Knoten davor.

### 1. Drei Haltepunkte in einem Lauf

`fragen`, `spec_freigabe` und `eskalation` halten alle per `interrupt` an, alle nach dem Muster aus Stufe 3: genau ein
interrupt je Durchlauf, bei ungültiger Antwort eine Kante zu sich selbst. Neu ist die Frage, **an welchem** der Lauf
gerade steht. Die Antwort steht im Checkpointer:

```python
zustand = graph.get_state(cfg)
next((a.name for a in zustand.tasks if a.name in WARTEPUNKTE and a.interrupts), None)   # speicher.wartepunkt
```
`fortsetzen` liest diesen Haltepunkt und prüft danach, ob die Angaben dazu passen. `--antwort` gilt nur an `fragen`,
`--entscheidung freigeben` nur an `spec_freigabe`. Passt es nicht, schickt die CLI gar kein `Command` und sagt, was
dort erlaubt ist. So kann eine Antwort nicht beim falschen Haltepunkt landen.

Zweite Neuerung: Läufe verschiedener Stufen liegen im selben Checkpointer. Einen Lauf liest und setzt man mit dem
Graphen **seiner** Stufe fort. Die Stufe steht seit Stufe 3 in `metadata` jedes Checkpoints
(`speicher.stufe_des_laufs`).

### 2. Die Fragen-Schleife mit dem Menschen

`klaeren → fragen ⏸ → klaeren` ist ein Zyklus wie die Fix-Schleife, nur dass in der Mitte ein Mensch sitzt. Die
Abbruchbedingung steht wieder im State (`klaer_runde < MAX_KLAERUNGEN`). Die Antworten sammelt
`klaerung: Annotated[list, operator.add]` – sie sollen wachsen, jede Runde sieht alle bisherigen.

### 3. Planungsagenten liefern JSON, Code schreibt die Dateien

Klärer, Spec-Schreiber, Test-Schreiber und Spec-Prüfer laufen mit `--tools Read,Glob,Grep` und `--json-schema`
(`strukturiert.py`). Sie können gar nicht schreiben. Was sie erzeugen, kommt als JSON zurück, und erst
`planung.lege_ab` legt Spec und Tests unter `berichte/<lauf>/` ab, außerhalb des Worktrees. Nach jedem
Planungsagenten prüft `_sauber`, dass sich nichts verändert hat. Der einzige schreibende Agent bleibt der
Implementierer, und der sieht die Tests nie.

Codex verlangt mit `--output-schema` **strenge** Schemas: alle Felder Pflicht, keine zusätzlichen
(`test_schemas_streng_und_passend`).

### 4. Wie gut sind Tests, die ein Agent schreibt?

Bis Stufe 3 habe ich die Akzeptanztests von Hand geschrieben. Jetzt schreibt sie ein Agent, und das ist die
schwächste Stelle der Stufe. Es gibt vier Sicherungen hintereinander:

| Sicherung | prüft | Art |
|---|---|---|
| `pruefe_akzeptanz` (per `ast`) | eine Datei, richtiger Name, Imports oben nur Standardbibliothek/pytest, Zielcode nur in Funktionen und nur aus den Schnittstellen der Spec, keine Umwege (`importlib`, `__import__`, `eval`, `.__globals__`) | deterministisch |
| Probe gegen main, **in einer Kopie** (`git archive`) | sammelbar, mindestens ein Test rot, keiner übersprungen, keiner mit Setup-Fehler | deterministisch |
| Spec-Prüfer (Claude + Codex parallel) | Spec gegen Wunsch und Antworten, Tests gegen Spec | Modell |
| Freigabe | Dominic liest Spec und Tests | Mensch |
| Hash-Vergleich vor jedem Testlauf | die Tests unter `berichte/` sind noch die freigegebenen | deterministisch |

Die letzten Zeilen kamen aus dem Codex-Review der Stufe: Die Probe lief zuerst im Worktree des Implementierers, ihr
Testcode hätte dort Spuren hinterlassen können. Ein Test mit fehlender Fixture galt als „rot“, obwohl er nie bis zu
seinem `assert` kommt. Und `berichte/` ist git-ignoriert, also für die Nachkontrolle unsichtbar: Testcode des
Implementierers hätte die freigegebenen Tests ersetzen können. **Lesen** kann er sie über ausgeführten Testcode
weiterhin; das verhindert erst eine Sandbox.

## Was der echte Lauf zeigte (A4, Lauf 20261020-120157)

**Klären:** Der Klärer las das Repo und stellte 5 Fragen, jede mit einer sinnvollen Voreinstellung. Die wichtigste
war die Zuordnung Projekt ↔ Ordner. Dominic nahm die Voreinstellungen; der Pfad je Eintrag kommt später als eigene
Aufgabe, weil er den Vertrag aus A1 ändern würde.

**Spec:** 109 Zeilen, 3 Module, 10 Annahmen, Muster mit Gegenbeispielen (`12:30`, `report = 5`, `08766`). 26 Tests.

**Die Spec-Prüfer** fanden 9 Punkte, alle `minor`, die meisten echte Testlücken (keine Datei ohne Endung, obwohl
Dominic „ohne Endungsliste“ geantwortet hatte). Einer war falsch: `REPO = parents[2]` passe nicht. Er passt, weil
die Pipeline die Tests nach `tests/_akzeptanz/` kopiert; das wusste der Prüfer nicht. Prüfer ohne Kontext erfinden
Probleme.

**Umsetzung:** Codex meldete in Runde 0 drei Fehler (Nicht-ASCII-Ziffern als Port, sehr lange Ziffernfolge
bricht die Suche ab, Zugriffsfehler nicht in `DriftFehler` übersetzt), in Runde 1 noch einen (nicht dekodierbare
`ports.toml`); der Implementierer behob sie, in Runde 2 meldete Codex PASS. Von Hand nachgeprüft habe ich die
Befunde nicht. Danach blieb nur noch „Akzeptanz 88/89“ – und daran hätten beliebig viele Runden nichts geändert.

**Der übersprungene Test.** Ein erzeugter Test legt einen Symlink an und ruft sonst `pytest.skip`. Auf diesem Rechner
fehlt dafür das Recht (`WinError 1314`). Drei Fehler meiner Pipeline kamen so zusammen:
1. Die Probe zählte den übersprungenen Test als „rot gegen main“ und meldete 25 von 26 statt 24 rot, 1 übersprungen.
2. Die Funktionsprüfung meldete „88/89“, ohne „übersprungen“ zu sagen.
3. Die Fix-Schleife schickte einen Befund an den Implementierer, den er gar nicht beheben konnte.

Behoben (Commit `db8f4ae`): Der Testlauf zählt `akzeptanz.uebersprungen`, die Funktionsprüfung nennt sie, die Probe
lehnt Tests mit Skip ab, und der Test-Schreiber soll Plattformabhängiges mit `monkeypatch` simulieren.

**Der Absturz der Anzeige** und die Wiederaufnahme: Die Live-Anzeige stürzte an `pruefen_spec_*` ab
(Zweig für `pruefen_*` griff zuerst). Im Checkpointer stand danach `next == ()`, obwohl beide Spec-Prüfer fertig
waren: ihre Ergebnisse lagen als ausstehende Writes bereit (`tasks` zeigte sie). `graph.invoke(None, cfg)` nahm
den Lauf an genau dieser Stelle wieder auf und **verwendete die Writes wieder**, ohne die Prüfer erneut zu starten
(an einer DB-Kopie mit gesperrten Agenten nachgewiesen). Dritte Lektion zu `next`: Es ist keine verlässliche
Auskunft über den Zustand eines Laufs.

## Was dieser Lauf an Schwächen gezeigt hat

- **Nachbessern nur der Tests fehlt.** `aendern` schickt den Hinweis an den Spec-Schreiber und erzeugt danach die
  Tests neu. Für Testlücken bei guter Spec ist das zu grob.
- **Lange Pausen vertragen keine Änderung an Lab 2.** Die Nachkontrolle vergleicht mit dem Stand beim Start. Wer
  während einer Freigabe-Pause in Lab 2 arbeitet, löst eine Grenzverletzung aus.
- Die Probe „mindestens ein Test rot“ ist schwach: Der grüne Test war hier `test_cli_wurzel_pflichtargument`, der
  gegen main nur deshalb besteht, weil argparse auch für den unbekannten Befehl Exit 2 liefert.

## Selbst prüfen

1. Warum prüft `fortsetzen` den Haltepunkt, bevor es ein `Command` schickt?
2. Warum dürfen die Planungsagenten nicht selbst `spec.md` schreiben?
3. Der Lauf ist mitten in den Spec-Prüfern abgebrochen. Warum liefen sie beim Wiederaufnehmen nicht noch einmal?
4. Warum ist ein übersprungener Akzeptanztest schlimmer als ein roter?

<details><summary>Antworten</summary>

1. Ein `Command(resume=…)` geht immer an den Haltepunkt, an dem der Lauf steht. Eine Antwort, die für einen anderen
   gedacht war, würde dort als ungültig gelten oder – schlimmer – als etwas Falsches verstanden.
2. Dann bräuchten sie Schreibrechte, und die Nachkontrolle müsste zwischen erlaubten und verbotenen Schreibzugriffen
   unterscheiden. So gilt einfach: Planung ändert nichts, jede Änderung ist eine Grenzverletzung.
3. Die beiden Prüfer waren im abgebrochenen Superstep fertig geworden; ihre Writes standen im Checkpointer.
   LangGraph führt beim Wiederaufnehmen nur die Aufgaben aus, die noch keine Writes haben.
4. Ein roter Test zeigt einen Fehler, den man beheben kann. Ein übersprungener prüft nichts, sieht in Zählungen aber
   oft wie ein roter aus – die Fix-Schleife jagt dann einen Fehler, den es im Code nicht gibt.
</details>
