"""Leitstand-Server (FastAPI). Nur 127.0.0.1, ein zufälliges Token je Start, Host- und Origin-Prüfung.

Warum das Token: Ein Server auf 127.0.0.1 ist von jeder Webseite aus erreichbar, die im Browser offen ist. Ohne
Token könnte eine fremde Seite per Anfrage eine Freigabe auslösen. Die Host-Prüfung wehrt DNS-Rebinding ab, die
Origin-Prüfung Anfragen anderer Seiten.
"""
import secrets
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from entwicklung.berater import BERATER, einwaende_fuer, kein_rat_text
from entwicklung.graph import BUDGET, Abhaengigkeiten
from entwicklung.leitstand import daten
from entwicklung.leitstand.ausfuehrer import STUFEN, Ausfuehrer, Belegt, KeinRat, StandGeaendert, WartetNicht
from entwicklung.pfade import berichte_dir, projekt_dir
from entwicklung.speicher import stufe_des_laufs, wartepunkt
from entwicklung.steuerung import DURCHLASS, ERLAUBT_KURZ, antwort_fuer, einwand_fehlt

STATIK = Path(__file__).parent / "static"
MODELLE = ["auto", "haiku", "sonnet", "opus"]  # bewusst ohne Fable; auto = Tabelle in stufen.py


class Start(BaseModel):
    repo: str
    aufgabe: str
    stufe: int = 4
    modell: str = "auto"
    pruefer_modell: str = "auto"
    budget: int = BUDGET  # Kostenrahmen in Agentenaufrufen (6b-2)


class Antwort(BaseModel):
    haltepunkt: str  # was der Browser angezeigt hat: eine Freigabe aus einem veralteten Tab trifft nichts anderes
    checkpoint_id: str
    entscheidung: str | None = None
    antwort: str | None = None
    hinweis: str | None = None
    begruendung: str | None = None  # freigeben/annehmen trotz Einwand; Einwände rechnet der Server selbst
    komplexitaet: str | None = None  # an der Plan-Freigabe: Stufe ändern (6b-2)


def standard_port(portliste: Path) -> int | None:
    """Der eingetragene Port des Leitstands aus portwarts ports.toml (Projekt langgraph-lab-2, Zweck „Leitstand“)."""
    import tomllib
    try:
        eintraege = tomllib.loads(portliste.read_text(encoding="utf-8")).get("port", [])
    except (OSError, tomllib.TOMLDecodeError):
        return None
    return next((e["port"] for e in eintraege if e.get("projekt") == "langgraph-lab-2"
                 and "Leitstand" in e.get("zweck", "")), None)


def _verweigert(grund: str) -> JSONResponse:
    return JSONResponse({"fehler": grund}, status_code=403)


def baue_app(abh: Abhaengigkeiten | None, cp, token: str, port: int, repos_dir: Path | None = None,
             demo: bool = False) -> FastAPI:
    abh = abh or Abhaengigkeiten()
    repos_dir = repos_dir or projekt_dir()
    aufgaben_dir = abh.aufgaben_dir or projekt_dir() / "aufgaben"
    host, herkunft = f"127.0.0.1:{port}", f"http://127.0.0.1:{port}"
    app = FastAPI(title="Leitstand", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.ausfuehrer = ausfuehrer = Ausfuehrer(abh, cp)

    @app.middleware("http")
    async def schutz(request: Request, call_next):
        if request.headers.get("host") != host:
            return _verweigert("falscher Host")
        origin = request.headers.get("origin")
        if origin is not None and origin != herkunft:
            return _verweigert("fremde Herkunft")
        if request.url.path.startswith("/api/"):  # Seite und Dateien enthalten keine Daten; alles Wichtige hier
            gegeben = request.headers.get("x-leitstand-token") or ""
            if not secrets.compare_digest(gegeben.encode(), token.encode()):
                return _verweigert("Token fehlt oder falsch")
        antwort = await call_next(request)
        if not request.url.path.startswith("/api/"):  # nach Updates nie ein altes app.js aus dem Cache
            antwort.headers["Cache-Control"] = "no-cache"
        return antwort

    def optionen() -> dict:
        repos = {}
        for r in sorted(p for p in repos_dir.iterdir() if _im_ordner(p) and (p / ".git").exists()
                        and (p / "entwicklung.toml").exists()):
            ordner = aufgaben_dir / r.name
            repos[r.name] = sorted(a.stem for a in ordner.glob("*.md")) if ordner.is_dir() else []
        return {"repos": repos, "modelle": MODELLE, "stufen": sorted(STUFEN), "budget": BUDGET}

    def _im_ordner(p: Path) -> bool:
        """Keine Verweise (Junction, Symlink) und nichts, was aufgelöst außerhalb von repos_dir liegt."""
        return not (p.is_symlink() or p.is_junction()) and p.resolve().is_relative_to(repos_dir.resolve())

    def bekannt(tid: str) -> bool:
        return cp.get_tuple({"configurable": {"thread_id": tid}}) is not None

    @app.get("/favicon.ico")
    def favicon():
        return Response(status_code=204)  # kein Symbol, aber auch kein Fehler in der Konsole

    @app.get("/")
    def seite():
        return FileResponse(STATIK / "index.html")

    @app.get("/api/info")
    def info():
        return {"demo": demo, "port": port}  # Demo mit Fake-Agenten: die Oberfläche zeigt es deutlich

    @app.get("/api/graph")
    def graph(stufe: int = 4):
        if stufe not in STUFEN:
            return JSONResponse({"fehler": f"Stufe {stufe} unbekannt"}, status_code=400)
        return daten.graph_daten(ausfuehrer.graph_fuer(stufe))

    @app.get("/api/laeufe")
    def laeufe():
        return [{**l, "zustand": ausfuehrer.zustand(l["thread_id"])}
                for l in daten.laeufe(cp, ausfuehrer.graph_fuer)]

    @app.get("/api/laeufe/{tid}")
    def lauf(tid: str):
        if not bekannt(tid):
            return JSONResponse({"fehler": "Lauf unbekannt"}, status_code=404)
        graph = ausfuehrer.graph_fuer(stufe_des_laufs(cp, tid))
        return {**daten.lauf_daten(graph, cp, tid), "zustand": ausfuehrer.zustand(tid),
                "erlaubt": ERLAUBT_KURZ.get(wartepunkt(graph, tid) or "", [])}

    @app.get("/api/start-optionen")
    def start_optionen():
        return optionen()

    @app.post("/api/laeufe", status_code=201)
    def starten(start: Start):
        o = optionen()
        if start.repo not in o["repos"] or start.aufgabe not in o["repos"][start.repo]:
            return JSONResponse({"fehler": "Repo oder Aufgabe unbekannt"}, status_code=400)
        if start.stufe not in o["stufen"] or start.modell not in MODELLE or start.pruefer_modell not in MODELLE:
            return JSONResponse({"fehler": "Stufe oder Modell nicht erlaubt"}, status_code=400)
        if not 1 <= start.budget <= 1000:
            return JSONResponse({"fehler": "Rahmen muss zwischen 1 und 1000 Aufrufen liegen"}, status_code=400)
        tid = ausfuehrer.starte(str((repos_dir / start.repo).resolve()), start.aufgabe, stufe=start.stufe,
                                modell=start.modell, pruefer_modell=start.pruefer_modell, budget=start.budget)
        return {"thread_id": tid}

    @app.post("/api/laeufe/{tid}/antwort", status_code=202)
    def antworten(tid: str, a: Antwort):
        if not bekannt(tid):
            return JSONResponse({"fehler": "Lauf unbekannt"}, status_code=404)
        graph = ausfuehrer.graph_fuer(stufe_des_laufs(cp, tid))
        punkt = wartepunkt(graph, tid)
        if punkt is None:
            return JSONResponse({"fehler": "Lauf wartet nicht auf eine Antwort"}, status_code=409)
        snap = graph.get_state({"configurable": {"thread_id": tid}})
        stand = snap.config["configurable"].get("checkpoint_id")
        if a.haltepunkt != punkt or a.checkpoint_id != stand:
            return JSONResponse({"fehler": f"Der Stand hat sich geändert (jetzt: {punkt}). Bitte neu ansehen und "
                                           f"dann entscheiden."}, status_code=409)
        antwort = antwort_fuer(punkt, a.entscheidung, a.antwort, a.hinweis, a.begruendung, a.komplexitaet)
        if antwort is None:
            return JSONResponse({"fehler": f"passt nicht zum Haltepunkt {punkt}", "erlaubt": ERLAUBT_KURZ[punkt]},
                                status_code=400)
        einwaende = einwaende_fuer(punkt, daten._frage(snap, punkt), berichte_dir() / snap.values["lauf_id"], stand)
        fehlt = einwand_fehlt(punkt, antwort, einwaende)
        if fehlt:
            return JSONResponse({"fehler": fehlt, "einwaende": einwaende}, status_code=400)
        if einwaende and antwort.get("entscheidung") in DURCHLASS:
            antwort["einwaende"] = einwaende  # landet mit der Begründung im State und im Bericht
        try:
            ausfuehrer.fortsetzen(tid, antwort, erwartet=(punkt, stand))
        except StandGeaendert:
            return JSONResponse({"fehler": "Der Stand hat sich geändert. Bitte neu ansehen und dann entscheiden."},
                                status_code=409)
        except (Belegt, WartetNicht) as e:
            return JSONResponse({"fehler": f"{type(e).__name__}: {e}"}, status_code=409)
        return {"thread_id": tid, "haltepunkt": punkt}

    @app.post("/api/laeufe/{tid}/rat", status_code=202)
    def rat_anfordern(tid: str, wer: str = "fable"):
        """Fable und/oder Astra beraten (1–5 min, nur auf Klick). Übernehmen geht über /antwort mit Haltepunkt und
        Stand des Rats."""
        if not bekannt(tid):
            return JSONResponse({"fehler": "Lauf unbekannt"}, status_code=404)
        if wer not in (*BERATER, "beide"):
            return JSONResponse({"fehler": f"unbekannter Berater {wer!r}", "erlaubt": [*BERATER, "beide"]},
                                status_code=400)
        gestartet, belegt = [], []
        for w in BERATER if wer == "beide" else (wer,):
            try:
                ausfuehrer.frage_rat(tid, w)
                gestartet.append(w)
            except Belegt:
                belegt.append(w)
            except WartetNicht as e:
                return JSONResponse({"fehler": f"WartetNicht: {e}"}, status_code=409)
            except KeinRat as e:
                return JSONResponse({"fehler": kein_rat_text(e.args[0] if e.args else "")}, status_code=409)
        if not gestartet:
            return JSONResponse({"fehler": "Berater denkt schon", "belegt": belegt}, status_code=409)
        return {"thread_id": tid, "gestartet": gestartet, "belegt": belegt}

    @app.get("/api/laeufe/{tid}/rat")
    def rat_lesen(tid: str):
        eintrag = ausfuehrer.rat(tid) if bekannt(tid) else None
        if eintrag is None:
            return Response(status_code=204)  # noch kein Rat: kein Fehler
        return eintrag

    app.mount("/static", StaticFiles(directory=STATIK), name="static")
    return app
