# Lab 2 · Lernstufe 7: Gesamtreview, Abschluss-Freigabe, lokaler Merge

**Ausprobieren:** `.venv\Scripts\python.exe docs\lernpfad\leitstand_demo.py --port <frei>` → „+ Neuer Lauf“ → Rückfrage
beantworten → Spec freigeben (mit Begründung, die Demo hat einen Codex-Einwand) → Plan freigeben. Der Lauf hält an
der Abschluss-Freigabe. Die Karte zeigt „Tür: einseitig“, weil das erste Gesamtreview der Demo der Selbstbewertung
widerspricht. „Mergen“ geht nur mit Begründung. Echt: ein Lauf mit Stufe 4 endet jetzt nicht mehr im Bericht, sondern
an `abschluss_freigabe`; danach `fortsetzen --entscheidung mergen` oder `nicht_mergen`.

## Die Idee in einem Satz

Ein grüner Lauf endet nicht mehr im Bericht: Codex urteilt über das Ganze, der Mensch entscheidet, und erst danach
führt die Pipeline den einzigen Schritt aus, der außerhalb des Worktrees wirkt, einen lokalen Fast-Forward.

## Der Ablauf

```
befunde_sammeln (grün, keine Fix-Runde) ─┐
eskalation (annehmen) ───────────────────┴→ budget_abschluss ⏸ → gesamtreview (Codex) → abschluss_freigabe ⏸
      → abschluss (mergen: Fast-Forward, Tests übernehmen, aufräumen | nicht_mergen: alles bleibt) → bericht
```

Rot, Grenzverletzung, Agentenfehler und Abbruch gehen wie bisher direkt zum Bericht. Stufe 3 bleibt unverändert;
`umsetzung_s3` bekommt dafür nur einen Parameter `ziel_gruen`, der in Stufe 3 weiter `bericht` ist.

## Lernstoff 1: Ein Haltepunkt, nach dem etwas passiert, das man nicht zurückspulen kann

Bisher stand hinter jedem Haltepunkt nur Arbeit im Worktree oder ein neuer Agentenaufruf. Hinter
`abschluss_freigabe` steht ein Seiteneffekt im Ziel-Repo. Daraus folgen drei Regeln im Code:

- **Freigabe und Seiteneffekt sind zwei Knoten.** `abschluss_freigabe` stellt nur die Frage (genau ein `interrupt`,
  ungültige Antworten laufen über die Kante zurück in denselben Knoten). Erst `abschluss` merged. Ein Knoten mit
  `interrupt` läuft beim Fortsetzen von vorn bis zum `interrupt`. Stünde der Merge im selben Knoten, liefe er vor
  oder nach jeder Wiederholung mit.
- **Vor dem Merge noch einmal nachsehen.** Zwischen Frage und Antwort können Stunden liegen. `merge_ff` prüft deshalb
  erst im Moment des Merges: derselbe Zweig wie beim Start, sauberer Stand, `HEAD` gleich der Basis des Laufs. Sonst
  `merge_abgelehnt` mit Grund, und Branch und Worktree bleiben stehen.
- **Was scheitert, bleibt stehen.** Existiert `aufgaben/<repo>/<id>/` schon, wird nichts überschrieben. Lässt sich der
  Worktree nicht ohne `--force` entfernen oder der Branch nicht mit `-d` löschen, steht der Grund im Bericht.

Bekannte Grenze: Stürzt der Prozess zwischen Merge und Aufräumen ab, wiederholt LangGraph den Knoten `abschluss`, und
`merge_ff` meldet dann „Hauptzweig ist weitergelaufen“. Das Repo ist korrekt gemergt, nur der Bericht ist irreführend.

## Lernstoff 2: Warum Fast-Forward die zweite Testrunde erspart

Ein Fast-Forward schiebt `main` auf genau den Commit, den `tests_ausfuehren` geprüft hat. Es entsteht kein neuer
Stand, also gibt es nichts neu zu testen. Ein Merge-Commit oder Rebase würde einen Stand erzeugen, den niemand
getestet hat. Deshalb lehnt die Pipeline ab, sobald `main` weitergelaufen ist, statt zu mergen.

## Lernstoff 3: Warum die andere Familie das letzte Wort hat

Spec, Plan und Code schreibt die Claude-Familie. Das Gesamtreview macht Codex (GPT), wie die Sperre aus 6b-1: Kein
Modell gibt sich selbst frei. Codex liest unter Windows keine Dateien, deshalb steht alles im Prompt (Spec, Plan, Diff,
Befunde der letzten Runde, Testergebnis, Selbstbewertung der Tür), gekürzt auf 200 000 Zeichen.

Einwände an der Abschluss-Freigabe, bei denen `mergen` eine Begründung braucht:

- ein `major` im Gesamtreview,
- ein Gesamtreview, das fehlt oder nicht verwertbar ist („weiß ich nicht“ zählt wie „nein“, Lehre aus 6c),
- eine einseitige Tür (siehe unten),
- übersprungene Tests ohne Plattform-Begründung.

Am Abschluss gibt es keinen Rat von Fable oder Astra: Das Gesamtreview ist schon die Zweitmeinung.

## Warum der Autor seine eigene Tür nicht allein bewertet

Die Tür-Zeile sagt, ob sich ein Merge zurückholen lässt: `zweiseitig` (Code, lokal per `git reset` umkehrbar) oder
`einseitig` (Schema-Migration, Löschen von Daten oder Dateien, Veröffentlichen, Schreiben in eine Produktions-DB,
Rechte und Secrets). Dazu kommt der Radius: Datei, Modul, Repo oder System.

- **Selbstbewertung ohne Modell:** `abschluss.tuer_selbst` sucht mit groben Mustern in den hinzugefügten Zeilen und in
  `git diff --name-status`. Das ist absichtlich grob. Ein Fehlalarm kostet eine Begründung, ein übersehener Fall
  kostet mehr. Der Implementierer bewertet nichts selbst, sein Prompt bleibt unverändert.
- **Gegenprüfung in derselben Anfrage:** Codex bekommt die Selbstbewertung und urteilt unabhängig. Lautet sie
  „zweiseitig“, steht im Prompt ausdrücklich, dass Codex versuchen soll, sie zu widerlegen.
- **Das strengere Urteil gilt** (`tuer_endgueltig`). Sind sich beide uneinig, zeigen Karte und Bericht beide Urteile.

Eine Diff-Heuristik lässt sich austricksen, ein Modell kann etwas übersehen. Zusammen und mit „das strengere gilt“
muss nur einer von beiden den Fall erkennen.

## Skips: dokumentiert oder Lücke

Ein übersprungener Test prüft nichts. Bisher fiel das nur bei den Akzeptanztests auf (dort ist ein Skip schon rot).
Bei den eigenen Tests des Implementierers lief ein Skip lautlos durch. Jetzt sammelt `testlauf` die Skip-Gründe aus
dem JUnit-XML. Beginnt ein Grund mit `plattform:` (z. B. `skipif(sys.platform != "win32", reason="plattform: nur
Windows")`), gilt der Skip als dokumentiert. Jeder andere Skip ist ein Einwand. Festlegung vom 13.11.2026, im Plan
nachgetragen.

## Bau und Prüfung

Gebaut am 13.11.2026 nach dem Plan vom 21.10. und den Entscheidungen 6 bis 8 vom 25.10., in drei Tasks mit Tests
zuerst (Ledger: `docs/superpowers/plans/2026-10-21-stufe-7-ledger.md`). Die Demo wurde im Browser bis zum Merge
durchgespielt. Die Abnahme an einer echten Aufgabe (A10) steht noch aus. Sie braucht einen echten Lauf mit Abo, und
während er läuft, darf in Lab 2 nichts geschrieben werden.
