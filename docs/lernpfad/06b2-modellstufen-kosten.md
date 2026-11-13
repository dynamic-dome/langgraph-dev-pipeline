# Lab 2 · Lernstufe 6b-2: Modellstufen und Kostenrahmen

**Ausprobieren:** im Leitstand „+ Neuer Lauf“ mit `auto` und einem Rahmen, oder
`.venv\Scripts\python.exe -m entwicklung lauf --repo portwart --aufgabe A8 --budget 40 --live`. Ohne echte Agenten:
`docs\lernpfad\leitstand_demo.py` (dort schätzt Claude „einfach“ und Codex „schwer“; mit Rahmen 3 hält der Lauf vor
dem Plan an).

## Die Idee in einem Satz

Ein einziger Regler, die Komplexität, wählt Modell und Reasoning für jede Rolle aus einer Tabelle, und geschätzt
wird sie von beiden Modellfamilien, nicht von Claude allein.

## Ein Regler statt zwei mal zwei

Vorher gab es zwei Modell-Felder (Implementierer, Prüfer) und kein Reasoning. Vier Einstellungen, die zueinander
passen müssen, stellt niemand an jeder Freigabe richtig ein. Jetzt steht alles in `entwicklung/stufen.py`:

| Komplexität | Implementierer | Prüfer der Umsetzung |
|---|---|---|
| einfach | sonnet · medium | opus · high |
| mittel | sonnet · high | opus · high |
| schwer | opus · high | opus · xhigh |

Die Leitlinie stammt von Dominic: sonnet implementiert, opus prüft. Die Prüfer stehen nie unter dem Implementierer.
Fable bleibt Berater auf Klick und kommt in der Tabelle nicht vor. haiku gibt es nur über die Startwahl: Wer es
testen will, überschreibt damit das Modell, das Reasoning kommt weiter aus der Tabelle. Die Planung läuft fest
(sonnet · high schreibt, opus · high prüft), denn die Komplexität ist erst nach der Spec bekannt.

**Codex bleibt auf `high`.** codex-cli 0.163.0 nahm am 20.10. auch den erfundenen Wert `ultra` ohne Fehler an. Ob
`xhigh` dort etwas bewirkt, ist damit nicht belegt, und eine Einstellung ohne Beleg kommt nicht in die Tabelle.

## Wer schätzt: beide Familien, die höhere gilt

Würde nur Claude schätzen, wäre das genau der blinde Fleck, den 6b-1 schließen sollte: Dieselbe Familie, die die
Spec schreibt, entscheidet dann auch, wie viel Prüfung die Umsetzung bekommt (Einwand von Dominic). Deshalb:
- Claude schätzt beim Schreiben der Spec (`komplexitaet`, `komplexitaet_grund` im Spec-Schema).
- Codex schätzt bei der Spec-Prüfung (eigenes Schema nur für diese Prüfung).
- Der Router-Knoten `stufe_waehlen` nimmt die höhere Schätzung. Unterschätzen kostet Fix-Runden und rutscht im
  schlimmsten Fall durch. Überschätzen kostet nur Geld.
- An der Plan-Freigabe bestätigt oder ändert Dominic. Der Bericht vermerkt „von Dominic geändert“.

**LangGraph-Begriff Router-Knoten:** `stufe_waehlen` entscheidet nichts über den Weg (die Kante danach ist fest).
Er schreibt eine Entscheidung in den State, die spätere Knoten lesen (`stufe_im_lauf(state, rolle)`). Eine bedingte
Kante wäre hier falsch: Es gibt keinen anderen Weg, nur andere Parameter auf demselben Weg.

## Kostenrahmen: zählen, ohne jeden Knoten anzufassen

Gemessen wird in **Agentenaufrufen**, nicht in Euro: Das Abo kennt keine Preise je Aufruf, Aufrufe sind zählbar und
für Dominic verständlich. Standard sind 40 Aufrufe. Ein normaler Lauf (Klären, Spec, Tests, 2 Spec-Prüfer, Plan,
Plan-Prüfung, Implementierer, 3 Prüfer mit Modell) braucht etwa 12.

**Zwei LangGraph-Bausteine dafür:**
- **Reducer:** `aufrufe: Annotated[int, operator.add]`. Jeder Knoten liefert nur seine eigenen Aufrufe, LangGraph
  addiert. Ohne Reducer würden die vier parallelen Prüfer (Send) einander überschreiben.
- **contextvar-Zähler:** Statt in jedem `return` von Hand `aufrufe` zu setzen, umhüllt `gezaehlt(knoten)` jeden
  Knoten. Die Agentenfunktionen rufen `zaehle()`, und der Zähler gehört zum Thread des Knotens. Parallele
  Send-Knoten zählen deshalb getrennt und richtig. `functools.wraps` ist nötig: LangGraph liest an der Annotation
  der Funktion, ob ein Send-Knoten den Auftrag bekommt.

**Drei Wächter-Knoten** (`budget_spec`, `budget_plan`, `budget_umsetzung`) stehen vor den teuren Schritten, der
letzte auch vor jeder Fix-Runde. Ist der Rahmen erreicht, halten sie per `interrupt` an: „mehr“ (+20) oder
„abbrechen“. Jeder hat eine eigene Rückkante zu sich selbst für ungültige Antworten (genau ein `interrupt` je
Durchlauf, wie bei allen Haltepunkten). Geprüft wird nur an diesen drei Stellen. Der Stand kann deshalb über dem
Rahmen liegen (in der Demo 5/3), dafür reißt nie ein Agent mitten in der Arbeit ab.

**Am Kostenrahmen gibt es keinen Rat.** Das fiel erst an der Demo auf: Die Berater-Knöpfe standen auch dort. Ein
Rat kostet selbst Aufrufe, und das Rat-Schema kennt „mehr“ gar nicht. Server (409), CLI und Oberfläche lehnen ihn
jetzt ab.

## Was sonst dazukam

- Fable und Astra beraten beide mit Reasoning `high`.
- Astra bekommt den von git verfolgten Code des Ziel-Repos auch an Rückfragen und Spec, erst den Code, dann
  `tests/`, nie `tests/_akzeptanz/` (aus der Abnahme von A7).

## Abnahme an A8 („portwart austragen“)

Lauf `lauf-20261021-120756` am 21.10., gestartet von Dominic mit `auto` und Rahmen 50. Ergebnis **🟢 grün**:
595/595 Tests, davon 317 Akzeptanztests aller Aufgaben bis A8. Keine Fix-Runde, 29 von 50 Aufrufen, dazu 6× Fable
und 6× Astra als Berater. Bericht: `berichte/20261021-120756.md`.

- **Schätzung:** Claude und Codex sagen beide „schwer“ (atomares Umschreiben der Portliste, eigener zeilenweiser
  TOML-Erkenner, Gefahr von Datenverlust). Die Tabelle gab opus · high für den Implementierer und opus · xhigh für
  die Prüfer. Der Implementierer brauchte 237 s und 19 Turns, die Akzeptanztests waren auf Anhieb grün.
- **Klären hat die absichtlich offene Stelle gefunden:** Die Pipeline fragte, ob Kommentare direkt über dem Block
  mit entfernt werden. Dominics Antwort: Alle Kommentare bleiben.
- **Vier Spec-Runden, 20 Aufrufe bis zur ersten Freigabe.** Die Befunde je Runde entstanden überwiegend **durch die
  vorige Korrektur**, die alten Befunde wurden nicht übersehen: Tests 27 → 30, Annahmen 9 → 15, Spec 21,7 KB. Der
  Schreiber flickt jeden Befund mit einer neuen, genaueren Regel, und die stärkeren Prüfer (sonnet · high, opus · high,
  Codex high; am 20.10. noch sonnet ohne Effort) finden genau das Neue. Nur die Reload-Absicherung kehrte jede Runde
  wieder. Die Planung war also nicht zu schwach eingestellt. Ihr fehlt eine **Abbruch- und Konvergenzlogik**:
  Diff-Prüfung gegen die Vorrunde, „ab Runde 2 nur noch Befunde aus der letzten Änderung oder Widersprüche zu den
  Antworten“, Grenzfälle lieber ablehnen als mit Sonderregeln lösen.
  Belegt hat das die Runde nach „Tests nachbessern“: Sobald die Spec nicht mehr angefasst wurde, kam sie zum ersten
  Mal ohne Major zurück.
- **Plan auf Anhieb freigegeben** (Codex PASS, Fable und Astra „freigeben“), 5 Aufrufe.
- **Offener Befund (security, minor, Spec-Lücke):** Bei mehreren Blöcken hängt sich eine Untertabelle des entfernten
  Eintrags (`[port.meta]`, `[[port.sub]]`) still an den vorherigen Eintrag. Die Kopfzahl stimmt, und `lade`
  ignoriert unbekannte Schlüssel, also besteht der Reload. Heute ohne Folgen, weil portwart keine Untertabellen
  nutzt. Kandidat für eine kleine Folgeaufgabe.
- **Reicht der Rahmen?** Der Standardrahmen 40 hätte gereicht (29). Ohne die Spec-Schleife wären es etwa 15–18
  gewesen.

## Selbst prüfen

1. Warum gilt die höhere der beiden Schätzungen und nicht der Durchschnitt?
2. Warum zählt ein contextvar im Knoten richtig, ein globaler Zähler aber nicht?
3. Warum hält der Lauf nur an drei Punkten an und nicht vor jedem einzelnen Agentenaufruf?

<details><summary>Antworten</summary>

1. Die Fehler kosten ungleich viel: Zu niedrig geschätzt heißt schwächere Prüfer und mehr Fix-Runden. Zu hoch
   geschätzt kostet nur Aufrufe. Bei drei Stufen gibt es außerdem keinen sinnvollen Durchschnitt aus „einfach“ und
   „schwer“.
2. Die vier Prüfer laufen gleichzeitig in eigenen Threads. Ein globaler Zähler würde gemischt, und kein Knoten
   wüsste, welche Aufrufe seine sind. Der contextvar gehört zum Thread, und der Reducer addiert danach die
   Ergebnisse der Knoten.
3. Ein Halt mitten in der Prüfung ließe einen halben Stand zurück (drei von vier Prüfern fertig). An den drei
   Punkten ist der Stand vollständig, und „mehr“ oder „abbrechen“ ist dort eine echte Entscheidung.
</details>
