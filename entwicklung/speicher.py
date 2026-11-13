"""Gedächtnis der Pipeline (ab Stufe 3): SQLite-Checkpointer und wartende Läufe.

Ein Lauf ist ein Thread (thread_id = "lauf-JJJJMMTT-HHMMSS"). Der Checkpointer speichert nach jedem Superstep den
State. Nur so kann der Graph an der Eskalation anhalten und Stunden später fortgesetzt werden.
Anders als in Lab 1 gibt es keine Merker-Datei: Welcher Lauf wartet, steht im Checkpointer selbst
(offenes interrupt der Aufgabe eskalation). Ein Merker kann veralten, der Checkpointer nicht.
"""
import sqlite3
from datetime import datetime

from langgraph.checkpoint.sqlite import SqliteSaver

from entwicklung.pfade import checkpoint_db_pfad

PRAEFIX = "lauf-"
WARTEPUNKTE = ("fragen", "spec_freigabe", "plan_freigabe", "eskalation",
               "budget_spec", "budget_plan", "budget_umsetzung",  # Knoten mit interrupt (Stufe 4: auch Planung)
               "abschluss_freigabe", "budget_abschluss")  # Stufe 7
STANDARD_STUFE = 3  # Läufe von vor Stufe 4 haben keine Angabe in metadata


def oeffne_checkpointer() -> SqliteSaver:
    return SqliteSaver(sqlite3.connect(checkpoint_db_pfad(), check_same_thread=False))


def _thread_id(jetzt: datetime) -> str:
    return f"{PRAEFIX}{jetzt:%Y%m%d-%H%M%S}"


def _schluessel(thread_id: str) -> tuple:
    """Zeitstempel, dann Suffix als Zahl (sonst stünde -10 vor -2)."""
    teile = thread_id[len(PRAEFIX):].split("-")
    nummer = int(teile[2]) if len(teile) > 2 and teile[2].isdigit() else 1
    return (teile[0], teile[1] if len(teile) > 1 else "", nummer)


def freie_thread_id(checkpointer: SqliteSaver, jetzt: datetime) -> str:
    """Vergibt die ID atomar: Der PRIMARY KEY der Tabelle reservierung lässt jede ID nur einmal zu, auch wenn zwei
    Läufe in derselben Sekunde starten und noch keiner einen Checkpoint geschrieben hat."""
    basis, nummer = _thread_id(jetzt), 1
    with checkpointer.conn:  # commit am Ende des Blocks
        checkpointer.conn.execute("CREATE TABLE IF NOT EXISTS reservierung (thread_id TEXT PRIMARY KEY)")
    while True:
        kandidat = basis if nummer == 1 else f"{basis}-{nummer}"
        if checkpointer.get_tuple({"configurable": {"thread_id": kandidat}}) is None:
            with checkpointer.conn:
                neu = checkpointer.conn.execute("INSERT OR IGNORE INTO reservierung VALUES (?)", (kandidat,))
            if neu.rowcount == 1:
                return kandidat
        nummer += 1


def wartepunkt(graph, thread_id: str) -> str | None:
    """Haltepunkt mit offener Frage, sonst None.

    next allein reicht nicht: Endet der Prozess nach dem Checkpoint von befunde_sammeln, steht eskalation schon in
    next, gestellt ist die Frage aber erst, wenn die Aufgabe ein offenes interrupt hat."""
    zustand = graph.get_state({"configurable": {"thread_id": thread_id}})
    return next((a.name for a in zustand.tasks if a.name in WARTEPUNKTE and a.interrupts), None)


def stufe_des_laufs(checkpointer: SqliteSaver, thread_id: str) -> int:
    """Mit welcher Stufe der Lauf begann (metadata jedes Checkpoints); der Graph zum Lesen muss dazu passen."""
    tupel = checkpointer.get_tuple({"configurable": {"thread_id": thread_id}})
    return int(((tupel.metadata if tupel else None) or {}).get("stufe", STANDARD_STUFE))


def wartende_laeufe(checkpointer: SqliteSaver, graph_fuer) -> list[str]:
    """Läufe mit offener Frage an einem Haltepunkt, jüngste zuerst. graph_fuer(stufe) liefert den passenden Graphen."""
    ids = {t.config["configurable"]["thread_id"] for t in checkpointer.list(None)}
    wartend = [tid for tid in ids if tid.startswith(PRAEFIX)
               and wartepunkt(graph_fuer(stufe_des_laufs(checkpointer, tid)), tid)]
    return sorted(wartend, key=_schluessel, reverse=True)
