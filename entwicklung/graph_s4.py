"""Stufe 4a: Planungsphase vor der Umsetzung (klären, Spec, Akzeptanztests aus der Spec, Freigabe).

    vorbereiten → klaeren ─┬→ fragen ⏸ ─→ klaeren                (Fragen offen, klaer_runde < MAX_KLAERUNGEN)
                           └→ spec_schreiben → akzeptanz_schreiben ↺ (abgelehnt: Gründe zurück, höchstens AKZ_VERSUCHE)
    → Send ×2: pruefen_spec_claude | pruefen_spec_codex → spec_pruefung_sammeln → spec_freigabe ⏸
         freigeben         → plan_schreiben → plan_pruefen (Codex) → plan_freigabe ⏸
         aendern           → spec_schreiben (Hinweis + Prüfpunkte)
         tests_nachbessern → akzeptanz_schreiben (Hinweis + vorige Fassung; Spec bleibt)
         abbrechen         → bericht
    plan_freigabe ⏸: freigeben → umsetzung_starten → implementieren → … (Stufe 3 unverändert; Aufgabe = Spec + Plan)
                     aendern   → plan_schreiben          abbrechen → bericht

Stufe 7 (Abschluss): grün oder an der Eskalation angenommen → budget_abschluss → gesamtreview (Codex) →
    abschluss_freigabe ⏸ → abschluss (mergen: lokaler Fast-Forward, Tests übernehmen, aufräumen;
    nicht_mergen: alles bleibt stehen) → bericht

Drei Haltepunkte in einem Lauf (fragen, spec_freigabe, eskalation), alle nach dem Muster aus Stufe 3: genau ein
interrupt je Durchlauf, bei ungültiger Antwort über eine Kante zu sich selbst zurück.
Alle Planungsagenten lesen nur und liefern JSON; die Dateien schreibt `planung.lege_ab` nach berichte/<lauf_id>/.
"""
import ast
import hashlib
import tempfile
from pathlib import Path

from langgraph.graph import START, StateGraph
from langgraph.types import Send, interrupt

from entwicklung import abschluss as ab
from entwicklung import worktree as wt_modul
from entwicklung.konvergenz import NACHPRUEF_SCHEMA, einordnen, nachpruef_text, nummeriert, verlauf_eintrag
from entwicklung.graph import (Abhaengigkeiten, _bausteine_s3, _geschuetzte, budget_knoten, gezaehlt, nach_budget,
                               umsetzung_s3, zaehle)
from entwicklung.bericht import tests_zeile, tuer_zeile
from entwicklung.pfade import berichte_dir, projekt_dir
from entwicklung.planung import (AKZEPTANZ_SCHEMA, KLAER_SCHEMA, PLAN_SCHEMA, SPEC_PRUEF_K_SCHEMA,
                                 SPEC_PRUEF_SCHEMA, SPEC_SCHEMA,
                                 akzeptanz_prompt, klaer_prompt, lege_ab, lege_plan_ab, plan_pruef_prompt, plan_prompt,
                                 pruefe_akzeptanz, pruefe_plan, spec_prompt, spec_pruef_prompt)
from entwicklung.state import LEEREN, EntwicklungState
from entwicklung.stufen import KOMPLEXITAETEN, PLANUNG_STUFEN, hoechste, stufe_im_lauf

MAX_KLAERUNGEN = 3
AKZ_VERSUCHE = 2
SPEC_PRUEFER = ("pruefen_spec_claude", "pruefen_spec_codex")
FREIGABEN = ("freigeben", "aendern", "tests_nachbessern", "abbrechen")  # an spec_freigabe
PLAN_FREIGABEN = ("freigeben", "aendern", "abbrechen")
MIT_HINWEIS = ("aendern", "tests_nachbessern")
ABSCHLUSS_ENTSCHEIDUNGEN = ab.ABSCHLUSS_ENTSCHEIDUNGEN  # an abschluss_freigabe (Stufe 7)
DURCHLASS = ("freigeben", "annehmen", "mergen")  # lassen etwas durch: trotz Einwand nur mit Begründung



def nach_spec_rahmen(state) -> str:
    """Hinter budget_spec: nach „Tests nachbessern“ nur die Tests neu, sonst die Spec (Codex 6b-2: Nachbessern lief
    am Kostenrahmen vorbei)."""
    return "akzeptanz_schreiben" if state.get("freigabe") == "tests_nachbessern" else "spec_schreiben"

def testnamen(dateien: list[dict]) -> list[str]:
    namen = []
    for d in dateien:
        namen += [k.name for k in ast.walk(ast.parse(d["inhalt"]))
                  if isinstance(k, (ast.FunctionDef, ast.AsyncFunctionDef)) and k.name.startswith("test_")]
    return namen


def pruefpunkte(spec_pruefungen: list[dict]) -> list[dict]:
    return [{"pruefer": p["pruefer"], **punkt} for p in spec_pruefungen or [] if p["ok"] for punkt in p["punkte"]]


def codex_einwaende(punkte: list[dict] | None, alte: list[dict] | None = None) -> list[str]:
    """Gegenstimme der anderen Modellfamilie: Spec, Tests und Plan schreibt die Claude-Familie, Codex ist GPT.

    Ab 6c auch alte Codex-Major, die Codex in der Nachprüfung nicht als gelöst meldet: Die Konvergenzregel steuert
    nur die Runden, die Sperre bleibt vollständig."""
    return ([f"Codex (GPT) meldet major: {p['aussage']}" for p in punkte or []
             if p.get("pruefer") == "codex" and p.get("schwere") == "major"]
            + [_alter_einwand(a) for a in alte or [] if a.get("pruefer") == "codex" and a.get("schwere") == "major"
               and (a.get("bewertet") or {}).get("codex") != "geloest"])


def _alter_einwand(alt: dict) -> str:
    status = (alt.get("bewertet") or {}).get("codex")
    if status is None:  # Codex fiel bei der Nachprüfung aus: nicht als gelöst bestätigt (Codex-Verifier 6c, V2)
        return f"Codex (GPT) hat major nicht nachgeprüft: {alt['aussage']}"
    return f"Codex (GPT) meldet major weiter {status}: {alt['aussage']}"


def ausloesende(state) -> list[dict]:
    """Was an den Spec-Schreiber geht. Läufe vor 6c haben keine Einordnung: dann alle Prüfpunkte wie bisher."""
    einordnung = state.get("spec_einordnung")
    return einordnung["ausloesend"] if einordnung else pruefpunkte(state.get("spec_pruefungen"))


def vorige_fassung(state) -> dict:
    """Stand, gegen den die nächste Prüfung nachprüft: Spec, Tests, die Punkte, die der Schreiber bekommt, und die
    Codex-Major von der Liste. Diese reisen nur für die Sperre mit, bis Codex sie als gelöst meldet (Verifier 6c, V1)."""
    felder = ("pruefer", "schwere", "aussage")
    sperre = [{**{k: p.get(k) for k in felder}, "nur_sperre": True}
              for p in (state.get("spec_einordnung") or {}).get("liste") or []
              if p.get("pruefer") == "codex" and p.get("schwere") == "major"]
    return {"spec": state.get("spec") or "", "tests": {d["name"]: d["inhalt"] for d in state.get("akz_dateien") or []},
            "punkte": nummeriert([{k: p.get(k) for k in felder} for p in ausloesende(state)] + sperre)}


def _einwand(antwort, punkt: str, entscheidung: str | None, eigene: list[str], state) -> tuple[str | None, dict]:
    """Prüft Freigeben trotz Einwand. (Fehlertext oder None, Update für einwand_freigaben)."""
    if not isinstance(antwort, dict) or entscheidung not in DURCHLASS:
        return None, {}
    mitgebracht = antwort.get("einwaende")
    if not (isinstance(mitgebracht, list) and all(isinstance(e, str) for e in mitgebracht)):
        mitgebracht = []  # nur list[str] zählt
    einwaende = list(dict.fromkeys([*eigene, *mitgebracht]))
    begruendung = antwort.get("begruendung")
    begruendung = begruendung.strip() if isinstance(begruendung, str) else ""
    if einwaende and not begruendung:  # eigene (Codex-Prüfer) und mitgebrachte (Räte, vom Server errechnet)
        return (f"{entscheidung} trotz Einwand braucht 'begruendung' (Text). Einwände: " + "; ".join(einwaende)), {}
    if not einwaende:
        return None, {}
    eintrag = {"haltepunkt": punkt, "entscheidung": entscheidung, "einwaende": einwaende, "begruendung": begruendung}
    return None, {"einwand_freigaben": (state.get("einwand_freigaben") or []) + [eintrag]}


def plan_punkte(state) -> list[dict]:
    """Gründe aus pruefe_plan (Code) und Punkte von Codex, in der Form der Spec-Prüfpunkte."""
    return ([{"pruefer": "code", "schwere": "major", "aussage": g} for g in state.get("plan_gruende") or []]
            + pruefpunkte(state.get("plan_pruefungen")))


def _freigabe_antwort(antwort, erlaubt: tuple) -> tuple[str | None, str | None]:
    """(entscheidung, hinweis) oder (None, None), wenn die Antwort nicht gilt."""
    entscheidung = antwort.get("entscheidung") if isinstance(antwort, dict) else None
    hinweis = antwort.get("hinweis") if isinstance(antwort, dict) else None
    if entscheidung not in erlaubt:
        return None, None
    if entscheidung in MIT_HINWEIS:
        if not (isinstance(hinweis, str) and hinweis.strip()):
            return None, None
        return entscheidung, hinweis.strip()
    return entscheidung, None


def hashes(ordner: Path) -> dict[str, str]:
    return {d.name: hashlib.sha256(d.read_bytes()).hexdigest() for d in sorted(ordner.glob("*.py"))}


def planung_sauber(abh: Abhaengigkeiten, state) -> list[str]:
    """Nachkontrolle nach jedem lesenden Agenten (Planung, Berater): Es darf sich nichts geändert haben."""
    repo, wt = Path(state["repo"]).resolve(), Path(state["worktree"])
    nachher = {name: abh.stand(p) for name, p in _geschuetzte(abh, repo).items()}
    return (wt_modul.grenzverletzungen(state["stand_vorher"], nachher)
            # alle Einträge, auch tests/_akzeptanz/ (geaenderte_dateien blendet ihn für den Testlauf aus)
            + [f"Worktree: {p} geändert (Planung darf nur lesen)" for _, p in wt_modul._status_eintraege(wt)]
            + [f"Worktree: {p} versteckt angelegt" for p in wt_modul.versteckte_dateien(wt)])


def _bausteine_s4(abh: Abhaengigkeiten):
    bausteine_s3 = _bausteine_s3(abh)
    vorbereiten_s3, tests_ausfuehren_s3 = bausteine_s3[0], bausteine_s3[4]

    def _sauber(state) -> list[str]:
        return planung_sauber(abh, state)

    def _agent(state, name: str, prompt: str, schema: dict, codex: bool = False) -> tuple[dict | None, dict]:
        """Ruft einen Planungsagenten und kontrolliert danach. Gibt (daten, Status-Update bei Fehler) zurück."""
        wt = Path(state["worktree"])
        zaehle()
        try:
            # Vor der Schätzung feste Stufen (stufen.PLANUNG_STUFEN), unabhängig von der Startwahl der Prüfer
            erg = (abh.planer_codex(name, prompt, wt, schema, effort=PLANUNG_STUFEN["codex"][1]) if codex
                   else abh.planer(name, prompt, wt, schema, modell=PLANUNG_STUFEN["planer"][0],
                                   effort=PLANUNG_STUFEN["planer"][1]))
        except Exception as e:  # ein Agent ist ein Befund, kein Absturz des Graphen
            erg = {"ok": False, "daten": None, "fehler": f"{type(e).__name__}: {e}"}
        verletzungen = _sauber(state)
        if verletzungen:
            return None, {"status": "grenzverletzung", "grenzverletzungen": verletzungen}
        if not erg["ok"]:
            return None, {"status": "agent_fehler", "planung_fehler": f"{name}: {erg['fehler']}"}
        return erg["daten"], {}

    def vorbereiten(state: EntwicklungState) -> dict:
        update = vorbereiten_s3(state)
        eigener = state["aufgabe_id"]  # Regression nur über die früheren Aufgaben; die eigenen Tests entstehen hier
        return {**update, "zielzweig": wt_modul.zweig(Path(state["repo"]).resolve()),  # Stufe 7: Merge nur dorthin
                "wunsch": update["aufgabe_text"], "klaer_runde": 0, "spec_runde": 0, "akz_versuch": 0,
                "plan_runde": 0, "akz_hinweis": None,
                "akz_gruende": [], "spec_aenderung": None, "offene_fragen": [], "halt_hinweis": "",
                "akzeptanz_dirs": [d for d in update["akzeptanz_dirs"] if Path(d).name != eigener]}

    def klaeren(state: EntwicklungState) -> dict:
        prompt = klaer_prompt(state["wunsch"], state.get("klaerung") or [], state["klaer_runde"] + 1, MAX_KLAERUNGEN)
        daten, fehler = _agent(state, "klaeren", prompt, KLAER_SCHEMA)
        if fehler:
            return fehler
        fragen = [] if daten["klar"] else [f for f in daten["fragen"] if f.strip()]
        return {"verstaendnis": daten["verstaendnis"], "offene_fragen": fragen}

    def nach_klaeren(state: EntwicklungState) -> str:
        if state.get("status"):
            return "bericht"
        return "fragen" if state["offene_fragen"] and state["klaer_runde"] < MAX_KLAERUNGEN else "budget_spec"

    def fragen(state: EntwicklungState) -> dict:
        antwort = interrupt({"art": "fragen", "fragen": state["offene_fragen"], "verstaendnis": state["verstaendnis"],
                             "runde": state["klaer_runde"] + 1, "max_runden": MAX_KLAERUNGEN,
                             "hinweis": state.get("halt_hinweis") or ""})
        if isinstance(antwort, dict) and antwort.get("entscheidung") == "abbrechen":
            return {"status": "abgebrochen", "halt_hinweis": ""}
        text = antwort.get("antwort") if isinstance(antwort, dict) else None
        if not isinstance(text, str) or not text.strip():
            return {"halt_hinweis": f"ungültige Antwort {antwort!r}, erlaubt: {{'antwort': '<Text>'}} "
                                    f"oder {{'entscheidung': 'abbrechen'}}"}
        return {"klaerung": [{"fragen": state["offene_fragen"], "antwort": text.strip()}],
                "klaer_runde": state["klaer_runde"] + 1, "offene_fragen": [], "halt_hinweis": ""}

    def nach_fragen(state: EntwicklungState) -> str:
        if state.get("status"):
            return "bericht"
        return "fragen" if state.get("halt_hinweis") else "klaeren"

    def spec_schreiben(state: EntwicklungState) -> dict:
        neu = state["spec_runde"] > 0
        prompt = spec_prompt(state["wunsch"], state.get("klaerung") or [],
                             state.get("spec_aenderung") if neu else None, state.get("spec") if neu else None,
                             ausloesende(state) if neu else [])
        daten, fehler = _agent(state, "spec_schreiben", prompt, SPEC_SCHEMA)
        if fehler:
            return fehler
        k = daten.get("komplexitaet")
        return {"vorige_fassung": vorige_fassung(state) if neu else None, "spec": daten["spec"], "schnittstellen": daten["schnittstellen"], "annahmen": daten["annahmen"],
                "komplexitaet_claude": k if k in KOMPLEXITAETEN else None,
                "komplexitaet_grund": str(daten.get("komplexitaet_grund") or ""),
                "akz_versuch": 0, "akz_gruende": [], "spec_pruefungen": LEEREN,
                "akz_dateien": [], "akz_ordner": None, "akz_probe": None,  # gehörten zur vorigen Fassung
                "akz_hinweis": None}

    def akzeptanz_schreiben(state: EntwicklungState) -> dict:
        hinweis = state.get("akz_hinweis")  # tests_nachbessern: verbessern statt neu schreiben
        vorige = {d["name"]: d["inhalt"] for d in state.get("akz_dateien") or []} if hinweis else None
        prompt = akzeptanz_prompt(state["spec"], state["schnittstellen"], state["aufgabe_id"], state["akz_gruende"],
                                  vorige=vorige, hinweis=hinweis)
        daten, fehler = _agent(state, "akzeptanz_schreiben", prompt, AKZEPTANZ_SCHEMA)
        if fehler:
            return fehler
        dateien = daten["dateien"]
        gruende = pruefe_akzeptanz(dateien, state["schnittstellen"], state["aufgabe_id"])
        update = {}
        if not gruende:
            ordner = lege_ab(berichte_dir() / state["lauf_id"], state["spec"], dateien, state["aufgabe_id"])
            # Probe gegen main in einer Kopie (nicht im Worktree): Was der erzeugte Testcode dort schreibt, sieht
            # der Implementierer nie. Die Tests müssen sammelbar sein und mindestens einer rot.
            with tempfile.TemporaryDirectory(prefix="lab2-probe-") as tmp:
                kopie = wt_modul.exportiere(Path(state["worktree"]), Path(tmp) / "main")
                probe = abh.tests(kopie, state["konfig"], [ordner])["akzeptanz"]
            verletzungen = _sauber(state)
            if verletzungen:
                return {"status": "grenzverletzung", "grenzverletzungen": verletzungen}
            if not probe["erwartet"] or probe["gesammelt"] != probe["erwartet"]:
                gruende = [f"Probe: Tests nicht sammelbar (erwartet {probe['erwartet']}, "
                           f"gesammelt {probe['gesammelt']})"]
            elif probe.get("fehler"):
                gruende = [f"Probe: {probe['fehler']} Test(s) mit Fehler statt Fehlschlag (Fixture, Setup): so ein "
                           f"Test läuft nie bis zu seinem assert und kann auch nach der Umsetzung nicht grün werden"]
            elif probe.get("uebersprungen"):
                gruende = [f"Probe: {probe['uebersprungen']} Test(s) werden auf diesem Rechner übersprungen "
                           f"(pytest.skip/skipif). Ein übersprungener Test prüft nichts: das Verhalten simulieren "
                           f"(z. B. monkeypatch) statt überspringen"]
            elif probe["bestanden"] >= probe["erwartet"]:
                gruende = [f"Probe: alle {probe['erwartet']} Tests bestehen schon gegen main, sie prüfen nichts Neues"]
            update = {"akz_dateien": dateien, "akz_ordner": str(ordner),
                      "akz_probe": {"erwartet": probe["erwartet"], "gesammelt": probe["gesammelt"],
                                    "bestanden": probe["bestanden"], "uebersprungen": probe.get("uebersprungen", 0),
                                    "fehler": probe.get("fehler", 0)}}
        if gruende:
            versuch = state["akz_versuch"] + 1
            update.update({"akz_versuch": versuch, "akz_gruende": gruende})
            if versuch >= AKZ_VERSUCHE:
                update["status"] = "akzeptanz_fehler"
            return update
        return {**update, "akz_gruende": []}

    def nach_akzeptanz(state: EntwicklungState):
        if state.get("status"):
            return "bericht"
        if state["akz_gruende"]:
            return "akzeptanz_schreiben"
        tests = {d["name"]: d["inhalt"] for d in state["akz_dateien"]}
        prompt = spec_pruef_prompt(state["wunsch"], state.get("klaerung") or [], state["spec"], tests)
        vorige = state.get("vorige_fassung")
        if vorige:  # 6c: Nachprüfung gegen die Vorfassung statt Prüfung von null
            prompt += "\n" + nachpruef_text(vorige, state["spec"], tests)
        auftrag = {"prompt": prompt, "worktree": state["worktree"], "nachpruefung": bool(vorige)}
        return [Send(k, auftrag) for k in SPEC_PRUEFER]

    def _spec_pruefung(name: str, codex: bool):
        def knoten(auftrag: dict) -> dict:  # auftrag: dict, sonst filtert LangGraph nach dem State-Typ
            wt = Path(auftrag["worktree"])
            schema = NACHPRUEF_SCHEMA if auftrag.get("nachpruefung") else SPEC_PRUEF_K_SCHEMA
            zaehle()
            try:
                erg = (abh.planer_codex(f"spec_{name}", auftrag["prompt"], wt, schema,
                                        effort=PLANUNG_STUFEN["codex"][1]) if codex
                       else abh.planer("spec_pruefer", auftrag["prompt"], wt, schema,
                                       modell=PLANUNG_STUFEN["spec_pruefer"][0],
                                       effort=PLANUNG_STUFEN["spec_pruefer"][1]))
            except Exception as e:
                erg = {"ok": False, "daten": None, "fehler": f"{type(e).__name__}: {e}"}
            daten = erg.get("daten") or {}
            k = daten.get("komplexitaet")
            return {"spec_pruefungen": [{"pruefer": name, "ok": erg["ok"], "verdict": daten.get("verdict"),
                                         "punkte": daten.get("punkte", []), "fehler": erg.get("fehler"),
                                         "alte_punkte": daten.get("alte_punkte", []),
                                         "komplexitaet": k if k in KOMPLEXITAETEN else None}]}
        return knoten

    def spec_pruefung_sammeln(state: EntwicklungState) -> dict:
        verletzungen = _sauber(state)  # Fan-in: einmal nach beiden Prüfern
        if verletzungen:
            return {"status": "grenzverletzung", "grenzverletzungen": verletzungen}
        # 6c: Einordnung hier und nicht in spec_freigabe: Dieser Knoten läuft je Prüfung genau einmal, das interrupt
        # dort bei jeder ungültigen Antwort erneut (doppelte Verlaufszeilen).
        vorige = state.get("vorige_fassung")
        einordnung = einordnen(state.get("spec_pruefungen"), vorige["punkte"] if vorige else None)
        zeile = verlauf_eintrag(state["spec_runde"], state.get("freigabe") == "tests_nachbessern", state["spec"],
                                state.get("annahmen") or [], testnamen(state["akz_dateien"]), einordnung)
        return {"spec_einordnung": einordnung, "spec_verlauf": [zeile]}

    def nach_spec_pruefung(state: EntwicklungState) -> str:
        return "bericht" if state.get("status") else "spec_freigabe"

    def spec_freigabe(state: EntwicklungState) -> dict:
        ordner = Path(state["akz_ordner"])
        punkte = pruefpunkte(state.get("spec_pruefungen"))
        einordnung = state.get("spec_einordnung") or {}
        einwaende = codex_einwaende(punkte, einordnung.get("alte"))
        antwort = interrupt({"art": "spec_freigabe", "spec_pfad": str(ordner.parent.parent / "spec.md"),
                             "akz_ordner": str(ordner), "annahmen": state["annahmen"],
                             "tests": testnamen(state["akz_dateien"]), "probe": state["akz_probe"],
                             "pruefpunkte": punkte, "einwaende": einwaende,
                             "nicht_verwertbar": [f"{p['pruefer']}: {p['fehler']}"
                                                  for p in state.get("spec_pruefungen") or [] if not p["ok"]],
                             "spec_runde": state["spec_runde"], "erlaubt": list(FREIGABEN),
                             "nachpruefung": bool(state.get("vorige_fassung")), "einordnung": einordnung,
                             "verlauf": state.get("spec_verlauf") or [],
                             "hinweis": state.get("halt_hinweis") or ""})
        entscheidung, hinweis = _freigabe_antwort(antwort, FREIGABEN)
        if entscheidung is None:
            return {"freigabe": None,
                    "halt_hinweis": f"ungültige Antwort {antwort!r}, erlaubt: {{'entscheidung': 'freigeben' | "
                                    f"'abbrechen'}} oder {{'entscheidung': 'aendern' | 'tests_nachbessern', "
                                    f"'hinweis': '<Text>'}}"}
        fehlt, update = _einwand(antwort, "spec_freigabe", entscheidung, einwaende, state)
        if fehlt:  # wie eine ungültige Antwort: zurück in denselben Knoten, kein zweites interrupt
            return {"freigabe": None, "halt_hinweis": fehlt}
        update.update({"freigabe": entscheidung, "halt_hinweis": ""})
        if entscheidung == "aendern":
            update.update({"spec_aenderung": hinweis, "spec_runde": state["spec_runde"] + 1})
        elif entscheidung == "tests_nachbessern":  # Spec bleibt; Tests neu mit Hinweis, Prüfung neu
            update.update({"akz_hinweis": hinweis, "akz_versuch": 0, "akz_gruende": [], "spec_pruefungen": LEEREN,
                           "vorige_fassung": vorige_fassung(state)})
        elif entscheidung == "abbrechen":
            update["status"] = "abgebrochen"
        return update

    def stufe_waehlen(state: EntwicklungState) -> dict:
        """Router (6b-2): Beide Familien schätzen, es gilt die höhere Schätzung (die vorsichtigere Wahl)."""
        claude = state.get("komplexitaet_claude")
        codex = next((p.get("komplexitaet") for p in state.get("spec_pruefungen") or []
                      if p["pruefer"] == "codex" and p["ok"]), None)
        hinweis = ""
        if codex is None:
            hinweis = ("Codex hat nicht geschätzt (Prüfung gescheitert oder ohne Wert); es gilt Claudes Schätzung."
                       if claude else "Keine Schätzung vorhanden; es gilt mittel.")
        k = hoechste(claude, codex)
        return {"komplexitaet": k, "komplexitaet_vorschlag": k, "komplexitaet_codex": codex,
                "komplexitaet_hinweis": hinweis}

    def nach_freigabe(state: EntwicklungState) -> str:
        return {None: "spec_freigabe", "freigeben": "stufe_waehlen", "aendern": "budget_spec",
                "tests_nachbessern": "budget_spec", "abbrechen": "bericht"}[state.get("freigabe")]

    def plan_schreiben(state: EntwicklungState) -> dict:
        neu = (state.get("plan_runde") or 0) > 0  # Läufe aus Stufe 4a kennen plan_runde nicht
        prompt = plan_prompt(state["spec"], state["schnittstellen"], state.get("plan_aenderung") if neu else None,
                             state.get("plan") if neu else None, plan_punkte(state) if neu else [])
        daten, fehler = _agent(state, "plan_schreiben", prompt, PLAN_SCHEMA)
        if fehler:
            return fehler
        lege_plan_ab(berichte_dir() / state["lauf_id"], daten["plan"])
        return {"plan": daten["plan"], "plan_dateien": daten["dateien"], "plan_pruefungen": LEEREN,
                "plan_gruende": pruefe_plan(daten["plan"], daten["dateien"], state["schnittstellen"])}

    def plan_pruefen(state: EntwicklungState) -> dict:
        """Codex prüft den Plan gegen die Spec. Scheitert Codex, blockiert das nicht: Dominic sieht es."""
        prompt = plan_pruef_prompt(state["spec"], state["plan"], state["plan_dateien"])
        daten, fehler = _agent(state, "plan_codex", prompt, SPEC_PRUEF_SCHEMA, codex=True)
        if fehler.get("status") == "grenzverletzung":
            return fehler
        if fehler:
            return {"plan_pruefungen": [{"pruefer": "codex", "ok": False, "verdict": None, "punkte": [],
                                         "fehler": fehler.get("planung_fehler")}]}
        return {"plan_pruefungen": [{"pruefer": "codex", "ok": True, "verdict": daten["verdict"],
                                     "punkte": daten["punkte"], "fehler": None}]}

    def plan_freigabe(state: EntwicklungState) -> dict:
        punkte = plan_punkte(state)
        einwaende = codex_einwaende(punkte)
        k = state.get("komplexitaet") or "mittel"  # Läufe ohne Router (vor 6b-2): mittel
        antwort = interrupt({"art": "plan_freigabe", "plan_pfad": str(berichte_dir() / state["lauf_id"] / "plan.md"),
                             "dateien": state["plan_dateien"], "pruefpunkte": punkte, "einwaende": einwaende,
                             "komplexitaet": k, "komplexitaet_claude": state.get("komplexitaet_claude"),
                             "komplexitaet_codex": state.get("komplexitaet_codex"),
                             "komplexitaet_grund": state.get("komplexitaet_grund") or "",
                             "komplexitaet_hinweis": state.get("komplexitaet_hinweis") or "",
                             "komplexitaeten": list(KOMPLEXITAETEN),
                             "stufen": {r: stufe_im_lauf({**state, "komplexitaet": k}, r)
                                        for r in ("implementierer", "pruefer")},
                             "tabelle": {s: {r: stufe_im_lauf({**state, "komplexitaet": s}, r)
                                             for r in ("implementierer", "pruefer")} for s in KOMPLEXITAETEN},
                             "nicht_verwertbar": [f"{p['pruefer']}: {p['fehler']}"
                                                  for p in state.get("plan_pruefungen") or [] if not p["ok"]],
                             "plan_runde": state.get("plan_runde") or 0, "erlaubt": list(PLAN_FREIGABEN),
                             "hinweis": state.get("halt_hinweis") or ""})
        entscheidung, hinweis = _freigabe_antwort(antwort, PLAN_FREIGABEN)
        if entscheidung is None:
            return {"plan_freigabe": None,
                    "halt_hinweis": f"ungültige Antwort {antwort!r}, erlaubt: {{'entscheidung': 'freigeben' | "
                                    f"'abbrechen'}} oder {{'entscheidung': 'aendern', 'hinweis': '<Text>'}}"}
        fehlt, update = _einwand(antwort, "plan_freigabe", entscheidung, einwaende, state)
        if fehlt:
            return {"plan_freigabe": None, "halt_hinweis": fehlt}
        if entscheidung == "freigeben" and "komplexitaet" in antwort:  # Dominic ändert die Stufe (einziger Regler)
            if antwort["komplexitaet"] not in KOMPLEXITAETEN:
                return {"plan_freigabe": None,
                        "halt_hinweis": f"ungültige komplexitaet {antwort['komplexitaet']!r}, erlaubt: "
                                        f"{' | '.join(KOMPLEXITAETEN)}"}
            update["komplexitaet"] = antwort["komplexitaet"]
        update.update({"plan_freigabe": entscheidung, "halt_hinweis": ""})
        if entscheidung == "aendern":
            update.update({"plan_aenderung": hinweis, "plan_runde": (state.get("plan_runde") or 0) + 1})
        elif entscheidung == "abbrechen":
            update["status"] = "abgebrochen"
        return update

    def nach_plan_freigabe(state: EntwicklungState) -> str:
        return {None: "plan_freigabe", "freigeben": "umsetzung_starten", "aendern": "budget_plan",
                "abbrechen": "bericht"}[state.get("plan_freigabe")]

    def umsetzung_starten(state: EntwicklungState) -> dict:
        """Ab hier sind Spec und Plan die Aufgabe, und die erzeugten Tests sind ihre Akzeptanztests."""
        return {"aufgabe_text": f"{state['spec']}\n\n## Plan\n\n{state['plan']}",
                "akzeptanz_dirs": [*state["akzeptanz_dirs"], state["akz_ordner"]],
                "runde": 0, "status": None, "akz_hashes": hashes(Path(state["akz_ordner"]))}

    def _abweichungen(state) -> list[str]:
        jetzt = hashes(Path(state["akz_ordner"]))
        namen = sorted(n for n in set(jetzt) | set(state["akz_hashes"]) if jetzt.get(n) != state["akz_hashes"].get(n))
        return [f"berichte: {n} weicht von der freigegebenen Fassung ab" for n in namen]

    def tests_ausfuehren(state: EntwicklungState) -> dict:
        """Vor und nach jedem Testlauf: Sind die erzeugten Tests noch die freigegebenen? Sie liegen unter berichte/
        (git-ignoriert, also nicht in der Nachkontrolle). Die eigenen Tests des Implementierers laufen vor den
        Akzeptanztests und könnten sie ersetzen, bevor sie kopiert werden (Codex-Review Export F1)."""
        vorher = _abweichungen(state)
        if vorher:
            return {"status": "grenzverletzung", "grenzverletzungen": [*state.get("grenzverletzungen", []), *vorher]}
        update = tests_ausfuehren_s3(state)
        nachher = _abweichungen(state)
        if nachher:
            update.update(status="grenzverletzung", grenzverletzungen=[
                *(update.get("grenzverletzungen") or state.get("grenzverletzungen", [])),
                *[f"Testlauf: {v}" for v in nachher]])
        return update


    # ------------------------------------------------------------------------------------------ Stufe 7: Abschluss
    aufgaben_dir = abh.aufgaben_dir or projekt_dir() / "aufgaben"

    def _uebernahme_ziel(state) -> Path:
        return aufgaben_dir / Path(state["repo"]).resolve().name / state["aufgabe_id"]

    def gesamtreview(state: EntwicklungState) -> dict:
        """Codex (GPT) urteilt über das Ganze: Spec, Plan, Diff, letzte Befunde, Tests, Tür. Scheitert Codex, ist
        das kein Abbruch, sondern ein Einwand an der Freigabe („Gesamtreview fehlt“)."""
        wt = Path(state["worktree"])
        geprueft = wt_modul.kopf(wt)  # vor dem Agenten: genau dieser Stand steht im Prompt (Codex-Review Export F3)
        diff = wt_modul.diff(wt, state["basis"], geprueft)
        selbst = ab.tuer_selbst(diff, wt_modul.name_status(wt, state["basis"]))
        zaehle()
        try:
            erg = abh.planer_codex("gesamtreview", ab.gesamt_prompt(state, diff, selbst), wt, ab.GESAMT_SCHEMA,
                                   effort=PLANUNG_STUFEN["codex"][1])
        except Exception as e:
            erg = {"ok": False, "daten": None, "fehler": f"{type(e).__name__}: {e}"}
        verletzungen = _sauber(state)
        if verletzungen:
            return {"status": "grenzverletzung", "grenzverletzungen": verletzungen}
        gesamt = {"ok": bool(erg["ok"]), "daten": erg.get("daten") if erg["ok"] else None,
                  "fehler": erg.get("fehler")}
        return {"gesamtreview": gesamt, "tuer": ab.tuer_endgueltig(selbst, gesamt["daten"]),
                "geprueft_kopf": geprueft, "abschluss_hinweis": ""}  # gemergt wird genau dieser Commit

    def abschluss_freigabe(state: EntwicklungState) -> dict:
        """Letzter Haltepunkt. Erst die Antwort hier löst den einzigen Seiteneffekt außerhalb des Worktrees aus."""
        wt = Path(state["worktree"])
        t = state.get("testergebnis") or {}
        einwaende = ab.einwaende(state.get("gesamtreview"), state.get("tuer"), state.get("testergebnis"))
        antwort = interrupt({"art": "abschluss_freigabe", "branch": f"lauf/{state['lauf_id']}",
                             "zielzweig": state.get("zielzweig") or "", "status": state.get("status"),
                             "diffstat": wt_modul.diffstat(wt, state["basis"]),
                             "tests": tests_zeile(state.get("testergebnis")),
                             "tests_zeile": f"Tests: {t.get('bestanden', 0)} bestanden · "
                                            f"{t.get('uebersprungen', 0)} übersprungen",
                             "gesamtreview": state.get("gesamtreview"), "tuer": state.get("tuer"),
                             "tuer_zeile": tuer_zeile(state.get("tuer")), "einwaende": einwaende,
                             "offene_befunde": state.get("befunde") or [],
                             "uebernahme_ziel": str(_uebernahme_ziel(state)),
                             "erlaubt": list(ABSCHLUSS_ENTSCHEIDUNGEN),
                             "hinweis": state.get("abschluss_hinweis") or ""})
        entscheidung = antwort.get("entscheidung") if isinstance(antwort, dict) else None
        if entscheidung not in ABSCHLUSS_ENTSCHEIDUNGEN:
            erlaubt = " | ".join(ABSCHLUSS_ENTSCHEIDUNGEN)
            return {"abschluss_entscheidung": None,
                    "abschluss_hinweis": f"ungültige Antwort {antwort!r}, erlaubt: {{'entscheidung': {erlaubt}}}"}
        fehlt, update = _einwand(antwort, "abschluss_freigabe", entscheidung, einwaende, state)
        if fehlt:  # wie eine ungültige Antwort: zurück in denselben Knoten, kein zweites interrupt
            return {"abschluss_entscheidung": None, "abschluss_hinweis": fehlt}
        return {**update, "abschluss_entscheidung": entscheidung, "abschluss_hinweis": ""}

    def nach_abschluss_freigabe(state: EntwicklungState) -> str:
        return "abschluss" if state.get("abschluss_entscheidung") else "abschluss_freigabe"

    def abschluss(state: EntwicklungState) -> dict:
        """mergen: Fast-Forward nur, wenn das Ziel-Repo noch wie beim Start dasteht; dann Tests übernehmen (nie
        überschreiben, nicht committen) und Worktree und Branch abbauen. Was scheitert, bleibt stehen."""
        ergebnis = {"entscheidung": state["abschluss_entscheidung"], "merge_commit": None, "uebernommen": [],
                    "aufgeraeumt": False, "grund": ""}
        if ergebnis["entscheidung"] != "mergen":
            return {"abschluss": {**ergebnis, "grund": "nicht gemergt (Entscheidung)"}}
        repo, wt = Path(state["repo"]).resolve(), Path(state["worktree"])
        branch = f"lauf/{state['lauf_id']}"
        if not state.get("geprueft_kopf"):  # fehlender Prüfanker heißt nein, nicht „nichts zu prüfen“
            return {"status": "merge_abgelehnt",
                    "abschluss": {**ergebnis, "grund": "geprüfter Stand unbekannt (kein geprueft_kopf), kein Merge"}}
        try:
            ergebnis["merge_commit"] = wt_modul.merge_ff(repo, branch, state["basis"], state.get("zielzweig") or "",
                                                         erwartet=state.get("geprueft_kopf"))
        except wt_modul.WorktreeFehler as e:
            return {"status": "merge_abgelehnt", "abschluss": {**ergebnis, "grund": str(e)}}
        gruende = []
        if state.get("akz_ordner"):
            try:
                ergebnis["uebernommen"] = [str(p) for p in ab.uebernimm_tests(Path(state["akz_ordner"]),
                                                                              _uebernahme_ziel(state))]
            except OSError as e:  # FileExistsError, aber auch Rechte oder voller Datenträger (Verifier S7-02)
                gruende.append(f"Akzeptanztests nicht übernommen: {e}")
        try:
            wt_modul.entfernen(repo, wt)
            wt_modul.branch_loeschen(repo, branch)
            ergebnis["aufgeraeumt"] = True
        except wt_modul.WorktreeFehler as e:
            gruende.append(f"Aufräumen unvollständig: {e}")
        return {"abschluss": {**ergebnis, "grund": "; ".join(gruende)}}

    planung = {"vorbereiten": vorbereiten, "klaeren": klaeren, "fragen": fragen, "spec_schreiben": spec_schreiben,
               "akzeptanz_schreiben": akzeptanz_schreiben, "pruefen_spec_claude": _spec_pruefung("claude", False),
               "stufe_waehlen": stufe_waehlen, "budget_spec": budget_knoten(nach_spec_rahmen),
               "budget_plan": budget_knoten("plan_schreiben"),
               "pruefen_spec_codex": _spec_pruefung("codex", True), "spec_pruefung_sammeln": spec_pruefung_sammeln,
               "spec_freigabe": spec_freigabe, "plan_schreiben": plan_schreiben, "plan_pruefen": plan_pruefen,
               "plan_freigabe": plan_freigabe, "umsetzung_starten": umsetzung_starten,
               "budget_abschluss": budget_knoten("gesamtreview"), "gesamtreview": gesamtreview,
               "abschluss_freigabe": abschluss_freigabe, "abschluss": abschluss}
    kanten = {"nach_klaeren": nach_klaeren, "nach_fragen": nach_fragen, "nach_akzeptanz": nach_akzeptanz,
              "nach_spec_pruefung": nach_spec_pruefung, "nach_freigabe": nach_freigabe,
              "nach_plan_freigabe": nach_plan_freigabe, "nach_abschluss_freigabe": nach_abschluss_freigabe}
    # tests_ausfuehren der Umsetzung mit Hash-Vergleich davor; sonst ist die Umsetzung die aus Stufe 3
    return planung, kanten, (*bausteine_s3[:4], tests_ausfuehren, *bausteine_s3[5:])


def baue_graph_s4(abh: Abhaengigkeiten | None = None, checkpointer=None):
    """Braucht einen Checkpointer: Mehrere Haltepunkte, und jeder kann Stunden auf den Menschen warten."""
    planung, k, bausteine_s3 = _bausteine_s4(abh or Abhaengigkeiten())
    g = StateGraph(EntwicklungState)
    for name, knoten in planung.items():
        g.add_node(name, gezaehlt(knoten))
    umsetzung_s3(g, bausteine_s3, ziel_gruen="budget_abschluss")
    g.add_edge(START, "vorbereiten")
    g.add_edge("vorbereiten", "klaeren")
    g.add_conditional_edges("klaeren", k["nach_klaeren"], ["fragen", "budget_spec", "bericht"])
    g.add_conditional_edges("budget_spec", nach_budget("budget_spec", nach_spec_rahmen),
                            ["budget_spec", "spec_schreiben", "akzeptanz_schreiben", "bericht"])
    g.add_conditional_edges("budget_plan", nach_budget("budget_plan", "plan_schreiben"),
                            ["budget_plan", "plan_schreiben", "bericht"])
    g.add_conditional_edges("fragen", k["nach_fragen"], ["fragen", "klaeren", "bericht"])
    g.add_conditional_edges("spec_schreiben", lambda s: "bericht" if s.get("status") else "akzeptanz_schreiben",
                            ["akzeptanz_schreiben", "bericht"])
    g.add_conditional_edges("akzeptanz_schreiben", k["nach_akzeptanz"],
                            ["akzeptanz_schreiben", *SPEC_PRUEFER, "bericht"])
    for knoten in SPEC_PRUEFER:
        g.add_edge(knoten, "spec_pruefung_sammeln")
    g.add_conditional_edges("spec_pruefung_sammeln", k["nach_spec_pruefung"], ["spec_freigabe", "bericht"])
    g.add_conditional_edges("spec_freigabe", k["nach_freigabe"],
                            ["spec_freigabe", "stufe_waehlen", "budget_spec", "bericht"])
    g.add_edge("stufe_waehlen", "budget_plan")
    g.add_conditional_edges("plan_schreiben", lambda s: "bericht" if s.get("status") else "plan_pruefen",
                            ["plan_pruefen", "bericht"])
    g.add_conditional_edges("plan_pruefen", lambda s: "bericht" if s.get("status") else "plan_freigabe",
                            ["plan_freigabe", "bericht"])
    g.add_conditional_edges("plan_freigabe", k["nach_plan_freigabe"],
                            ["plan_freigabe", "umsetzung_starten", "budget_plan", "bericht"])
    g.add_edge("umsetzung_starten", "budget_umsetzung")
    g.add_conditional_edges("budget_abschluss", nach_budget("budget_abschluss", "gesamtreview"),
                            ["budget_abschluss", "gesamtreview", "bericht"])
    g.add_conditional_edges("gesamtreview", lambda s: "bericht" if s.get("status") == "grenzverletzung"
                            else "abschluss_freigabe", ["abschluss_freigabe", "bericht"])
    g.add_conditional_edges("abschluss_freigabe", k["nach_abschluss_freigabe"],
                            ["abschluss_freigabe", "abschluss"])
    g.add_edge("abschluss", "bericht")
    return g.compile(checkpointer=checkpointer)
