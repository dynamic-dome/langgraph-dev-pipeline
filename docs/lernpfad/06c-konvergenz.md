# Lab 2 · Lernstufe 6c: Konvergenz der Spec-Runden

**Ausprobieren:** `docs\lernpfad\leitstand_demo.py --port <frei>` → „+ Neuer Lauf“ → Rückfrage beantworten → an der
ersten Spec-Freigabe „Spec ändern“. Die zweite Fassung zeigt dann die beiden Gruppen, den Verlauf und den Einwand
„Codex meldet major weiter teilweise“. Echt: `.venv\Scripts\python.exe -m entwicklung lauf --repo portwart --aufgabe A9 --live`.

## Die Idee in einem Satz

Ab der zweiten Fassung prüfen die Prüfer gegen die Vorfassung statt von vorn, und ein fester Schritt im Graphen
entscheidet, welche ihrer Punkte überhaupt eine neue Runde rechtfertigen.

## Warum: A8 brauchte vier Fassungen

In A8 („portwart austragen“) kam die Spec viermal zurück. Die meisten Befunde einer Runde entstanden erst durch die
Korrektur der vorigen: Tests 27 → 30, Annahmen 9 → 15, am Ende 21,7 KB Spec für „einen Eintrag löschen“. Die Prüfer
waren nicht zu schwach, sie prüften jede Fassung von null, und der Schreiber flickte jeden Befund mit einer neuen
Sonderregel. Dazu kam: Astra und Fable empfahlen dreimal „ändern“, weil jeder Major gleich viel zählte.

## Drei Bausteine

1. **Nachprüfung** (`konvergenz.nachpruef_text`, `NACHPRUEF_SCHEMA`): Die Prüfer bekommen den Diff von Spec und
   Tests und die alten Punkte. Zu jedem alten Punkt melden sie `geloest`, `teilweise` oder `offen`, zu jedem neuen
   die Herkunft `aenderung`, `widerspruch` oder `sonstiges`.
2. **Regel im Graphen** (`konvergenz.einordnen`): Eine neue Runde lösen nur aus: neue Major aus der Änderung oder im
   Widerspruch zu Dominics Antworten, und alte Major, die nicht gelöst sind. Der Rest landet auf einer Liste für
   Dominic. Nur die auslösenden Punkte gehen an den Spec-Schreiber und in die Regel für die Berater.
3. **Zuschnitt-Bremse** (`planung.spec_prompt`): Bei „ändern“ liest der Schreiber die ganze Spec gegen die Antworten
   und löst Punkte durch Streichen, Vereinfachen oder Ablehnen, nicht durch neue Sonderregeln. Wie die Spec wächst,
   steht je Fassung im Verlauf (Zeichen, Annahmen, Tests).

**Ehrlich gesagt:** Die Regel allein hätte A8 nicht gebremst. Dort waren die meisten Befunde „durch die Änderung
entstanden“ und hätten zu Recht ausgelöst. Den Unterschied sollen die Bremse und die Nachprüfung machen.

## Wo die Regel sitzt, und warum dort

**Im Fan-in-Knoten `spec_pruefung_sammeln`, nicht in `spec_freigabe`.** Ein Knoten mit `interrupt` läuft beim
Fortsetzen von vorn bis zum interrupt. Nach einer ungültigen Antwort läuft er sogar noch einmal ganz. Stünde die
Verlaufszeile dort, käme sie bei jeder ungültigen Antwort doppelt in den State. `spec_pruefung_sammeln` läuft je
Prüfung genau einmal, nachdem beide Send-Zweige fertig sind.

**Im Graphen, nicht im Prompt.** Dem Schreiber „bitte nur die wichtigen Punkte beheben“ zu sagen, wäre eine Bitte.
Ihm nur die auslösenden Punkte zu geben, ist eine Garantie: Was er nicht sieht, kann er nicht flicken.

## Die Sperre bleibt ganz

Die Regel steuert nur die Runden, nicht die Codex-Sperre aus 6b-1. Jeder Codex-Major braucht weiter eine Begründung
zum Freigeben, auch einer mit Herkunft `sonstiges`. Der Codex-Verifier fand zwei Löcher, durch die die Sperre sonst
still entfallen wäre:

- **V1:** Ein Codex-Major von der Liste war in der Vorfassung nicht mehr enthalten. Nach „Tests nachbessern“ war
  sein Einwand weg, obwohl nichts gelöst war. Jetzt reist er als `nur_sperre` mit. Er löst keine Runde aus und bleibt
  Einwand, bis Codex ihn als gelöst meldet.
- **V2:** Fiel Codex bei der Nachprüfung aus, fehlte seine Bewertung, und der alte Major sperrte nicht mehr. Jetzt
  heißt eine fehlende Bewertung „nicht nachgeprüft“, und das bleibt ein Einwand.

Beide Male war die Ursache dieselbe: Ein fehlender Wert wurde als „nichts zu tun“ gelesen. Für eine Sperre muss
„weiß ich nicht“ wie „nein“ zählen.

## Abnahme an A9 („Austragen mit Untertabellen“)

Lauf `lauf-20261021-193226` am 21.10. mit `auto`, gefahren von Claude im Auftrag von Dominic. An den Freigaben hat
Claude nach der Einordnung entschieden, ohne Fable und ohne Astra. In A8 hatte Dominic mit beiden Beratern
entschieden, der Vergleich ist also nicht ganz sauber.

| | A8 (6b-2, 21.10.) | A9 (6c, 21.10.) |
|---|---|---|
| Spec-Fassungen bis zur Freigabe | 4 | **1** (+ einmal Tests nachgebessert) |
| Spec-Prüfungen | 5 | 2 |
| Spec-Größe zuletzt | 21,7 KB | 9,1 KB |
| Plan-Fassungen | 1 | 2 |
| Agentenaufrufe | 29 von 50 | 20 von 40 (Spec 8, Plan 4, Umsetzung 8) |
| Ergebnis | 🟢, 0 Fix-Runden | 🟡 angenommen nach 1 Fix-Runde; 621/621, Akzeptanz 272/272 |

**Was die Regel getan hat:** Fassung 1 hatte 2 auslösende Punkte. Beide Familien fanden unabhängig denselben falschen
Byte-Erwartungswert in einem Test, dazu kamen 3 Minor. Deshalb wurden nur die Tests nachgebessert, nicht die Spec. Die
Nachprüfung kam mit 0 neuen Punkten zurück, und beide alten Punkte waren „gelöst“. Freigabe nach 2 Prüfungen. Damit
ist das Kriterium „höchstens 2 Spec-Fassungen“ erfüllt.

**Was die Messung nicht hergibt:** Die Herkunft-Labels wurden kaum geprüft. Die einzige Nachprüfung lieferte keine neuen
Punkte, also gab es auch keine Herkunft zu bewerten. Den Status der alten Punkte lieferten beide Prüfer vollständig.
Ein Lauf ist eine Stichprobe, keine Statistik.

**Wo das Muster aus A8 wieder auftauchte: in Plan und Fix-Schleife.** Nach der Korrektur des Plans meldete Codex
einen neuen, exotischen Fall (`nan != nan` im Datenvergleich). In der Umsetzung fand der Codex-Prüfer auf `xhigh` zwei
pathologische Fälle nacheinander: einen RecursionError bei Untertabellen mit 600 Ebenen (behoben) und eine
Kopfzeile ohne Werte, die stehen bleibt, ohne die Daten zu ändern. Beide Male galt: Die Antwort „lieber ablehnen“ und
die Bremse sprachen gegen eine weitere Sonderregel. Deshalb Freigabe mit Begründung bzw. „annehmen“. Die Plan-Runden
und die Fix-Schleife haben noch keine Konvergenzlogik. Das ist der nächste Kandidat, falls Dominic will.

**Ein eigener Fehler unterwegs:** Der erste Versuch brach nach den Rückfragen mit `grenzverletzung` ab. Claude hatte
während des Laufs eine Zeile ins Ledger von Lab 2 geschrieben. Die Nachkontrolle griff, wie sie soll. Im zweiten
Versuch stellte der Klärer keine Rückfragen mehr, und die Spec entschied beide Punkte selbst als Annahmen.

## Selbst prüfen

1. Warum zählt eine fehlende Bewertung eines alten Punkts als `offen` und nicht als `geloest`?
2. Warum bekommt der Spec-Schreiber die Punkte von der Liste nicht, die Prüfer der nächsten Runde den Codex-Major von
   der Liste aber schon?
3. Warum steht die Verlaufszeile in `spec_pruefung_sammeln` und nicht in `spec_freigabe`?

<details><summary>Antworten</summary>

1. Ein Prüfer, der einen Punkt auslässt, hat ihn nicht geprüft. Wer „nicht geprüft“ als „gelöst“ liest, lässt einen
   echten Major still durch. Im schlimmsten Fall kostet „offen“ eine Runde oder eine Begründung.
2. Der Schreiber soll nur ändern, was eine Runde rechtfertigt, sonst flickt er wieder lokal. Die Prüfer müssen den
   Codex-Major weiter sehen, damit die Sperre erst endet, wenn Codex ihn wirklich als gelöst meldet.
3. Ein Knoten mit `interrupt` läuft beim Fortsetzen erneut bis zum interrupt, nach einer ungültigen Antwort sogar
   ganz. Der Fan-in-Knoten läuft je Prüfung genau einmal.

</details>
