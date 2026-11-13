from pathlib import Path

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from entwicklung import pfade
from entwicklung.graph_s4 import AKZ_VERSUCHE, MAX_KLAERUNGEN, baue_graph_s4
from tests.test_graph_s1 import _abh, umgebung  # noqa: F401  (umgebung ist eine Fixture)
from tests.test_graph_s2 import _codex, _pruefer
from tests.test_graph_s3 import FALSCH, RICHTIG, Implementierer

WUNSCH = "# M2: plus für große Zahlen\nplus soll auch mit großen Zahlen rechnen.\n"
KLAR = {"klar": True, "verstaendnis": "plus für große Zahlen", "fragen": []}
FRAGEN = {"klar": False, "verstaendnis": "unklar", "fragen": ["Auch negative Zahlen?"]}
SPEC = {"spec": "# M2: plus\n## Vertrag\n`mathe.plus(a, b)` gibt a + b zurück.\n",
        "schnittstellen": [{"modul": "mathe", "namen": ["plus"]}], "annahmen": ["nur ganze Zahlen"]}
GEN_TEST = "def test_plus_gross():\n    from mathe import plus\n    assert plus(20, 22) == 42\n"
TESTS_OK = {"dateien": [{"name": "test_akzeptanz_m2.py", "inhalt": GEN_TEST}]}
TESTS_MODULEBENE = {"dateien": [{"name": "test_akzeptanz_m2.py",
                                 "inhalt": "from mathe import plus\n\n\ndef test_x():\n    assert plus(1, 1) == 2\n"}]}
TESTS_MIT_SKIP = {"dateien": [{"name": "test_akzeptanz_m2.py", "inhalt": GEN_TEST
                               + "\n\ndef test_symlink():\n    import pytest\n    pytest.skip('hier nicht')\n"}]}
TESTS_SETUP_FEHLER = {"dateien": [{"name": "test_akzeptanz_m2.py",
                                   "inhalt": "def test_x(gibt_es_nicht):\n    assert True\n"}]}
TESTS_MIT_SPUR = {"dateien": [{"name": "test_akzeptanz_m2.py", "inhalt": (
    "from pathlib import Path\n\n\ndef test_spur():\n"
    "    (Path(__file__).resolve().parents[2] / 'spur.txt').write_text('x', encoding='utf-8')\n"
    "    from mathe import plus\n    assert plus(20, 22) == 42\n")}]}
TESTS_SCHON_GRUEN = {"dateien": [{"name": "test_akzeptanz_m2.py", "inhalt": "def test_x():\n    assert 1 + 1 == 2\n"}]}
PRUEF_OK = {"verdict": "PASS", "punkte": []}
PLAN_OK = {"plan": "# Plan M2\n## Schritt 1: mathe.py\nTest zuerst (tests/test_mathe.py), dann plus.\n",
           "dateien": ["mathe.py", "tests/test_mathe.py"]}
PLAN_OHNE_SCHNITTSTELLE = {"plan": "# Plan\n## Schritt 1\nirgendwas\n", "dateien": ["ports.toml"]}
PRUEF_PUNKT = {"verdict": "FAIL", "punkte": [{"schwere": "major", "aussage": "Negative Zahlen fehlen"}]}
GESAMT_OK = {"verdict": "PASS", "zusammenfassung": "erfüllt die Spec", "spec_erfuellt": True, "restpunkte": [],
             "tuer": {"urteil": "zweiseitig", "radius": "Datei", "begruendung": "nur Code", "faelle": [],
                      "selbstbewertung_stimmt": True}}  # Stufe 7: Gesamtreview durch Codex


class Planer:
    """Fake für claude_strukturiert/codex_strukturiert: je Name eine Liste von Ergebnissen (die letzte bleibt)."""

    def __init__(self, extra=None, **antworten):
        standard = {"klaeren": [KLAR], "spec_schreiben": [SPEC], "akzeptanz_schreiben": [TESTS_OK],
                    "spec_pruefer": [PRUEF_OK], "spec_codex": [PRUEF_OK], "plan_schreiben": [PLAN_OK],
                    "plan_codex": [PRUEF_OK], "gesamtreview": [GESAMT_OK]}
        self.antworten = {**standard, **antworten}
        self.prompts: dict[str, list[str]] = {}
        self.stufen: dict[str, list[tuple]] = {}
        self.extra = extra or {}

    def __call__(self, name, prompt, cwd, schema, modell="sonnet", timeout=600, effort=None, runner=None):
        self.prompts.setdefault(name, []).append(prompt)
        self.stufen.setdefault(name, []).append((modell, effort))
        if name in self.extra:
            self.extra[name](Path(cwd))
        liste = self.antworten[name]
        daten = liste.pop(0) if len(liste) > 1 else liste[0]
        return {"name": name, "ok": daten is not None, "daten": daten,
                "fehler": None if daten is not None else "kein Schema", "dauer_s": 0.1}

    def codex(self, name, prompt, cwd, schema, timeout=900, effort=None, runner=None):
        return self(name, prompt, cwd, schema, modell=None, effort=effort)


@pytest.fixture
def s4(umgebung):
    repo, aufgaben = umgebung
    (aufgaben / "mini" / "M2.md").write_text(WUNSCH, encoding="utf-8")
    return repo, aufgaben


def _graph(aufgaben, planer=None, impl=None):
    planer = planer or Planer()
    abh = _abh(aufgaben, implementierer=impl or Implementierer(RICHTIG), pruefer=_pruefer(), codex=_codex(),
               planer=planer, planer_codex=planer.codex)
    return baue_graph_s4(abh, checkpointer=InMemorySaver()), planer


CFG = {"configurable": {"thread_id": "t4"}}


def _start(graph, repo):
    return graph.invoke({"repo": str(repo), "aufgabe_id": "M2"}, CFG)


def _weiter(graph, antwort):
    return graph.invoke(Command(resume=antwort), CFG)


def _halt(graph):
    return graph.get_state(CFG).next


def _bis_umsetzung(graph):
    """Spec und Plan freigeben (ab Stufe 4b zwei Freigaben)."""
    _weiter(graph, {"entscheidung": "freigeben"})
    assert _halt(graph) == ("plan_freigabe",)
    return _weiter(graph, {"entscheidung": "freigeben"})


def test_klar_ohne_fragen_bis_freigabe(s4):
    repo, aufgaben = s4
    graph, planer = _graph(aufgaben)
    erg = _start(graph, repo)
    assert _halt(graph) == ("spec_freigabe",)
    assert "fragen" not in planer.prompts
    frage = erg["__interrupt__"][0].value
    assert frage["art"] == "spec_freigabe" and frage["annahmen"] == ["nur ganze Zahlen"]
    spec = Path(frage["spec_pfad"])
    assert spec.read_text(encoding="utf-8") == SPEC["spec"] and spec.is_relative_to(pfade.berichte_dir())
    assert (Path(frage["akz_ordner"]) / "test_akzeptanz_m2.py").read_text(encoding="utf-8") == GEN_TEST
    assert frage["tests"] == ["test_plus_gross"]
    assert frage["probe"] == {"erwartet": 1, "gesammelt": 1, "bestanden": 0, "uebersprungen": 0, "fehler": 0}
    assert {p["pruefer"] for p in erg["spec_pruefungen"]} == {"claude", "codex"}


def test_fragen_schleife(s4):
    repo, aufgaben = s4
    graph, planer = _graph(aufgaben, Planer(klaeren=[FRAGEN, FRAGEN, KLAR]))
    erg = _start(graph, repo)
    assert _halt(graph) == ("fragen",)
    assert erg["__interrupt__"][0].value["fragen"] == ["Auch negative Zahlen?"]
    _weiter(graph, {"antwort": "ja, auch negative"})
    assert _halt(graph) == ("fragen",)
    _weiter(graph, {"antwort": "nur ganze Zahlen"})
    assert _halt(graph) == ("spec_freigabe",)
    assert len(planer.prompts["klaeren"]) == 3
    spec_prompt = planer.prompts["spec_schreiben"][0]
    assert "ja, auch negative" in spec_prompt and "nur ganze Zahlen" in spec_prompt


def test_max_klaerungen_dann_spec(s4):
    repo, aufgaben = s4
    graph, planer = _graph(aufgaben, Planer(klaeren=[FRAGEN]))
    _start(graph, repo)
    for i in range(MAX_KLAERUNGEN):
        assert _halt(graph) == ("fragen",)
        _weiter(graph, {"antwort": f"Antwort {i}"})
    assert _halt(graph) == ("spec_freigabe",)
    assert len(planer.prompts["klaeren"]) == MAX_KLAERUNGEN + 1


@pytest.mark.parametrize("antwort", [{}, {"antwort": "  "}, {"antwort": 3}, "ja", {"entscheidung": "freigeben"}])
def test_leere_antwort_haelt_erneut_an_fragen(s4, antwort):
    repo, aufgaben = s4
    graph, planer = _graph(aufgaben, Planer(klaeren=[FRAGEN, KLAR]))
    _start(graph, repo)
    erg = _weiter(graph, antwort)
    assert _halt(graph) == ("fragen",)
    if antwort != {}:  # {} zählt in LangGraph 1.2.10 nicht als Antwort: Originalfrage ohne Hinweis (Stufe 3)
        assert erg["__interrupt__"][0].value["hinweis"]
    assert len(planer.prompts["klaeren"]) == 1


@pytest.mark.parametrize("antwort", [{}, {"entscheidung": "aendern"}, {"entscheidung": "aendern", "hinweis": " "},
                                     {"entscheidung": "weiter"}, {"antwort": "gut"}])
def test_leere_antwort_haelt_erneut_an_freigabe(s4, antwort):
    repo, aufgaben = s4
    graph, planer = _graph(aufgaben)
    _start(graph, repo)
    erg = _weiter(graph, antwort)
    assert _halt(graph) == ("spec_freigabe",)
    if antwort != {}:
        assert erg["__interrupt__"][0].value["hinweis"]
    assert len(planer.prompts["spec_schreiben"]) == 1


def test_freigeben_dann_umsetzung_gruen(s4):
    repo, aufgaben = s4
    impl = Implementierer(RICHTIG)
    graph, planer = _graph(aufgaben, impl=impl)
    _start(graph, repo)
    erg = _bis_umsetzung(graph)
    assert erg["status"] == "gruen" and erg["freigabe"] == "freigeben" and erg["plan_freigabe"] == "freigeben"
    assert SPEC["spec"] in impl.prompts[0] and "assert plus(20, 22)" not in impl.prompts[0]
    akz = erg["testergebnis"]["akzeptanz"]
    assert akz == {"gesammelt": 3, "bestanden": 3, "erwartet": 3, "uebersprungen": 0, "fehler": 0}  # M1 (2, Regression) + erzeugter Test (1)
    assert [Path(d).name for d in erg["akzeptanz_dirs"]] == ["M1", "M2"]
    assert erg["aufgabe_text"] == SPEC["spec"] + "\n\n## Plan\n\n" + PLAN_OK["plan"] and erg["wunsch"] == WUNSCH


def test_aendern_schreibt_spec_neu(s4):
    repo, aufgaben = s4
    planer = Planer(spec_pruefer=[PRUEF_PUNKT, PRUEF_OK])
    graph, planer = _graph(aufgaben, planer)
    _start(graph, repo)
    erg = _weiter(graph, {"entscheidung": "aendern", "hinweis": "Bitte auch negative Zahlen"})
    assert _halt(graph) == ("spec_freigabe",)
    zweiter = planer.prompts["spec_schreiben"][1]
    assert "Bitte auch negative Zahlen" in zweiter and "Negative Zahlen fehlen" in zweiter and SPEC["spec"] in zweiter
    assert len(erg["spec_pruefungen"]) == 2  # frisch, nicht 4
    assert all(not p["punkte"] for p in erg["spec_pruefungen"])
    assert erg["spec_runde"] == 1


def test_import_auf_modulebene_zweiter_versuch_dann_fehler(s4):
    repo, aufgaben = s4
    graph, planer = _graph(aufgaben, Planer(akzeptanz_schreiben=[TESTS_MODULEBENE]))
    erg = _start(graph, repo)
    assert erg["status"] == "akzeptanz_fehler" and erg["akz_versuch"] == AKZ_VERSUCHE
    assert len(planer.prompts["akzeptanz_schreiben"]) == AKZ_VERSUCHE
    assert "Modulebene" in planer.prompts["akzeptanz_schreiben"][1]  # Gründe gingen in den zweiten Versuch
    assert _halt(graph) == () and Path(erg["bericht_pfad"]).exists()


def test_zweiter_versuch_kann_gelingen(s4):
    repo, aufgaben = s4
    graph, planer = _graph(aufgaben, Planer(akzeptanz_schreiben=[TESTS_MODULEBENE, TESTS_OK]))
    _start(graph, repo)
    assert _halt(graph) == ("spec_freigabe",)


def test_probe_gegen_main_gruen_zaehlt_als_fehlversuch(s4):
    repo, aufgaben = s4
    graph, planer = _graph(aufgaben, Planer(akzeptanz_schreiben=[TESTS_SCHON_GRUEN, TESTS_OK]))
    _start(graph, repo)
    assert _halt(graph) == ("spec_freigabe",)
    assert "gegen main" in planer.prompts["akzeptanz_schreiben"][1]


def test_planer_schreibt_ist_grenzverletzung(s4):
    repo, aufgaben = s4
    impl = Implementierer(RICHTIG)
    planer = Planer(extra={"spec_schreiben": lambda wt: (wt / "notiz.txt").write_text("x", encoding="utf-8")})
    graph, planer = _graph(aufgaben, planer, impl=impl)
    erg = _start(graph, repo)
    assert erg["status"] == "grenzverletzung" and any("notiz.txt" in g for g in erg["grenzverletzungen"])
    assert impl.prompts == [] and "akzeptanz_schreiben" not in planer.prompts


def test_planer_fehler_ist_agent_fehler(s4):
    repo, aufgaben = s4
    graph, planer = _graph(aufgaben, Planer(klaeren=[None]))
    erg = _start(graph, repo)
    assert erg["status"] == "agent_fehler" and "klaeren" in erg["planung_fehler"]


def test_abbrechen_an_fragen_und_freigabe(s4):
    repo, aufgaben = s4
    graph, _ = _graph(aufgaben, Planer(klaeren=[FRAGEN]))
    _start(graph, repo)
    erg = _weiter(graph, {"entscheidung": "abbrechen"})
    assert erg["status"] == "abgebrochen" and _halt(graph) == ()
    graph, _ = _graph(aufgaben)
    _start(graph, repo)
    erg = _weiter(graph, {"entscheidung": "abbrechen"})
    assert erg["status"] == "abgebrochen" and _halt(graph) == ()


def test_keine_akzeptanzdatei_im_worktree_vor_testlauf(s4):
    repo, aufgaben = s4
    gesehen = []

    def nachsehen(wt):
        gesehen.extend(str(p.relative_to(wt)) for p in wt.rglob("test_akzeptanz*"))
    impl = Implementierer(RICHTIG, extra={0: nachsehen})
    graph, _ = _graph(aufgaben, impl=impl)
    _start(graph, repo)
    _bis_umsetzung(graph)
    assert gesehen == []


def test_probe_mit_skip_zaehlt_als_fehlversuch(s4):
    """Ein Test, der auf diesem Rechner übersprungen wird, prüft hier nichts (echter Lauf 20261020-120157)."""
    repo, aufgaben = s4
    graph, planer = _graph(aufgaben, Planer(akzeptanz_schreiben=[TESTS_MIT_SKIP, TESTS_OK]))
    _start(graph, repo)
    assert _halt(graph) == ("spec_freigabe",)
    assert "übersprungen" in planer.prompts["akzeptanz_schreiben"][1]


def test_probe_setup_fehler_zaehlt_als_fehlversuch(s4):
    """Codex F4: Fixture fehlt (--noconftest) – der Test könnte nie grün werden."""
    repo, aufgaben = s4
    graph, planer = _graph(aufgaben, Planer(akzeptanz_schreiben=[TESTS_SETUP_FEHLER, TESTS_OK]))
    _start(graph, repo)
    assert _halt(graph) == ("spec_freigabe",)
    assert "Fehler" in planer.prompts["akzeptanz_schreiben"][1]


def test_probe_laeuft_ausserhalb_des_worktrees(s4):
    """Codex F5: was der Probe-Test schreibt, landet nie im Worktree des Implementierers."""
    repo, aufgaben = s4
    graph, _ = _graph(aufgaben, Planer(akzeptanz_schreiben=[TESTS_MIT_SPUR]))
    erg = _start(graph, repo)
    assert _halt(graph) == ("spec_freigabe",), erg.get("grenzverletzungen")
    assert not (Path(erg["worktree"]) / "spur.txt").exists()


def test_veraenderte_erzeugte_tests_sind_grenzverletzung(s4):
    """Codex F1: Testcode des Implementierers könnte die Tests unter berichte/ ersetzen."""
    repo, aufgaben = s4
    ziel = {}

    def ersetzen(wt):
        datei = Path(ziel["akz_ordner"]) / "test_akzeptanz_m2.py"
        datei.write_text("def test_plus_gross():\n    assert True\n", encoding="utf-8")
    impl = Implementierer(RICHTIG, extra={0: ersetzen})
    graph, _ = _graph(aufgaben, impl=impl)
    erg = _start(graph, repo)
    ziel["akz_ordner"] = erg["akz_ordner"]
    erg = _bis_umsetzung(graph)
    assert erg["status"] == "grenzverletzung"
    assert any("test_akzeptanz_m2.py" in g and "freigegeben" in g for g in erg["grenzverletzungen"])


def test_aendern_mit_gescheiterten_tests_laesst_keine_alten_stehen(s4):
    """Codex F7: nach aendern dürfen Probe und Ordner der vorigen Fassung nicht als Beleg stehen bleiben."""
    repo, aufgaben = s4
    graph, _ = _graph(aufgaben, Planer(akzeptanz_schreiben=[TESTS_OK, TESTS_MODULEBENE]))
    _start(graph, repo)
    erg = _weiter(graph, {"entscheidung": "aendern", "hinweis": "anders"})
    assert erg["status"] == "akzeptanz_fehler"
    assert erg.get("akz_ordner") is None and erg.get("akz_probe") is None and erg.get("akz_dateien") == []



def test_spec_freigeben_dann_plan_freigabe(s4):
    repo, aufgaben = s4
    graph, planer = _graph(aufgaben)
    _start(graph, repo)
    erg = _weiter(graph, {"entscheidung": "freigeben"})
    assert _halt(graph) == ("plan_freigabe",)
    frage = erg["__interrupt__"][0].value
    assert frage["art"] == "plan_freigabe" and frage["dateien"] == PLAN_OK["dateien"]
    plan = Path(frage["plan_pfad"])
    assert plan.read_text(encoding="utf-8") == PLAN_OK["plan"] and plan.is_relative_to(pfade.berichte_dir())
    assert SPEC["spec"] in planer.prompts["plan_schreiben"][0] and PLAN_OK["plan"] in planer.prompts["plan_codex"][0]
    assert [p["pruefer"] for p in erg["plan_pruefungen"]] == ["codex"] and frage["pruefpunkte"] == []


def test_plan_freigeben_dann_umsetzung(s4):
    repo, aufgaben = s4
    impl = Implementierer(RICHTIG)
    graph, _ = _graph(aufgaben, impl=impl)
    _start(graph, repo)
    erg = _bis_umsetzung(graph)
    assert erg["status"] == "gruen"
    assert SPEC["spec"] in impl.prompts[0] and "## Plan" in impl.prompts[0] and PLAN_OK["plan"] in impl.prompts[0]
    assert "assert plus(20, 22)" not in impl.prompts[0]


def test_fix_prompt_enthaelt_plan(s4):
    repo, aufgaben = s4
    impl = Implementierer(FALSCH, RICHTIG)
    graph, _ = _graph(aufgaben, impl=impl)
    _start(graph, repo)
    erg = _bis_umsetzung(graph)
    assert erg["status"] == "gruen" and len(impl.prompts) == 2
    assert "Fix-Runde 1" in impl.prompts[1] and PLAN_OK["plan"] in impl.prompts[1]


def test_plan_aendern_nur_plan_neu(s4):
    repo, aufgaben = s4
    planer = Planer(plan_codex=[PRUEF_PUNKT, PRUEF_OK])
    graph, planer = _graph(aufgaben, planer)
    _start(graph, repo)
    vorher = _weiter(graph, {"entscheidung": "freigeben"})
    erg = _weiter(graph, {"entscheidung": "aendern", "hinweis": "erst die Tests für negative Zahlen"})
    assert _halt(graph) == ("plan_freigabe",)
    zweiter = planer.prompts["plan_schreiben"][1]
    assert "erst die Tests für negative Zahlen" in zweiter and "Negative Zahlen fehlen" in zweiter
    assert PLAN_OK["plan"] in zweiter
    for feld in ("spec", "spec_runde", "akz_dateien", "akz_probe", "akz_ordner"):
        assert erg[feld] == vorher[feld], feld
    assert len(planer.prompts["spec_schreiben"]) == 1 and len(planer.prompts["akzeptanz_schreiben"]) == 1
    assert erg["plan_runde"] == 1 and len(erg["plan_pruefungen"]) == 1 and not erg["plan_pruefungen"][0]["punkte"]


def test_plan_gruende_in_der_freigabe(s4):
    repo, aufgaben = s4
    graph, _ = _graph(aufgaben, Planer(plan_schreiben=[PLAN_OHNE_SCHNITTSTELLE]))
    _start(graph, repo)
    erg = _weiter(graph, {"entscheidung": "freigeben"})
    assert _halt(graph) == ("plan_freigabe",)
    code = [p for p in erg["__interrupt__"][0].value["pruefpunkte"] if p["pruefer"] == "code"]
    assert any("mathe.plus" in p["aussage"] for p in code) and any("ports.toml" in p["aussage"] for p in code)


def test_tests_nachbessern(s4):
    repo, aufgaben = s4
    graph, planer = _graph(aufgaben, Planer(akzeptanz_schreiben=[TESTS_OK, TESTS_OK]))
    vorher = _start(graph, repo)
    erg = _weiter(graph, {"entscheidung": "tests_nachbessern", "hinweis": "auch negative Zahlen testen"})
    assert _halt(graph) == ("spec_freigabe",)
    zweiter = planer.prompts["akzeptanz_schreiben"][1]
    assert "auch negative Zahlen testen" in zweiter and GEN_TEST in zweiter
    assert erg["spec"] == vorher["spec"] and erg["spec_runde"] == vorher["spec_runde"] == 0
    assert len(planer.prompts["spec_schreiben"]) == 1
    assert len(erg["spec_pruefungen"]) == 2 and len(planer.prompts["spec_pruefer"]) == 2


@pytest.mark.parametrize("antwort", [{}, {"entscheidung": "aendern"}, {"entscheidung": "tests_nachbessern",
                                                                       "hinweis": "x"}, {"entscheidung": "weiter"}])
def test_ungueltig_an_plan_freigabe_haelt_erneut(s4, antwort):
    repo, aufgaben = s4
    graph, planer = _graph(aufgaben)
    _start(graph, repo)
    _weiter(graph, {"entscheidung": "freigeben"})
    erg = _weiter(graph, antwort)
    assert _halt(graph) == ("plan_freigabe",)
    if antwort != {}:
        assert erg["__interrupt__"][0].value["hinweis"]
    assert len(planer.prompts["plan_schreiben"]) == 1


def test_tests_nachbessern_ohne_hinweis_haelt_erneut(s4):
    repo, aufgaben = s4
    graph, planer = _graph(aufgaben)
    _start(graph, repo)
    erg = _weiter(graph, {"entscheidung": "tests_nachbessern"})
    assert _halt(graph) == ("spec_freigabe",) and erg["__interrupt__"][0].value["hinweis"]
    assert len(planer.prompts["akzeptanz_schreiben"]) == 1


def test_abbrechen_an_plan_freigabe(s4):
    repo, aufgaben = s4
    graph, _ = _graph(aufgaben)
    _start(graph, repo)
    _weiter(graph, {"entscheidung": "freigeben"})
    erg = _weiter(graph, {"entscheidung": "abbrechen"})
    assert erg["status"] == "abgebrochen" and _halt(graph) == () and Path(erg["bericht_pfad"]).exists()



def test_alter_lauf_ohne_plan_runde(s4):
    """L2-005: Ein Lauf, der unter Stufe 4a angelegt wurde, kennt plan_runde nicht."""
    repo, aufgaben = s4
    graph, _ = _graph(aufgaben)
    _start(graph, repo)
    graph.update_state(CFG, {"plan_runde": None})
    _weiter(graph, {"entscheidung": "freigeben"})
    assert _halt(graph) == ("plan_freigabe",)


# ---------------------------------------------------------------------------------------------- Stufe 6b-1
CODEX_MAJOR = {"verdict": "FAIL", "punkte": [{"schwere": "major", "aussage": "Idempotenz widerspricht der ./-Regel"}]}
CODEX_MINOR = {"verdict": "PASS", "punkte": [{"schwere": "minor", "aussage": "Kleinigkeit"}]}
EINWAND = "Codex (GPT) meldet major: Idempotenz widerspricht der ./-Regel"


def test_codex_einwaende():
    from entwicklung.graph_s4 import codex_einwaende
    punkte = [{"pruefer": "codex", "schwere": "major", "aussage": "A"},
              {"pruefer": "claude", "schwere": "major", "aussage": "B"},
              {"pruefer": "codex", "schwere": "minor", "aussage": "C"}]
    assert codex_einwaende(punkte) == ["Codex (GPT) meldet major: A"] and codex_einwaende(None) == []


def test_spec_freigabe_codex_major_braucht_begruendung(s4):
    repo, aufgaben = s4
    graph, _ = _graph(aufgaben, Planer(spec_codex=[CODEX_MAJOR]))
    erg = _start(graph, repo)
    assert erg["__interrupt__"][0].value["einwaende"] == [EINWAND]
    erg = _weiter(graph, {"entscheidung": "freigeben"})
    assert _halt(graph) == ("spec_freigabe",)
    hinweis = erg["__interrupt__"][0].value["hinweis"]
    assert "begruendung" in hinweis and "Codex" in hinweis
    _weiter(graph, {"entscheidung": "freigeben", "begruendung": "   "})
    assert _halt(graph) == ("spec_freigabe",)
    _weiter(graph, {"entscheidung": "freigeben", "begruendung": " Widerspruch geprüft: Satz gestrichen "})
    assert _halt(graph) == ("plan_freigabe",)
    assert graph.get_state(CFG).values["einwand_freigaben"] == [
        {"haltepunkt": "spec_freigabe", "entscheidung": "freigeben", "einwaende": [EINWAND],
         "begruendung": "Widerspruch geprüft: Satz gestrichen"}]


def test_plan_freigabe_codex_major_braucht_begruendung(s4):
    repo, aufgaben = s4
    graph, _ = _graph(aufgaben, Planer(plan_codex=[CODEX_MAJOR]))
    _start(graph, repo)
    erg = _weiter(graph, {"entscheidung": "freigeben"})
    assert _halt(graph) == ("plan_freigabe",) and erg["__interrupt__"][0].value["einwaende"] == [EINWAND]
    _weiter(graph, {"entscheidung": "freigeben"})
    assert _halt(graph) == ("plan_freigabe",)
    erg = _weiter(graph, {"entscheidung": "freigeben", "begruendung": "Plan deckt das ab"})
    assert erg["status"] == "gruen"
    assert [e["haltepunkt"] for e in erg["einwand_freigaben"]] == ["plan_freigabe"]


def test_codex_minor_und_claude_major_sperren_nicht(s4):
    repo, aufgaben = s4
    graph, _ = _graph(aufgaben, Planer(spec_pruefer=[PRUEF_PUNKT], spec_codex=[CODEX_MINOR]))
    erg = _start(graph, repo)
    assert erg["__interrupt__"][0].value["einwaende"] == []
    _weiter(graph, {"entscheidung": "freigeben"})
    assert _halt(graph) == ("plan_freigabe",)
    assert not graph.get_state(CFG).values.get("einwand_freigaben")


def test_aendern_trotz_codex_major_ohne_begruendung(s4):
    repo, aufgaben = s4
    # ab 6c bewertet die Nachprüfung den alten Punkt; ohne Bewertung bliebe er offen und damit ein Einwand
    geloest = {**PRUEF_OK, "alte_punkte": [{"nr": 1, "status": "geloest", "grund": "Satz gestrichen"}]}
    graph, _ = _graph(aufgaben, Planer(spec_codex=[CODEX_MAJOR, geloest]))
    _start(graph, repo)
    erg = _weiter(graph, {"entscheidung": "aendern", "hinweis": "Idempotenz-Satz streichen"})
    assert _halt(graph) == ("spec_freigabe",) and erg["spec_runde"] == 1
    assert erg["__interrupt__"][0].value["einwaende"] == []


def test_einwaende_aus_der_antwort_werden_gespeichert(s4):
    """Die Einwände der Berater kommen vom Server mit der Antwort; der Graph legt sie mit der Begründung ab."""
    repo, aufgaben = s4
    graph, _ = _graph(aufgaben)
    _start(graph, repo)
    _weiter(graph, {"entscheidung": "freigeben", "begruendung": "geprüft", "einwaende": ["Astra rät zu aendern"]})
    assert graph.get_state(CFG).values["einwand_freigaben"][0]["einwaende"] == ["Astra rät zu aendern"]
    _weiter(graph, {"entscheidung": "freigeben", "einwaende": "kein Liste"})  # kein list[str]: gilt als leer
    assert len(graph.get_state(CFG).values["einwand_freigaben"]) == 1



def test_mitgebrachte_einwaende_brauchen_begruendung(s4):
    """Codex 6b-1 F-002: Auch Einwände, die mit der Antwort kommen (Räte), sperren Freigeben ohne Begründung."""
    repo, aufgaben = s4
    graph, _ = _graph(aufgaben)
    _start(graph, repo)
    erg = _weiter(graph, {"entscheidung": "freigeben", "einwaende": ["Astra rät zu aendern"]})
    assert _halt(graph) == ("spec_freigabe",) and "Astra rät zu aendern" in erg["__interrupt__"][0].value["hinweis"]
    _weiter(graph, {"entscheidung": "freigeben", "einwaende": ["Astra rät zu aendern"], "begruendung": "geprüft"})
    assert _halt(graph) == ("plan_freigabe",)
    _weiter(graph, {"entscheidung": "freigeben", "einwaende": ["Fable empfiehlt aendern, Astra freigeben"]})
    assert _halt(graph) == ("plan_freigabe",)



# ---------------------------------------------------------------------------------------------- 6b-2 Modellstufen
CODEX_SCHWER = {"verdict": "PASS", "punkte": [], "komplexitaet": "schwer", "komplexitaet_grund": "Dateivertrag"}


class ImplMitStufe(Implementierer):
    def __init__(self, *codes):
        super().__init__(*codes)
        self.stufen = []

    def __call__(self, prompt, wt, python, modell="sonnet", timeout=600, effort=None, runner=None):
        self.stufen.append((modell, effort, timeout))
        return super().__call__(prompt, wt, python, modell, timeout, effort, runner)


def _pruefer_liste(liste):
    from tests.test_graph_s2 import _ok

    def pruefer(rolle, prompt, wt, modell="sonnet", timeout=600, effort=None, runner=None):
        liste.append((rolle, modell, effort, timeout))
        return _ok(rolle)
    return pruefer


def _graph_stufen(aufgaben, planer, impl, liste):
    abh = _abh(aufgaben, implementierer=impl, pruefer=_pruefer_liste(liste), codex=_codex(), planer=planer,
               planer_codex=planer.codex)
    return baue_graph_s4(abh, checkpointer=InMemorySaver())


def _bis_plan(graph, repo, **eingabe):
    graph.invoke({"repo": str(repo), "aufgabe_id": "M2", **eingabe}, CFG)
    erg = _weiter(graph, {"entscheidung": "freigeben"})
    assert _halt(graph) == ("plan_freigabe",)
    return erg["__interrupt__"][0].value


def test_router_nimmt_hoehere_schaetzung(s4):
    repo, aufgaben = s4
    impl, liste = ImplMitStufe(RICHTIG), []
    graph = _graph_stufen(aufgaben, Planer(spec_schreiben=[{**SPEC, "komplexitaet": "einfach"}],
                                           spec_codex=[CODEX_SCHWER]), impl, liste)
    frage = _bis_plan(graph, repo)
    assert (frage["komplexitaet"], frage["komplexitaet_claude"], frage["komplexitaet_codex"]) == (
        "schwer", "einfach", "schwer")
    assert frage["stufen"]["implementierer"] == {"modell": "opus", "effort": "high", "timeout": 900}
    erg = _weiter(graph, {"entscheidung": "freigeben"})
    assert erg["status"] == "gruen" and impl.stufen == [("opus", "high", 900)]
    assert {(r, m, e, t) for r, m, e, t in liste} == {("security", "opus", "xhigh", 1200),
                                                       ("clean_code", "opus", "xhigh", 1200)}


def test_router_ohne_codex_schaetzung(s4):
    repo, aufgaben = s4
    graph = _graph_stufen(aufgaben, Planer(spec_schreiben=[{**SPEC, "komplexitaet": "einfach"}], spec_codex=[None]),
                          ImplMitStufe(RICHTIG), [])
    frage = _bis_plan(graph, repo)
    assert frage["komplexitaet"] == "einfach" and frage["komplexitaet_codex"] is None
    assert "Codex" in frage["komplexitaet_hinweis"]


def test_plan_freigabe_komplexitaet_aendern(s4):
    repo, aufgaben = s4
    impl = ImplMitStufe(RICHTIG)
    graph = _graph_stufen(aufgaben, Planer(), impl, [])
    assert _bis_plan(graph, repo)["komplexitaet"] == "mittel"
    erg = _weiter(graph, {"entscheidung": "freigeben", "komplexitaet": "einfach"})
    assert impl.stufen == [("sonnet", "medium", 600)]
    assert erg["komplexitaet"] == "einfach" and erg["komplexitaet_vorschlag"] == "mittel"


@pytest.mark.parametrize("wert", ["extrem", "opus", 3])
def test_plan_freigabe_ungueltige_komplexitaet(s4, wert):
    repo, aufgaben = s4
    graph = _graph_stufen(aufgaben, Planer(), ImplMitStufe(RICHTIG), [])
    _bis_plan(graph, repo)
    erg = _weiter(graph, {"entscheidung": "freigeben", "komplexitaet": wert})
    assert _halt(graph) == ("plan_freigabe",) and "einfach" in erg["__interrupt__"][0].value["hinweis"]


def test_startmodell_haiku_nur_implementierer(s4):
    repo, aufgaben = s4
    impl, liste = ImplMitStufe(RICHTIG), []
    graph = _graph_stufen(aufgaben, Planer(spec_codex=[CODEX_SCHWER]), impl, liste)
    _bis_plan(graph, repo, modell="haiku")
    _weiter(graph, {"entscheidung": "freigeben"})
    assert impl.stufen == [("haiku", "high", 600)]
    assert {m for _, m, _, _ in liste} == {"opus"} and {e for _, _, e, _ in liste} == {"xhigh"}


def test_planung_feste_stufen(s4):
    repo, aufgaben = s4
    planer = Planer()
    graph = _graph_stufen(aufgaben, planer, ImplMitStufe(RICHTIG), [])
    _bis_plan(graph, repo, pruefer_modell="haiku")  # Startwahl der Prüfer gilt nicht für die Planung
    for name in ("klaeren", "spec_schreiben", "akzeptanz_schreiben", "plan_schreiben"):
        assert planer.stufen[name][0] == ("sonnet", "high"), name
    assert planer.stufen["spec_pruefer"][0] == ("opus", "high")
    assert planer.stufen["spec_codex"][0] == (None, "high") and planer.stufen["plan_codex"][0] == (None, "high")



# ---------------------------------------------------------------------------------------------- 6b-2 Kostenrahmen
def test_aufrufe_zaehlen_parallel(s4):
    """klären 1, Spec 1, Akzeptanz 1, Spec-Prüfer 2, Plan 1, Plan-Prüfung 1, Implementierer 1, Prüfer 3 (funktion 0),
    ab Stufe 7 Gesamtreview 1 (der Lauf hält danach an abschluss_freigabe)."""
    repo, aufgaben = s4
    graph, _ = _graph(aufgaben)
    _start(graph, repo)
    erg = _bis_umsetzung(graph)
    assert erg["status"] == "gruen" and erg["aufrufe"] == 12


def _budget_halt(graph):
    halt = _halt(graph)
    assert halt and halt[0].startswith("budget"), halt
    return graph.get_state(CFG).tasks[0].interrupts[0].value


def test_budget_haelt_an_und_mehr(s4, monkeypatch):
    from entwicklung import graph as graph_modul
    monkeypatch.setattr(graph_modul, "BUDGET_SCHRITT", 4)
    repo, aufgaben = s4
    graph, _ = _graph(aufgaben, impl=Implementierer(FALSCH))
    graph.invoke({"repo": str(repo), "aufgabe_id": "M2", "budget": 11}, CFG)
    _bis_umsetzung(graph)
    frage = _budget_halt(graph)
    assert frage["art"] == "budget" and frage["aufrufe"] == 11 and frage["budget"] == 11
    assert _halt(graph) == ("budget_umsetzung",) and frage["naechster"] == "implementieren"
    _weiter(graph, {"entscheidung": "mehr"})
    frage = _budget_halt(graph)
    assert (frage["aufrufe"], frage["budget"]) == (15, 15)


def test_budget_abbrechen_schreibt_bericht(s4):
    repo, aufgaben = s4
    graph, _ = _graph(aufgaben)
    graph.invoke({"repo": str(repo), "aufgabe_id": "M2", "budget": 7}, CFG)
    _bis_umsetzung(graph)
    assert _budget_halt(graph)["aufrufe"] == 7
    erg = _weiter(graph, {"entscheidung": "abbrechen"})
    assert erg["status"] == "abgebrochen" and Path(erg["bericht_pfad"]).exists() and not erg.get("agent")


def test_budget_ungueltige_antwort_haelt_erneut(s4):
    repo, aufgaben = s4
    graph, _ = _graph(aufgaben)
    graph.invoke({"repo": str(repo), "aufgabe_id": "M2", "budget": 7}, CFG)
    _bis_umsetzung(graph)
    _weiter(graph, {"entscheidung": "weiter"})
    frage = _budget_halt(graph)
    assert "mehr" in frage["hinweis"] and "abbrechen" in frage["hinweis"]


def test_budget_vor_spec_und_plan(s4):
    repo, aufgaben = s4
    graph, _ = _graph(aufgaben)
    graph.invoke({"repo": str(repo), "aufgabe_id": "M2", "budget": 1}, CFG)
    assert _halt(graph) == ("budget_spec",)
    _weiter(graph, {"entscheidung": "mehr"})  # 1 + 20 = 21, reicht bis zur Umsetzung
    assert _halt(graph) == ("spec_freigabe",)


def test_alter_lauf_ohne_budget_laeuft():
    from entwicklung.graph import budget_knoten
    assert budget_knoten("implementieren")({"aufrufe": 99}) == {}
    assert budget_knoten("implementieren")({"aufrufe": 3, "budget": 40}) == {}



def test_plan_freigabe_zeigt_tabelle(s4):
    """Für die Oberfläche: Modell und Effort je Rolle für jede Komplexität, damit ein Wechsel sofort sichtbar ist."""
    repo, aufgaben = s4
    graph = _graph_stufen(aufgaben, Planer(), ImplMitStufe(RICHTIG), [])
    frage = _bis_plan(graph, repo)
    assert set(frage["tabelle"]) == {"einfach", "mittel", "schwer"}
    assert frage["tabelle"]["einfach"]["implementierer"]["effort"] == "medium"
    assert frage["tabelle"]["schwer"]["pruefer"] == {"modell": "opus", "effort": "xhigh", "timeout": 1200}


def test_tests_nachbessern_haelt_am_kostenrahmen(s4):
    """Codex 6b-2: „Tests nachbessern“ ging direkt zu akzeptanz_schreiben, am Kostenrahmen vorbei."""
    repo, aufgaben = s4
    graph, _ = _graph(aufgaben, Planer(akzeptanz_schreiben=[TESTS_OK, TESTS_OK]))
    vorher = graph.invoke({"repo": str(repo), "aufgabe_id": "M2", "budget": 100}, CFG)
    bis_freigabe = vorher["aufrufe"]
    graph, _ = _graph(aufgaben, Planer(akzeptanz_schreiben=[TESTS_OK, TESTS_OK]))
    graph.invoke({"repo": str(repo), "aufgabe_id": "M2", "budget": bis_freigabe}, CFG)
    assert _halt(graph) == ("spec_freigabe",)
    _weiter(graph, {"entscheidung": "tests_nachbessern", "hinweis": "mehr Randfälle"})
    frage = _budget_halt(graph)
    assert _halt(graph) == ("budget_spec",) and frage["naechster"] == "akzeptanz_schreiben"
    _weiter(graph, {"entscheidung": "mehr"})
    assert _halt(graph) == ("spec_freigabe",)


def test_mehr_haelt_erneut_wenn_weiter_ueber_dem_rahmen(s4, monkeypatch):
    """Codex 6b-2: Nach „mehr“ startete der nächste Schritt auch, wenn der erhöhte Rahmen noch erreicht war."""
    from entwicklung import graph as graph_modul
    monkeypatch.setattr(graph_modul, "BUDGET_SCHRITT", 0)
    repo, aufgaben = s4
    graph, _ = _graph(aufgaben)
    graph.invoke({"repo": str(repo), "aufgabe_id": "M2", "budget": 7}, CFG)
    _bis_umsetzung(graph)
    assert _budget_halt(graph)["aufrufe"] == 7
    _weiter(graph, {"entscheidung": "mehr"})
    frage = _budget_halt(graph)
    assert _halt(graph) == ("budget_umsetzung",) and "über dem Rahmen" in frage["hinweis"]
