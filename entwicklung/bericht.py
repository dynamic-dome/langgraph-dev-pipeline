"""Bericht je Lauf: berichte/<lauf_id>.md (zum Lesen) und .json (für spätere Stufen und den Leitstand)."""
import json
from pathlib import Path

from entwicklung.konvergenz import verlauf_zeile
from entwicklung.pfade import berichte_dir
from entwicklung.stufen import stufe_im_lauf

SYMBOL = {"gruen": "🟢", "rot": "🔴", "grenzverletzung": "⛔", "agent_fehler": "🟠", "angenommen": "🟡",
          "abgebrochen": "⏹", "akzeptanz_fehler": "⚠", "merge_abgelehnt": "🚫"}
JSON_FELDER = ("repo", "aufgabe_id", "lauf_id", "modell", "worktree", "basis", "sicherung", "status", "agent",
               "grenzverletzungen", "geaenderte_dateien", "testergebnis", "pruefer_modell", "pruefberichte",
               "befunde", "nicht_verwertbar", "nicht_pruefbar", "fix_noetig", "runde", "max_runden", "runden",
               "entscheidung", "wunsch", "klaerung", "spec", "schnittstellen", "annahmen", "spec_runde",
               "akz_versuch", "akz_gruende", "akz_ordner", "akz_probe", "spec_pruefungen", "freigabe", "planung_fehler",
               "akz_hinweis", "plan", "plan_dateien", "plan_runde", "plan_gruende", "plan_pruefungen", "plan_freigabe",
               "einwand_freigaben", "aufrufe", "budget", "komplexitaet", "komplexitaet_vorschlag",
               "komplexitaet_claude", "komplexitaet_codex", "komplexitaet_grund", "spec_verlauf", "spec_einordnung",
               "zielzweig", "gesamtreview", "tuer", "abschluss", "befund_filter")  # Stufe 7, öffentliche Fassung


def tests_zeile(t: dict | None) -> str:
    if not t:
        return "nicht gelaufen"
    a = t["akzeptanz"]
    return (f"{t['bestanden']}/{t['gesammelt']} bestanden, {t['fehlgeschlagen']} fehlgeschlagen, "
            f"{t['fehler']} Fehler · Akzeptanz {a['bestanden']}/{a['gesammelt']}")


def pruefer_zeile(p: dict, nicht_verwertbar: list[dict] | None = None) -> str:
    """Auch ein Bericht, den erst der Filter verworfen hat, ist nicht verwertbar und nie ein PASS."""
    verworfen = {n["pruefer"]: n["fehler"] for n in nicht_verwertbar or []}
    if not p.get("ok") or p["pruefer"] in verworfen:
        return f"{p['pruefer']}: nicht verwertbar ({verworfen.get(p['pruefer']) or p.get('fehler')})"
    befunde = p["bericht"]["findings"]
    return f"{p['pruefer']}: {p['bericht']['verdict']} · {p.get('dauer_s', 0)} s · {len(befunde)} Befunde"


def befund_zeile(b: dict) -> str:
    marke = "⚑ " if b["ausloesend"] else ""
    bremse = " · gebremst: nur Clean Code, keine zweite Stimme" if b.get("gebremst") else ""
    return (f"{marke}[{b['severity']}/{b['kind']}] {b['path']}:{b['line']} — {b['claim']} "
            f"({', '.join(b['pruefer'])}; {b['topf']}{bremse})")


def _pruef_abschnitte(s: dict) -> list[str]:
    if "pruefberichte" not in s and "befunde" not in s:
        return []
    zeilen = ["", "## Prüfer", *_liste(pruefer_zeile(p, s.get("nicht_verwertbar"))
                                       for p in sorted(s.get("pruefberichte") or [], key=lambda p: p["pruefer"]))]
    zeilen += ["", f"Befund-Filter: {s.get('befund_filter') or 'fusion-harness'}",
               f"Fix-Runde nötig: {'ja' if s.get('fix_noetig') else 'nein'}",
               "", "## Befunde (⚑ = löst eine Fix-Runde aus)", *_liste(befund_zeile(b) for b in s.get("befunde") or [])]
    if s.get("nicht_pruefbar"):
        zeilen += ["", "## Nicht prüfbar (laut Prüfern)",
                   *_liste(f"{n['pruefer']}: {n['was']} — {n['warum']}" for n in s["nicht_pruefbar"])]
    return zeilen


def runden_zeile(r: dict) -> str:
    return (f"Runde {r['runde']}: {SYMBOL.get(r['status'], '')} {r['status']} · {r['tests']} · "
            f"{r['befunde']} Befunde, {r['ausloesend']} auslösend")


def _runden_abschnitt(s: dict) -> list[str]:
    if "runden" not in s:
        return []
    zeilen = ["", f"## Runden (höchstens {s.get('max_runden')} Fix-Runden)", *_liste(runden_zeile(r) for r in s["runden"])]
    if s.get("entscheidung"):
        zeilen += ["", f"Entscheidung an der Eskalation: {s['entscheidung']}"]
    return zeilen


def _planung_abschnitte(s: dict) -> list[str]:
    """Ab Stufe 4: was vor der Umsetzung geklärt, geschrieben und freigegeben wurde."""
    if "wunsch" not in s:
        return []
    zeilen = ["", "## Klärung"]
    for i, k in enumerate(s.get("klaerung") or [], 1):
        zeilen += [f"Runde {i}:", *[f"- {f}" for f in k["fragen"]], f"- **Antwort:** {k['antwort']}"]
    if not s.get("klaerung"):
        zeilen.append("- keine Rückfragen")
    if s.get("planung_fehler"):
        zeilen += ["", f"Planung gescheitert: {s['planung_fehler']}"]
    if s.get("spec"):
        ordner = s.get("akz_ordner")
        zeilen += ["", "## Spec", f"- Datei: `{Path(ordner).parent.parent / 'spec.md'}`" if ordner else "- (nicht abgelegt)",
                   f"- Spec-Runden: {s.get('spec_runde', 0) + 1}", "- Annahmen:",
                   *[f"  - {a}" for a in s.get("annahmen") or []]]
    if s.get("spec_verlauf"):  # ab 6c: eine Zeile je Spec-Prüfung
        zeilen += ["", "## Spec-Verlauf", *[f"- {verlauf_zeile(v)}" for v in s["spec_verlauf"]]]
    if s.get("akz_probe") or s.get("akz_gruende"):
        p = s.get("akz_probe") or {}
        zeilen += ["", "## Akzeptanztests aus der Spec", f"- Ordner: `{s.get('akz_ordner') or '–'}`",
                   f"- Versuche: {s.get('akz_versuch', 0) + (0 if s.get('akz_gruende') else 1)}"]
        if p:
            zeilen.append(f"- Probe: {p['erwartet'] - p['bestanden']} von {p['erwartet']} rot gegen main")
        zeilen += [f"- abgelehnt: {g}" for g in s.get("akz_gruende") or []]
    if s.get("spec_pruefungen") is not None and s.get("spec"):
        zeilen += ["", "## Spec-Prüfung"]
        for p in s.get("spec_pruefungen") or []:
            if not p["ok"]:
                zeilen.append(f"- {p['pruefer']}: nicht verwertbar ({p['fehler']})")
                continue
            zeilen.append(f"- {p['pruefer']}: {p['verdict']} · {len(p['punkte'])} Punkte")
            zeilen += [f"  - [{punkt['schwere']}] {punkt['aussage']}" for punkt in p["punkte"]]
    if s.get("freigabe"):
        zeilen += ["", f"Freigabe: {s['freigabe']}"]
    if s.get("plan"):
        ordner = berichte_dir() / s["lauf_id"]
        zeilen += ["", "## Plan", f"- Datei: `{ordner / 'plan.md'}`", f"- Plan-Runden: {s.get('plan_runde', 0) + 1}",
                   f"- Dateien: {', '.join(s.get('plan_dateien') or []) or '–'}"]
        zeilen += [f"- [code] {g}" for g in s.get("plan_gruende") or []]
        for p in s.get("plan_pruefungen") or []:
            zeilen.append(f"- {p['pruefer']}: {p['verdict']} · {len(p['punkte'])} Punkte" if p["ok"]
                          else f"- {p['pruefer']}: nicht verwertbar ({p['fehler']})")
            zeilen += [f"  - [{punkt['schwere']}] {punkt['aussage']}" for punkt in p["punkte"]]
        if s.get("plan_freigabe"):
            zeilen += ["", f"Plan-Freigabe: {s['plan_freigabe']}"]
    return zeilen


def _berater_abschnitt(s: dict) -> list[str]:
    """Ab Stufe 6a: wo Fable beraten hat (Dateien rat-<haltepunkt>-<n>.json neben Spec und Plan)."""
    if not s.get("lauf_id"):
        return []
    dateien = sorted((berichte_dir() / s["lauf_id"]).glob("rat-*.json"))
    if not dateien:
        return []
    zeilen = ["", "## Berater (Fable, Astra)"]
    for d in dateien:
        try:
            e = json.loads(d.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        rat = e.get("rat") or {}
        zeilen.append(f"- {e.get('haltepunkt')} · {e.get('wer') or 'fable'}: {rat.get('entscheidung', 'kein Rat')} "
                      f"({rat.get('sicherheit', '–')})"
                      + (f" · nicht verwertbar: {e['grund']}" if e.get("grund") else "")
                      + (f" · Fehler: {e['fehler']}" if e.get("fehler") else "") + f" · `{d.name}`")
    return zeilen


def _aufrufe_zeile(s: dict) -> list[str]:
    """Ab 6b-2: Agentenaufrufe gegen den Rahmen; Berater (nur auf Klick, außerhalb des Rahmens) aus den Rat-Dateien."""
    if s.get("budget") is None:
        return []
    wer = []
    for d in sorted((berichte_dir() / s["lauf_id"]).glob("rat-*.json")) if s.get("lauf_id") else []:
        try:
            wer.append(json.loads(d.read_text(encoding="utf-8")).get("wer") or "fable")
        except (OSError, ValueError):
            continue
    return [f"- Agentenaufrufe: {s.get('aufrufe') or 0} von {s['budget']}; "
            f"Berater: {wer.count('fable')}× Fable, {wer.count('astra')}× Astra"]


def _stufen_abschnitt(s: dict) -> list[str]:
    """Ab 6b-2: Schätzungen beider Familien, was galt, und Modell/Reasoning je Rolle."""
    if not s.get("komplexitaet"):
        return []
    zeilen = ["", "## Modellstufen",
              f"- Komplexität: {s['komplexitaet']} (Claude: {s.get('komplexitaet_claude') or '–'}, "
              f"Codex: {s.get('komplexitaet_codex') or '–'}, Vorschlag: {s.get('komplexitaet_vorschlag') or '–'})"
              + (" · an der Plan-Freigabe geändert" if s.get("komplexitaet_vorschlag") not in (None, s["komplexitaet"])
                 else "")]
    if s.get("komplexitaet_grund"):
        zeilen.append(f"- Grund (Claude): {s['komplexitaet_grund']}")
    if s.get("komplexitaet_hinweis"):
        zeilen.append(f"- Hinweis: {s['komplexitaet_hinweis']}")
    for rolle in ("implementierer", "pruefer"):
        st = stufe_im_lauf(s, rolle)
        zeilen.append(f"- {rolle}: {st['modell']} · {st['effort']}")
    return zeilen


def _einwand_abschnitt(s: dict) -> list[str]:
    """Ab Stufe 6b-1: wo Dominic trotz Einwand der anderen Modellfamilie (oder der Berater) durchgelassen hat."""
    eintraege = s.get("einwand_freigaben") or []
    if not eintraege:
        return []
    zeilen = ["", "## Freigaben trotz Einwand"]
    for e in eintraege:
        zeilen.append(f"- {e['haltepunkt']}: {e['entscheidung']}. Begründung: {e.get('begruendung') or '–'}")
        zeilen += [f"  - Einwand: {w}" for w in e.get("einwaende") or []]
    return zeilen


def gesamt_zeile(g: dict | None) -> str:
    if not g:
        return "Gesamtreview (Codex): nicht gelaufen"
    if not g.get("ok") or not g.get("daten"):
        return f"Gesamtreview (Codex): nicht verwertbar ({g.get('fehler') or 'kein Ergebnis'})"
    d = g["daten"]
    major = sum(1 for p in d.get("restpunkte") or [] if p.get("schwere") == "major")
    return (f"Gesamtreview (Codex): {d.get('verdict')} · Spec erfüllt: {'ja' if d.get('spec_erfuellt') else 'nein'}"
            f" · {len(d.get('restpunkte') or [])} Restpunkte, {major} major")


def tuer_zeile(tuer: dict | None) -> str:
    """Merge-Danger-Zeile (Stufe 7, Entscheidung 6). Bei Uneinigkeit beide Urteile."""
    if not tuer:
        return "Tür: nicht bewertet"
    zeile = f"Tür: {tuer['urteil']} · Radius: {tuer['radius']}"
    if tuer.get("uneinig"):
        zeile += (f" (Selbstbewertung {tuer['selbst']['urteil']}, Codex {tuer['codex']['urteil']}; "
                  f"das strengere gilt)")
    return zeile


def abschluss_zeile(a: dict | None, status: str | None = None) -> str:
    if not a:
        return "Abschluss: nicht erreicht"
    if status == "merge_abgelehnt":
        return f"🚫 Merge abgelehnt: {a.get('grund')}"
    if a.get("merge_commit"):
        return (f"Gemergt: {a['merge_commit'][:7]} · {len(a.get('uebernommen') or [])} Testdatei(en) übernommen · "
                f"aufgeräumt: {'ja' if a.get('aufgeraeumt') else 'nein'}" + (f" · {a['grund']}" if a.get("grund") else ""))
    return f"Nicht gemergt: {a.get('grund') or 'Entscheidung'}"


def _abschluss_abschnitt(s: dict) -> list[str]:
    """Ab Stufe 7: Gesamtreview, Tür, Entscheidung und was der Merge getan hat."""
    if not s.get("gesamtreview") and not s.get("abschluss"):
        return []
    tuer = s.get("tuer") or {}
    zeilen = ["", "## Abschluss", f"- {tuer_zeile(tuer or None)}"]
    zeilen += [f"  - einseitig: {f}" for f in tuer.get("faelle") or []]
    zeilen.append(f"- {gesamt_zeile(s.get('gesamtreview'))}")
    daten = (s.get("gesamtreview") or {}).get("daten") or {}
    if daten.get("zusammenfassung"):
        zeilen.append(f"  - {daten['zusammenfassung']}")
    zeilen += [f"  - [{p['schwere']}] {p['aussage']}" for p in daten.get("restpunkte") or []]
    a = s.get("abschluss") or {}
    if a:
        zeilen += [f"- Entscheidung: {a.get('entscheidung')}",
                   f"- Zielzweig: {s.get('zielzweig') or '–'} · Merge-Commit: {a.get('merge_commit') or '–'}",
                   f"- {abschluss_zeile(a, s.get('status'))}",
                   f"- Übernommen: {', '.join(Path(p).name for p in a.get('uebernommen') or []) or 'nichts'}",
                   f"- Aufgeräumt: {'ja' if a.get('aufgeraeumt') else 'nein'}"]
    return zeilen


def _liste(eintraege) -> list[str]:
    eintraege = list(eintraege or [])  # None: Lauf endete vor dem Schritt (z. B. in der Planung)
    return [f"- {e}" for e in eintraege] if eintraege else ["- keine"]


def _markdown(s: dict) -> str:
    agent = s.get("agent") or {}
    t = s.get("testergebnis")
    zeilen = [
        f"# Lauf {s['lauf_id']}: {s['aufgabe_id']} → {SYMBOL.get(s['status'], '')} {s['status']}",
        "",
        f"- Repo: `{s['repo']}`",
        f"- Worktree: `{s['worktree']}` (Branch `lauf/{s['lauf_id']}`, Sicherung `{s.get('sicherung') or '–'}`)",
        f"- Implementierer: {stufe_im_lauf(s, 'implementierer')['modell']} · {agent.get('dauer_s', 0)} s · "
        f"{agent.get('turns')} Turns"
        + (f" · Fehler: {agent['fehler']}" if agent.get("fehler") else ""),
        f"- Tests: {tests_zeile(t)}",
        *_aufrufe_zeile(s),
        "",
        "## Geänderte Dateien", *_liste(s.get("geaenderte_dateien")),
        "",
        "## Grenzverletzungen", *_liste(s.get("grenzverletzungen")),
        "",
        "## Verweigerte Versuche des Implementierers", *_liste(agent.get("verweigerungen")),
        "",
        "## Zusammenfassung des Implementierers",
        agent.get("zusammenfassung") or "–",
        *_planung_abschnitte(s),
        *_stufen_abschnitt(s),
        *_berater_abschnitt(s),
        *_einwand_abschnitt(s),
        *_pruef_abschnitte(s),
        *_runden_abschnitt(s),
        *_abschluss_abschnitt(s),
    ]
    if t:
        zeilen += ["", "## Testauszug", "```", t.get("auszug", ""), "```"]
    return "\n".join(zeilen) + "\n"


def _exklusiv(basis: Path, endung: str) -> Path:
    """Nie einen alten Bericht überschreiben: bei Kollision -2, -3 …"""
    n = 1
    while True:
        pfad = basis.with_name(basis.name + ("" if n == 1 else f"-{n}") + endung)
        if not pfad.exists() and not pfad.with_suffix(".json").exists():
            return pfad
        n += 1


def schreibe_bericht(state: dict) -> Path:
    md = _exklusiv(berichte_dir() / state["lauf_id"], ".md")
    with md.open("x", encoding="utf-8") as f:
        f.write(_markdown(state))
    with md.with_suffix(".json").open("x", encoding="utf-8") as f:
        json.dump({k: state.get(k) for k in JSON_FELDER}, f, ensure_ascii=False, indent=1)
    return md
