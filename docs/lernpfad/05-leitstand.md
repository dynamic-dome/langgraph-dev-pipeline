# Lab 2 · Lernstufe 5: Leitstand (Checkpointer als Schnittstelle, Command aus einer Oberfläche)

**Ausprobieren:** `leitstand.cmd` (oder `.venv\Scripts\python.exe -m entwicklung leitstand`).
Ohne echte Agenten: `.venv\Scripts\python.exe docs\lernpfad\leitstand_demo.py` (rot gestreift: DEMO).

## Die Idee in einem Satz

Eine kleine Weboberfläche zeigt jeden Lauf als Ablaufdiagramm, nimmt an jedem Haltepunkt Dominics Antwort entgegen
und startet neue Läufe. Sie liest alles aus dem Checkpointer und schreibt nur über `Command(resume=…)`.

## Aufbau

```
Browser (app.js, SVG)  ──1×/s GET /api/laeufe, /api/laeufe/{id}──▶  FastAPI (server.py, 127.0.0.1:8790)
        │                                                                │  liest
        └──POST /api/laeufe/{id}/antwort {haltepunkt, checkpoint_id, …}─▶ │  SqliteSaver (data/checkpoints.db)
                                                                         │  ◀── schreibt auch die CLI (anderer Prozess)
                                                    Ausfuehrer (Thread je Lauf): graph.invoke(Command(resume=…))
```

### 1. Der Checkpointer ist die Schnittstelle zwischen Prozessen

Die CLI und der Leitstand teilen sich keinen Speicher, nur die Datei `data/checkpoints.db`. Was einer schreibt, liest
der andere (`test_lauf_aus_anderem_prozess`). Deshalb fragt die Oberfläche einmal je Sekunde nach (Polling) statt
Server-Sent Events: SSE sähe nur Läufe, die im Server selbst laufen. Eine Falle beim Mitlesen: SQLite im WAL-Modus
hat frische Daten in `checkpoints.db-wal`. Wer die Datenbank zum Ansehen kopiert, muss `-wal` und `-shm` mitkopieren.

### 2. Der Graph beschreibt sich selbst

`graph.get_graph().to_json()` liefert Knoten und Kanten. `daten.graph_daten` berechnet Ebenen (längster Weg ab
`__start__`, Rückkanten per Tiefensuche ausgenommen) und markiert Haltepunkte und Abbruchwege. Welche Kante ein
Lauf wirklich gegangen ist, steht nicht im Graphen, sondern im Verlauf: aufeinanderfolgende Einträge von
`get_state_history`. Die erste Fassung leitete „gegangen“ aus „beide Enden erledigt“ ab – dann leuchteten
Abbruchwege, die nie benutzt wurden.

### 3. `Command(resume)` aus einer Oberfläche

Die Antwort an einen Haltepunkt baut dieselbe Funktion wie in der CLI (`steuerung.antwort_fuer`). Neu ist die Zeit:
Zwischen Anzeigen und Klicken kann sich der Lauf geändert haben (zweiter Tab, zweiter Klick). Deshalb schickt der
Browser mit, **welchen** Haltepunkt und **welchen** Stand (`checkpoint_id`) er angezeigt hat. Passt das nicht mehr,
antwortet der Server 409 statt die Antwort an einen anderen Haltepunkt zu geben (Codex-Befund, `test_veraltete_antwort_409`).
Ein `Command` geht immer an den Haltepunkt, an dem der Lauf *jetzt* steht – also muss man prüfen, ob es der ist,
den der Mensch gesehen hat.

### 4. Ein Server auf 127.0.0.1 ist nicht privat

Jede Webseite im Browser kann Anfragen an `127.0.0.1` schicken. Deshalb: zufälliges Token je Start (Header für alle
`/api`-Aufrufe), Prüfung von `Host` (gegen DNS-Rebinding) und `Origin` (gegen fremde Seiten). Text von Agenten
(Spec, Tests, Plan) kommt nur per `textContent` ins DOM, nie als HTML.

## Was der echte Betrieb zeigte

- Mit Fakes im Browser geprüft (Playwright): alle vier Haltepunkt-Formulare, Start, Ablehnungen, F5. Dabei gefunden:
  `replaceChildren(null)` schreibt den Text „null“; F5 gab 403, weil das Token aus der Adresszeile entfernt war; die
  Meldung zur vorigen Antwort blieb am neuen Haltepunkt stehen.
- **Verwechslung:** Das Playwright-Testfenster war auf Dominics Bildschirm sichtbar. Er hielt den Demo-Leitstand für
  seinen Lauf und klickte „Freigeben“ an einem schon beendeten Server. Seitdem: Demo rot gestreift gekennzeichnet,
  Verbindungsverlust als deutlicher Hinweis mit gesperrten Knöpfen, Testfenster nach Prüfungen schließen.
- **Abnahme:** A5 komplett im Leitstand – Rückfragen beantwortet, Spec einmal geändert und dann freigegeben, Plan
  freigegeben, Umsetzung grün.

## Grenzen des Prototyps

- Setzen CLI und Leitstand **gleichzeitig** denselben Lauf fort, läuft er doppelt (keine Sperre über Prozessgrenzen).
  Gehört zu Stufe 6.
- Ein Lauf, der in einem anderen Prozess rechnet, lässt sich nicht abbrechen.
- Das Diagramm ist lang und schlicht (eine Spalte je Ebene).

## Selbst prüfen

1. Warum Polling und nicht SSE?
2. Was würde ohne `checkpoint_id` in der Antwort passieren, wenn zwei Tabs offen sind?
3. Warum reicht „nur 127.0.0.1“ als Schutz nicht?

<details><summary>Antworten</summary>

1. SSE liefert Ereignisse aus dem eigenen Prozess. Läufe der CLI schreiben nur in die Datenbank; die sieht man nur,
   wenn man nachfragt.
2. Tab A gibt die Spec frei, der Lauf steht an der Plan-Freigabe. Ein „Freigeben“ aus Tab B gäbe den Plan frei, den
   niemand gesehen hat.
3. Der Browser selbst ist auf 127.0.0.1 – und jede geöffnete Webseite kann ihn Anfragen schicken lassen.
</details>
