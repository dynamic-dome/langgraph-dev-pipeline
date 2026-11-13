# Lab 2 · Lernstufe 1: Ein Agent als Knoten

**Ausprobieren:** `.venv\Scripts\python.exe -m entwicklung lauf --repo portwart --aufgabe A1 --live`
(im Projektordner, Dauer etwa eine Minute)

## Die Idee in einem Satz

Im Ökosystem-Puls (Lab 1) haben die Knoten nur **gelesen**. Hier gibt es zum ersten Mal einen Knoten, der
**Code schreibt**: einen echten Agenten (`claude -p`). Der Graph drumherum sorgt dafür, dass er nur dort schreiben
kann, wo er soll, und dass „fertig“ erst gilt, wenn unabhängige Tests es bestätigen.

## Der Ablauf am echten Code

```
vorbereiten → implementieren → grenzen_pruefen ─┬→ tests_ausfuehren → bericht
                                                 └→ bericht    (Grenzverletzung oder Agentenfehler)
```

`entwicklung/graph.py`, `baue_graph_s1`. Die LangGraph-Bausteine kennst du schon aus Lab 1: State als `TypedDict`
(`state.py`), Teil-Updates, eine bedingte Kante (`nach_grenzen`). Neu ist, **was** in den Knoten passiert:

| Knoten | macht | schreibt in den State |
|---|---|---|
| `vorbereiten` | Aufgabe lesen, `entwicklung.toml` aus dem **Hauptrepo** lesen, Stand der geschützten Repos merken, Worktree anlegen | `aufgabe_text`, `konfig`, `stand_vorher`, `worktree`, `lauf_id` |
| `implementieren` | Agent im Worktree starten | `agent` (ok, Zusammenfassung, Dauer, Turns, verweigerte Versuche) |
| `grenzen_pruefen` | Stand der geschützten Repos neu messen und vergleichen; Ergebnis des Agenten als Commit sichern | `grenzverletzungen`, `geaenderte_dateien`, `sicherung`, ggf. `status` |
| `tests_ausfuehren` | Akzeptanztests hineinkopieren, pytest, zählen, wieder entfernen | `testergebnis`, `status` |
| `bericht` | `berichte/<lauf_id>.md` und `.json` | `bericht_pfad` |

## Warum ein Worktree?

Der Agent bekommt nicht das portwart-Repo selbst, sondern eine **zweite Arbeitskopie** desselben Repos auf einem
eigenen Branch (`git worktree add -b lauf/<zeit>`, `worktree.py`). Der Hauptzweig bleibt unberührt, egal was der
Agent anstellt. Mehrere Läufe können nebeneinander stehen, und am Ende sieht man den Unterschied als normalen
git-Diff. Gemergt wird erst in Stufe 7, nach allen Prüfungen.

Der Agent darf selbst kein git. Die Pipeline committet sein Ergebnis (`worktree.sichern`). Danach ist der Worktree
sauber und lässt sich ohne `--force` entfernen (`python -m entwicklung aufraeumen`); der Branch bleibt als Sicherung.

## Zwei Sperren, weil eine nicht reicht

**Sperre 1, vorher: was der Agent überhaupt darf** (`agenten.py`). Gemessen im Spike
(`docs/spike-2026-10-19-restricted.md`):
- `--restricted`: Datei-Werkzeuge nur im Arbeitsordner.
- `--permission-prompts none` + `--allowedTools "Bash(<python> -m pytest:*)"`: Nur der Testbefehl läuft; git, curl
  und alles andere wird ohne Rückfrage verweigert. Im echten Lauf versuchte der Agent zum Beispiel, Dateien per
  `cat > … <<EOF` anzulegen, wurde abgewiesen und nahm dann das Write-Werkzeug. Das steht im Bericht unter
  „Verweigerte Versuche“.

**Sperre 2, nachher: was tatsächlich passiert ist** (`grenzen_pruefen`). Sperre 1 hat eine Lücke: Code, den der
Agent über pytest ausführt, kann überall schreiben. Deshalb misst die Pipeline vor und nach dem Agenten den
git-Stand von portwart **und** Lab 2 (`worktree.stand`, mit Inhalts-Hash je geänderter Datei). Weicht etwas ab,
endet der Lauf mit `grenzverletzung`, und die Tests laufen gar nicht erst.

Die zweite Sperre hat sich beim ersten echten Lauf gleich bewiesen, nur nicht so, wie gedacht: Ich habe während
des Laufs `HOW-TO-USE.md` in Lab 2 bearbeitet. Die Nachkontrolle meldete
`langgraph-lab-2: HOW-TO-USE.md neu oder verändert` und brach ab. Sie kann nicht wissen, *wer* geschrieben hat,
nur *dass*. Daraus folgt eine Regel: Während ein Lauf läuft, arbeitet niemand in den geschützten Repos.

Ganz dicht wird es erst mit einer echten Sandbox (WSL, Docker oder ein zweiter Rechner mit Linux), siehe Entwurf.

## Warum unabhängige Akzeptanztests?

Wenn der Agent seine eigenen Tests schreibt und sie grün bekommt, beweist das nur, dass Code und Tests
zueinander passen, nicht dass beides zur Aufgabe passt. Deshalb gibt es `aufgaben/portwart/A1/test_akzeptanz_a1.py`
(19 Tests), die der Agent **nie sieht**: Sie stehen nicht im Prompt und nicht im Repo
(`test_prompt_enthaelt_aufgabe_aber_keine_akzeptanztests`). `testlauf.py` kopiert sie erst zum Testlauf nach
`tests/_akzeptanz/`, überschreibt dabei alles, was der Agent dort abgelegt haben könnte, und entfernt sie danach.

Der Agent bekommt stattdessen den **Vertrag** (`aufgaben/portwart/A1.md`): Namen, Signaturen, Ausgaben, Exit-Codes.
Genau das ist auch in echten Teams die Arbeitsteilung: Spezifikation und Abnahme kommen nicht vom Implementierer.

## „Grün“ heißt: gezählt, nicht gemeldet

`testlauf.py` liest das **JUnit-XML** von pytest, nicht die Textausgabe und nicht die Zusammenfassung des Agenten.
`gruen` gilt nur, wenn
- mehr als 0 eigene Tests gesammelt wurden (ein Importfehler ergibt 0 gesammelt plus 1 Fehler, also nicht grün),
- nichts fehlgeschlagen oder abgebrochen ist und beide pytest-Läufe mit Exit-Code 0 enden,
- genau so viele Akzeptanztests liefen wie erwartet, und alle bestanden.

**Nachgeschärft nach dem Codex-Review:** Der Worktree gehört dem Agenten, also auch eine `conftest.py` oder
`pytest.ini` darin. Eine conftest kann Tests beim Sammeln still abwählen. Deshalb laufen die Akzeptanztests in einem
**zweiten, abgeschirmten** pytest-Lauf (`--noconftest`, leere Konfiguration aus dem Temp-Ordner), und ihre Anzahl
wird vorher in einem leeren Ordner ohne jeden Code des Agenten gezählt (`_erwartete_anzahl`). Fehlt danach auch
nur einer, ist der Lauf nicht grün. Ebenso neu: Dateien, die der Agent per `.gitignore` versteckt, gelten als
Grenzverletzung, denn sie würden getestet, aber nicht gesichert.

Das ist dieselbe Regel wie beim Codex-Verifier: Status ist kein Beweis, gezählte Ergebnisse sind einer.

## Der echte Lauf (19.10.2026, 20:17)

```
[   0.4 s] ✓ vorbereiten       Worktree portwart-20261019-201746
[  44.3 s] ✓ implementieren    ok · 43.8 s · 8 Turns
[  44.7 s] ✓ grenzen_pruefen   4 Dateien, 0 Verletzungen
[  48.0 s] ✓ tests_ausfuehren  32/32 bestanden, 0 fehlgeschlagen, 0 Fehler · Akzeptanz 19/19
[  48.0 s] ✓ bericht
🟢 gruen
```
Von Hand nachgeprüft: `python -m portwart pruefen` auf der echten `ports.toml` meldet
`Port 8770 doppelt: job-radar, tool-tracker` (Exit 1), also die bekannte Kollision der damaligen Liste. Der portwart-Hauptzweig steht
unverändert auf dem Grundgerüst.

Abschlusslauf nach den Korrekturen (20:31): wieder grün, 35/35, Akzeptanz 19/19 von 19 erwarteten. Der
Implementierer brauchte diesmal 185 s statt 44 s, bei gleicher Aufgabe. Agenten sind nicht deterministisch, auch
nicht in der Laufzeit.

## Was noch fehlt (kommt in den nächsten Stufen)

- Stufe 2: parallele Prüfungen (Security, Clean Code, Codex) mit `Send`, wie die Komponenten im Puls.
- Stufe 3: Fix-Schleife. Rote Tests oder ernste Befunde gehen mit Begründung zurück an den Implementierer, höchstens
  zweimal, dann Eskalation.
- Stufe 4: Klären, Spec und Plan vor dem Implementieren, mit Freigaben per `interrupt`.

## Selbst prüfen

1. Warum liest `vorbereiten` die `entwicklung.toml` aus dem Hauptrepo und nicht aus dem Worktree?
2. Was würde passieren, wenn `tests_ausfuehren` die Akzeptanztests nicht vorher löscht, sondern nur dazukopiert?
3. Der Agent schreibt in einem Test `Path("C:/Users/<name>/notiz.txt").write_text("x")`. Welche Sperre fängt das, und
   welche nicht?

<details><summary>Antworten</summary>

1. Der Agent könnte die Datei im Worktree ändern und sich einen bequemeren Testbefehl geben (etwa einen, der nichts
   prüft).
2. Der Agent könnte unter `tests/_akzeptanz/` eine eigene Datei mit gleichem Namen anlegen, die immer grün ist;
   sie würde dann bestehen bleiben oder zusätzliche „Akzeptanztests“ einschmuggeln
   (`test_manipulierte_akzeptanz_wird_ersetzt`).
3. Keine der beiden: `--restricted` prüft nur Werkzeugaufrufe, nicht, was pytest-Code intern tut, und die
   Nachkontrolle beobachtet nur portwart und Lab 2. Das ist die bekannte Lücke; schließen lässt sie nur eine
   Sandbox.
</details>
