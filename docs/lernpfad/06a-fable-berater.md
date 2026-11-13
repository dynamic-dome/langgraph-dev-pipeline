# Lab 2 · Lernstufe 6a: Fable als Berater an den Haltepunkten

**Ausprobieren:** im Leitstand an einem Haltepunkt „🧠 Fable fragen“, oder `.venv\Scripts\python.exe -m entwicklung rat`.

## Die Idee in einem Satz

Ein teures Modell arbeitet nicht mit, sondern **berät**: Auf Klick liest Fable, was Dominic freigeben soll, und das
Repo, schätzt jeden Prüfpunkt ein und füllt das Formular vor. Abgeschickt wird erst mit Dominics Klick.

## Bausteine

- **`berater.py`:** Prompt mit „Wissen über die Pipeline“ (wo die Tests liegen, was `aendern` und
  `tests_nachbessern` bewirken), strenges Schema, und `rat_pruefen` übersetzt den Rat über dieselbe Regel wie Knopf
  und CLI (`steuerung.antwort_fuer`). Was dort nicht erlaubt ist, ist „nicht verwertbar“.
- **Gebunden an einen Stand:** Ein Rat gilt nur für Haltepunkt und `checkpoint_id`, für die er angefordert wurde.
  Antwortet Dominic inzwischen selbst, ist er „veraltet“; „übernehmen“ gibt dann 409. Auch der Thread, der Fable
  fragt, prüft das vor dem Aufruf (sonst bekäme ein Klick auf A still einen Rat für B).
- **Nur lesend, nachkontrolliert:** `--tools Read,Glob,Grep`, danach `planung_sauber` (inklusive `tests/_akzeptanz/`).
- **Abgelegt:** jeder Rat als `berichte/<lauf>/rat-<haltepunkt>-<n>.json`, im Bericht unter „Berater (Fable)“.
- **Was im Feld steht, gilt:** Ändert Dominic Fables vorausgefüllten Text, sendet „übernehmen“ seine Fassung.

## Der Vergleich am echten Lauf (A6, Lauf 20261020-184036)

| Haltepunkt | Fable | Dauer | Mein Urteil | Was wirklich geschah |
|---|---|---|---|---|
| Rückfragen | Antworten, fertiger Text | 73 s | einverstanden | Fable erkannte den `lade()`-Fallstrick (neuer Schlüssel nur für `drift` lesen, sonst ändern sich `pruefen`/`abgleich`/`frei`). Kam so in Spec und Plan an. |
| Spec 1 | Tests nachbessern, 4 konkrete Punkte | 110 s | einverstanden | Ein Test war bei jeder Umsetzung unerfüllbar (`"././a"`). Nachbesserung hat ihn behoben. |
| Spec 2 | Freigeben; Idempotenz-Widerspruch „klein“ | 144 s | einverstanden | **Falsch.** Codex hatte den Widerspruch als `major` gemeldet. |
| Plan | Freigeben | 52 s | einverstanden | Plan passte. |
| Eskalation | Annehmen | 35 s | einverstanden | Richtig: Zwei der drei Fix-Runden gingen auf genau den Spec-Widerspruch zurück. |

Fable war gründlich (er zitierte Codezeilen), schnell genug und schrieb Texte, die man ohne Änderung abschicken
konnte. Zweimal hat er Wesentliches beigetragen. Aber an der wichtigsten Stelle hat er sich geirrt – und ich mit ihm.

## Die wichtigste Lehre: gleiche Familie, gleicher blinder Fleck

In der Spec standen zwei Sätze, die sich widersprechen („ein führendes `./` einmal entfernen“ und „die
Normalisierung ist idempotent“). So urteilten die Beteiligten an der Spec-Freigabe:

| Wer | Modellfamilie | Urteil |
|---|---|---|
| Codex-Prüfer | GPT | **major** – vorher beheben |
| Claude-Prüfer | Claude | minor |
| Fable | Claude | klein, herabgestuft mit plausibler Begründung |
| ich | Claude | harmlos |

Die Umsetzung lief danach zwei Fix-Runden lang gegen denselben Befund und eskalierte. Codex prüft die Umsetzung
gegen die Spec; steht dort ein Widerspruch, meldet er ihn in jeder Runde neu, und keine Umsetzung kann ihn
erfüllen. Drei übereinstimmende Claude-Urteile waren hier kein Beleg, sondern ein gemeinsamer blinder Fleck – die
einzige Gegenstimme kam aus der anderen Modellfamilie und wurde überstimmt.

Folgerungen (Dominic, Gate 6a):
- **Ein Widerspruch in der Spec ist nie harmlos.** Vor der Freigabe beheben (`aendern`).
- **Uneinigkeit zwischen den Familien ist ein Signal, keine Mehrheitsfrage.** Meldet die GPT-Familie ein `major`,
  das die Claude-Familie herabstuft, wiegt das schwerer – gerade bei Spec, Tests und Plan, die die Claude-Familie
  geschrieben hat.
- Dafür braucht es neben „Fable fragen“ eine Zweitmeinung aus der anderen Familie und eine Freigabe, die diese
  Uneinigkeit nicht still übergeht (Stufe 6b).

## Selbst prüfen

1. Warum gibt Fable nicht selbst frei, obwohl seine Räte meist stimmen?
2. Warum muss der Rat-Thread den Stand vor dem Aufruf noch einmal prüfen?
3. Was hätte an der Spec-Freigabe von A6 die zwei vergeudeten Runden verhindert?

<details><summary>Antworten</summary>

1. Weil „meist“ nicht reicht: An Spec 2 hat er sich geirrt. Die Freigabe soll ein Mensch verantworten; Fable
   macht sie schneller und besser begründet, aber nicht überflüssig.
2. Zwischen Klick und Thread-Start kann der Lauf weitergelaufen sein. Ohne Prüfung käme ein Rat für einen
   Haltepunkt, den Dominic gar nicht angefragt hat – und er sähe aus, als gehöre er zum aktuellen.
3. Codex' `major` ernst nehmen: „Spec ändern“ mit „Idempotenz-Satz streichen“. Allgemein: Uneinigkeit zwischen
   den Modellfamilien als Warnsignal behandeln statt die Mehrheit entscheiden zu lassen.
</details>
