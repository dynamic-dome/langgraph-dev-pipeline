"""Berater an den Haltepunkten: Fable (Stufe 6a) und Astra (6b-1) empfehlen, Dominic entscheidet.

Auf Klick liest Fable, was Dominic freigeben soll, und das Repo (nur lesend), schätzt jeden Prüfpunkt ein und schreibt
die Antwort bzw. den Hinweis fertig vor. Abgeschickt wird erst, wenn Dominic „übernehmen“ klickt. Die Empfehlung
geht durch dieselbe Regel wie Knopf und CLI (steuerung.antwort_fuer): Was dort nicht erlaubt ist, ist „nicht
verwertbar“. Fable gibt nie selbst frei (Grundregel seit Stufe 3).

Astra ist Codex (GPT-Familie, Standardmodell, high): die Gegenstimme zur Claude-Familie, die Spec, Tests und Plan
geschrieben hat (Lehre A6). Codex kann hier keine Prozesse starten und damit keine Dateien lesen; der Prompt bettet die
relevanten Quelldateien aus dem Worktree ein. Wer das später ändern will („Astra liest selbst“, z. B. unter Linux),
tauscht nur quelldateien und Abhaengigkeiten.berater_astra.
"""
import json
import time
from pathlib import Path
from typing import Callable

from entwicklung.graph import BUDGET_PUNKTE
from entwicklung.graph_s4 import MIT_HINWEIS
from entwicklung.konvergenz import punkt_zeile
from entwicklung.planung import _TEXT, _liste, _objekt
from entwicklung.steuerung import DURCHLASS, ERLAUBT_KURZ, antwort_fuer

BERATER_MODELL = "fable"  # nur hier und nur auf Klick (Entscheid Dominic 20.10.)
BERATER_TIMEOUT = 900
MAX_ZEICHEN = 40_000
BERATER = ("fable", "astra")
ASTRA_TIMEOUT = 900
# Am Kostenrahmen entscheidet nur der Mensch; ein Rat kostet selbst (6b-2). Am Abschluss ist das Gesamtreview
# (Codex) schon die Zweitmeinung (Stufe 7).
OHNE_RAT = (*BUDGET_PUNKTE, "abschluss_freigabe")
KEIN_RAT_TEXT = "Am Kostenrahmen gibt es keinen Rat: mehr erlauben oder abbrechen entscheidest du."
KEIN_RAT_ABSCHLUSS = ("Am Abschluss gibt es keinen Rat: Das Gesamtreview (Codex) ist schon die Zweitmeinung, "
                      "mergen oder nicht mergen entscheidest du.")


def kein_rat_text(punkt: str) -> str:
    return KEIN_RAT_ABSCHLUSS if punkt == "abschluss_freigabe" else KEIN_RAT_TEXT
BERATER_EFFORT = "high"  # gleiche Reasoning-Stufe für Fable und Astra (Idee Dominic 20.10.)
VERMERK = "\n… (gekürzt: Grenze für eingebettete Quellen erreicht)"
MAX_QUELLEN = 60_000  # eingebettete Quelldateien für Astra, alle zusammen
# Vorbelegt wird bei Uneinigkeit die vorsichtigere Empfehlung: erst nachbessern, dann verwerfen, dann durchlassen
VORSICHT = {"spec_freigabe": ["aendern", "tests_nachbessern", "abbrechen", "freigeben"],
            "plan_freigabe": ["aendern", "abbrechen", "freigeben"],
            "eskalation": ["weiter", "abbrechen", "annehmen"]}

RAT_SCHEMA = _objekt(entscheidung=_TEXT, text=_TEXT, begruendung=_TEXT,
                     sicherheit={"type": "string", "enum": ["hoch", "mittel", "niedrig"]},
                     punkte=_liste(_objekt(aussage=_TEXT, warum=_TEXT,
                                           einschaetzung={"type": "string",
                                                          "enum": ["echt", "klein", "falscher_alarm"]})))

BEDEUTUNG = {
    "antwort": "die Rückfragen beantworten (text = deine Antworten, alle in einem Text)",
    "abbrechen": "den Lauf beenden",
    "freigeben": "so freigeben, wie es ist",
    "aendern": "neu schreiben lassen (text = Hinweis, was anders werden soll)",
    "tests_nachbessern": "nur die Akzeptanztests verbessern, die Spec bleibt (text = konkrete Punkte)",
    "weiter": "eine weitere Fix-Runde",
    "annehmen": "den Stand trotz offener Befunde annehmen",
}

WISSEN = """## Wissen über die Pipeline (wichtig für dein Urteil)
- Die Akzeptanztests liegen beim Testlauf in `tests/_akzeptanz/` im Worktree; `Path(__file__).resolve().parents[2]`
  zeigt dort auf das Repo. Hinweise der Prüfer, `parents[2]` stimme nicht, sind deshalb falscher Alarm.
- `aendern` an der Spec-Freigabe: Der Spec-Schreiber bekommt deinen Hinweis und alle Prüfpunkte; danach werden die
  Tests komplett neu geschrieben.
- `tests_nachbessern`: Die Spec bleibt. Der Test-Schreiber sieht seine vorige Fassung und den Hinweis, aber
  keine Prüfpunkte. Alles, was er beheben soll, muss deshalb konkret im Hinweis stehen.
- Ein Akzeptanztest, der bei jeder Umsetzung scheitert (z. B. kaputter Testaufbau), führt sicher in die Eskalation:
  dann nicht freigeben.
- Bleiben nur `minor`-Punkte, ist Freigeben meist richtig; Feinschliff prüfen später die Prüfer der Umsetzung.
- Ein übersprungener Akzeptanztest prüft nichts; Plattformabhängiges (Symlinks unter Windows) muss simuliert werden.
- Ein Widerspruch in der Spec ist nie harmlos: Codex prüft die Umsetzung gegen die Spec und meldet ihn in jeder
  Fix-Runde neu (A6: zwei vergeudete Runden). Empfiehl `aendern` mit dem Satz, der fallen oder umformuliert werden soll.
- Ein `major` des Codex-Prüfers (andere Modellfamilie als du) stufst du nur mit Gegenbeleg aus dem Code herab.
  Zitiere ihn. Ohne Beleg ist der Punkt `echt`.
"""


def _kurz(text, grenze: int = MAX_ZEICHEN) -> str:
    text = str(text or "")
    return text if len(text) <= grenze else text[:grenze] + "\n… (gekürzt)"


def _klaerung(werte: dict) -> str:
    zeilen = []
    for i, k in enumerate(werte.get("klaerung") or [], 1):
        zeilen += [f"Runde {i}:", *[f"- {f}" for f in k["fragen"]], f"Antwort von Dominic: {k['antwort']}"]
    return "\n".join(zeilen) or "(keine)"


def _vertrag(werte: dict, mit_tests: bool) -> list[str]:
    """Die freigegebene Spec (und ihre Tests): Sie liegen unter berichte/, wo Fable selbst nicht lesen kann."""
    teile = [f"## Freigegebene Spec\n{_kurz(werte.get('spec'))}"] if werte.get("spec") else []
    if mit_tests and werte.get("akz_dateien"):
        teile.append("## Freigegebene Akzeptanztests\n" + "\n\n".join(
            f"### {d['name']}\n```python\n{_kurz(d['inhalt'])}\n```" for d in werte["akz_dateien"]))
    return teile


KONVERGENZ_REGEL = ("Ab Fassung 2 empfiehlst du `aendern` nur, wenn ein Punkt unter „Lösen eine neue Runde aus“ "
                    "echt ist. Die Liste allein ist kein Grund für eine neue Runde; nenne sie in `begruendung`.")


def _material(punkt: str, frage: dict, werte: dict) -> str:
    teile = []
    if punkt == "fragen":
        teile += [f"## Verständnis des Klärers\n{frage.get('verstaendnis', '')}",
                  "## Rückfragen an Dominic\n" + "\n".join(f"{i}. {q}" for i, q in enumerate(frage.get("fragen", []), 1))]
    if punkt == "spec_freigabe":
        p = frage.get("probe") or {}
        teile += [f"## Spec (Fassung {frage.get('spec_runde', 0) + 1})\n{_kurz(frage.get('spec_text'))}",
                  "## Akzeptanztests\n" + "\n\n".join(f"### {n}\n```python\n{_kurz(i)}\n```"
                                                     for n, i in (frage.get("tests_text") or {}).items()),
                  f"## Probe gegen main\n{p.get('erwartet', 0) - p.get('bestanden', 0)} von {p.get('erwartet')} rot",
                  "## Annahmen\n" + "\n".join(f"- {a}" for a in frage.get("annahmen") or [])]
    if punkt == "plan_freigabe":
        teile += _vertrag(werte, mit_tests=True)
        teile += [f"## Plan (Fassung {frage.get('plan_runde', 0) + 1})\n{_kurz(frage.get('plan_text'))}",
                  "## Dateien laut Plan\n" + "\n".join(f"- {d}" for d in frage.get("dateien") or [])]
    if punkt == "eskalation":
        teile += _vertrag(werte, mit_tests=False)
        if werte.get("plan"):
            teile.append(f"## Freigegebener Plan\n{_kurz(werte['plan'])}")
        teile += [f"## Lage\n{frage.get('frage', '')}\nTests: {frage.get('tests', '')}",
                  "## Auslösende Befunde\n" + "\n".join(
                      f"- [{b.get('severity')}/{b.get('kind')}] {b.get('path')}:{b.get('line')} — {b.get('claim')}"
                      for b in frage.get("ausloesend") or [])]
    einordnung = frage.get("einordnung") if punkt == "spec_freigabe" and frage.get("nachpruefung") else None
    if einordnung:  # 6c: Nachprüfung, die Punkte stehen nach Gruppen statt in einer Liste
        teile += ["## Lösen eine neue Runde aus\n" + ("\n".join(f"- {punkt_zeile(p)}" for p in einordnung["ausloesend"])
                                                      or "- keine"),
                  "## Liste für Dominic (keine neue Runde nötig)\n" + ("\n".join(
                      f"- {punkt_zeile(p)}" for p in einordnung["liste"]) or "- keine"),
                  KONVERGENZ_REGEL]
    elif frage.get("pruefpunkte"):
        teile.append("## Punkte der Prüfer\n" + "\n".join(f"- [{p.get('pruefer')}, {p.get('schwere')}] {p.get('aussage')}"
                                                         for p in frage["pruefpunkte"]))
    return "\n\n".join(teile)


def _modulpfad(name: str) -> str:
    return name if "/" in name or name.endswith(".py") else name.replace(".", "/") + ".py"


def _repo_dateien(worktree: Path) -> list[str]:
    """Von git verfolgte *.py: erst Code, dann tests/, nie tests/_akzeptanz/ (die Tests sieht nur der Testlauf)."""
    from entwicklung.worktree import WorktreeFehler, _git
    try:
        lauf = _git(worktree, "ls-files", "*.py", pruefen=False)
    except (WorktreeFehler, OSError):
        return []
    if lauf.returncode != 0:
        return []
    namen = [z.strip() for z in lauf.stdout.splitlines() if z.strip() and not z.startswith("tests/_akzeptanz/")]
    return [n for n in namen if not n.startswith("tests/")] + [n for n in namen if n.startswith("tests/")]


def quelldateien(werte: dict, frage: dict, punkt: str, worktree: Path) -> dict[str, str]:
    """Die Dateien, die Astra eingebettet bekommt: laut Plan, an der Eskalation die geänderten, dann die Schnittstellen.

    Nur Dateien im Worktree; Pfade kommen teils von Agenten und dürfen nie nach draußen zeigen (../, absolut)."""
    kandidaten = []
    if punkt in ("plan_freigabe", "eskalation"):
        kandidaten += frage.get("dateien") or werte.get("plan_dateien") or []
    if punkt == "eskalation":
        kandidaten += werte.get("geaenderte_dateien") or []
    kandidaten += [_modulpfad(s["modul"]) for s in werte.get("schnittstellen") or [] if s.get("modul")]
    kandidaten += _repo_dateien(Path(worktree))  # der bestehende Code, auch an Rückfragen und Spec
    wurzel = Path(worktree).resolve()
    quellen, rest = {}, MAX_QUELLEN
    for name in kandidaten:
        pfad = (wurzel / str(name)).resolve()
        if not pfad.is_relative_to(wurzel) or not pfad.is_file():
            continue
        schluessel = pfad.relative_to(wurzel).as_posix()
        if schluessel in quellen or rest <= 0:
            continue
        inhalt = pfad.read_text(encoding="utf-8", errors="replace")
        if len(inhalt) > rest:  # der Vermerk zählt mit (Codex 6b-1 F-005)
            if rest <= len(VERMERK):
                break
            inhalt = inhalt[:rest - len(VERMERK)] + VERMERK
        quellen[schluessel] = inhalt
        rest -= len(inhalt)
    return quellen


def berater_prompt(punkt: str, frage: dict, werte: dict, quellen: dict[str, str] | None = None) -> str:
    erlaubt = ERLAUBT_KURZ.get(punkt, [])
    if quellen is None:
        lesen = ("Du kannst das Repo im aktuellen Ordner lesen (nur lesen): Sieh nach, statt zu raten, wenn eine "
                 "Aussage vom Code abhängt.")
    else:
        lesen = ("Du kannst keine Dateien lesen. Die relevanten Quelldateien stehen unten. Fehlt dir eine, sag es in "
                 "`begruendung` und senke `sicherheit`.")
    eingebettet = ""
    if quellen is not None:  # auch leer zeigen: Neue Module gibt es an der Spec-Freigabe oft noch nicht
        eingebettet = ("## Quelldateien (Worktree)\n" + ("\n\n".join(
            f"### {n}\n```\n{i}\n```" for n, i in quellen.items()) or "(keine passenden Dateien im Worktree: Die "
            "Module aus Spec und Plan gibt es dort noch nicht. Urteile über Spec und Tests.)") + "\n\n")
    return f"""Du berätst Dominic an einem Haltepunkt seiner Entwicklungs-Pipeline. Er entscheidet, du empfiehlst.
{lesen}

## Aufgabe {werte.get('aufgabe_id', '')}: Wunsch von Dominic
{_kurz(werte.get('wunsch'), 5000)}

## Bisherige Rückfragen und Antworten
{_klaerung(werte)}

{_material(punkt, frage, werte)}

{eingebettet}{WISSEN}
## Erlaubte Entscheidungen an diesem Haltepunkt ({punkt})
{chr(10).join(f"- `{e}`: {BEDEUTUNG.get(e, '')}" for e in erlaubt)}

## Auftrag
- Schätze jeden Prüfpunkt ein: `echt` (muss vor der Freigabe behoben werden), `klein` (kann bleiben) oder
  `falscher_alarm` (stimmt nicht; sag warum). Prüfe im Repo, wo nötig.
- Empfiehl genau eine der erlaubten Entscheidungen. `text`: die fertige Antwort bzw. den fertigen Hinweis, so dass
  Dominic ihn ohne Änderung abschicken kann; bei `freigeben`, `abbrechen`, `weiter`, `annehmen` leer.
- `begruendung`: 2–5 Sätze, das Wichtigste zuerst. `sicherheit`: wie sicher du dir bist.
"""


def rat_pruefen(punkt: str, rat: dict) -> tuple[dict | None, str | None]:
    """Übersetzt den Rat in die Antwort an den Haltepunkt, oder (None, Grund), wenn er dort nicht gilt."""
    entscheidung, text = rat.get("entscheidung"), rat.get("text") or ""
    if punkt == "fragen" and entscheidung == "antwort":
        antwort = antwort_fuer(punkt, None, text, None)
    else:
        antwort = antwort_fuer(punkt, entscheidung, None, text if entscheidung in MIT_HINWEIS else None)
    if antwort is None:
        return None, (f"Empfehlung „{entscheidung}“ ist an {punkt} nicht erlaubt oder unvollständig "
                      f"(erlaubt: {', '.join(ERLAUBT_KURZ.get(punkt, []))})")
    return antwort, None


def hole_rat(abh, punkt: str, frage: dict, werte: dict, worktree: Path, sauber: Callable[[], list[str]],
             wer: str = "fable") -> dict:
    start = time.monotonic()
    ergebnis = {"wer": wer, "ok": False, "rat": None, "antwort": None, "grund": None, "fehler": None, "dauer_s": 0.0}
    try:
        if wer == "astra":
            prompt = berater_prompt(punkt, frage, werte, quellen=quelldateien(werte, frage, punkt, worktree))
            erg = abh.berater_astra("berater_astra", prompt, worktree, RAT_SCHEMA, timeout=ASTRA_TIMEOUT,
                                    effort=BERATER_EFFORT)
        else:
            erg = abh.berater("berater", berater_prompt(punkt, frage, werte), worktree, RAT_SCHEMA,
                              modell=BERATER_MODELL, timeout=BERATER_TIMEOUT, effort=BERATER_EFFORT)
    except Exception as e:  # ein Berater, der scheitert, ist eine Meldung, kein Absturz
        erg = {"ok": False, "daten": None, "fehler": f"{type(e).__name__}: {e}"}
    ergebnis["dauer_s"] = round(time.monotonic() - start, 1)
    verletzungen = sauber()
    if verletzungen:
        return {**ergebnis, "fehler": "Grenzverletzung beim Rat: " + "; ".join(verletzungen)}
    if not erg.get("ok"):
        return {**ergebnis, "fehler": erg.get("fehler") or "Berater ohne Ergebnis"}
    antwort, grund = rat_pruefen(punkt, erg["daten"])
    return {**ergebnis, "ok": True, "rat": erg["daten"], "antwort": antwort, "grund": grund}


def _gilt(e: dict | None) -> bool:
    return bool(e and e.get("ok") and e.get("antwort") and e.get("rat"))


def vergleiche(punkt: str, fable: dict | None, astra: dict | None) -> dict | None:
    """Einig oder uneinig, und welcher Rat vorbelegt wird. None, solange es nichts zu vergleichen gibt."""
    if not (_gilt(fable) and _gilt(astra)):
        return None
    if (fable["haltepunkt"], fable["checkpoint_id"]) != (astra["haltepunkt"], astra["checkpoint_id"]):
        return None
    if punkt == "fragen":  # zwei Antworttexte: kein Entscheid zu vergleichen
        return {"einig": True, "vorbelegt": "fable", "einwaende": []}
    f, a = fable["rat"]["entscheidung"], astra["rat"]["entscheidung"]
    reihe = VORSICHT.get(punkt, [])
    rang = {e: i for i, e in enumerate(reihe)}
    vorbelegt = "fable" if rang.get(f, len(reihe)) < rang.get(a, len(reihe)) else "astra"
    return {"einig": f == a, "vorbelegt": vorbelegt, "einwaende": einwaende_aus_raeten(punkt, {"fable": fable,
                                                                                               "astra": astra})}


def raete_fuer_stand(ordner: Path, punkt: str, checkpoint_id: str | None) -> dict[str, dict]:
    """Je Berater der neueste abgelegte Rat für genau diesen Haltepunkt und Stand (Dateien aus 6a ohne wer: Fable).

    Aus den Dateien, nicht aus dem Speicher des Servers: So gilt für CLI und Leitstand dieselbe Grundlage."""
    ordner = Path(ordner)
    if not ordner.is_dir():
        return {}
    raete = {}
    for datei in sorted(ordner.glob("rat-*.json"), key=lambda p: (p.stat().st_mtime_ns, p.name)):
        try:
            e = json.loads(datei.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(e, dict) and e.get("haltepunkt") == punkt and e.get("checkpoint_id") == checkpoint_id:
            raete[e.get("wer") or "fable"] = e
    return raete


def einwaende_fuer(punkt: str, frage: dict | None, ordner: Path, checkpoint_id: str | None) -> list[str]:
    """Alle Einwände am aktuellen Stand: Codex-Prüfer (aus dem Haltepunkt) und Räte. Gleiche Regel für CLI und
    Leitstand; was ein Browser als Einwand mitschickt, zählt nicht."""
    eigene = [e for e in (frage or {}).get("einwaende") or [] if isinstance(e, str)]
    return list(dict.fromkeys(eigene + einwaende_aus_raeten(punkt, raete_fuer_stand(ordner, punkt, checkpoint_id))))


def _erster_satz(text: str) -> str:
    text = " ".join(str(text or "").split())
    ende = text.find(". ")
    return text[:ende + 1] if ende >= 0 else text


def einwaende_aus_raeten(punkt: str, raete: dict[str, dict]) -> list[str]:
    """Einwände aus den Räten: Uneinigkeit der Familien, oder Astra (GPT) rät, nicht durchzulassen."""
    if punkt == "fragen":
        return []
    fable, astra = raete.get("fable"), raete.get("astra")
    einwaende = []
    if _gilt(fable) and _gilt(astra) and fable["rat"]["entscheidung"] != astra["rat"]["entscheidung"]:
        einwaende.append(f"Fable empfiehlt {fable['rat']['entscheidung']}, Astra {astra['rat']['entscheidung']}")
    if _gilt(astra) and astra["rat"]["entscheidung"] not in DURCHLASS:
        einwaende.append(f"Astra (GPT) rät zu {astra['rat']['entscheidung']}: "
                         f"{_erster_satz(astra['rat'].get('begruendung'))}")
    return list(dict.fromkeys(einwaende))
