from datetime import datetime
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from entwicklung import pfade, speicher


class _S(TypedDict, total=False):
    x: int
    antwort: str


def _mini_graph(cp):
    """vorher → eskalation (interrupt) → Ende; so wie der echte Graph an der Eskalation anhält."""
    g = StateGraph(_S)
    g.add_node("vorher", lambda s: {"x": 1})
    g.add_node("eskalation", lambda s: {"antwort": interrupt({"frage": "?"})})
    g.add_edge(START, "vorher")
    g.add_edge("vorher", "eskalation")
    g.add_edge("eskalation", END)
    return g.compile(checkpointer=cp)


def test_db_liegt_im_umgeleiteten_data_dir():
    cp = speicher.oeffne_checkpointer()
    pfad = pfade.checkpoint_db_pfad()
    assert pfad.parent == pfade.data_dir() and pfad.exists()
    assert cp is not None


def test_freie_thread_id_kollision():
    cp = speicher.oeffne_checkpointer()
    graph = _mini_graph(cp)
    jetzt = datetime(2026, 10, 19, 22, 0, 5)
    erste = speicher.freie_thread_id(cp, jetzt)
    assert erste == "lauf-20261019-220005"
    graph.invoke({}, {"configurable": {"thread_id": erste}})
    assert speicher.freie_thread_id(cp, jetzt) == "lauf-20261019-220005-2"


def test_wartende_laeufe():
    cp = speicher.oeffne_checkpointer()
    graph = _mini_graph(cp)
    for tid in ("lauf-20261019-210000", "lauf-20261019-220000", "lauf-20261019-220000-2",
                "lauf-20261019-220000-10"):
        graph.invoke({}, {"configurable": {"thread_id": tid}})
    from langgraph.types import Command
    graph.invoke(Command(resume="ok"), {"configurable": {"thread_id": "lauf-20261019-220000-2"}})  # fertig
    assert speicher.wartende_laeufe(cp, lambda stufe: graph) == [
        "lauf-20261019-220000-10", "lauf-20261019-220000", "lauf-20261019-210000"]


def test_keine_wartenden_laeufe():
    cp = speicher.oeffne_checkpointer()
    assert speicher.wartende_laeufe(cp, lambda stufe: _mini_graph(cp)) == []


def test_freie_thread_id_reserviert_ohne_checkpoint():
    """Zwei Läufe in derselben Sekunde: Der zweite bekommt -2, auch wenn der erste noch keinen Checkpoint hat."""
    cp = speicher.oeffne_checkpointer()
    jetzt = datetime(2026, 10, 19, 22, 0, 5)
    assert speicher.freie_thread_id(cp, jetzt) == "lauf-20261019-220005"
    andere_verbindung = speicher.oeffne_checkpointer()  # wie ein zweiter Prozess
    assert speicher.freie_thread_id(andere_verbindung, jetzt) == "lauf-20261019-220005-2"


def test_geplante_eskalation_ohne_interrupt_wartet_nicht():
    """Endet ein Prozess nach dem Checkpoint vor der Eskalation, steht eskalation schon in next,
    aber es gibt keine offene Frage. So ein Lauf darf nicht als wartend gelten."""
    cp = speicher.oeffne_checkpointer()
    g = StateGraph(_S)
    g.add_node("vorher", lambda s: {"x": 1})
    g.add_node("eskalation", lambda s: {"antwort": interrupt({"frage": "?"})})
    g.add_edge(START, "vorher")
    g.add_edge("vorher", "eskalation")
    g.add_edge("eskalation", END)
    abgebrochen = g.compile(checkpointer=cp, interrupt_before=["eskalation"])
    abgebrochen.invoke({}, {"configurable": {"thread_id": "lauf-20261019-230000"}})
    graph = _mini_graph(cp)
    assert graph.get_state({"configurable": {"thread_id": "lauf-20261019-230000"}}).next == ("eskalation",)
    graph.invoke({}, {"configurable": {"thread_id": "lauf-20261019-220000"}})  # wartet wirklich
    assert speicher.wartende_laeufe(cp, lambda stufe: graph) == ["lauf-20261019-220000"]


def _halt_graph(cp, knoten: str):
    """vorher → <knoten> (interrupt) → Ende."""
    g = StateGraph(_S)
    g.add_node("vorher", lambda s: {"x": 1})
    g.add_node(knoten, lambda s: {"antwort": interrupt({"frage": knoten})})
    g.add_edge(START, "vorher")
    g.add_edge("vorher", knoten)
    g.add_edge(knoten, END)
    return g.compile(checkpointer=cp)


def test_wartepunkt_nennt_haltepunkt():
    from langgraph.types import Command
    cp = speicher.oeffne_checkpointer()
    graph = _halt_graph(cp, "fragen")
    cfg = {"configurable": {"thread_id": "lauf-20261020-090000"}}
    graph.invoke({}, cfg)
    assert speicher.wartepunkt(graph, "lauf-20261020-090000") == "fragen"
    graph.invoke(Command(resume="ok"), cfg)
    assert speicher.wartepunkt(graph, "lauf-20261020-090000") is None
    assert set(speicher.WARTEPUNKTE) == {"fragen", "spec_freigabe", "plan_freigabe", "eskalation",
                                        "budget_spec", "budget_plan", "budget_umsetzung",  # ab 6b-2
                                        "abschluss_freigabe", "budget_abschluss"}  # ab Stufe 7


def test_wartende_laeufe_ueber_stufen():
    """Jeder Thread wird mit dem Graphen seiner Stufe (metadata.stufe) gelesen; ohne Angabe gilt Stufe 3."""
    cp = speicher.oeffne_checkpointer()
    graphen = {3: _halt_graph(cp, "eskalation"), 4: _halt_graph(cp, "spec_freigabe")}
    graphen[3].invoke({}, {"configurable": {"thread_id": "lauf-20261020-080000"}})  # alter Lauf ohne Stufe
    graphen[4].invoke({}, {"configurable": {"thread_id": "lauf-20261020-090000"}, "metadata": {"stufe": 4}})
    gesehen = []

    def graph_fuer(stufe):
        gesehen.append(stufe)
        return graphen[stufe]

    assert speicher.wartende_laeufe(cp, graph_fuer) == ["lauf-20261020-090000", "lauf-20261020-080000"]
    assert sorted(gesehen) == [3, 4]
    assert speicher.stufe_des_laufs(cp, "lauf-20261020-090000") == 4
