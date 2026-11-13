# HOW-TO-USE — langgraph-lab-2

## Leitstand (Browser)
Unter Windows `leitstand.cmd` doppelklicken, oder:
```
cd langgraph-dev-pipeline
.venv\Scripts\python.exe -m entwicklung leitstand
```
- Startet den Server auf `127.0.0.1:8790` (Port aus `portwart\ports.toml`, sonst 8790) und öffnet den Browser mit einem
  frischen Zugangsschlüssel. Das Fenster (minimiert) schließen beendet den Server.
- Links die Läufe (auch die über die Kommandozeile gestarteten), in der Mitte das Ablaufdiagramm des gewählten Laufs
  (gelaufene Knoten gefüllt, aktive pulsieren, ◆ Haltepunkte), rechts die Details.
- An jedem Haltepunkt das passende Formular: Rückfragen beantworten, Spec und Tests lesen und freigeben / ändern /
  Tests nachbessern, Plan freigeben / ändern, Eskalation weiter / annehmen / abbrechen. Gleiche Regeln wie
  `fortsetzen` auf der Kommandozeile.
- **„+ Neuer Lauf“** startet eine Aufgabe (Repo, Aufgabe, Stufe 3 oder 4, Modelle; kein Fable). Modelle stehen auf
  `auto` (Modell und Reasoning nach der Komplexität, siehe unten), daneben der **Rahmen** in Agentenaufrufen
  (Standard 40). Die Kopfzeile des Laufs zeigt „Aufrufe N/M“.
- **Plan-Freigabe:** Der Kasten „Modellstufe“ zeigt beide Schätzungen (Claude schreibt die Spec, Codex prüft sie; die
  höhere gilt, gelb umrandet, wenn sie uneinig sind) und die Auswahl einfach/mittel/schwer. Die Tabelle darunter
  zeigt sofort, welches Modell mit welchem Reasoning Implementierer und Prüfer dann bekommen.
- **Kostenrahmen:** Ist er erreicht, hält der Lauf vor Spec, Plan, Umsetzung oder Gesamtreview an: „Mehr erlauben
  (+20)“ oder „Abbrechen“. Geprüft wird nur an diesen vier Punkten, der Stand kann also über dem Rahmen liegen (z. B. 5/3).
- **Berater an jedem Haltepunkt (nur auf Klick):** „🧠 Fable fragen“ (Claude-Familie, liest das Repo selbst),
  „🛰️ Astra fragen“ (Codex, GPT-Familie, bekommt die Quelldateien eingebettet) oder „⚖️ Beide fragen“. Jeder Rat
  füllt das Formular vor; abgeschickt wird erst mit „Empfehlung übernehmen“. Bei „Beide“ zeigt eine Leiste
  einig/uneinig, und bei Uneinigkeit ist die vorsichtigere Empfehlung vorbelegt (erst nachbessern, dann verwerfen,
  dann durchlassen). Beide laufen mit Reasoning `high`; Astra bekommt den von git verfolgten Code des Repos mit
  (ohne die Akzeptanztests). Am Kostenrahmen gibt es keinen Rat: das entscheidest nur du.
- **Einwand-Kasten:** Meldet der Codex-Prüfer ein `major`, sind Fable und Astra uneinig oder rät Astra zum
  Nachbessern, geben „Freigeben“ und „Annehmen“ nur mit Begründung frei. Die Begründung steht im Bericht unter
  „Freigaben trotz Einwand“.
- **Demo ohne Abo:** `.venv\Scripts\python.exe -m entwicklung demo` baut im Temp-Ordner ein frisches Repo aus
  `examples\portwart` und startet den Leitstand mit Fake-Agenten; der Lauf D1 beginnt von selbst und geht bis zum
  Merge, wenn du an den Haltepunkten freigibst. `--durchlauf` macht dasselbe ohne Browser.
- Zum Ausprobieren der Lernstufen ohne echte Agenten: `.venv\Scripts\python.exe docs\lernpfad\leitstand_demo.py`
  (Fakes, alles in einem Temp-Ordner, `http://127.0.0.1:8795/?token=demo`).
- Sicherheit: nur 127.0.0.1, Host- und Herkunftsprüfung, alle Daten und Aktionen nur mit dem Schlüssel des Starts.
  Läuft der Leitstand schon, meldet ein zweiter Start „Port belegt“; dann das offene Browserfenster nehmen.

## Pipeline starten
```
cd langgraph-dev-pipeline
.venv\Scripts\python.exe -m entwicklung lauf --repo portwart --aufgabe A4 --live
```
- **Ab Stufe 4 (Standard)** ist die Aufgabendatei nur ein **Wunsch** (z. B. `aufgaben\portwart\A4.md`). Vor der
  Umsetzung stellt die Pipeline Rückfragen (hält an), schreibt eine Spec, lässt einen eigenen Agenten daraus
  Akzeptanztests schreiben, prüft sie (Imports nur aus der Spec, mindestens einer rot gegen `main`), lässt Codex und
  Claude Spec und Tests prüfen und hält zur **Freigabe** an. Spec und Tests liegen unter `berichte\<zeit>\`.
  Danach schreibt ein Agent einen **Plan** (`berichte\<zeit>\plan.md`), Code und Codex prüfen ihn gegen die Spec, und
  der Lauf hält zur **Plan-Freigabe** an. Erst danach beginnt die Umsetzung unten, mit Spec und Plan als Aufgabe.
- **A1 bis A3 sind fertige Verträge mit eigenen Akzeptanztests:** für sie `--stufe 3`.
- Legt einen Worktree `arbeit\portwart-<zeit>` auf Branch `lauf/<zeit>` an und lässt dort den Implementierer
  (`claude -p --restricted`, über das Abo) die Aufgabe `aufgaben\portwart\A1.md` umsetzen.
- Danach: Nachkontrolle (wurde portwart oder Lab 2 außerhalb des Worktrees verändert?), Sicherung des Ergebnisses
  als Commit auf dem Lauf-Branch, Tests inklusive der unabhängigen Akzeptanztests, Bericht.
- Ab Stufe 2 (Standard) prüfen danach vier Prüfer gleichzeitig: Funktion (gezählte Tests), Security und Clean Code
  (`claude -p`, nur lesend), Codex (`codex exec -s read-only`). Ihre Befunde laufen durch den Befund-Filter
  (fusion-harness, wenn in `lokal.toml` eingetragen, sonst der eingebaute; der Bericht nennt, welcher lief);
  der Bericht sagt, ob eine Fix-Runde nötig wäre. Die Akzeptanztests aller früheren Aufgaben laufen mit (Regression).
- Ab Stufe 3 (Standard) geht der Lauf bei nötiger Fix-Runde mit den auslösenden Befunden zurück an den
  Implementierer, höchstens `--max-runden` Mal (Standard 2, erlaubt 0 bis 5). Sind danach noch Befunde offen, hält
  der Lauf an und wartet auf deine Entscheidung (siehe unten).
- Dauer: 1 bis 4 Minuten je Runde. `--live` zeigt jeden fertigen Schritt sofort. `--stufe 1` = ohne Prüfer,
  `--stufe 2` = mit Prüfern, aber ohne Fix-Runden.
- **Modellstufen (Standard `auto`):** Claude (Spec) und Codex (Spec-Prüfung) schätzen die Komplexität, die höhere
  gilt, und du bestätigst oder änderst sie an der Plan-Freigabe. Daraus folgen Modell und Reasoning:

  | Komplexität | Implementierer | Prüfer der Umsetzung |
  |---|---|---|
  | einfach | sonnet · medium | opus · high |
  | mittel (ohne Schätzung) | sonnet · high | opus · high |
  | schwer | opus · high | opus · xhigh |

  Die Planung läuft fest (Planer sonnet · high, Spec-Prüfer opus · high), Codex immer auf `high`.
  `--modell` und `--pruefer-modell` mit `haiku|sonnet|opus` überschreiben nur das Modell, das Reasoning bleibt aus
  der Tabelle (kein Fable).
- **Kostenrahmen:** `--budget N` (Standard 40 Agentenaufrufe; Berater zählen nicht). Ist er erreicht, hält der Lauf
  vor Spec, Plan, Umsetzung (auch vor jeder Fix-Runde) oder Gesamtreview an.
- Exit-Code 0 nur bei Status `gruen` und ohne nötige Fix-Runde; 3 = der Lauf wartet auf dich (ab Stufe 7 auch an
  der Abschluss-Freigabe); sonst 1 (auch bei `angenommen`, `abgebrochen`, `merge_abgelehnt` und `akzeptanz_fehler` ⚠).

## Angehaltenen Lauf fortsetzen (ab Stufe 3)
Endet ein Lauf mit `⏸ Lauf lauf-<zeit> …`, liegt sein Stand in `data\checkpoints.db`. Das Fenster darf
zu sein; weiter geht es jederzeit. Was erlaubt ist, hängt vom Haltepunkt ab; die Ausgabe nennt den passenden
Befehl, und eine unpassende Angabe wird abgelehnt, ohne etwas zu entscheiden.

**Rückfragen (ab Stufe 4):** alle Antworten in einem Text.
```
.venv\Scripts\python.exe -m entwicklung fortsetzen --antwort "1. nur .py und .toml  2. Kommentare ignorieren" --live
.venv\Scripts\python.exe -m entwicklung fortsetzen --entscheidung abbrechen
```
**Spec-Freigabe (ab Stufe 4):** vorher `berichte\<zeit>\spec.md` und die Tests in `berichte\<zeit>\akzeptanz\` lesen.
```
.venv\Scripts\python.exe -m entwicklung fortsetzen --entscheidung freigeben --live
.venv\Scripts\python.exe -m entwicklung fortsetzen --entscheidung aendern --hinweis "Exit-Code 1 bei Drift" --live
.venv\Scripts\python.exe -m entwicklung fortsetzen --entscheidung tests_nachbessern --hinweis "Datei ohne Endung testen" --live
.venv\Scripts\python.exe -m entwicklung fortsetzen --entscheidung abbrechen
```
`aendern` schreibt Spec und Tests neu, `tests_nachbessern` nur die Tests (die Spec bleibt).

**Plan-Freigabe (ab Stufe 4):** vorher `berichte\<zeit>\plan.md` lesen.
```
.venv\Scripts\python.exe -m entwicklung fortsetzen --entscheidung freigeben --live
.venv\Scripts\python.exe -m entwicklung fortsetzen --entscheidung aendern --hinweis "erst die CLI, dann das Modul" --live
.venv\Scripts\python.exe -m entwicklung fortsetzen --entscheidung abbrechen
.venv\Scripts\python.exe -m entwicklung fortsetzen --entscheidung freigeben --komplexitaet schwer --live
```
Ohne `--komplexitaet` gilt die angezeigte Schätzung.

**Kostenrahmen:**
```
.venv\Scripts\python.exe -m entwicklung fortsetzen --entscheidung mehr --live        Rahmen +20, weiter
.venv\Scripts\python.exe -m entwicklung fortsetzen --entscheidung abbrechen          beenden (⏹)
```
**Abschluss (ab Stufe 7):** Ein grüner oder an der Eskalation angenommener Lauf geht über ein Gesamtreview durch
Codex zur Abschluss-Freigabe. Die Ausgabe zeigt die Tür (`zweiseitig` oder `einseitig` mit Fällen, das strengere Urteil
aus Selbstbewertung und Codex gilt), die Tests (bestanden · übersprungen), das Gesamtreview, Branch und Diffstat.
```
.venv\Scripts\python.exe -m entwicklung fortsetzen --entscheidung mergen         lokaler Fast-Forward, Tests nach aufgaben\, aufräumen
.venv\Scripts\python.exe -m entwicklung fortsetzen --entscheidung nicht_mergen   Branch und Worktree bleiben stehen
```
Einwände (major im Gesamtreview, Gesamtreview fehlt, Tür einseitig, Tests ohne Grund `plattform:` übersprungen)
verlangen `--begruendung`. Gemergt wird nur der geprüfte Commit und nur, wenn das Ziel-Repo noch wie beim Start dasteht
(gleicher Zweig, sauber, Hauptzweig nicht weitergelaufen); sonst Status `merge_abgelehnt` mit Grund. Die übernommenen
Akzeptanztests sind nicht committet. Am Abschluss gibt es keinen Rat. Kein Push.

**Eskalation (ab Stufe 3):**
```
.venv\Scripts\python.exe -m entwicklung fortsetzen --entscheidung weiter --live      eine Fix-Runde mehr
.venv\Scripts\python.exe -m entwicklung fortsetzen --entscheidung annehmen --live    Stand so lassen (🟡)
.venv\Scripts\python.exe -m entwicklung fortsetzen --entscheidung abbrechen --live   beenden (⏹)
```
**Berater und Einwände (ab Stufe 6):**
```
.venv\Scripts\python.exe -m entwicklung rat --wer beide          Fable und Astra parallel (1–5 min), mit Vergleich
.venv\Scripts\python.exe -m entwicklung fortsetzen --entscheidung freigeben --begruendung "Widerspruch geprüft: …"
```
`rat` gibt den Befehl zum Übernehmen aus (gebunden an Haltepunkt und Stand). Liegt ein Einwand vor, lehnt
`fortsetzen` freigeben/annehmen ohne `--begruendung` ab und nennt die Einwände.

Ohne `--thread` nimmt `fortsetzen` den jüngsten wartenden Lauf; `--thread lauf-<zeit>` wählt einen bestimmten.
`weiter` kann wieder an der Eskalation enden, `aendern` führt zu einer neuen Freigabe. In Git Bash (`!` in Claude Code) Pfade mit `/` schreiben:
`cd langgraph-dev-pipeline && .venv/Scripts/python.exe -m entwicklung fortsetzen --entscheidung annehmen --live`.

Ergebnis ansehen:
```
type berichte\<zeit>.md                                    Bericht (daneben .json)
cd arbeit\portwart-<zeit>
..\..\.venv\Scripts\python.exe -m pytest -q                Tests von Hand
..\..\.venv\Scripts\python.exe -m portwart pruefen         doppelte Ports in der echten ports.toml
..\..\.venv\Scripts\python.exe -m portwart abgleich        lauschende Ports gegen die Liste (A2)
```
Bis zur Abschluss-Freigabe bleibt der Hauptzweig von portwart unberührt; das Ergebnis liegt nur auf `lauf/<zeit>`.

## Aufräumen
```
.venv\Scripts\python.exe -m entwicklung aufraeumen          alle Worktrees bis auf den jüngsten je Repo
.venv\Scripts\python.exe -m entwicklung aufraeumen --alle   alle
```
Entfernt nur Worktrees ohne ungesicherte Arbeit (kein `--force`). Die Branches `lauf/<zeit>` bleiben.

## Maschinenspezifisches (`lokal.toml`)
Optional, git-ignoriert, im Projektordner (Umgebungsvariablen haben Vorrang):
```
fusion_harness = "C:/Werkzeuge/fusion-harness/fusion_harness.py"   # oder ENTWICKLUNG_FUSION_HARNESS (leer = aus)
verbotene_wurzeln = ["C:/Daten/anderes-projekt"]                    # oder ENTWICKLUNG_VERBOTENE_WURZELN
```
Ohne Datei läuft der eingebaute Befund-Filter, und es gibt keine zusätzlich verbotenen Ordner.

## Tests
```
.venv\Scripts\python.exe -m pytest -q
```
Laufen isoliert in Temp-Ordnern und starten nie einen echten Agenten.
Lernnotizen: `docs\lernpfad\`. Spike zu den Rechten des Implementierers: `docs\spike-2026-10-19-restricted.md`.
