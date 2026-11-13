# Lab 2 · Lernstufe 4b: Plan, Plan-Prüfung, Plan-Freigabe; Tests nachbessern

**Ausprobieren:** im Leitstand einen Lauf mit Stufe 4 starten (oder `lauf --repo portwart --aufgabe A5 --live`).
Nach der Spec-Freigabe hält der Lauf ein zweites Mal an: an der Plan-Freigabe.

## Die Idee in einem Satz

Zwischen „was soll entstehen“ (Spec) und „mach“ (Implementierer) steht jetzt „wie gehen wir vor“ (Plan). Ein Agent
schreibt ihn, Code und Codex prüfen ihn gegen die Spec, Dominic gibt ihn frei, und der Implementierer bekommt Spec
**und** Plan.

## Der Ablauf am echten Code

```
… spec_freigabe ⏸ ─ freigeben         → plan_schreiben → plan_pruefen (Codex) → plan_freigabe ⏸
                   ─ aendern           → spec_schreiben (Spec und danach Tests neu)
                   ─ tests_nachbessern → akzeptanz_schreiben (Spec bleibt)
                   ─ abbrechen         → bericht
plan_freigabe ⏸ ─ freigeben → umsetzung_starten → implementieren … (Aufgabe = Spec + „## Plan“ + Plan)
                ─ aendern   → plan_schreiben (nur der Plan neu)
                ─ abbrechen → bericht
```

### 1. Eine Freigabe ist eine Weiche

`spec_freigabe` hat jetzt vier Ausgänge, `plan_freigabe` drei. In LangGraph ist das eine bedingte Kante mit einem
Wörterbuch Entscheidung → Ziel (`nach_freigabe`, `nach_plan_freigabe`). Jeder Weg setzt nur die Felder zurück, die
er neu erzeugt: `aendern` an der Plan-Freigabe lässt Spec, Tests und Probe unberührt
(`test_plan_aendern_nur_plan_neu`), `tests_nachbessern` lässt die Spec und ihre Runde unberührt.

### 2. Deterministische Prüfung neben der Modellprüfung

`pruefe_plan` (Code) prüft, was sich zählen lässt: Kommt jede Schnittstelle der Spec im Plan vor? Bleiben die Dateien
im Rahmen (nicht `ports.toml`, nicht `tests/_akzeptanz/`, kein `..`, nicht absolut)? Codex prüft, was sich nicht
zählen lässt: Würde ein Implementierer, der dem Plan folgt, die Spec erfüllen? Beide Ergebnisse **blockieren nicht**;
sie stehen in der Freigabe, Dominic entscheidet.

### 3. Erzeugte Tests gehören in die Regression

Die Akzeptanztests von A4 lagen nur unter `berichte/…`. Für A5 liefen sie deshalb zunächst nicht mit. Jetzt liegen
sie in `aufgaben/portwart/A4/`, und A5 lief gegen 123 Akzeptanztests (88 aus A1–A4 plus 35 neue). Einen Test habe
ich beim Übernehmen gestrichen: Er braucht einen Ordner-Symlink, der hier nicht erlaubt ist, und ein übersprungener
Test in der Regression würde jede spätere Aufgabe rot machen. Das Übernehmen wird in Stufe 7 automatisch.

## Was der echte Lauf zeigte (A5, Lauf 20261020-164410)

- **Klären:** 5 Fragen. Bei Frage 3 hat Dominic die Voreinstellung (fehlender Pfad = Abbruch mit Exit 2) bewusst
  geändert: ein fehlender Pfad ist ein Befund `pfad-fehlt`, die übrigen Projekte werden weiter geprüft.
- **Spec, Fassung 1:** Claude und Codex fanden unabhängig denselben kaputten Test (`liste/liste/p.toml`, scheitert bei
  jeder Umsetzung) und einen Widerspruch zu einem vorhandenen Test (`drift` ohne Wurzel). Ohne Spec-Prüfung wäre
  der Lauf sicher in der Eskalation geendet. Dominic: `aendern` mit „alle Punkte einarbeiten“ plus Einzelheiten.
- **Spec, Fassung 2:** nur noch `minor`-Punkte, Test repariert. Freigegeben.
- **Plan:** 140 Zeilen, 5 Schritte test-first, Codex ohne Punkte. Freigegeben.
- **Umsetzung:** Runde 0 grün mit einem auslösenden Befund (PermissionError erst beim Durchlaufen des Ordners),
  Runde 1 grün ohne auslösenden Befund. 232 Tests, Akzeptanz 123/123.
- **Erster echter Einsatz:** `drift` mit einem echten Projektpfad: schnell (0,4 s), `pfad-fehlt` stimmt, aber 201 von
  204 `unbekannt`-Zeilen stammen aus Berichten und Daten-JSON. Nächster Wunsch (A6): Ordner ausschließen.

## Was dieser Lauf an Schwächen gezeigt hat

- **`tests_nachbessern` sieht die Prüfpunkte nicht.** Der Spec-Schreiber bekommt sie bei `aendern`, der
  Test-Schreiber bei `tests_nachbessern` nur Dominics Hinweis. „Alle Punkte einarbeiten“ ginge dort ins Leere.
- **Prüfer ohne Kontext:** Der Hinweis zu `parents[2]` kam zum zweiten Mal (falsch, die Tests liegen beim Lauf in
  `tests/_akzeptanz/`). Ein Satz dazu im Prüf-Prompt würde ihn abstellen.
- **Codex konnte das Repo diesmal nicht selbst lesen** (Sandbox, `CreateProcessAsUserW`) und prüfte nur, was im
  Prompt stand.

## Selbst prüfen

1. Warum lässt `tests_nachbessern` die `spec_runde` unverändert?
2. Warum blockieren die Gründe aus `pruefe_plan` nicht?
3. Was wäre bei A5 passiert, wenn die A4-Tests nicht in der Regression gelegen hätten?

<details><summary>Antworten</summary>

1. Die Spec ist dieselbe; nur die Tests werden besser. Die Runde zählt Fassungen der Spec.
2. Code kann zählen, aber nicht urteilen: Ein Plan, der eine Schnittstelle anders benennt, kann trotzdem richtig
   sein. Dominic sieht den Grund und entscheidet.
3. A5 ändert `drift` (aus A4). Ein Fehler, der A4-Verhalten bricht, wäre nur über die eigenen Tests des
   Implementierers aufgefallen – also über Tests, die er selbst geschrieben und selbst angepasst hat.
</details>
