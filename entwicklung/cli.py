"""Kommandozeile.

python -m entwicklung lauf --repo portwart --aufgabe A4 [--stufe 1|2|3|4] [--modell sonnet] [--pruefer-modell sonnet]
                          [--max-runden 2] [--live]
                                     (ab Stufe 4) klären, Spec, Akzeptanztests aus der Spec, Freigabe; dann
                                     Implementierer im Worktree, Nachkontrolle, Tests, (ab Stufe 2) vier Prüfer
                                     parallel, (ab Stufe 3) Fix-Runden und Eskalation, Bericht
python -m entwicklung fortsetzen [--antwort TEXT] [--entscheidung E] [--hinweis TEXT] [--thread ID] [--live]
                                     angehaltenen Lauf fortsetzen; was erlaubt ist, hängt vom Haltepunkt ab:
                                     Fragen: --antwort "…" | Spec-Freigabe: --entscheidung freigeben|aendern|abbrechen
                                     (aendern mit --hinweis "…") | Eskalation: --entscheidung weiter|annehmen|abbrechen
python -m entwicklung rat [--thread ID]
                                     Fable berät am Haltepunkt des wartenden Laufs (1–3 min, nur lesend);
                                     entscheiden musst du selbst (fortsetzen)
python -m entwicklung aufraeumen [--alle]
                                     alte Worktrees entfernen (ohne --force; der Branch lauf/<id> bleibt)
python -m entwicklung leitstand [--port P] [--kein-browser]
                                     Leitstand im Browser: Ablaufdiagramm, Freigaben, neue Läufe (nur 127.0.0.1)
"""
import argparse
import sys
import time
from pathlib import Path

from entwicklung import worktree
from langgraph.types import Command

from entwicklung.bericht import SYMBOL, befund_zeile, pruefer_zeile, runden_zeile, tests_zeile
from entwicklung.bericht import abschluss_zeile, gesamt_zeile, tuer_zeile
from entwicklung.graph import (BUDGET, BUDGET_PUNKTE, BUDGET_SCHRITT, ENTSCHEIDUNGEN, MAX_RUNDEN, PRUEFER_KNOTEN, Abhaengigkeiten, baue_graph_s1, baue_graph_s2,
                               baue_graph_s3)
from entwicklung.graph_s4 import FREIGABEN, baue_graph_s4
from entwicklung.graph_s4 import ABSCHLUSS_ENTSCHEIDUNGEN
from entwicklung.konvergenz import punkt_zeile, verlauf_zeile
from entwicklung.steuerung import DURCHLASS, antwort_fuer, einwand_fehlt
from entwicklung.speicher import freie_thread_id, oeffne_checkpointer, stufe_des_laufs, wartende_laeufe, wartepunkt
from entwicklung.pfade import arbeit_dir, berichte_dir, projekt_dir

MODELLE = ["auto", "haiku", "sonnet", "opus"]  # bewusst ohne Fable; auto = Tabelle in stufen.py
STUFEN = {1: baue_graph_s1, 2: baue_graph_s2, 3: baue_graph_s3, 4: baue_graph_s4}
MIT_GEDAECHTNIS = {3, 4}  # ab hier kann der Lauf anhalten und braucht den Checkpointer
WARTET = 3  # Exit-Code: Lauf hält an einem Haltepunkt
BEFEHL = "python -m entwicklung fortsetzen"
ERLAUBT = {  # je Haltepunkt: was fortsetzen dort annimmt
    "fragen": f'{BEFEHL} --antwort "…"   (deine Antworten, alle in einem Text)\n'
              f"  {BEFEHL} --entscheidung abbrechen",
    "spec_freigabe": f"{BEFEHL} --entscheidung freigeben\n"
                     f'  {BEFEHL} --entscheidung aendern --hinweis "…"   (Spec neu, danach Tests neu)\n'
                     f'  {BEFEHL} --entscheidung tests_nachbessern --hinweis "…"   (Spec bleibt)\n'
                     f"  {BEFEHL} --entscheidung abbrechen",
    "plan_freigabe": f"{BEFEHL} --entscheidung freigeben   [--komplexitaet einfach|mittel|schwer]\n"
                     f'  {BEFEHL} --entscheidung aendern --hinweis "…"   (nur der Plan neu)\n'
                     f"  {BEFEHL} --entscheidung abbrechen",
    **{p: f"{BEFEHL} --entscheidung mehr       (Kostenrahmen um {BUDGET_SCHRITT} Aufrufe erhöhen)\n"
          f"  {BEFEHL} --entscheidung abbrechen" for p in (*BUDGET_PUNKTE, "budget")},
    "abschluss_freigabe": f"{BEFEHL} --entscheidung mergen        (lokaler Fast-Forward, Tests übernehmen, aufräumen)\n"
                          f"  {BEFEHL} --entscheidung nicht_mergen  (Branch und Worktree bleiben stehen)",
    "eskalation": f"{BEFEHL} --entscheidung weiter     (eine Fix-Runde mehr)\n"
                  f"  {BEFEHL} --entscheidung annehmen   (Stand so lassen)\n"
                  f"  {BEFEHL} --entscheidung abbrechen",
}


def _repo_pfad(angabe: str) -> Path:
    pfad = Path(angabe)
    if not pfad.is_dir():
        pfad = projekt_dir() / angabe
    if not (pfad / ".git").exists():
        raise SystemExit(f"Kein git-Repo: {pfad}")
    return pfad.resolve()


def _detail(knoten: str, update: dict) -> str:
    if knoten == "vorbereiten":
        return f"Worktree {Path(update['worktree']).name}"
    if knoten == "implementieren":
        a = update["agent"]
        return f"{'ok' if a['ok'] else 'Fehler: ' + str(a['fehler'])} · {a['dauer_s']} s · {a['turns']} Turns"
    if knoten == "grenzen_pruefen":
        return f"{len(update['geaenderte_dateien'])} Dateien, {len(update['grenzverletzungen'])} Verletzungen"
    if knoten == "tests_ausfuehren":
        return tests_zeile(update["testergebnis"])
    if knoten in PRUEFER_KNOTEN:  # nicht pruefen_spec_* (Stufe 4), die liefern spec_pruefungen
        return pruefer_zeile(update["pruefberichte"][0])
    if knoten == "befunde_sammeln":
        ausloesend = sum(b["ausloesend"] for b in update["befunde"])
        return (f"{len(update['befunde'])} Befunde, {ausloesend} auslösend · "
                f"Fix-Runde nötig: {'ja' if update['fix_noetig'] else 'nein'}")
    if knoten == "fix_runde":
        return f"Runde {update['runde']}: {len(update['fix_auftrag']['befunde'])} Befunde zurück an den Implementierer"
    if knoten == "eskalation":
        return f"Entscheidung: {update.get('entscheidung') or 'ungültig, frage erneut'}"
    if update.get("status") in ("grenzverletzung", "agent_fehler"):
        return f"{update['status']}: {update.get('planung_fehler') or '; '.join(update.get('grenzverletzungen', []))}"
    if knoten == "klaeren":
        return f"{len(update['offene_fragen'])} Fragen" if update["offene_fragen"] else "klar"
    if knoten == "fragen":
        return "abgebrochen" if update.get("status") else ("ungültig, frage erneut" if update.get("halt_hinweis")
                                                           else "Antwort erhalten")
    if knoten == "spec_schreiben":
        return f"Spec · {len(update['schnittstellen'])} Module · {len(update['annahmen'])} Annahmen"
    if knoten == "akzeptanz_schreiben":
        if update.get("akz_gruende"):
            return f"abgelehnt (Versuch {update['akz_versuch']}): {update['akz_gruende'][0]}"
        p = update["akz_probe"]
        return f"{p['erwartet']} Tests · {p['erwartet'] - p['bestanden']} von {p['erwartet']} rot gegen main"
    if knoten.startswith("pruefen_spec_"):
        s = update["spec_pruefungen"][0]
        return f"{s['verdict']} · {len(s['punkte'])} Punkte" if s["ok"] else f"nicht verwertbar ({s['fehler']})"
    if knoten == "spec_freigabe":
        return f"Freigabe: {update.get('freigabe') or 'ungültig, frage erneut'}"
    if knoten == "plan_schreiben":
        return f"Plan · {len(update['plan_dateien'])} Dateien · {len(update['plan_gruende'])} Gründe"
    if knoten == "plan_pruefen":
        s = update["plan_pruefungen"][0]
        return (f"codex: {s['verdict']} · {len(s['punkte'])} Punkte" if s["ok"]
                else f"codex: nicht verwertbar ({s['fehler']})")
    if knoten == "plan_freigabe":
        return f"Plan-Freigabe: {update.get('plan_freigabe') or 'ungültig, frage erneut'}"
    if knoten == "umsetzung_starten":
        return "Spec und Plan sind jetzt die Aufgabe"
    if knoten == "gesamtreview":
        return f"{gesamt_zeile(update.get('gesamtreview'))} · {tuer_zeile(update.get('tuer'))}"
    if knoten == "abschluss_freigabe":
        return f"Entscheidung: {update.get('abschluss_entscheidung') or 'ungültig, frage erneut'}"
    if knoten == "abschluss":
        return abschluss_zeile(update.get("abschluss"), update.get("status"))
    return ""


def _lauf_live(graph, eingabe, cfg: dict | None = None) -> dict:
    start, ergebnis = time.perf_counter(), {}
    for modus, daten in graph.stream(eingabe, cfg, stream_mode=["updates", "values"]):
        if modus == "values":
            ergebnis = dict(daten)
            continue
        for knoten, update in daten.items():
            if knoten == "__interrupt__":
                print(f"[{time.perf_counter() - start:6.1f} s] ⏸ wartet auf dich", flush=True)
                ergebnis["__interrupt__"] = update
                continue
            print(f"[{time.perf_counter() - start:6.1f} s] ✓ {knoten:<17} {_detail(knoten, update or {})}".rstrip(),
                  flush=True)
    return ergebnis


def _ausfuehren(graph, eingabe, cfg, live: bool) -> dict:
    ergebnis = _lauf_live(graph, eingabe, cfg) if live else dict(graph.invoke(eingabe, cfg))
    if cfg is not None:  # Endstand aus dem Checkpointer, dazu offene interrupts
        zustand = graph.get_state(cfg)
        ergebnis = {**zustand.values}
        offen = [i for aufgabe in zustand.tasks for i in aufgabe.interrupts]
        if offen:
            ergebnis["__interrupt__"] = offen
    return ergebnis


def _zeige_einwaende(frage: dict, einwaende: list[str] | None = None) -> None:
    einwaende = frage.get("einwaende") or [] if einwaende is None else einwaende
    if einwaende:
        print("  ⚠ Einwand der anderen Modellfamilie: freigeben nur mit --begruendung '<dein Grund>'")
        for e in einwaende:
            print(f"    {e}")


def _zeige_halt(ergebnis: dict, thread_id: str) -> int:
    frage = ergebnis["__interrupt__"][0].value
    art = frage.get("art", "eskalation")
    if art == "fragen":
        print(f"\n⏸ Lauf {thread_id} hat Rückfragen (Runde {frage['runde']} von höchstens {frage['max_runden']})")
        print(f"Verständnis: {frage['verstaendnis']}")
        for i, f in enumerate(frage["fragen"], 1):
            print(f"  {i}. {f}")
    elif art == "spec_freigabe":
        p = frage["probe"]
        print(f"\n⏸ Lauf {thread_id} wartet auf deine Freigabe der Spec (Fassung {frage['spec_runde'] + 1})")
        print(f"Spec: {frage['spec_pfad']}")
        print(f"Akzeptanztests: {frage['akz_ordner']}")
        print(f"  {', '.join(frage['tests'])}")
        print(f"  Probe: {p['erwartet'] - p['bestanden']} von {p['erwartet']} rot gegen main")
        for a in frage["annahmen"]:
            print(f"  Annahme: {a}")
        einordnung = frage.get("einordnung")
        if frage.get("nachpruefung") and einordnung:  # 6c: zwei Gruppen statt einer Liste
            for titel, gruppe in (("Lösen eine neue Runde aus:", "ausloesend"),
                                  ("Liste für dich (keine neue Runde nötig):", "liste")):
                print(f"  {titel}")
                for punkt in einordnung[gruppe] or [{"pruefer": "–", "schwere": "–", "herkunft": "–",
                                                    "aussage": "keine"}]:
                    print(f"    {punkt_zeile(punkt)}")
        else:
            for punkt in frage["pruefpunkte"]:
                print(f"  [{punkt['pruefer']}, {punkt['schwere']}] {punkt['aussage']}")
        for v in frage.get("verlauf") or []:
            print(f"  {verlauf_zeile(v)}")
        for n in frage["nicht_verwertbar"]:
            print(f"  Spec-Prüfer nicht verwertbar: {n}")
        _zeige_einwaende(frage)
    elif art == "plan_freigabe":
        print(f"\n⏸ Lauf {thread_id} wartet auf deine Freigabe des Plans (Fassung {frage['plan_runde'] + 1})")
        print(f"Plan: {frage['plan_pfad']}")
        print(f"  Dateien: {', '.join(frage['dateien']) or '–'}")
        for punkt in frage["pruefpunkte"]:
            print(f"  [{punkt['pruefer']}, {punkt['schwere']}] {punkt['aussage']}")
        for n in frage["nicht_verwertbar"]:
            print(f"  Plan-Prüfer nicht verwertbar: {n}")
        if frage.get("komplexitaet"):
            st = frage.get("stufen") or {}
            print(f"  Komplexität: {frage['komplexitaet']} (Claude: {frage.get('komplexitaet_claude') or '–'}, "
                  f"Codex: {frage.get('komplexitaet_codex') or '–'})"
                  + (f" · {frage['komplexitaet_hinweis']}" if frage.get("komplexitaet_hinweis") else ""))
            for rolle, s in st.items():
                print(f"    {rolle}: {s['modell']} · {s['effort']}")
        _zeige_einwaende(frage)
    elif art == "abschluss_freigabe":
        print(f"\n⏸ Lauf {thread_id} wartet auf deine Abschluss-Freigabe ({frage['status']})")
        print(f"  {frage['tuer_zeile']}")
        for fall in (frage.get("tuer") or {}).get("faelle") or []:
            print(f"    einseitig: {fall}")
        print(f"  {frage['tests_zeile']}  ({frage['tests']})")
        print(f"  {gesamt_zeile(frage.get('gesamtreview'))}")
        for punkt in ((frage.get("gesamtreview") or {}).get("daten") or {}).get("restpunkte") or []:
            print(f"    [{punkt['schwere']}] {punkt['aussage']}")
        print(f"  Branch {frage['branch']} → {frage.get('zielzweig') or '?'} (nur Fast-Forward)")
        for zeile in (frage.get("diffstat") or "").rstrip().splitlines():
            print(f"    {zeile.strip()}")
        offen = [b for b in frage.get("offene_befunde") or []]
        if offen:
            print(f"  Offene Befunde ({len(offen)}):")
            for b in offen[:10]:
                print(f"    {befund_zeile(b)}")
        print(f"  Akzeptanztests übernehmen nach: {frage['uebernahme_ziel']} (nicht committet)")
        _zeige_einwaende(frage)
    elif art == "budget":
        print(f"\n⏸ Lauf {thread_id}: Kostenrahmen erreicht ({frage['aufrufe']} von {frage['budget']} "
              f"Agentenaufrufen). Als Nächstes käme: {frage['naechster']}")
    else:
        print(f"\n⏸ Lauf {thread_id} wartet: {frage['frage']}")
        print(f"Runde {frage['runde']} von höchstens {frage['max_runden']} · Tests: {frage['tests']}")
        for b in frage["ausloesend"]:
            print(f"  {befund_zeile(b)}")
    if frage.get("hinweis"):
        print(f"Hinweis: {frage['hinweis']}")
    print(f"Worktree: {ergebnis.get('worktree')}")
    print(f"\nWeiter mit:\n  {ERLAUBT[art]}")
    return WARTET


def _abschluss(ergebnis: dict, thread_id: str | None) -> int:
    if "__interrupt__" in ergebnis:
        return _zeige_halt(ergebnis, thread_id)
    _zeigen(ergebnis)
    return 0 if ergebnis["status"] == "gruen" and not ergebnis.get("fix_noetig") else 1


def _zeigen(e: dict) -> None:
    print(f"\n{SYMBOL.get(e['status'], '')} {e['status']}  ·  Lauf {e['lauf_id']}  ·  {e['aufgabe_id']}")
    print(f"Tests: {tests_zeile(e.get('testergebnis'))}")
    print(f"Geändert: {', '.join(e.get('geaenderte_dateien') or []) or 'nichts'}")
    for v in e.get("grenzverletzungen") or []:
        print(f"⛔ {v}")
    if (e.get("agent") or {}).get("fehler"):
        print(f"Implementierer: {e['agent']['fehler']}")
    if e.get("planung_fehler"):
        print(f"Planung: {e['planung_fehler']}")
    for g in e.get("akz_gruende") or []:
        print(f"Akzeptanztests abgelehnt: {g}")
    if e.get("freigabe"):
        print(f"Spec-Freigabe: {e['freigabe']}")
    if e.get("plan_freigabe"):
        print(f"Plan-Freigabe: {e['plan_freigabe']}")
    if "fix_noetig" in e:
        for p in sorted(e.get("pruefberichte") or [], key=lambda p: p["pruefer"]):
            print(f"Prüfer {pruefer_zeile(p, e.get('nicht_verwertbar'))}")
        for b in e["befunde"]:
            if b["ausloesend"]:
                print(f"  {befund_zeile(b)}")
        print(f"Fix-Runde nötig: {'ja' if e['fix_noetig'] else 'nein'} "
              f"({len(e['befunde'])} Befunde, Details im Bericht)")
    for r in e.get("runden") or []:
        print(runden_zeile(r))
    if e.get("entscheidung"):
        print(f"Entscheidung an der Eskalation: {e['entscheidung']}")
    if e.get("abschluss"):
        print(abschluss_zeile(e["abschluss"], e.get("status")))
    print(f"Worktree: {e['worktree']}")
    print(f"Bericht: {e['bericht_pfad']}")


def _lauf(args, abh: Abhaengigkeiten | None) -> int:
    eingabe = {"repo": str(_repo_pfad(args.repo)), "aufgabe_id": args.aufgabe, "modell": args.modell,
               "pruefer_modell": args.pruefer_modell, "max_runden": args.max_runden, "budget": args.budget}
    cfg, thread_id = None, None
    if args.stufe in MIT_GEDAECHTNIS:
        cp = oeffne_checkpointer()
        graph = STUFEN[args.stufe](abh, checkpointer=cp)
        thread_id = freie_thread_id(cp, (abh or Abhaengigkeiten()).jetzt())
        # metadata landet in jedem Checkpoint: fortsetzen weiß so, mit welcher Stufe der Lauf begann.
        cfg = {"configurable": {"thread_id": thread_id}, "metadata": {"stufe": args.stufe}}
    else:
        graph = STUFEN[args.stufe](abh)
    if args.live:
        print(f"Lauf {args.aufgabe} mit {args.modell} (der Implementierer braucht einige Minuten) …"
              + (f"  [{thread_id}]" if thread_id else ""), flush=True)
    return _abschluss(_ausfuehren(graph, eingabe, cfg, args.live), thread_id)


def _graph_fuer(cp, abh: Abhaengigkeiten | None):
    """Liefert je Stufe den Graphen mit Checkpointer (einmal gebaut). Ein Lauf wird mit dem Graphen seiner Stufe
    gelesen und fortgesetzt."""
    gebaut: dict[int, object] = {}

    def graph_fuer(stufe: int):
        if stufe not in gebaut:
            gebaut[stufe] = STUFEN[stufe](abh, checkpointer=cp)
        return gebaut[stufe]
    return graph_fuer


def _fortsetzen(args, abh: Abhaengigkeiten | None) -> int:
    cp = oeffne_checkpointer()
    graph_fuer = _graph_fuer(cp, abh)
    wartend = wartende_laeufe(cp, graph_fuer)
    if not wartend:
        print("Kein Lauf wartet auf eine Entscheidung.")
        return 1
    thread_id = args.thread or wartend[0]
    if thread_id not in wartend:
        print(f"Lauf {thread_id} wartet nicht auf eine Entscheidung. Wartend: {', '.join(wartend)}")
        return 1
    stufe = stufe_des_laufs(cp, thread_id)
    graph = graph_fuer(stufe)
    punkt = wartepunkt(graph, thread_id)
    stand = graph.get_state({"configurable": {"thread_id": thread_id}}).config["configurable"].get("checkpoint_id")
    if (args.haltepunkt and args.haltepunkt != punkt) or (args.stand and args.stand != stand):
        print(f"Der Stand hat sich geändert: Lauf {thread_id} steht jetzt an „{punkt}“. Bitte neu ansehen "
              f"(oder neuen Rat holen).")
        return WARTET
    antwort = antwort_fuer(punkt, args.entscheidung, args.antwort, args.hinweis, args.begruendung,
                           args.komplexitaet)
    if antwort is None:  # passt nicht zum Haltepunkt: nichts schicken, sagen, was dort geht
        print(f"Lauf {thread_id} wartet an „{punkt}“. Dort erlaubt:\n  {ERLAUBT[punkt]}")
        return WARTET  # der Lauf wartet weiter
    einwaende = _einwaende_jetzt(graph, thread_id, punkt, stand)
    fehlt = einwand_fehlt(punkt, antwort, einwaende)
    if fehlt:  # vorher prüfen: nichts schicken, was der Graph ablehnen würde
        print(f"Lauf {thread_id} wartet an „{punkt}“: {fehlt}")
        _zeige_einwaende({}, einwaende)
        return WARTET
    if einwaende and antwort.get("entscheidung") in DURCHLASS:
        antwort["einwaende"] = einwaende
    cfg = {"configurable": {"thread_id": thread_id}, "metadata": {"stufe": stufe}}
    print(f"Lauf {thread_id} ({punkt}): {antwort.get('entscheidung') or 'Antwort'}", flush=True)
    return _abschluss(_ausfuehren(graph, Command(resume=antwort), cfg, args.live), thread_id)


def _einwaende_jetzt(graph, thread_id: str, punkt: str, stand: str | None) -> list[str]:
    """Codex-Prüfer und abgelegte Räte zum aktuellen Stand (dieselbe Regel wie im Leitstand)."""
    from entwicklung.berater import einwaende_fuer
    snap = graph.get_state({"configurable": {"thread_id": thread_id}})
    aufgabe = next((a for a in snap.tasks if a.name == punkt and a.interrupts), None)
    wert = aufgabe.interrupts[0].value if aufgabe is not None else {}
    return einwaende_fuer(punkt, wert if isinstance(wert, dict) else {}, berichte_dir() / snap.values["lauf_id"], stand)


def _wartende_worktrees() -> set[Path]:
    """Worktrees der Läufe, die an der Eskalation auf eine Entscheidung warten: Sie werden noch gebraucht."""
    cp = oeffne_checkpointer()
    graph_fuer = _graph_fuer(cp, None)
    return {Path(graph_fuer(stufe_des_laufs(cp, tid)).get_state({"configurable": {"thread_id": tid}})
                 .values["worktree"]).resolve()
            for tid in wartende_laeufe(cp, graph_fuer)}


def _aufraeumen(alle: bool) -> int:
    wartend = _wartende_worktrees()
    je_repo: dict[Path, list[tuple[str, Path]]] = {}
    for wt in sorted(p for p in arbeit_dir().iterdir() if (p / ".git").is_file()):
        gemeinsam = worktree._git(wt, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip()
        branch = worktree._git(wt, "branch", "--show-current").stdout.strip()
        je_repo.setdefault(Path(gemeinsam).parent, []).append((branch, wt))
    fehler = 0
    for repo, eintraege in je_repo.items():
        eintraege.sort()
        for branch, wt in (eintraege if alle else eintraege[:-1]):  # ohne --alle bleibt der jüngste stehen
            if wt.resolve() in wartend:
                print(f"behalten: {wt.name}: Lauf wartet auf eine Entscheidung (fortsetzen)")
                continue
            try:
                worktree.entfernen(repo, wt)
                print(f"entfernt: {wt.name} (Branch {branch} bleibt)")
            except worktree.WorktreeFehler as e:
                fehler += 1
                print(f"behalten: {wt.name}: {e}")
    return 1 if fehler else 0


def _ps(text: str) -> str:
    """Für PowerShell sicher quoten: in einfachen Anführungszeichen wirken $() und " nicht; ' wird verdoppelt."""
    return "'" + text.replace("'", "''") + "'"


def _befehl_fuer(antwort: dict, e: dict, thread_id: str) -> str:
    """Übernahme-Befehl, gebunden an Haltepunkt und Stand des Rats (fortsetzen prüft beides)."""
    teile = [BEFEHL]
    if "antwort" in antwort:
        teile.append(f"--antwort {_ps(antwort['antwort'])}")
    else:
        teile.append(f"--entscheidung {antwort['entscheidung']}")
        if antwort.get("hinweis"):
            teile.append(f"--hinweis {_ps(antwort['hinweis'])}")
    return " ".join(teile + [f"--thread {thread_id}", f"--haltepunkt {e['haltepunkt']}",
                             f"--stand {e['checkpoint_id']}"])


def _zeige_rat(e: dict) -> bool:
    """Gibt einen Rat aus; True, wenn er übernommen werden kann."""
    name = (e.get("wer") or "fable").capitalize()
    if e.get("fehler"):
        print(f"\n{name}: kein Rat: {e['fehler']}")
        return False
    rat = e["rat"]
    print(f"\n{name} empfiehlt: {rat['entscheidung']} (Sicherheit {rat['sicherheit']}) an {e['haltepunkt']}")
    print(rat["begruendung"])
    for p in rat["punkte"]:
        print(f"  [{p['einschaetzung']}] {p['aussage']} — {p['warum']}")
    if e["antwort"] is None:
        print(f"Nicht verwertbar: {e['grund']}")
        return False
    return True


def _rat(args, abh: Abhaengigkeiten | None) -> int:
    """Fable und/oder Astra beraten am Haltepunkt (blockiert 1–5 min). Abgeschickt wird nichts: Dominic entscheidet
    mit fortsetzen."""
    import threading

    from entwicklung.berater import BERATER, OHNE_RAT, kein_rat_text, vergleiche
    from entwicklung.leitstand.ausfuehrer import WartetNicht, _stand, rat_fuer_lauf
    cp = oeffne_checkpointer()
    graph_fuer = _graph_fuer(cp, abh)
    wartend = wartende_laeufe(cp, graph_fuer)
    thread_id = args.thread or (wartend[0] if wartend else None)
    if thread_id not in wartend:
        print("Kein Lauf wartet auf eine Entscheidung." if not wartend
              else f"Lauf {thread_id} wartet nicht. Wartend: {', '.join(wartend)}")
        return 1
    wer = list(BERATER) if args.wer == "beide" else [args.wer]
    graph = graph_fuer(stufe_des_laufs(cp, thread_id))
    _, punkt, stand = _stand(graph, thread_id)
    if punkt is None:
        print(f"Lauf {thread_id} wartet nicht mehr.")
        return 1
    if punkt in OHNE_RAT:
        print(kein_rat_text(punkt))
        return 1
    print(f"{' und '.join(w.capitalize() for w in wer)} beraten Lauf {thread_id} (1–5 min) …", flush=True)
    raete: dict[str, dict] = {}

    def hole(w: str) -> None:
        try:
            raete[w] = rat_fuer_lauf(abh or Abhaengigkeiten(), graph, thread_id, erwartet=(punkt, stand), wer=w)
        except WartetNicht:
            raete[w] = {"wer": w, "fehler": "Lauf wartet nicht mehr", "antwort": None}
        except Exception as e:  # ein Berater, der scheitert, ist eine Meldung
            raete[w] = {"wer": w, "fehler": f"{type(e).__name__}: {e}", "antwort": None}
    faeden = [threading.Thread(target=hole, args=(w,), daemon=True) for w in wer]
    for t in faeden:
        t.start()
    for t in faeden:
        t.join()
    brauchbar = [w for w in wer if _zeige_rat(raete[w])]
    if not brauchbar:
        return 1
    vergleich = vergleiche(punkt, raete.get("fable"), raete.get("astra"))
    gewaehlt = brauchbar[0]
    if vergleich:
        gewaehlt = vergleich["vorbelegt"]
        print("\n" + ("einig: beide empfehlen " + raete["fable"]["rat"]["entscheidung"] if vergleich["einig"] else
                      f"uneinig: Fable {raete['fable']['rat']['entscheidung']} · Astra "
                      f"{raete['astra']['rat']['entscheidung']}. Vorbelegt ist die vorsichtigere Empfehlung "
                      f"({gewaehlt.capitalize()})."))
    e = raete[gewaehlt]
    print(f"\nÜbernehmen (du entscheidest; der Befehl gilt nur für diesen Stand):\n  "
          f"{_befehl_fuer(e['antwort'], e, thread_id)}")
    einwaende = _einwaende_jetzt(graph, thread_id, punkt, stand)
    if einwaende and e["antwort"].get("entscheidung") in DURCHLASS:
        print("Freigeben trotz Einwand braucht --begruendung '<dein Grund>'.")
        _zeige_einwaende({}, einwaende)
    for w in brauchbar:
        print(f"Rat abgelegt: {raete[w]['datei']}")
    return 0


def _leitstand(args) -> int:
    """Startet den Leitstand-Server auf 127.0.0.1 mit einem frischen Token und öffnet den Browser."""
    import secrets
    import socket
    import threading
    import webbrowser

    import uvicorn

    from entwicklung.leitstand.server import baue_app, standard_port
    port = args.port or standard_port(projekt_dir() / "portwart" / "ports.toml") or 8790
    with socket.socket() as probe:  # belegt? Dann klar melden statt auf einen anderen Port auszuweichen
        try:
            probe.bind(("127.0.0.1", port))
        except OSError as e:
            print(f"Port {port} ist belegt ({e}). Läuft der Leitstand schon? Sonst mit --port anderen wählen.")
            return 2
    token = secrets.token_urlsafe(24)
    app = baue_app(None, oeffne_checkpointer(), token, port)
    url = f"http://127.0.0.1:{port}/?token={token}"
    print(f"Leitstand: {url}\n(Beenden mit Strg+C)", flush=True)
    if not args.kein_browser:
        threading.Timer(1.0, webbrowser.open, [url]).start()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
    return 0


def _demo(args) -> int:
    """Demo ohne Abo (entwicklung/demo.py): alles in einem neuen Temp-Ordner, nur Fake-Agenten."""
    import os
    import secrets
    import socket
    import threading
    import webbrowser

    from entwicklung import demo
    ziel = demo.temp_ordner()
    for name in ("DATA", "BERICHTE", "ARBEIT"):  # vor jedem Zugriff auf pfade: nichts im Projekt anlegen
        os.environ[f"ENTWICKLUNG_{name}_DIR"] = str(ziel / name.lower())
    print(f"Demo in {ziel} (Fake-Agenten, kein Abo nötig)", flush=True)
    if args.durchlauf:
        erg = demo.durchlauf(ziel, ausgabe=lambda z: print(z, flush=True))
        a = erg.get("abschluss") or {}
        print(f"\n{SYMBOL.get(erg['status'], '')} {erg['status']} · Aufgabe {demo.AUFGABE} · "
              f"{abschluss_zeile(a, erg.get('status'))}")
        print(f"Tests: {tests_zeile(erg.get('testergebnis'))}")
        print(f"Bericht: {erg.get('bericht_pfad')}")
        return 0 if erg["status"] == "gruen" and a.get("merge_commit") else 1
    import uvicorn

    from entwicklung.leitstand.server import baue_app
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", args.port))
        except OSError as e:
            print(f"Port {args.port} ist belegt ({e}). Mit --port einen anderen wählen.")
            return 2
    repo, aufgaben = demo.baue_umgebung(ziel)
    token = secrets.token_urlsafe(24)
    app = baue_app(demo.abhaengigkeiten(aufgaben, pause=1.5), oeffne_checkpointer(), token, args.port,
                   repos_dir=ziel, demo=True)
    tid = app.state.ausfuehrer.starte(str(repo), demo.AUFGABE)
    url = f"http://127.0.0.1:{args.port}/?token={token}#{tid}"
    print(f"Leitstand (Demo): {url}\nLauf {tid} startet; an den Haltepunkten entscheidest du im Browser."
          f"\n(Beenden mit Strg+C)", flush=True)
    if not args.kein_browser:
        threading.Timer(1.0, webbrowser.open, [url]).start()
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
    return 0


def main(argv=None, abh: Abhaengigkeiten | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m entwicklung", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="befehl", required=True)
    lauf = sub.add_parser("lauf", help="eine Aufgabe von der Pipeline umsetzen lassen")
    lauf.add_argument("--repo", required=True, help="Pfad oder Name unter langgraph-lab-2/")
    lauf.add_argument("--aufgabe", required=True, help="z. B. A1 (aus aufgaben/<repo>/A1.md)")
    lauf.add_argument("--stufe", type=int, choices=sorted(STUFEN), default=max(STUFEN))
    lauf.add_argument("--modell", choices=MODELLE, default="auto", help="Implementierer (auto: nach Komplexität)")
    lauf.add_argument("--budget", type=int, default=BUDGET, help=f"Kostenrahmen in Agentenaufrufen (Standard {BUDGET})")
    lauf.add_argument("--pruefer-modell", choices=MODELLE, default="auto",
                      help="Security und Clean Code (auto: nach Komplexität)")
    lauf.add_argument("--max-runden", type=int, choices=range(0, 6), default=MAX_RUNDEN, metavar="0-5",
                      help="Fix-Runden bis zur Eskalation (ab Stufe 3)")
    lauf.add_argument("--live", action="store_true", help="jeden fertigen Knoten sofort zeigen")
    fort = sub.add_parser("fortsetzen", help="angehaltenen Lauf mit deiner Entscheidung fortsetzen")
    fort.add_argument("--entscheidung", choices=sorted(set(ENTSCHEIDUNGEN) | set(FREIGABEN) | {"mehr"}
                                                       | set(ABSCHLUSS_ENTSCHEIDUNGEN)))
    fort.add_argument("--antwort", help="Antwort auf die Rückfragen (alle in einem Text)")
    fort.add_argument("--hinweis", help="mit aendern (Spec oder Plan) oder tests_nachbessern: was anders werden soll")
    fort.add_argument("--haltepunkt", help="nur fortsetzen, wenn der Lauf an diesem Haltepunkt steht")
    fort.add_argument("--stand", help="nur fortsetzen, wenn der Lauf noch diesen Stand (checkpoint_id) hat")
    fort.add_argument("--begruendung", help="freigeben/annehmen trotz Einwand: warum (landet im Bericht)")
    fort.add_argument("--komplexitaet", choices=["einfach", "mittel", "schwer"],
                      help="an der Plan-Freigabe: Komplexität ändern (Modell und Reasoning folgen der Tabelle)")
    fort.add_argument("--thread", help="welcher Lauf (Standard: der jüngste wartende)")
    fort.add_argument("--live", action="store_true")
    auf = sub.add_parser("aufraeumen", help="alte Worktrees entfernen")
    auf.add_argument("--alle", action="store_true", help="auch den jüngsten")
    rat = sub.add_parser("rat", help="Fable/Astra beraten am Haltepunkt (nur lesend, entscheiden musst du)")
    rat.add_argument("--thread", help="welcher Lauf (Standard: der jüngste wartende)")
    rat.add_argument("--wer", choices=["fable", "astra", "beide"], default="fable",
                     help="Fable (Claude), Astra (Codex, GPT-Familie) oder beide parallel")
    leit = sub.add_parser("leitstand", help="Leitstand im Browser (nur 127.0.0.1)")
    leit.add_argument("--port", type=int, help="Standard: Eintrag in portwart/ports.toml")
    leit.add_argument("--kein-browser", action="store_true")
    dem = sub.add_parser("demo", help="Demo ohne Abo: Fake-Agenten an examples/portwart (Temp-Ordner)")
    dem.add_argument("--durchlauf", action="store_true", help="ohne Browser bis zum Merge durchlaufen")
    dem.add_argument("--port", type=int, default=8795)
    dem.add_argument("--kein-browser", action="store_true")
    args = parser.parse_args(argv)
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    if args.befehl == "lauf":
        return _lauf(args, abh)
    if args.befehl == "fortsetzen":
        return _fortsetzen(args, abh)
    if args.befehl == "leitstand":
        return _leitstand(args)
    if args.befehl == "rat":
        return _rat(args, abh)
    if args.befehl == "demo":
        return _demo(args)
    return _aufraeumen(args.alle)
