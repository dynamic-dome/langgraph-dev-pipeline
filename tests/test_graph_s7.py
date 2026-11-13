"""Stufe 7, Task 2: Kostenrahmen, Gesamtreview, Abschluss-Freigabe und lokaler Merge im Graphen."""
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from entwicklung.graph import baue_graph_s3
from tests.test_graph_s1 import _abh, _git, umgebung  # noqa: F401  (umgebung ist eine Fixture)
from tests.test_graph_s3 import FALSCH, RICHTIG, Implementierer
from tests.test_graph_s4 import (CFG, GESAMT_OK, PLAN_OK, SPEC, Planer, _bis_umsetzung, _graph, _halt, _start,
                                 _weiter, s4)  # noqa: F401  (s4 ist eine Fixture)

GESAMT_MAJOR = {**GESAMT_OK, "verdict": "FAIL", "spec_erfuellt": False,
                "restpunkte": [{"schwere": "major", "aussage": "Vertrag für negative Zahlen fehlt"}]}
GESAMT_EINSEITIG = {**GESAMT_OK, "tuer": {"urteil": "einseitig", "radius": "System", "begruendung": "löscht",
                                          "faelle": ["Löschen von Daten: mathe.py"],
                                          "selbstbewertung_stimmt": False}}
MIT_RMTREE = RICHTIG + "\n\nimport shutil\n\n\ndef weg(p):\n    shutil.rmtree(p)\n"


def _rev(repo, ref="HEAD"):
    return _git(repo, "rev-parse", ref).strip()


def _frage(graph):
    return graph.get_state(CFG).tasks[0].interrupts[0].value


def _bis_abschluss(s4, planer=None, impl=None):
    repo, aufgaben = s4
    graph, planer = _graph(aufgaben, planer, impl)
    _start(graph, repo)
    _bis_umsetzung(graph)
    assert _halt(graph) == ("abschluss_freigabe",)
    return graph, planer, repo, aufgaben


def _branch_da(repo, branch):
    return _git(repo, "branch", "--list", branch).strip() != ""


def test_gruen_haelt_an_abschluss(s4):
    graph, planer, repo, _ = _bis_abschluss(s4)
    frage = _frage(graph)
    assert frage["art"] == "abschluss_freigabe" and frage["erlaubt"] == ["mergen", "nicht_mergen"]
    assert frage["einwaende"] == [] and frage["gesamtreview"]["ok"] is True
    assert frage["branch"].startswith("lauf/") and "mathe.py" in frage["diffstat"]
    assert frage["uebernahme_ziel"].replace("\\", "/").endswith("aufgaben/mini/M2")
    prompt = planer.prompts["gesamtreview"][0]
    assert SPEC["spec"] in prompt and PLAN_OK["plan"] in prompt and "+def plus(a, b):" in prompt
    assert graph.get_state(CFG).values["status"] == "gruen"


def test_mergen_fast_forward_und_uebernahme(s4):
    graph, _, repo, aufgaben = _bis_abschluss(s4)
    state = graph.get_state(CFG).values
    branch, wt = _frage(graph)["branch"], Path(state["worktree"])
    lauf_kopf = _rev(repo, branch)
    erg = _weiter(graph, {"entscheidung": "mergen"})
    assert _halt(graph) == ()
    assert _rev(repo) == lauf_kopf and (repo / "mathe.py").is_file()
    assert (aufgaben / "mini" / "M2" / "test_akzeptanz_m2.py").is_file()
    assert not wt.exists() and not _branch_da(repo, branch)
    a = erg["abschluss"]
    assert a["entscheidung"] == "mergen" and a["merge_commit"] == lauf_kopf and a["aufgeraeumt"] is True
    assert [Path(p).name for p in a["uebernommen"]] == ["test_akzeptanz_m2.py"]
    assert erg["status"] == "gruen" and Path(erg["bericht_pfad"]).is_file()


def test_nicht_mergen_laesst_alles_stehen(s4):
    graph, _, repo, aufgaben = _bis_abschluss(s4)
    basis = _rev(repo)
    state = graph.get_state(CFG).values
    branch = _frage(graph)["branch"]
    erg = _weiter(graph, {"entscheidung": "nicht_mergen"})
    assert _halt(graph) == ()
    assert _rev(repo) == basis and Path(state["worktree"]).exists() and _branch_da(repo, branch)
    assert not (aufgaben / "mini" / "M2").exists()
    assert erg["abschluss"]["entscheidung"] == "nicht_mergen" and erg["abschluss"]["merge_commit"] is None


def test_gesamtreview_major_braucht_begruendung(s4):
    graph, _, repo, _ = _bis_abschluss(s4, Planer(gesamtreview=[GESAMT_MAJOR]))
    basis = _rev(repo)
    assert _frage(graph)["einwaende"] == ["Gesamtreview (Codex) meldet major: Vertrag für negative Zahlen fehlt"]
    _weiter(graph, {"entscheidung": "mergen"})
    assert _halt(graph) == ("abschluss_freigabe",) and _rev(repo) == basis
    assert "begruendung" in _frage(graph)["hinweis"]
    erg = _weiter(graph, {"entscheidung": "mergen", "begruendung": "negative Zahlen sind Folgeaufgabe"})
    assert _halt(graph) == () and erg["abschluss"]["merge_commit"]
    assert erg["einwand_freigaben"][-1]["haltepunkt"] == "abschluss_freigabe"
    assert erg["einwand_freigaben"][-1]["begruendung"] == "negative Zahlen sind Folgeaufgabe"


def test_gesamtreview_fehlt_ist_einwand(s4):
    graph, _, _, _ = _bis_abschluss(s4, Planer(gesamtreview=[None]))
    frage = _frage(graph)
    assert frage["einwaende"] == ["Gesamtreview fehlt: kein Schema"] and frage["gesamtreview"]["ok"] is False
    _weiter(graph, {"entscheidung": "mergen"})
    assert _halt(graph) == ("abschluss_freigabe",)


def test_nicht_mergen_braucht_keine_begruendung(s4):
    graph, _, _, _ = _bis_abschluss(s4, Planer(gesamtreview=[GESAMT_MAJOR]))
    _weiter(graph, {"entscheidung": "nicht_mergen"})
    assert _halt(graph) == ()


def test_angenommen_geht_auch_zum_abschluss(s4):
    repo, aufgaben = s4
    graph, _ = _graph(aufgaben, impl=Implementierer(FALSCH))
    graph.invoke({"repo": str(repo), "aufgabe_id": "M2", "max_runden": 0}, CFG)
    _bis_umsetzung(graph)
    assert _halt(graph) == ("eskalation",)
    _weiter(graph, {"entscheidung": "annehmen"})
    assert _halt(graph) == ("abschluss_freigabe",)
    assert graph.get_state(CFG).values["status"] == "angenommen"
    assert _frage(graph)["offene_befunde"]


def test_rot_und_abbruch_enden_wie_bisher(s4):
    repo, aufgaben = s4
    graph, planer = _graph(aufgaben, impl=Implementierer(FALSCH))
    graph.invoke({"repo": str(repo), "aufgabe_id": "M2", "max_runden": 0}, CFG)
    _bis_umsetzung(graph)
    erg = _weiter(graph, {"entscheidung": "abbrechen"})
    assert _halt(graph) == () and erg["status"] == "abgebrochen" and "abschluss" not in erg
    assert "gesamtreview" not in planer.prompts
    graph2, _ = _graph(aufgaben)
    graph2.invoke({"repo": str(repo), "aufgabe_id": "M2"}, {"configurable": {"thread_id": "t7b"}})
    erg2 = graph2.invoke(Command(resume={"entscheidung": "abbrechen"}), {"configurable": {"thread_id": "t7b"}})
    assert erg2["status"] == "abgebrochen" and "abschluss" not in erg2


def test_merge_abgelehnt_wenn_main_weiter(s4):
    graph, _, repo, aufgaben = _bis_abschluss(s4)
    state = graph.get_state(CFG).values
    branch = _frage(graph)["branch"]
    (repo / "anders.txt").write_text("weiter\n", encoding="utf-8")
    _git(repo, "add", "anders.txt")
    _git(repo, "commit", "-q", "-m", "main läuft weiter")
    weiter = _rev(repo)
    erg = _weiter(graph, {"entscheidung": "mergen"})
    assert _halt(graph) == () and erg["status"] == "merge_abgelehnt"
    assert "Hauptzweig ist weitergelaufen" in erg["abschluss"]["grund"]
    assert _rev(repo) == weiter and not (aufgaben / "mini" / "M2").exists()
    assert Path(state["worktree"]).exists() and _branch_da(repo, branch)


def test_uebernahme_vorhanden_merge_trotzdem(s4):
    """Zweiter Lauf derselben Aufgabe: der Ordner existiert schon, nichts wird überschrieben, gemergt wird."""
    repo, aufgaben = s4
    (aufgaben / "mini" / "M2").mkdir()
    (aufgaben / "mini" / "M2" / "test_alt.py").write_text("alt\n", encoding="utf-8")
    graph, _ = _graph(aufgaben)
    _start(graph, repo)
    _bis_umsetzung(graph)
    erg = _weiter(graph, {"entscheidung": "mergen"})
    assert erg["abschluss"]["merge_commit"] and erg["abschluss"]["uebernommen"] == []
    assert "existiert schon" in erg["abschluss"]["grund"]
    assert sorted(p.name for p in (aufgaben / "mini" / "M2").iterdir()) == ["test_alt.py"]


def test_budget_abschluss_haelt(s4):
    repo, aufgaben = s4
    graph, planer = _graph(aufgaben)
    graph.invoke({"repo": str(repo), "aufgabe_id": "M2", "budget": 11}, CFG)
    _bis_umsetzung(graph)
    assert _halt(graph) == ("budget_abschluss",) and "gesamtreview" not in planer.prompts
    _weiter(graph, {"entscheidung": "mehr"})
    assert _halt(graph) == ("abschluss_freigabe",)


def test_abschluss_ungueltige_antwort(s4):
    graph, _, repo, _ = _bis_abschluss(s4)
    basis = _rev(repo)
    _weiter(graph, {"entscheidung": "vielleicht"})
    assert _halt(graph) == ("abschluss_freigabe",) and _rev(repo) == basis
    assert "ungültige Antwort" in _frage(graph)["hinweis"]
    _weiter(graph, {"entscheidung": "nicht_mergen"})
    assert _halt(graph) == ()


def test_einseitige_tuer_braucht_begruendung(s4):
    graph, _, _, _ = _bis_abschluss(s4, impl=Implementierer(MIT_RMTREE))
    frage = _frage(graph)
    assert frage["tuer"]["urteil"] == "einseitig"
    assert any(e.startswith("Tür einseitig: Löschen von Daten oder Dateien") for e in frage["einwaende"])
    _weiter(graph, {"entscheidung": "mergen"})
    assert _halt(graph) == ("abschluss_freigabe",)


def test_tuer_im_payload_der_freigabe(s4):
    graph, _, _, _ = _bis_abschluss(s4, Planer(gesamtreview=[GESAMT_EINSEITIG]))
    tuer = _frage(graph)["tuer"]
    assert tuer["urteil"] == "einseitig" and tuer["radius"] == "System" and tuer["uneinig"] is True
    assert tuer["selbst"]["urteil"] == "zweiseitig" and tuer["codex"]["urteil"] == "einseitig"
    assert tuer["faelle"] == ["Löschen von Daten: mathe.py"]


def _mit_skip(grund):
    def extra(wt):
        (wt / "tests" / "test_skip.py").write_text(
            f"import pytest\n\n\n@pytest.mark.skip(reason={grund!r})\ndef test_s():\n    pass\n", encoding="utf-8")
    return extra


def test_skips_sind_einwand(s4):
    graph, _, _, _ = _bis_abschluss(s4, impl=Implementierer(RICHTIG, extra={0: _mit_skip("fixture fehlt")}))
    frage = _frage(graph)
    assert "1 übersprungen" in frage["tests_zeile"]
    assert any(e.startswith("Tests übersprungen: 1") for e in frage["einwaende"])


def test_plattform_skip_ist_kein_einwand_im_graphen(s4):
    graph, _, _, _ = _bis_abschluss(s4, impl=Implementierer(RICHTIG, extra={0: _mit_skip("plattform: nur Linux")}))
    frage = _frage(graph)
    assert "1 übersprungen" in frage["tests_zeile"] and frage["einwaende"] == []


def test_stufe3_unveraendert(umgebung):
    repo, aufgaben = umgebung
    from tests.test_graph_s2 import _codex, _pruefer
    abh = _abh(aufgaben, implementierer=Implementierer(RICHTIG), pruefer=_pruefer(), codex=_codex())
    graph = baue_graph_s3(abh, checkpointer=InMemorySaver())
    erg = graph.invoke({"repo": str(repo), "aufgabe_id": "M1"}, CFG)
    assert erg["status"] == "gruen" and graph.get_state(CFG).next == () and "abschluss" not in erg


def test_zielzweig_gemerkt(s4):
    graph, _, _, _ = _bis_abschluss(s4)
    assert graph.get_state(CFG).values["zielzweig"] == "main"



def test_commit_nach_pruefung_wird_nicht_gemergt(s4):
    """Codex-Verifier S7-01: gemergt wird genau der Stand, den Tests und Gesamtreview gesehen haben."""
    graph, _, repo, aufgaben = _bis_abschluss(s4)
    wt = Path(graph.get_state(CFG).values["worktree"])
    basis = _rev(repo)
    (wt / "spaet.py").write_text("y = 2\n", encoding="utf-8")
    _git(wt, "add", "spaet.py")
    _git(wt, "commit", "-q", "-m", "nach der Prüfung")
    erg = _weiter(graph, {"entscheidung": "mergen"})
    assert erg["status"] == "merge_abgelehnt" and "seit der Prüfung" in erg["abschluss"]["grund"]
    assert _rev(repo) == basis and not (aufgaben / "mini" / "M2").exists()


def test_schreibfehler_bei_uebernahme_bricht_nicht_ab(s4, monkeypatch):
    """Codex-Verifier S7-02: Nach dem Merge darf ein Schreibfehler den Abschluss nicht ohne Bericht abbrechen."""
    from entwicklung import abschluss as ab

    def kaputt(quelle, ziel):
        raise PermissionError("Zugriff verweigert")

    graph, _, repo, _ = _bis_abschluss(s4)
    monkeypatch.setattr(ab, "uebernimm_tests", kaputt)
    erg = _weiter(graph, {"entscheidung": "mergen"})
    assert _halt(graph) == () and erg["abschluss"]["merge_commit"] == _rev(repo)
    assert "nicht übernommen" in erg["abschluss"]["grund"] and "Zugriff verweigert" in erg["abschluss"]["grund"]
    assert erg["abschluss"]["aufgeraeumt"] is True and Path(erg["bericht_pfad"]).is_file()


def test_ohne_pruefanker_kein_merge(s4):
    """Codex-Verifier Runde 2: Fehlt der geprüfte Commit im Zustand, wird nicht gemergt (kein stiller Durchlass)."""
    graph, _, repo, _ = _bis_abschluss(s4)
    basis = _rev(repo)
    graph.update_state(CFG, {"geprueft_kopf": ""}, as_node="gesamtreview")
    assert _halt(graph) == ("abschluss_freigabe",)
    erg = _weiter(graph, {"entscheidung": "mergen"})
    assert erg["status"] == "merge_abgelehnt" and "geprüfter Stand unbekannt" in erg["abschluss"]["grund"]
    assert _rev(repo) == basis


SPUR_TEST = (
    "import os\nfrom pathlib import Path\n\n\n"
    "def test_schreibt_akzeptanz_um():\n"
    "    for d in Path(os.environ['ENTWICKLUNG_BERICHTE_DIR']).glob('*/akzeptanz/M2/*.py'):\n"
    "        d.write_text('def test_x():\\n    assert True\\n', encoding='utf-8')\n")


def test_eigener_test_aendert_akzeptanztests_ist_grenzverletzung(s4):
    """Codex-Review Export F1: Testcode des Implementierers darf die freigegebenen Tests nicht unbemerkt ersetzen."""
    repo, aufgaben = s4

    def spur(wt):
        (wt / "tests" / "test_spur.py").write_text(SPUR_TEST, encoding="utf-8")

    graph, _ = _graph(aufgaben, impl=Implementierer(RICHTIG, extra={0: spur}))
    _start(graph, repo)
    erg = _bis_umsetzung(graph)
    assert erg["status"] == "grenzverletzung"
    assert any("freigegebenen Fassung" in g for g in erg["grenzverletzungen"])


def test_commit_waehrend_gesamtreview_wird_nicht_gemergt(s4):
    """Codex-Review Export F3: Der Prüfanker ist der Stand vor dem Gesamtreview, nicht danach."""
    def commit(wt):
        (wt / "spaet.py").write_text("y = 2\n", encoding="utf-8")
        _git(wt, "add", "spaet.py")
        _git(wt, "commit", "-q", "-m", "während des Reviews")

    graph, _, repo, _ = _bis_abschluss(s4, Planer(extra={"gesamtreview": commit}))
    basis = _rev(repo)
    erg = _weiter(graph, {"entscheidung": "mergen"})
    assert erg["status"] == "merge_abgelehnt" and _rev(repo) == basis
