from langgraph.types import Command

from entwicklung import speicher
from entwicklung.graph_s4 import baue_graph_s4
from entwicklung.leitstand import daten
from tests.test_graph_s1 import _abh, umgebung  # noqa: F401  (Fixture)
from tests.test_graph_s2 import _codex, _pruefer
from tests.test_graph_s3 import RICHTIG, Implementierer
from tests.test_graph_s4 import FRAGEN, GEN_TEST, PLAN_OK, SPEC, Planer, s4  # noqa: F401  (s4 Fixture)


def _graph(aufgaben, cp, planer=None):
    planer = planer or Planer()
    abh = _abh(aufgaben, implementierer=Implementierer(RICHTIG), pruefer=_pruefer(), codex=_codex(),
               planer=planer, planer_codex=planer.codex)
    return baue_graph_s4(abh, checkpointer=cp)


def _start(graph, repo, tid="lauf-20261020-150000"):
    cfg = {"configurable": {"thread_id": tid}, "metadata": {"stufe": 4}}
    graph.invoke({"repo": str(repo), "aufgabe_id": "M2"}, cfg)
    return cfg


def test_graph_daten_ebenen_und_haltepunkte():
    d = daten.graph_daten(baue_graph_s4())
    knoten = {k["id"]: k for k in d["knoten"]}
    assert knoten["__start__"]["ebene"] == 0 and knoten["vorbereiten"]["ebene"] == 1
    assert {k for k, v in knoten.items() if v["haltepunkt"]} == {"fragen", "spec_freigabe", "plan_freigabe",
                                                                  "eskalation", "budget_spec", "budget_plan",
                                                                  "budget_umsetzung", "budget_abschluss",
                                                                  "abschluss_freigabe"}  # Stufe 7
    assert knoten["klaeren"]["phase"] == "planung" and knoten["implementieren"]["phase"] == "umsetzung"
    assert knoten["pruefen_codex"]["phase"] == "pruefung"
    assert all(k["text"] for k in d["knoten"] if not k["id"].startswith("__")), "jeder Knoten braucht einen Satz"
    zurueck = {(k["von"], k["nach"]) for k in d["kanten"] if k["zurueck"]}
    assert ("fix_runde", "budget_umsetzung") in zurueck and ("fragen", "klaeren") in zurueck
    abbruch = {(k["von"], k["nach"]) for k in d["kanten"] if k["abbruch"]}
    assert ("klaeren", "bericht") in abbruch and ("befunde_sammeln", "bericht") not in abbruch
    # in jeder Ebene haben die Knoten verschiedene Spalten
    belegt = [(k["ebene"], k["spalte"]) for k in d["knoten"]]
    assert len(belegt) == len(set(belegt))


def test_lauf_daten_wartend(s4):
    repo, aufgaben = s4
    cp = speicher.oeffne_checkpointer()
    graph = _graph(aufgaben, cp)
    cfg = _start(graph, repo)
    d = daten.lauf_daten(graph, cp, "lauf-20261020-150000")
    assert d["wartepunkt"] == "spec_freigabe" and d["status"] == "wartet" and d["stufe"] == 4
    assert d["aufgabe_id"] == "M2" and d["frage"]["art"] == "spec_freigabe"
    assert d["frage"]["spec_text"] == SPEC["spec"]
    assert d["frage"]["tests_text"] == {"test_akzeptanz_m2.py": GEN_TEST}
    assert d["verlauf"][0]["knoten"] == ["vorbereiten"] and d["verlauf"][0]["zeit"]
    assert "klaeren" in d["erledigt"] and "spec_freigabe" not in d["erledigt"]
    graph.invoke(Command(resume={"entscheidung": "freigeben"}), cfg)
    d = daten.lauf_daten(graph, cp, "lauf-20261020-150000")
    assert d["wartepunkt"] == "plan_freigabe" and d["frage"]["plan_text"] == PLAN_OK["plan"]


def test_lauf_daten_fertig(s4):
    repo, aufgaben = s4
    cp = speicher.oeffne_checkpointer()
    graph = _graph(aufgaben, cp)
    cfg = _start(graph, repo)
    graph.invoke(Command(resume={"entscheidung": "freigeben"}), cfg)
    graph.invoke(Command(resume={"entscheidung": "freigeben"}), cfg)
    graph.invoke(Command(resume={"entscheidung": "mergen"}), cfg)  # ab Stufe 7
    d = daten.lauf_daten(graph, cp, "lauf-20261020-150000")
    assert d["status"] == "gruen" and d["wartepunkt"] is None and d["frage"] is None
    assert d["aktiv"] == [] and d["bericht_pfad"].endswith(".md") and "bericht" in d["erledigt"]


def test_laeufe_liste_ueber_stufen(s4):
    repo, aufgaben = s4
    cp = speicher.oeffne_checkpointer()
    graph = _graph(aufgaben, cp, Planer(klaeren=[FRAGEN]))  # beide Läufe fragen
    _start(graph, repo, "lauf-20261020-150000")
    _start(graph, repo, "lauf-20261020-160000")
    liste = daten.laeufe(cp, lambda stufe: graph)
    assert [l["thread_id"] for l in liste] == ["lauf-20261020-160000", "lauf-20261020-150000"]
    assert all(l["wartepunkt"] == "fragen" and l["aufgabe_id"] == "M2" and l["stufe"] == 4 for l in liste)


def test_lauf_aus_anderem_prozess(s4):
    """Ein Lauf, den die CLI über eine eigene Verbindung schreibt, ist über eine zweite Verbindung lesbar."""
    repo, aufgaben = s4
    schreiber = speicher.oeffne_checkpointer()
    _start(_graph(aufgaben, schreiber, Planer(klaeren=[FRAGEN])), repo)
    leser = speicher.oeffne_checkpointer()
    d = daten.lauf_daten(_graph(aufgaben, leser), leser, "lauf-20261020-150000")
    assert d["wartepunkt"] == "fragen" and d["frage"]["fragen"] == FRAGEN["fragen"]



def test_checkpoint_id_und_frage_aus_einem_schnappschuss(s4):
    repo, aufgaben = s4
    cp = speicher.oeffne_checkpointer()
    graph = _graph(aufgaben, cp)
    _start(graph, repo)
    d = daten.lauf_daten(graph, cp, "lauf-20261020-150000")
    snap = graph.get_state({"configurable": {"thread_id": "lauf-20261020-150000"}})
    assert d["checkpoint_id"] == snap.config["configurable"]["checkpoint_id"]
    assert daten._frage(snap, "plan_freigabe") is None  # Haltepunkt nicht in diesem Schnappschuss: kein Absturz



def test_lauf_daten_aufrufe_und_rahmen(s4):
    """Kopfzeile im Leitstand: Aufrufe N/M."""
    from entwicklung import speicher
    from entwicklung.graph_s4 import baue_graph_s4
    from entwicklung.leitstand.daten import lauf_daten
    from tests.test_cli_s4 import _abh4
    repo, aufgaben = s4
    cp = speicher.oeffne_checkpointer()
    graph = baue_graph_s4(_abh4(aufgaben), checkpointer=cp)
    cfg = {"configurable": {"thread_id": "lauf-1"}, "metadata": {"stufe": 4}}
    graph.invoke({"repo": str(repo), "aufgabe_id": "M2", "budget": 30}, cfg)
    d = lauf_daten(graph, cp, "lauf-1")
    assert d["budget"] == 30 and d["aufrufe"] == 5  # klären, Spec, Akzeptanz, 2 Spec-Prüfer
