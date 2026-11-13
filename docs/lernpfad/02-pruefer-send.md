# Lab 2 · Lernstufe 2: Vier Prüfer gleichzeitig (Send, Reducer, Fan-in)

**Ausprobieren:** `.venv\Scripts\python.exe -m entwicklung lauf --repo portwart --aufgabe A2 --live`
(Dauer 2 bis 3 Minuten; mit `--stufe 1` läuft die alte Pipeline ohne Prüfer)

## Die Idee in einem Satz

Nach den Tests prüfen vier Prüfer dasselbe Ergebnis **gleichzeitig**. LangGraph startet sie mit `Send`, sammelt ihre
Berichte mit einem **Reducer** ein und lässt `befunde_sammeln` erst laufen, wenn alle vier fertig sind.

## Der Ablauf am echten Code

```
… → tests_ausfuehren ─┬→ pruefen_funktion   ┐
                      ├→ pruefen_security   │  ein Superstep, laufen gleichzeitig
                      ├→ pruefen_clean_code │
                      ├→ pruefen_codex      ┘→ befunde_sammeln → bericht
                      └→ bericht   (Testcode hat in ein geschütztes Repo geschrieben)
```
`entwicklung/graph.py`, `baue_graph_s2`.

### 1. Send an verschiedene Ziele

In Lab 1 ging `Send` an *denselben* Knoten (eine Prüfung je Komponente). Hier geht je ein `Send` an einen
**anderen** Knoten (`zu_pruefern`):

```python
return [Send(knoten, auftrag) for knoten in PRUEFER_KNOTEN]
```

Der Auftrag (`auftrag`) ist nicht der State, sondern ein eigenes kleines Paket: Worktree, Aufgabe, Diff,
geänderte Dateien, Testergebnis. Deshalb sind die Prüfer mit `auftrag: dict` annotiert. Mit dem State-Typ würde
LangGraph Felder herausfiltern, die nicht im State stehen (die Falle aus Lab 1, Stufe 5).

Dieselbe bedingte Kante kann statt der Liste auch einen Knotennamen zurückgeben: `"bericht"`, wenn der Testlauf schon
eine Grenzverletzung gefunden hat. `add_conditional_edges` bekommt dafür alle möglichen Ziele mit.

### 2. Reducer: vier Knoten schreiben in dasselbe Feld

```python
pruefberichte: Annotated[list[dict], operator.add]   # state.py
```
Jeder Prüfer gibt `{"pruefberichte": [sein_bericht]}` zurück. Ohne Reducer würde der Graph mit
`InvalidUpdateError` abbrechen, weil im selben Superstep vier Knoten dasselbe Feld setzen. Mit `operator.add` werden
die vier Listen aneinandergehängt.

### 3. Fan-in: Der Superstep ist der Wartepunkt

Alle vier Prüfer haben eine Kante zu `befunde_sammeln`. Weil sie im selben Superstep laufen, startet
`befunde_sammeln` genau einmal, im nächsten Superstep, mit allen vier Berichten. Eine eigene Warte- oder Zähllogik
braucht es nicht.

Belegt im echten Lauf (19.10., 21:15). Die Zeitstempel kommen aus `--live`:

```
[  49.2 s] ✓ tests_ausfuehren  53/53 bestanden · Akzeptanz 34/34
[  49.2 s] ✓ pruefen_funktion  PASS · 0.0 s
[  85.9 s] ✓ pruefen_security  PASS · 36.7 s · 1 Befund
[  93.5 s] ✓ pruefen_clean_code PASS · 44.3 s · 3 Befunde
[ 139.7 s] ✓ pruefen_codex     PASS · 90.5 s · 2 Befunde
[ 140.2 s] ✓ befunde_sammeln   6 Befunde, 0 auslösend
```
Die drei Agenten starteten alle bei 49,2 s. Jeder endete bei 49,2 s plus der eigenen Dauer. Nacheinander wären es
171 s Prüfzeit gewesen, so waren es 91 s, also so lange wie der langsamste (Codex). LangGraph führt die Aufgaben
eines Supersteps in einem Thread-Pool aus. Unsere Knoten warten nur auf Subprozesse, deshalb reicht das.

Die `updates` kommen in der Reihenfolge, in der die Prüfer **fertig** werden. Im State steht die Liste dagegen in
Send-Reihenfolge (Lernnotiz Lab 1, Stufe 2). Wer „wer war zuerst fertig“ wissen will, muss den Stream lesen.

## Warum „Funktion“ kein LLM ist

`pruefen_funktion` (`pruefer.funktion_bericht`) liest nur das gezählte Testergebnis und macht daraus Befunde im
selben Schema wie die anderen. Ob Tests grün sind, ist eine Tatsache, keine Meinung. Ein Modell, das das
„beurteilt“, kann sich nur irren. Deshalb gehen Funktionsbefunde auch ohne Filter durch (`topf: deterministisch`).

## Befunde: Quellenprüfung statt Blindübernahme

Die drei anderen Prüfer sind Modelle und können sich Dinge ausdenken. `befunde.sammle` schickt jeden Bericht durch
den Filter von fusion-harness. Der prüft, ob das Zitat (`quote`) wirklich im gesicherten Commit steht, und sortiert
in Töpfe:

| Topf | heißt | löst Fix-Runde aus |
|---|---|---|
| `deterministisch` | aus dem Testlauf gezählt | ja |
| `candidates` | Zitat gefunden, blocker/major | ja |
| `quote_missing` | Zitat steht nicht im Code | nein |
| `side` | minor oder Stil | nein |
| `out_of_scope` | Datei nicht im Diff | nein |

Im echten Lauf: 6 Befunde, alle `minor`, also keine Fix-Runde. Einer ist an der Quelle nachgeprüft:
`--netstat-datei ""` startet tatsächlich still das echte netstat (`if args.netstat_datei:` statt `is not None`).
Clean Code **und** Codex haben ihn gefunden, mit verschiedenen Worten. Die Dublettenerkennung vergleicht den Wortlaut
und hat beide deshalb nicht zusammengeführt. Das ist eine Grenze, die man kennen muss.

## Die Prüfer lesen nur, und das wird nachgeprüft

- Security und Clean Code: `claude -p --restricted --tools Read,Glob,Grep`, also ohne Schreib- und Befehlswerkzeuge.
- Codex: `-s read-only`. Hier kann Codex gar keine Prozesse starten, deshalb stehen Diff und Dateien im Prompt
  (`docs/spike-2026-10-19-pruefer.md`).
- `befunde_sammeln` vergleicht den Worktree und die geschützten Repos vor und nach den Prüfern.
  (`test_pruefer_schreibt_ist_grenzverletzung`)
- Neu: Auch **nach dem Testlauf** werden die geschützten Repos verglichen, denn dort läuft Code des Agenten.
  Ein Test, der ins portwart-Hauptrepo schreibt, ergibt jetzt `grenzverletzung`, und die Prüfer laufen nicht.
  (`test_testcode_schreibt_ins_hauptrepo`)

## Was portwart jetzt kann

`python -m portwart abgleich` gegen das echte netstat dieses Rechners: alle vier eingetragenen Ports derzeit frei
(auch 8770), dazu **25 lauschende Ports, die in keiner Liste stehen** (u. a. 7801, 7811, 8000, 9000–9004). Das ist
genau der Stoff für die zentrale Portliste.

## Selbst prüfen

1. Was passiert, wenn man in `state.py` den Reducer bei `pruefberichte` weglässt?
2. Warum annotieren die Prüfer `auftrag: dict` und nicht `EntwicklungState`?
3. Die Prüfer laufen parallel. Warum dauert der Prüfabschnitt trotzdem 91 s und nicht 37 s?

<details><summary>Antworten</summary>

1. Vier Knoten setzen im selben Superstep dasselbe Feld: `InvalidUpdateError`. Der Graph bricht ab.
2. LangGraph filtert die Eingabe nach dem annotierten Typ. Felder des Auftrags wie `diff` und `dateien` stehen nicht
   im State und wären weg.
3. Der Wartepunkt ist der Superstep: `befunde_sammeln` startet erst, wenn auch der langsamste Prüfer (Codex, 90,5 s)
   fertig ist.
</details>
