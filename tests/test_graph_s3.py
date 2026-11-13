from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from entwicklung.graph import baue_graph_s3
from tests.test_graph_s1 import EIGENER_TEST, _abh, _git, umgebung  # noqa: F401  (umgebung ist eine Fixture)
from tests.test_graph_s2 import _codex, _pruefer

RICHTIG = "def plus(a, b):\n    return a + b\n"
FALSCH = "def plus(a, b):\n    return 0\n"


class Implementierer:
    """Fake: liefert je Aufruf den nächsten Code aus `codes` (der letzte bleibt), merkt sich die Prompts."""

    def __init__(self, *codes, extra=None):
        self.codes, self.extra, self.prompts = list(codes), extra or {}, []

    def __call__(self, prompt, wt, python, modell="sonnet", timeout=600, effort=None, runner=None):
        nr = len(self.prompts)
        self.prompts.append(prompt)
        (wt / "mathe.py").write_text(self.codes[min(nr, len(self.codes) - 1)], encoding="utf-8")
        (wt / "tests").mkdir(exist_ok=True)
        (wt / "tests" / "test_mathe.py").write_text(EIGENER_TEST, encoding="utf-8")
        if nr in self.extra:
            self.extra[nr](wt)
        return {"ok": True, "zusammenfassung": f"Runde {nr}", "rc": 0, "dauer_s": 0.1, "fehler": None, "turns": 2,
                "verweigerungen": []}


def _graph(aufgaben, impl):
    abh = _abh(aufgaben, implementierer=impl, pruefer=_pruefer(), codex=_codex())
    return baue_graph_s3(abh, checkpointer=InMemorySaver())


def _cfg(name="t1"):
    return {"configurable": {"thread_id": name}}


def _start(graph, repo, **eingabe):
    return graph.invoke({"repo": str(repo), "aufgabe_id": "M1", **eingabe}, _cfg())


def test_ohne_befunde_keine_runde(umgebung):
    repo, aufgaben = umgebung
    impl = Implementierer(RICHTIG)
    erg = _start(_graph(aufgaben, impl), repo)
    assert erg["status"] == "gruen" and erg["runde"] == 0
    assert len(impl.prompts) == 1 and len(erg["runden"]) == 1
    assert Path(erg["bericht_pfad"]).exists()


def test_fix_runde_behebt(umgebung):
    repo, aufgaben = umgebung
    impl = Implementierer(FALSCH, RICHTIG)
    erg = _start(_graph(aufgaben, impl), repo)
    assert erg["status"] == "gruen" and erg["runde"] == 1
    assert [r["runde"] for r in erg["runden"]] == [0, 1]
    assert erg["runden"][0]["ausloesend"] >= 1 and erg["runden"][1]["status"] == "gruen"
    assert "Fix-Runde 1" in impl.prompts[1] and "Akzeptanztests" in impl.prompts[1]
    assert "assert" in impl.prompts[1]  # Testauszug wie im CI
    log = _git(repo, "log", "--format=%s", f"lauf/{erg['lauf_id']}").splitlines()
    assert log[0].endswith("Fix-Runde 1 (sonnet)") and "Implementierer" in log[1]


def test_pruefberichte_je_runde_frisch(umgebung):
    repo, aufgaben = umgebung
    erg = _start(_graph(aufgaben, Implementierer(FALSCH, RICHTIG)), repo)
    assert len(erg["pruefberichte"]) == 4
    assert erg["befunde"] == []  # nur Befunde der letzten Runde


def test_eskalation_nach_max_runden(umgebung):
    repo, aufgaben = umgebung
    impl = Implementierer(FALSCH)
    graph = _graph(aufgaben, impl)
    erg = _start(graph, repo)
    assert graph.get_state(_cfg()).next == ("eskalation",)
    frage = erg["__interrupt__"][0].value
    assert frage["runde"] == 2 and frage["max_runden"] == 2 and frage["ausloesend"]
    assert len(impl.prompts) == 3


def test_weiter_gibt_eine_runde(umgebung):
    repo, aufgaben = umgebung
    impl = Implementierer(FALSCH)
    graph = _graph(aufgaben, impl)
    _start(graph, repo)
    erg = graph.invoke(Command(resume={"entscheidung": "weiter"}), _cfg())
    assert len(impl.prompts) == 4
    assert graph.get_state(_cfg()).next == ("eskalation",)
    assert erg["__interrupt__"][0].value["max_runden"] == 3


def test_weiter_kann_beheben(umgebung):
    repo, aufgaben = umgebung
    graph = _graph(aufgaben, Implementierer(FALSCH, FALSCH, FALSCH, RICHTIG))
    _start(graph, repo)
    erg = graph.invoke(Command(resume={"entscheidung": "weiter"}), _cfg())
    assert erg["status"] == "gruen" and erg["entscheidung"] == "weiter" and erg["runde"] == 3


def test_annehmen(umgebung):
    repo, aufgaben = umgebung
    graph = _graph(aufgaben, Implementierer(FALSCH))
    _start(graph, repo)
    erg = graph.invoke(Command(resume={"entscheidung": "annehmen"}), _cfg())
    assert erg["status"] == "angenommen" and erg["entscheidung"] == "annehmen"
    assert "angenommen" in Path(erg["bericht_pfad"]).read_text(encoding="utf-8")
    assert graph.get_state(_cfg()).next == ()


def test_abbrechen(umgebung):
    repo, aufgaben = umgebung
    graph = _graph(aufgaben, Implementierer(FALSCH))
    _start(graph, repo)
    erg = graph.invoke(Command(resume={"entscheidung": "abbrechen"}), _cfg())
    assert erg["status"] == "abgebrochen"


def test_ungueltige_antwort_haelt_erneut(umgebung):
    repo, aufgaben = umgebung
    impl = Implementierer(FALSCH)
    graph = _graph(aufgaben, impl)
    _start(graph, repo)
    # {} zählt in LangGraph 1.2.10 gar nicht als Antwort: Das interrupt feuert erneut mit der Originalfrage.
    # Command(resume=None) stürzt dort intern ab (UnboundLocalError), die CLI schickt immer ein dict (gemessen 19.10.).
    for antwort, hinweis in (({}, False), ({"entscheidung": "ja"}, True), ("weiter", True)):
        erg = graph.invoke(Command(resume=antwort), _cfg())
        assert graph.get_state(_cfg()).next == ("eskalation",)
        assert ("ungültig" in erg["__interrupt__"][0].value["hinweis"]) is hinweis
    assert len(impl.prompts) == 3
    erg = graph.invoke(Command(resume={"entscheidung": "annehmen"}), _cfg())
    assert erg["status"] == "angenommen"


def test_grenzverletzung_in_fix_runde_beendet(umgebung):
    repo, aufgaben = umgebung
    impl = Implementierer(FALSCH, RICHTIG,
                          extra={1: lambda wt: (repo / "boese.py").write_text("x\n", encoding="utf-8")})
    graph = _graph(aufgaben, impl)
    erg = _start(graph, repo)
    assert erg["status"] == "grenzverletzung" and len(impl.prompts) == 2
    assert graph.get_state(_cfg()).next == ()


def test_max_runden_0_eskaliert_sofort(umgebung):
    repo, aufgaben = umgebung
    impl = Implementierer(FALSCH)
    graph = _graph(aufgaben, impl)
    _start(graph, repo, max_runden=0)
    assert graph.get_state(_cfg()).next == ("eskalation",) and len(impl.prompts) == 1


def test_geaenderte_dateien_ueber_runden(umgebung):
    repo, aufgaben = umgebung
    impl = Implementierer(FALSCH, RICHTIG, extra={0: lambda wt: (wt / "notiz.md").write_text("n", encoding="utf-8")})
    erg = _start(_graph(aufgaben, impl), repo)
    assert erg["geaenderte_dateien"] == ["mathe.py", "notiz.md", "tests/test_mathe.py"]


def test_abbruch_in_fix_runde_zeigt_keine_alten_ergebnisse(umgebung):
    """Bricht eine Fix-Runde vor dem Testlauf ab, darf der Bericht nicht Tests und Befunde der Vorrunde
    als aktuelles Ergebnis zeigen. Die Vorrunde steht weiter in runden."""
    repo, aufgaben = umgebung
    impl = Implementierer(FALSCH, RICHTIG,
                          extra={1: lambda wt: (repo / "boese.py").write_text("x\n", encoding="utf-8")})
    erg = _start(_graph(aufgaben, impl), repo)
    assert erg["status"] == "grenzverletzung"
    assert erg.get("testergebnis") is None
    assert erg["befunde"] == [] and not erg["fix_noetig"]
    assert erg["nicht_verwertbar"] == [] and erg["nicht_pruefbar"] == []
    assert [r["runde"] for r in erg["runden"]] == [0] and erg["runden"][0]["status"] == "rot"
    assert Path(erg["bericht_pfad"]).exists()



def test_eskalation_annehmen_speichert_einwand(umgebung):
    repo, aufgaben = umgebung
    graph = _graph(aufgaben, Implementierer(FALSCH))
    _start(graph, repo)
    erg = graph.invoke(Command(resume={"entscheidung": "annehmen", "begruendung": "Rest ist kosmetisch",
                                       "einwaende": ["Astra rät zu weiter"]}), _cfg())
    assert erg["status"] == "angenommen"
    assert erg["einwand_freigaben"] == [{"haltepunkt": "eskalation", "entscheidung": "annehmen",
                                         "einwaende": ["Astra rät zu weiter"], "begruendung": "Rest ist kosmetisch"}]


def test_eskalation_annehmen_ohne_einwand_kein_eintrag(umgebung):
    repo, aufgaben = umgebung
    graph = _graph(aufgaben, Implementierer(FALSCH))
    _start(graph, repo)
    erg = graph.invoke(Command(resume={"entscheidung": "annehmen"}), _cfg())
    assert not erg.get("einwand_freigaben")


# ---------------------------------------------------------------------------------------------- Frühabbruch (6b-1)
def _befund(path, line, quote, claim, kind="bug"):
    return {"verdict": "FAIL", "findings": [{"id": "C1", "severity": "major", "kind": kind, "path": path, "line": line,
                                             "claim": claim, "quote": quote, "check": "gelesen",
                                             "status": "read-only"}], "not_checkable": []}


def _codex_folge(*berichte):
    """Fake-Codex: je Runde der nächste Bericht (der letzte bleibt)."""
    from tests.test_graph_s2 import _ok
    folge = list(berichte)

    def codex(prompt, wt, timeout=900, effort=None, runner=None):
        return _ok("codex", folge.pop(0) if len(folge) > 1 else folge[0])
    return codex


def _graph_codex(aufgaben, impl, codex):
    abh = _abh(aufgaben, implementierer=impl, pruefer=_pruefer(), codex=codex)
    return baue_graph_s3(abh, checkpointer=InMemorySaver())


GLEICH_0 = _befund("mathe.py", 2, "return a + b", "Idempotenz widerspricht der Spec")
GLEICH_1 = _befund("mathe.py", 1, "def plus(a, b):", "Spec-Widerspruch: Idempotenz, anders formuliert")
ANDERS = _befund("mathe.py", 2, "return a + b", "Rückgabetyp unklar", kind="spec")
PASS_BERICHT = {"verdict": "PASS", "findings": [], "not_checkable": []}


def test_befund_schluessel_und_wiederkehrend():
    from entwicklung.graph import befund_schluessel, wiederkehrend
    b = {"pruefer": ["security", "codex"], "path": "a.py", "kind": "bug", "line": 3, "claim": "x"}
    assert befund_schluessel(b) == "codex+security|a.py|bug"
    assert wiederkehrend([{"runde": 0, "schluessel": ["k", "m"]}, {"runde": 1, "schluessel": ["k"]}]) == ["k"]
    assert wiederkehrend([{"runde": 0, "schluessel": ["k"]}, {"runde": 2, "schluessel": ["k"]}]) == []
    assert wiederkehrend([{"runde": 0, "schluessel": ["k"]}]) == []
    assert wiederkehrend([{"runde": 0}, {"runde": 1}]) == []  # alte Läufe ohne Schlüssel


def test_wiederkehrender_befund_eskaliert_nach_runde_1(umgebung):
    repo, aufgaben = umgebung
    impl = Implementierer(RICHTIG)
    graph = _graph_codex(aufgaben, impl, _codex_folge(GLEICH_0, GLEICH_1))
    erg = _start(graph, repo, max_runden=3)
    assert graph.get_state(_cfg()).next == ("eskalation",)
    frage = erg["__interrupt__"][0].value
    assert frage["runde"] == 1 and frage["wiederkehrend"] == ["codex|mathe.py|bug"]
    assert "zwei Runden nacheinander" in frage["frage"] and len(impl.prompts) == 2


def test_anderer_befund_laeuft_weiter(umgebung):
    repo, aufgaben = umgebung
    impl = Implementierer(RICHTIG)
    graph = _graph_codex(aufgaben, impl, _codex_folge(GLEICH_0, ANDERS, PASS_BERICHT))
    erg = _start(graph, repo, max_runden=3)
    assert erg["status"] == "gruen" and erg["runde"] == 2 and len(impl.prompts) == 3


def test_weiter_nach_fruehabbruch(umgebung):
    repo, aufgaben = umgebung
    impl = Implementierer(RICHTIG)
    graph = _graph_codex(aufgaben, impl, _codex_folge(GLEICH_0, GLEICH_1, GLEICH_0, PASS_BERICHT))
    _start(graph, repo, max_runden=3)
    erg = graph.invoke(Command(resume={"entscheidung": "weiter"}), _cfg())
    assert graph.get_state(_cfg()).next == ("eskalation",) and erg["__interrupt__"][0].value["wiederkehrend"]
    erg = graph.invoke(Command(resume={"entscheidung": "weiter"}), _cfg())
    assert erg["status"] == "gruen" and len(impl.prompts) == 4


def test_rote_tests_brechen_nicht_frueh_ab(umgebung):
    """Ruling 6b-1: Gemessene rote Tests sind kein Prüfer-Urteil; die Fix-Runde mit Testauszug darf weiterlaufen."""
    repo, aufgaben = umgebung
    impl = Implementierer(FALSCH)
    graph = _graph(aufgaben, impl)
    erg = _start(graph, repo)
    assert erg["__interrupt__"][0].value["runde"] == 2 and erg["__interrupt__"][0].value["wiederkehrend"] == []



def test_s3_budget_vor_implementieren(umgebung):
    repo, aufgaben = umgebung
    graph = _graph(aufgaben, Implementierer(FALSCH))
    _start(graph, repo, budget=4)  # Implementierer 1 + Prüfer 3
    assert graph.get_state(_cfg()).next == ("budget_umsetzung",)
    erg = graph.invoke(Command(resume={"entscheidung": "mehr"}), _cfg())
    assert erg["aufrufe"] >= 8
