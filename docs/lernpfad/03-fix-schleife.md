# Lab 2 · Lernstufe 3: Fix-Schleife und Eskalation (Zyklus, interrupt, Checkpointer)

**Ausprobieren:** `.venv\Scripts\python.exe -m entwicklung lauf --repo portwart --aufgabe A3 --live`
(Dauer 5 bis 10 Minuten. Endet der Lauf mit `⏸ … wartet`, geht es weiter mit
`.venv\Scripts\python.exe -m entwicklung fortsetzen --entscheidung weiter|annehmen|abbrechen --live`)

## Die Idee in einem Satz

Lösen die Prüfer eine Fix-Runde aus, geht der Lauf **zurück** zum Implementierer, höchstens `max_runden` Mal. Danach
hält der Graph an und **Dominic** entscheidet, ob es weitergeht. Der Lauf wartet dabei im Checkpointer, auch wenn der
Prozess längst beendet ist.

## Der Ablauf am echten Code

```
vorbereiten → implementieren → grenzen_pruefen → tests_ausfuehren → 4 Prüfer → befunde_sammeln ─┬→ bericht
                    ↑                                                                           │
                    └──────────────── fix_runde ←─── (runde < max_runden) ──────────────────────┤
                                          ↑                                                     │
                                          └── weiter ── eskalation ←── (runde = max_runden) ────┘
                                                          │  ↺ ungültige Antwort
                                                          └→ annehmen / abbrechen → bericht
```
`entwicklung/graph.py`, `baue_graph_s3`.

### 1. Der Zyklus: eine Kante zurück und eine Abbruchbedingung im State

Der Zyklus besteht aus einer einzigen gewöhnlichen Kante: `g.add_edge("fix_runde", "implementieren")`. LangGraph
erlaubt das ohne Weiteres. Damit der Lauf irgendwann endet, braucht es zwei Zahlen im State, `runde` und
`max_runden`, und eine bedingte Kante, die sie liest (`nach_befunden`):

```python
if state.get("status") in ("grenzverletzung", "agent_fehler") or not state["fix_noetig"]:
    return "bericht"
return "fix_runde" if state["runde"] < state["max_runden"] else "eskalation"
```
Ohne diese Bedingung bricht erst LangGraph selbst ab, mit `GraphRecursionError`, wenn `recursion_limit` erreicht
ist. Ältere Versionen und viele Tutorials nennen dafür 25 Supersteps. In LangGraph 1.2.10 ist der Standard aber
**10007** (`langgraph/_internal/_config.py`, gezählt je Aufruf ab dem Fortsetzungspunkt). Eine Runde ist hier
6 Supersteps lang (implementieren, grenzen_pruefen, tests_ausfuehren, die vier Prüfer zusammen, befunde_sammeln,
fix_runde). Das wären rund 1600 Runden mit echten Modellaufrufen, also praktisch endlos. Die Bedingung im State ist
der Ablauf, das Limit nur die Notbremse.

### 2. Ein Reducer, der auch leeren kann

In Stufe 2 sammelte `operator.add` die vier Prüferberichte. `operator.add` kann aber nur wachsen. In Runde 2 lägen
dann acht Berichte im State, vier davon von Code, den es nicht mehr gibt. Deshalb gibt es einen eigenen Reducer
(`state.py`):

```python
def sammeln_oder_leeren(alt, neu):
    if neu is LEEREN:        # LEEREN = None
        return []
    return (alt or []) + neu
```
`fix_runde` schreibt `{"pruefberichte": LEEREN}` und leert die Liste so für die nächste Runde. Die Rundengeschichte
geht dabei nicht verloren: `runden` hat weiter `operator.add` und bekommt je Runde eine Zeile mit Tests und Befunden.
Dieselbe Frage („wächst das Feld oder ist es je Runde neu?“) muss man für jedes Feld eines Zyklus beantworten.

### 3. interrupt als Notausgang

`eskalation` ruft `interrupt({...})` auf. Der Graph hält **mitten im Knoten** an, speichert den Stand und gibt die
Frage im Stream als `__interrupt__` heraus. Weiter geht es mit `graph.invoke(Command(resume={"entscheidung": "weiter"}),
cfg)`. Dann läuft der Knoten **von vorn**, und `interrupt(...)` gibt diesmal die Antwort zurück, statt anzuhalten.

`weiter` erhöht `max_runden` um 1 und geht zu `fix_runde`. `annehmen` und `abbrechen` setzen den Status und gehen
zum Bericht.

### 4. Drei Fallen in LangGraph 1.2.10 (gemessen 19.10.)

| Versuch | Was passiert |
|---|---|
| Zweites `interrupt` im selben Knoten (um bei ungültiger Antwort neu zu fragen) | Der Graph hält an, aber `get_state().next` ist leer. Nach `next` sieht ein wartender Lauf aus wie ein fertiger (nur `tasks` zeigt noch das offene interrupt). |
| `Command(resume={})` | Zählt nicht als Antwort; das interrupt feuert erneut mit der Originalfrage. |
| `Command(resume=None)` | Absturz: `UnboundLocalError` in `_loop._first`. |

Daraus folgt die Regel im Code: **genau ein interrupt je Knotendurchlauf.** Bei einer ungültigen Antwort setzt
`eskalation` nur `entscheidung: None` und einen Hinweis, und `nach_eskalation` schickt den Lauf über eine Kante zu sich
selbst zurück (`"eskalation"`). Der nächste Durchlauf fragt neu, und diesmal mit dem Hinweis. Die CLI schickt immer
ein dict, also nie `None`.

### 5. Ohne Checkpointer kein Fortsetzen

Ein interrupt ohne Checkpointer hält zwar an, aber man kann nie weitermachen: Der Stand liegt nirgends. Deshalb
öffnet die CLI ab Stufe 3 einen `SqliteSaver` (`data/checkpoints.db`, `speicher.py`). Jeder Lauf bekommt eine
`thread_id` wie `lauf-20261019-225712`. In den Tests ersetzt `InMemorySaver` ihn. Die ID wird atomar vergeben
(Tabelle `reservierung` mit PRIMARY KEY in derselben DB), damit zwei Läufe aus derselben Sekunde nie denselben
Thread teilen.

**Fortsetzen ohne Merker-Datei.** Welcher Lauf wartet, steht schon im Checkpointer, man muss nur fragen:

```python
zustand = graph.get_state({"configurable": {"thread_id": tid}})               # speicher._wartet
any(a.name == "eskalation" and a.interrupts for a in zustand.tasks)
```
`zustand.next` allein reicht **nicht**. Es nennt die Knoten, die als Nächstes laufen würden. Wird der Prozess nach dem
Checkpoint von `befunde_sammeln` beendet, steht dort schon `eskalation`, obwohl noch keine Frage gestellt ist
(Befund aus dem Codex-Review, Test `test_geplante_eskalation_ohne_interrupt_wartet_nicht`). Erst ein offenes
interrupt an der Aufgabe heißt „wartet auf Antwort“.

Eine eigene Datei „wartet gerade“ könnte vom echten Stand abweichen (Absturz, zweiter Lauf). Der Checkpointer kann
das nicht. Zu Falle 1 nachgemessen (20.10.): Nach dem zweiten interrupt ist `next` leer, `tasks` zeigt die Aufgabe
`eskalation` aber weiter mit offenem interrupt. Die jetzige Prüfung über `tasks` hätte den Lauf also gefunden, die
erste über `next` nicht. Die Kante zu sich selbst bleibt trotzdem richtig: `next` ist die Stelle, an der man in
LangGraph nachsieht, „wo der Lauf steht“, und sie soll nicht lügen.
Auch `aufraeumen` fragt den Checkpointer und lässt den Worktree eines wartenden Laufs stehen.

Nach dem Lauf liest die CLI den Endstand ebenfalls aus dem Checkpointer (`get_state` plus offene interrupts). So
werden `--live` und der stille Lauf gleich ausgewertet. Exit-Code `3` heißt: Der Lauf wartet.

## Die echten Runden

**A2, Lauf 20261019-225129** (gemergt, portwart `2353b83`):

| Runde | Tests | Auslösend |
|---|---|---|
| 0 | 54/54, Akzeptanz 35/35 | clean_code major/test-gap: die Garantie „netstat nur aus System32“ hat keinen eigenen Test |
| 1 | 63/63, Akzeptanz 35/35 | keiner, Ergebnis 🟢 (neu: `tests/test_lauschen.py`) |

Das ist der Normalfall, für den die Schleife gebaut ist: ein echter Befund, eine Runde, fertig.

**A3, Lauf 20261019-225712** (angenommen 🟡):

| Runde | Tests | Auslösend |
|---|---|---|
| 0 | 93/93, Akz. 61/61 | codex: `frei -1-5` wird von argparse als Option gelesen, kein `Fehler:` auf stderr |
| 1 | 94/94, Akz. 61/61 | codex 2×: die Korrektur zerlegt `--`; eine sehr lange Ziffernfolge ergibt `ValueError` statt `BereichsFehler` |
| 2 | 96/96, Akz. 61/61 | clean_code major/bug: netstat-Lesecode doppelt in `_frei` und `_abgleich` → **Eskalation**, Entscheidung `weiter` |
| 3 | 96/96, Akz. 61/61 | clean_code major/bug: `main()` durch den `-1-5`-Sonderfall schwer wartbar → **Eskalation**, Entscheidung `annehmen` |

Funktional war A3 ab Runde 0 grün. Die ersten beiden Runden haben echte Randfälle geschlossen. Runde 3 hat den
Befund aus Runde 2 erledigt (`_lies_text`). Der neue Befund betrifft Code, den die Schleife selbst geschrieben hat.

## Schwere-Inflation: die Grenze der Fix-Regel

Die Regel lautet: Eine Fix-Runde startet, wenn ein Befund aus dem Topf `candidates` die Schwere `blocker` oder `major`
hat. **Die Schwere vergibt der Prüfer selbst.** Clean Code nannte doppelten Code und ein umständliches `main()`
„major/bug“, obwohl keiner der beiden Punkte bei der Benutzung auffällt. Jede Runde schreibt neuen Code, darin findet
Clean Code den nächsten Punkt, und die Schleife hat kein natürliches Ende. Die Eskalation hat genau das abgefangen:
Bei Runde 3 hat ein Mensch entschieden, dass es reicht.

**Geschärft nach dem Stufen-Gate (20.10., Entscheid Dominic):** Ein `major` von Clean Code (Topf `candidates`)
löst nur aus, wenn ein zweiter Modell-Prüfer (Security oder Codex) dieselbe Stelle meldet: dieselbe Datei, höchstens
3 Zeilen entfernt, gültige Zeile, Zitat im Code gefunden (Topf `candidates` oder `side`). Sonst ist der Befund
`gebremst` und steht nur im Bericht (`befunde._zweite_stimme`). Sonst bleibt die Regel wie vorher: Jeder
Funktionsbefund löst aus, von den Modell-Prüfern nur `blocker` oder `major` im Topf `candidates`; davon ist jetzt
nur das Clean-Code-`major` gebremst.

Die Regel prüft die **Rohbefunde vor dem Zusammenführen**. Nach dem Zusammenführen stehen mehrere Prüfer an einem
Befund mit nur einem Topf; dann wüsste man nicht mehr, ob die zweite Stimme ein belegtes Zitat hatte (Befund aus dem
Codex-Review des Nachtrags).

Rückwirkend auf die echten Runden angewandt (Befunde aus einer Kopie der Checkpoint-DB):

| Lauf · Runde | vorher auslösend | mit Regel |
|---|---|---|
| A2 · 0 | 1 | 1 (die Testlücke hatte eine zweite Stimme) |
| A3 · 0 und 1 | 1 und 2 | 1 und 2 (Codex) |
| A3 · 2 | 1 | 0, gebremst: doppelter netstat-Lesecode |
| A3 · 3 | 1 | 0, gebremst: `main()` schwer wartbar |

A3 wäre also nach Runde 2 grün geendet, ohne Eskalation. Der Preis: Einen echten Wartbarkeitsfehler, den nur Clean
Code sieht, behebt die Schleife nicht mehr von selbst. Der Schiedsrichter-Knoten, der jedes `major` nach seiner
Wirkung neu einstuft, kommt in Stufe 6 (Modellstufen).

## Selbst prüfen

1. Was passiert, wenn man in `nach_befunden` den Vergleich `runde < max_runden` weglässt und Clean Code in jeder Runde
   etwas findet?
2. Warum reicht `operator.add` für `pruefberichte` nicht mehr, für `runden` aber schon?
3. Warum fragt `eskalation` bei einer ungültigen Antwort nicht einfach mit einem zweiten `interrupt` neu?
4. Wie findet `fortsetzen` den wartenden Lauf, obwohl der erste Prozess beendet ist?

<details><summary>Antworten</summary>

1. Der Zyklus läuft, bis LangGraph bei `recursion_limit` (Standard 10007 in 1.2.10) mit `GraphRecursionError`
   abbricht, nach rund 1600 Runden, ohne Bericht und ohne Frage an Dominic. Praktisch: endlos und teuer.
2. Die Prüfer einer Runde sollen nur den aktuellen Code bewerten, also muss die Liste je Runde neu beginnen. `runden`
   ist dagegen die Geschichte und soll wachsen.
3. In LangGraph 1.2.10 ist danach `get_state().next` leer: Der wartende Lauf wäre nicht mehr als wartend zu erkennen.
   Stattdessen: ein interrupt je Durchlauf, Kante zu sich selbst.
4. Über den SqliteSaver: Alle `thread_id`s durchgehen und die nehmen, deren `get_state().next` die Eskalation ist.
</details>
