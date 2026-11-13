# Spike 19.10.: Prüfer-Aufrufe (claude -p mit Schema, codex exec)

Ziel: Vor dem Bau der Prüfer-Adapter gegen die echten Programme klären, wo das strukturierte Ergebnis steht, ob es
dem Review-Schema genügt und ob die Prüfer wirklich nur lesen. Aufbau: Temp-Repo mit `rechner.py`, darin ein
absichtlicher Path-Traversal (`open("/daten/" + name)`) und eine Division ohne Prüfung. Der Prompt verlangt
zusätzlich einen Schreibversuch (`notiz.txt`) als Rechtetest. Skript (Wegwerf): `%TEMP%\lab2_spike_pruefer.py`.

## claude -p als Prüfer (10,7 s, rc 0)
```
claude -p --model sonnet --restricted --strict-mcp-config --permission-prompts none
       --settings '{"disableAllHooks": true}' --tools Read,Glob,Grep
       --json-schema "<Inhalt von REVIEW_SCHEMA.json>" --output-format json --max-turns 20
```
- Das Ergebnis steht im Feld **`structured_output`** als fertiges Objekt; `result` enthält dasselbe als Text.
- Schema-gültig: 4 Befunde, darunter Path-Traversal als `major/security` mit wörtlichem Zitat.
- Rechtetest: Der Agent hatte kein Schreibwerkzeug, hat es gemeldet (`not_checkable`) und nichts versucht.
  `notiz.txt` fehlt, `git status` ist leer.

## codex exec als Prüfer (49,3 s, rc 0)
```
codex exec -s read-only -c approval_policy=never -c model_reasoning_effort="high"
           --skip-git-repo-check --output-schema <REVIEW_SCHEMA.json> -o <datei> -
```
per Python-`subprocess`, Prompt per stdin, `shutil.which("codex")` → `...\npm\codex.CMD`.
- Das Ergebnis steht in der `-o`-Datei als Schema-JSON; dasselbe steht am Ende von stdout und stderr.
- Schema-gültig: 3 Befunde, Path-Traversal ebenfalls als `major/security`.
- Codex kann hier **keine Prozesse starten** (`CreateProcessAsUserW failed: 5`), weder zum Lesen noch zum
  Schreiben. Er arbeitet nur mit dem, was im Prompt steht. Deshalb gehören Diff **und** volle geänderte Dateien in
  den Prompt. Das deckt sich mit früheren Erfahrungen.
- Zitate übernimmt Codex mit führenden Leerzeichen (`"    return a / b"`); der Filter muss das vertragen
  (prüfen in Task 5).
- In stderr stehen Zeilen `hook: Stop`: Codex' eigene Hooks laufen mit. Das ist harmlos, im Bericht aber nicht
  verwerten.

## Folgerungen
1. Prüfer-Adapter lesen bei claude `structured_output`, bei Codex die `-o`-Datei. Fehlen sie oder verletzen sie
   das Schema: „nicht verwertbar“.
2. Prompt für alle Prüfer: Aufgabe, Diff, volle geänderte Dateien (gedeckelt), Schema-Regeln.
3. Laufzeit: Codex braucht ein Mehrfaches von claude. Weil die Prüfer parallel laufen, bestimmt Codex die Wartezeit.
