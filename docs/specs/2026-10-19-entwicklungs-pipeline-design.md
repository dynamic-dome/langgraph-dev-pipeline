# LangGraph-Lab 2: Entwicklungs-Pipeline — Entwurf (Stand 2026-10-19, Builder-Check eingearbeitet, wartet auf Freigabe)

## Absicht und Warum

Dominic kennt den Entwicklungsablauf aus Superpowers und dem eigenen Skill `gzif-pipeline`:
klären → Spec → Plan → implementieren → prüfen → Fix-Schleife → Abschluss. Dort ist der Ablauf **Text**, an den sich
das Modell meistens hält. Er möchte denselben Ablauf **einmal als LangGraph-Graphen** bauen, um zu verstehen, wie
Phasen, Freigaben, parallele Prüfungen und Rücksprünge als Knoten und Kanten aussehen. Es gab dafür keinen
Problemanlass; es geht um Verständnis.

Trotzdem ist das Ziel **keine Attrappe**. Ab der ersten Stufe ist es eine **funktionierende Pipeline**, die mit echten
Agenten echten Code schreibt und echt prüft, in Stufen erweitert. Vorhandene Bausteine des Ökosystems werden
wiederverwendet, nicht nachgebaut.

Vorbild für Form und Arbeitsweise ist `AI/langgraph-lab` (Ökosystem-Puls): Lernstufen mit Lernnotiz, Halt nach
jeder Stufe, Tests mit Isolation, Codex-Review je Stufe.

## Das Übungsprojekt: portwart

Die Pipeline arbeitet an einem eigenen kleinen Repo **portwart**: eine zentrale Portliste mit Prüfer. Es gibt dafür
einen echten Anlass: zwei offene Punkte aus meiner Aufgabenliste (Ports zentral registrieren nach einer Kollision
am 16.10. auf 8766; 8770 doppelt vergeben). portwart liest nur und ändert nirgends Ports.

Die Aufgaben, die die Pipeline nacheinander bekommt:

| Aufgabe | Ergebnis |
|---|---|
| A1 | `ports.toml` lesen (Projekt → Port → Zweck) und doppelte Ports melden |
| A2 | Lauschende Ports gegen die Liste halten: belegt, frei, unbekannt |
| A3 | `portwart frei 8700-8799`: nächsten freien Port vorschlagen (weder belegt noch eingetragen) |
| A4 | Projekte nur lesend nach Port-Angaben durchsuchen und mit der Liste vergleichen (Drift) |

portwart ist ein **eigenes git-Repo** (`AI/langgraph-lab-2/portwart`), Python 3.12, pytest. Die Pipeline arbeitet je
Lauf in einem **eigenen git-Worktree**. Ins Hauptrepo kommt nur, was Dominic beim Abschluss freigibt, und zwar lokal.
Es gibt nie einen Push.

## Ziel-Ablauf (nach der letzten Stufe)

```
Aufgabe → klären ⇄ (Fragen an Dominic) → spec_schreiben → spec_review ⇉ (parallel) → spec_freigabe ⏸
→ plan_schreiben → plan_pruefen (gegen Spec und Anforderungen) → plan_freigabe ⏸
→ modellstufe_waehlen → implementieren → tests_ausfuehren
→ ⇉ pruefen_security | pruefen_clean_code | pruefen_funktion | pruefen_codex   (parallel, Send)
→ befunde_sammeln (dedupliziert, gefiltert)
→ [Befunde offen und Runde < N] → implementieren (Fix-Runde)  ↺
→ [Runde = N] → eskalation ⏸ (Dominic entscheidet)
→ gesamtreview → abschluss_freigabe ⏸ → lokal mergen + Bericht
```

## Lernstufen (jede Stufe ist eine lauffähige Pipeline)

| Stufe | Pipeline danach | LangGraph-Lernstoff | portwart |
|---|---|---|---|
| 1 | Aufgabe → implementieren (echtes `claude -p` im Worktree) → tests_ausfuehren → Bericht | Agent als Knoten mit Schreibrechten, Worktree, deterministischer Prüfknoten | A1 |
| 2 | + parallele Prüfungen Security, Clean Code, Funktion, Codex + befunde_sammeln | Send mit verschiedenen Zielen, Reducer, strukturierte Befunde | A2 |
| 3 | + Fix-Schleife (höchstens N Runden) + Eskalation an Dominic | Zyklus, Abbruchbedingung, interrupt als Notausgang | A3 |
| 4 | + klären, Spec, Spec-Review, Plan, Plan-Prüfung mit Freigaben | mehrere interrupts, Fragen-Schleife mit Mensch, Phasen | A4 |
| 5 | + **Leitstand**: lokale Weboberfläche mit Live-Ablaufdiagramm und Freigaben im Browser | stream, Graph als Daten, Command(resume) aus einer UI | — |
| 6 | + Modellstufen je Komplexität, Kostenrahmen, Wiederaufnahme nach Abbruch | Router-Knoten, Checkpointer-Resume, Budget im State | — |
| 7 | + Gesamtreview, Abschluss-Freigabe, lokaler Merge | Abschluss-Gate, Bericht | — |
| Gesellenstück | Die Pipeline erweitert den Leitstand selbst, Dominic gibt im Leitstand frei | alles zusammen | — |

## Ziele

- Eine echte, wiederverwendbare Entwicklungs-Pipeline als LangGraph-Graph, Aufruf
  `python -m entwicklung lauf --repo <pfad> --aufgabe "<text>"` (Name des Pakets ist Sache des Bauenden).
- Je Stufe eine Lernnotiz am echten Code (wie im Puls).
- portwart A1–A4 werden **durch die Pipeline** gebaut, nicht von Hand. Danach ist die zentrale Portliste nutzbar und die bekannte Kollision sichtbar.
- Ein Leitstand im Browser (127.0.0.1), der zeigt, was wo passiert, und an der Halt-Stelle die Freigabe annimmt.

## Nicht-Ziele

- Superpowers, `gzif-pipeline` oder fusion-harness ersetzen. Bausteine daraus werden benutzt.
- Arbeit an echten Projekten vor dem Gesellenstück.
- Push, Deploy, Veröffentlichen. Die Pipeline merged höchstens lokal und nur nach Freigabe.
- Mehrere Repos gleichzeitig, mehrere Aufgaben gleichzeitig.

## Anti-Ziele (Fehlschlag, selbst wenn es technisch läuft)

- Ein Agent schreibt außerhalb seines Worktrees oder führt etwas anderes aus als Tests und Lesebefehle.
- „Funktioniert“ wird behauptet, ohne dass die Tests wirklich gelaufen sind.
- Endlose Fix-Runden oder unkontrollierte Kosten.
- Eine Freigabe wird umgangen, oder das Modell gibt sich selbst frei.
- Tests der Pipeline rufen echte Agenten auf.

## Randbedingungen

- **Agenten nur als Subprozesse über das Abo:** `claude -p` (Härtungen für Subprozesse unter Windows, wie im Vorgänger-Lab)
  und `codex exec` (`-s read-only` für Prüfer,
  `model_reasoning_effort="high"`). Keine API-Keys.
- **Implementierer:** `claude -p` mit `cwd` = Worktree und genau den Werkzeugen, die er braucht (lesen, editieren,
  schreiben, `pytest` ausführen). Alles darüber hinaus wird verweigert. Timeout je Aufruf.
- **Prüfer** lesen nur. Security und Clean Code laufen als `claude -p` mit Lesewerkzeugen, Codex mit `-s read-only`.
  Alle liefern Befunde im Schema `REVIEW_SCHEMA.json` von fusion-harness (seit der öffentlichen Fassung als Kopie
  `entwicklung/review_schema.json`). Gefiltert wird mit
  `fusion_harness.py befunde`, also mit Quellenprüfung statt Blindübernahme.
- **Funktion** prüft kein LLM: Der Knoten `tests_ausfuehren` lässt pytest im Worktree laufen und wertet das Ergebnis
  aus. Exit-Code und Zählung werden gelesen; „Exit 0“ allein reicht nicht.
- **Modelle:** kein Fable. Standard: Implementierer `sonnet` (einfache Aufgaben `haiku`, schwere `opus` ab Stufe 6),
  Prüfer `sonnet`, Codex wie konfiguriert mit `high`. Modell je Rolle per Konfiguration überschreibbar.
- **Freigaben** immer per `interrupt` an Dominic: Klärungsfragen, Spec, Plan, Eskalation, Abschluss.
- **Speicher:** SqliteSaver unter `langgraph-lab-2/data/` mit lazy Pfad, Hard-Guards und Test-Isolation wie im
  Puls. In Tests sind alle Agenten Fakes, und eine `BaseException`-Sperre verhindert echte Aufrufe.
- **Fremdes Material** nur nach `privat/` (git-ignoriert), wie in Lab 1.
- **Windows:** Worktrees per `git worktree add`; Aufräumen ohne `rm -rf` (Hook), über `git worktree remove`.

## Was Dominic entschieden hat (19.10.)

- Lernprojekt in **neuem Ordner** `AI/langgraph-lab-2`, stufenweise, aber jede Stufe eine **echte, funktionierende
  Pipeline**.
- Vorhandene Bausteine nutzen statt nachbauen.
- Übungs-Repo: **portwart** (Portliste). Ein Skelett-Prüfer ist für später vorgemerkt.
- Ein **Leitstand** (Ablaufdiagramm live, Freigabe-Popups) gehört dazu, als eigene Stufe, sobald es Freigaben gibt.
  Später erweitert die Pipeline ihn selbst (Gesellenstück).

- **Absicherung des Implementierers (19.10.):** Allowlist und Nachkontrolle.
  - Er darf nur lesen, editieren, schreiben und pytest ausführen.
  - Deny-Regeln gelten für git, Löschen und Netz.
  - Nach **jedem** Agentenaufruf prüft Code, ob sich außerhalb des Worktrees etwas geändert hat (`git status` im
    Hauptrepo von portwart und in Lab 2, geänderte Pfade gegen den Worktree). Bei einem Verstoß bricht der Lauf ab und
    meldet es.
  - Hooks bleiben im Subprozess aus, wie im Puls: schnell und ohne Kapern.
  - Bewusst in Kauf genommen: Die Nachkontrolle erkennt Verstöße erst **nach** dem Aufruf, nicht vorher. Die
    Allowlist ist die erste Sperre, die Nachkontrolle die zweite.
- **Nachtrag nach der Freigabe (19.10.): `claude --restricted`.** Das installierte Claude Code (2.1.303) kennt diesen
  Modus. Laut `--help`:
  - Er entfernt Befehle ausführende Werkzeuge, solange `--tools` sie nicht nennt.
  - Er ignoriert Nutzer- und Projekteinstellungen, also auch die Hooks.
  - Er beschränkt Datei-Werkzeuge auf die Arbeitsverzeichnisse.
  - Er verweigert `bypassPermissions`.
  - Schreibzugriffe auf git- und Einstellungsdateien lässt er nur nach Zustimmung zu.

  Zusammen mit `--permission-prompts none` wird alles, was nachfragen würde, abgelehnt. Der Implementierer läuft
  deshalb mit `--restricted`, `--tools` (Lesen, Editieren, Schreiben, Suchen, Bash) und
  `--allowedTools "Bash(<testbefehl>:*)"` im Worktree als Arbeitsverzeichnis. **Stufe 1 prüft dieses Verhalten zuerst
  gegen das echte Programm** (Schreiben außerhalb, Befehl außerhalb der Allowlist, git-Commit), bevor darauf gebaut
  wird. Die Nachkontrolle bleibt als zweite Sperre.

## Perspektive: echte Sandbox (später, nicht in diesem Lab)

Wenn die Absicherung im Verlauf nicht reicht, kommen in Frage:

- eine WSL-Distribution als Sandbox auf diesem Rechner
- Docker
- ein zweiter Rechner mit Linux (dort sind Sandboxen einfacher)

Von Dominic am 19.10. angeregt. Wird erst gebaut, wenn ein konkretes Problem es nötig macht.

## Meine Entscheidungen (bitte prüfen)

- **Reihenfolge der Stufen** wie in der Tabelle: das Risiko (schreibende Agenten) zuerst, Klären/Spec/Plan erst in
  Stufe 4. Begründung: Der Durchstich muss stabil sein, bevor davor noch Phasen hängen.
- **Leitstand-Technik:** FastAPI + uvicorn (in anderen eigenen Projekten schon im Einsatz) mit Server-Sent
  Events für Live-Ereignisse. Neue Abhängigkeiten nur im venv von Lab 2. Port wird in portwarts `ports.toml`
  eingetragen.
- **Rundenlimit N = 2** für die Fix-Schleife (wie der Evaluator im Puls). Danach Eskalation.
- **Kostenrahmen ab Stufe 6:** höchstens eine feste Zahl von Agentenaufrufen je Lauf. Danach hält der Lauf an und
  fragt nach.
- **Paketname** der Pipeline: `entwicklung` (Arbeitstitel).
- **Was „richtig“ heißt (Stufen 1–3):** Zu jeder portwart-Aufgabe gibt es vorab eine Aufgabendatei
  (`aufgaben/A1.md` …) mit Akzeptanzkriterien (u. a. Format von `ports.toml`, CLI-Namen) und **unabhängige
  Akzeptanztests**, die der Implementierer weder sieht noch ändern kann. Sie werden erst zum Testen in den Worktree
  kopiert. Seine eigenen Tests laufen zusätzlich. Ab Stufe 4 entstehen Kriterien und Akzeptanztests aus der Spec, und
  zwar durch einen eigenen Agenten, nicht durch den Implementierer.
- **`pruefen_funktion`** ist ein deterministischer Knoten. Er macht aus dem Ergebnis von `tests_ausfuehren`
  (Akzeptanz- und eigene Tests, Zahl gesammelter Tests > 0) Befunde. Er nutzt kein LLM.
- **Was eine Fix-Runde auslöst:** rote Akzeptanztests immer. Prüfer-Befunde nur, wenn sie den Befund-Filter
  (`fusion_harness.py befunde`) im Topf „an der Quelle prüfen“ passieren, also mit gefundenem Zitat, und mindestens
  `major` sind. Kleineres steht nur im Bericht. In Stufen 1–2 gibt es noch keine Schleife; dort wird nur berichtet.
  fusion-harness wird per absolutem Pfad als Subprozess aufgerufen und nie verändert.
- **Planungsumfang:** Der Plan beschreibt Stufe 1 im Detail; jede weitere Stufe bekommt ihren eigenen Plan nach dem
  Stufen-Gate (wie in Lab 1). Je Stufe gehört ein echter Pipeline-Lauf an portwart zur Abnahme. Ich führe ihn aus,
  Dominic wiederholt ihn.
- **Repos und Ordner:** `langgraph-lab-2` ist ein eigenes git-Repo. `portwart/` ist ein eigenes git-Repo darin und
  steht in der `.gitignore` von Lab 2. Worktrees liegen unter `langgraph-lab-2/arbeit/` (git-ignoriert). Das
  portwart-Grundgerüst (pyproject, leeres Paket, Test-Skelett, Beispiel-`ports.toml`) lege ich vor Stufe 1 von Hand an.
  Je Zielrepo steht in `entwicklung.toml` der Testbefehl und der Python-Pfad. So ist `--repo` wiederverwendbar, auch
  für das Gesellenstück.
- **Prüfer-Eingabe:** Codex bekommt den Diff eingebettet (`codex exec -s read-only`), statt selbst Befehle
  auszuführen. Das entspricht der Erfahrung auf diesem Rechner.
