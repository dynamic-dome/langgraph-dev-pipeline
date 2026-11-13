# Lab 2 · Lernstufe 6b-1: Zweitmeinung aus der anderen Modellfamilie

**Ausprobieren:** im Leitstand an einem Haltepunkt „⚖️ Beide fragen“, oder
`.venv\Scripts\python.exe -m entwicklung rat --wer beide`. Ohne echte Agenten: `docs\lernpfad\leitstand_demo.py`
(dort widerspricht Astra Fable an der Spec, und der Fake-Codex meldet ein `major`).

## Die Idee in einem Satz

Spec, Tests und Plan schreibt die Claude-Familie; eine Gegenstimme aus der GPT-Familie darf deshalb nicht still
überstimmt werden, auch nicht von drei Claude-Urteilen (Lehre aus A6, siehe 06a).

## Zwei Sperren, zwei Stärken

| | Harte Sperre im Graphen | Sperre über die Räte |
|---|---|---|
| Auslöser | Codex-Prüfer meldet `major` an Spec- oder Plan-Freigabe | Fable und Astra uneinig, oder Astra rät nicht zum Durchlassen |
| Wo geprüft | im Knoten (`spec_freigabe`, `plan_freigabe`) | `steuerung.einwand_fehlt`, gleich für Leitstand und CLI |
| Braucht einen Klick | nein | ja, die Räte gibt es nur auf Klick |
| Umgehbar? | nein: Ohne `begruendung` hält der Knoten erneut an | nur am Server vorbei (direkt `Command(resume=…)`) |

Beide verlangen dasselbe: `freigeben` oder `annehmen` nur mit Begründung. Die Einwände rechnet der Server selbst aus
dem Haltepunkt und den abgelegten Rat-Dateien des aktuellen Stands; was ein Browser als Einwand mitschickt, zählt
nicht. Ein Rat zu einer früheren Spec-Fassung erzeugt keinen Einwand mehr (andere `checkpoint_id`).

Die harte Sperre hätte A6 allein abgefangen: Dort meldete Codex den Widerspruch als `major`.

## Warum Astra eingebettete Dateien braucht

Codex läuft hier in der Windows-Sandbox und darf keine Prozesse starten, also auch keine Datei selbst lesen. Der
Prompt bettet deshalb die Dateien laut Plan, an der Eskalation die geänderten, und die Module der Schnittstellen ein
(höchstens 60 000 Zeichen, nur Dateien im Worktree, kein `../`). An der Spec-Freigabe gibt es neue Module oft noch
nicht; das steht dann ausdrücklich im Prompt. Für große Codebases reicht das nicht. Dann wird „Astra liest selbst“
gebaut (z. B. unter Linux, wo die read-only-Sandbox lesen darf), und zwar nur an zwei Stellen:
`berater.quelldateien` und `Abhaengigkeiten.berater_astra`.

## Frühabbruch

Jede Fix-Runde merkt sich die Schlüssel ihrer auslösenden Prüfer-Befunde: `Prüfer|Pfad|Art`. Taucht ein Schlüssel
in zwei Runden nacheinander auf, fragt der Lauf sofort an der Eskalation („Derselbe Befund kam in zwei Runden
nacheinander“), statt eine weitere Runde zu vergeuden. Zeile und Wortlaut zählen bewusst nicht mit, sie ändern sich
nach jedem Fix. Der Preis: Ein anderer Befund derselben Art in derselben Datei kann zu früh fragen. Das kostet eine
Rückfrage, keinen Code. Rote Tests lösen den Frühabbruch nicht aus: Sie sind gemessen, und die Fix-Runde bekommt den
Testauszug.

## Abnahme an A7 (Lauf 20261020-213457, „portwart eintragen“)

Dominic hat an jedem Haltepunkt „Beide fragen“ geklickt.

| Haltepunkt | Fable | Astra | einig? | Dominic | Was geschah |
|---|---|---|---|---|---|
| Rückfragen | Antwort, hoch, 49 s | Antwort, mittel, 52 s | ja | Fables Text | Fable ergänzte Blockformat, Escaping und Doppel-Ports. Astra senkte die Sicherheit, weil ihr der Code fehlte (siehe unten). |
| Spec 1 | ändern, hoch, 75 s | ändern, hoch, 61 s | ja | ändern mit Astras Hinweis | Der Codex-Prüfer meldete ein `major`: `lade` akzeptiert `port = []`, daran kann kein `[[port]]` angehängt werden. Beide Berater nannten es `echt`. Fable schrieb: „Der Codex-Major ist echt“. |
| Spec 2 | freigeben, hoch, 126 s | freigeben, hoch, 54 s | ja | freigeben | nur noch `minor`, kein Einwand |
| Plan | freigeben, hoch, 37 s | freigeben, hoch, 30 s | ja | freigeben | Beide erkannten die zwei `major` der Code-Prüfung („portwart.liste kommt im Plan nicht vor“) unabhängig als falschen Alarm. |

Ergebnis: 🟢 in Runde 0 ohne Fix-Runde, 436/436 Tests, Akzeptanz 243/243 (A1–A7). Zum Vergleich A6: zwei vergeudete
Fix-Runden und eine Eskalation, weil ein Codex-`major` an der Spec herabgestuft wurde.

Was die Abnahme zeigt:
- **Die Lehre aus A6 kam an:** Diesmal hat niemand das Codex-`major` herabgestuft. Behoben wurde es vor der
  Umsetzung, und die Umsetzung lief durch.
- **Sperre und Frühabbruch haben nicht ausgelöst.** Das ist richtig so: Es gab keinen Durchlass trotz Einwand und
  keine Fix-Runde. Belegt sind sie bisher nur durch Tests und die Demo.
- **Astra sah an den Rückfragen keinen Code:** Schnittstellen gibt es dort noch nicht, also wurde nichts
  eingebettet. Astra hat das offen gesagt und die Sicherheit gesenkt, so wie vorgesehen. Für „Astra liest selbst“
  heißt das: Schon an den Rückfragen braucht Astra die bestehenden Module des Ziel-Repos.
- **Die vier Paare waren einig.** Bei einer einfachen Aufgabe ist das auch zu erwarten. Wie viel die Gegenstimme
  wert ist, zeigt sich erst bei Uneinigkeit, und die kam hier nicht vor.

## Selbst prüfen

1. Warum reicht es nicht, Fable und Astra abstimmen zu lassen und die Mehrheit zu nehmen?
2. Warum errechnet der Server die Einwände selbst, statt sie vom Browser zu übernehmen?
3. Warum zählen Zeilennummer und Wortlaut nicht zum Schlüssel des Frühabbruchs?

<details><summary>Antworten</summary>

1. Bei zwei Stimmen gibt es keine Mehrheit, und mit den Claude-Prüfern zusammen gewönne immer die Familie, die Spec
   und Tests geschrieben hat. Gemeinsame blinde Flecken heben sich nicht auf, sie addieren sich.
2. Sonst könnte ein veralteter Tab oder ein Skript eine leere Liste schicken und die Sperre aushebeln.
3. Nach einem Fix verschiebt sich der Code, und das Modell formuliert denselben Einwand anders. Mit Zeile und
   Wortlaut würde derselbe Befund nie als derselbe erkannt.
</details>
