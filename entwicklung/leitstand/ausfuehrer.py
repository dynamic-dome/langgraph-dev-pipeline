"""Läufe, die der Leitstand startet oder fortsetzt, laufen in Hintergrund-Threads des Servers.

Je Lauf höchstens ein Thread: Ein Doppelklick auf „freigeben“ darf nicht zwei Fortsetzungen auslösen. Fehler im
Thread werden festgehalten und nie nach außen geworfen; der Server läuft weiter. Den Stand des Laufs selbst liest die
Oberfläche aus dem Checkpointer (daten.py), hier geht es nur um „läuft gerade“ und „ist abgestürzt“.
"""
import json
import threading
from pathlib import Path

from langgraph.types import Command

from entwicklung.berater import BERATER, OHNE_RAT, hole_rat, vergleiche
from entwicklung.graph import MAX_RUNDEN, Abhaengigkeiten, baue_graph_s3
from entwicklung.graph_s4 import baue_graph_s4, planung_sauber
from entwicklung.leitstand.daten import _frage
from entwicklung.pfade import berichte_dir, pruefe_schreibziel
from entwicklung.speicher import WARTEPUNKTE, freie_thread_id, stufe_des_laufs, wartepunkt

STUFEN = {3: baue_graph_s3, 4: baue_graph_s4}  # nur Stufen mit Gedächtnis können anhalten und fortgesetzt werden


def _stand(graph, thread_id: str) -> tuple:
    snap = graph.get_state({"configurable": {"thread_id": thread_id}})
    punkt = next((a.name for a in snap.tasks if a.name in WARTEPUNKTE and a.interrupts), None)
    return snap, punkt, snap.config["configurable"].get("checkpoint_id")


def _ablegen(werte: dict, punkt: str, eintrag: dict) -> str:
    ordner = pruefe_schreibziel(berichte_dir() / werte["lauf_id"])
    ordner.mkdir(parents=True, exist_ok=True)
    wer = eintrag.get("wer") or "fable"
    n = len(list(ordner.glob(f"rat-{punkt}-{wer}-*.json"))) + 1
    while True:  # „x“: nie eine andere Rat-Datei überschreiben, auch nicht bei zwei gleichzeitigen Räten
        datei = ordner / f"rat-{punkt}-{wer}-{n}.json"
        try:
            with datei.open("x", encoding="utf-8") as f:
                json.dump(eintrag, f, ensure_ascii=False, indent=1)
            return str(datei)
        except FileExistsError:
            n += 1


def rat_fuer_lauf(abh, graph, thread_id: str, erwartet: tuple | None = None, wer: str = "fable") -> dict:
    """Holt Fables Rat für den Haltepunkt, an dem der Lauf jetzt steht (blockiert 1–3 min), und legt ihn ab.

    erwartet = (Haltepunkt, checkpoint_id) beim Anfordern: Steht der Lauf inzwischen woanders, wird Fable gar nicht
    erst gefragt. Sonst bekäme ein Klick auf Haltepunkt A still einen Rat für Haltepunkt B."""
    snap, punkt, checkpoint_id = _stand(graph, thread_id)
    if erwartet is not None and (punkt, checkpoint_id) != tuple(erwartet):
        return {"wer": wer, "haltepunkt": erwartet[0], "checkpoint_id": erwartet[1], "ok": False, "rat": None,
                "antwort": None, "grund": None, "dauer_s": 0.0, "datei": None,
                "fehler": f"Der Stand hat sich geändert, bevor {wer.capitalize()} begann. Bitte neu fragen."}
    if punkt is None:
        raise WartetNicht(thread_id)
    werte = snap.values
    ergebnis = hole_rat(abh, punkt, _frage(snap, punkt), werte, Path(werte["worktree"]),
                        sauber=lambda: planung_sauber(abh, werte), wer=wer)
    eintrag = {"haltepunkt": punkt, "checkpoint_id": checkpoint_id, **ergebnis}
    eintrag["datei"] = _ablegen(werte, punkt, eintrag)
    return eintrag


class Belegt(Exception):
    """Für diesen Lauf arbeitet schon ein Thread."""


class WartetNicht(Exception):
    """Der Lauf steht an keinem Haltepunkt."""


class KeinRat(Exception):
    """An diesem Haltepunkt gibt es keinen Rat (Kostenrahmen, Abschluss)."""


class StandGeaendert(Exception):
    """Der Lauf steht nicht mehr an dem Haltepunkt und Stand, für den die Antwort gedacht war."""


class Ausfuehrer:
    def __init__(self, abh: Abhaengigkeiten | None, cp):
        self.abh, self.cp = abh or Abhaengigkeiten(), cp
        self._graphen: dict[int, object] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._fehler: dict[str, str] = {}
        self._sperre = threading.Lock()
        self._rat_threads: dict[tuple[str, str], threading.Thread] = {}  # je (Lauf, Berater)
        self._raete: dict[tuple[str, str], dict] = {}

    def graph_fuer(self, stufe: int):
        if stufe not in self._graphen:
            self._graphen[stufe] = STUFEN[stufe](self.abh, checkpointer=self.cp)
        return self._graphen[stufe]

    def _los(self, thread_id: str, graph, eingabe, cfg, pruefung=None) -> None:
        def arbeit():
            try:
                graph.invoke(eingabe, cfg)
            except Exception as e:  # ein abgestürzter Lauf ist ein Zustand, kein Absturz des Servers
                self._fehler[thread_id] = f"{type(e).__name__}: {e}"

        with self._sperre:
            alt = self._threads.get(thread_id)
            if alt is not None and alt.is_alive():
                raise Belegt(thread_id)
            if pruefung is not None:
                pruefung()  # unter der Sperre: zwischen Prüfung und Start kann keine zweite Antwort dazwischen
            self._fehler.pop(thread_id, None)
            t = threading.Thread(target=arbeit, name=f"lauf {thread_id}", daemon=True)
            self._threads[thread_id] = t
            t.start()

    def starte(self, repo: str, aufgabe_id: str, stufe: int = 4, modell: str = "auto",
               pruefer_modell: str = "auto", max_runden: int = MAX_RUNDEN, budget: int | None = None) -> str:
        thread_id = freie_thread_id(self.cp, self.abh.jetzt())
        cfg = {"configurable": {"thread_id": thread_id}, "metadata": {"stufe": stufe}}
        eingabe = {"repo": repo, "aufgabe_id": aufgabe_id, "modell": modell, "pruefer_modell": pruefer_modell,
                   "budget": budget,
                   "max_runden": max_runden}
        self._los(thread_id, self.graph_fuer(stufe), eingabe, cfg)
        return thread_id

    def fortsetzen(self, thread_id: str, antwort: dict, erwartet: tuple | None = None) -> None:
        """erwartet = (Haltepunkt, checkpoint_id), die der Server geprüft hat (Codex 6b-1 F-001)."""
        t = self._threads.get(thread_id)
        if t is not None and t.is_alive():
            raise Belegt(thread_id)
        stufe = stufe_des_laufs(self.cp, thread_id)
        graph = self.graph_fuer(stufe)
        if wartepunkt(graph, thread_id) is None:
            raise WartetNicht(thread_id)
        cfg = {"configurable": {"thread_id": thread_id}, "metadata": {"stufe": stufe}}

        def pruefung():
            if erwartet is not None and _stand(graph, thread_id)[1:] != tuple(erwartet):
                raise StandGeaendert(thread_id)
        self._los(thread_id, graph, Command(resume=antwort), cfg, pruefung)

    def frage_rat(self, thread_id: str, wer: str = "fable") -> None:
        """Startet den Rat eines Beraters im Hintergrund. Je Lauf und Berater höchstens ein Rat gleichzeitig."""
        if wer not in BERATER:
            raise ValueError(f"unbekannter Berater {wer!r}")
        schluessel = (thread_id, wer)
        graph = self.graph_fuer(stufe_des_laufs(self.cp, thread_id))
        _, punkt, checkpoint_id = _stand(graph, thread_id)
        if punkt is None:
            raise WartetNicht(thread_id)
        if punkt in OHNE_RAT:
            raise KeinRat(punkt)

        def arbeit():
            try:
                self._raete[schluessel] = {**rat_fuer_lauf(self.abh, graph, thread_id, erwartet=(punkt, checkpoint_id),
                                                           wer=wer), "zustand": "fertig"}
            except Exception as e:
                self._raete[schluessel] = {"zustand": "fehler", "wer": wer, "haltepunkt": punkt,
                                           "checkpoint_id": checkpoint_id, "ok": False, "rat": None, "antwort": None,
                                           "grund": None, "fehler": f"{type(e).__name__}: {e}"}

        with self._sperre:
            alt = self._rat_threads.get(schluessel)
            if alt is not None and alt.is_alive():
                raise Belegt(f"{thread_id} ({wer})")
            self._raete[schluessel] = {"zustand": "laeuft", "wer": wer, "haltepunkt": punkt,
                                       "checkpoint_id": checkpoint_id, "ok": False, "rat": None, "antwort": None,
                                       "grund": None, "fehler": None}
            t = threading.Thread(target=arbeit, name=f"rat {thread_id} {wer}", daemon=True)
            self._rat_threads[schluessel] = t
            t.start()

    def rat(self, thread_id: str) -> dict | None:
        """Der letzte Rat je Berater; veraltet, wenn der Lauf inzwischen woanders steht. Dazu der Vergleich."""
        eintraege = {w: self._raete.get((thread_id, w)) for w in BERATER}
        if not any(eintraege.values()):
            return None
        graph = self.graph_fuer(stufe_des_laufs(self.cp, thread_id))
        _, punkt, checkpoint_id = _stand(graph, thread_id)
        raete = {w: None if e is None else
                 {**e, "veraltet": (punkt, checkpoint_id) != (e["haltepunkt"], e["checkpoint_id"])}
                 for w, e in eintraege.items()}
        fable, astra = raete["fable"], raete["astra"]
        aktuell = fable and astra and not fable["veraltet"] and not astra["veraltet"]
        return {**raete, "vergleich": vergleiche(punkt, fable, astra) if aktuell else None}

    def warte_rat(self, thread_id: str, timeout: float | None = None) -> None:
        for wer in BERATER:
            t = self._rat_threads.get((thread_id, wer))
            if t is not None:
                t.join(timeout)

    def zustand(self, thread_id: str) -> dict:
        t = self._threads.get(thread_id)
        return {"laeuft": bool(t and t.is_alive()), "fehler": self._fehler.get(thread_id)}

    def warte(self, thread_id: str, timeout: float | None = None) -> None:
        t = self._threads.get(thread_id)
        if t is not None:
            t.join(timeout)
