"""Stufe 6c: Nachprüfung der Spec gegen die Vorfassung, Einordnung, Verlauf und Zuschnitt-Bremse im Graphen."""
from entwicklung.konvergenz import NACHPRUEF_SCHEMA
from entwicklung.planung import SPEC_PRUEF_K_SCHEMA, spec_prompt
from tests.test_graph_s1 import umgebung  # noqa: F401  (umgebung ist eine Fixture)
from tests.test_graph_s4 import (CFG, CODEX_MAJOR, GEN_TEST, PRUEF_OK, PRUEF_PUNKT, SPEC, Planer, _graph, _halt,
                                 _start, _weiter, s4)  # noqa: F401  (s4 ist eine Fixture)

SPEC2 = {**SPEC, "spec": SPEC["spec"] + "Negative Zahlen sind erlaubt.\n"}
NACH_OK = {"verdict": "PASS", "punkte": [], "alte_punkte": [{"nr": 1, "status": "geloest", "grund": "steht drin"}]}
NACH_MIX = {"verdict": "FAIL", "alte_punkte": [{"nr": 1, "status": "geloest", "grund": ""}],
            "punkte": [{"schwere": "major", "aussage": "Neu kaputt", "herkunft": "aenderung"},
                       {"schwere": "major", "aussage": "Stand schon so", "herkunft": "sonstiges"}]}
CODEX_OFFEN = {"verdict": "FAIL", "punkte": [], "alte_punkte": [{"nr": 1, "status": "offen", "grund": "weiter da"}]}
CODEX_SONSTIGES = {"verdict": "FAIL", "alte_punkte": [{"nr": 1, "status": "geloest", "grund": ""}],
                   "punkte": [{"schwere": "major", "aussage": "Alt übersehen", "herkunft": "sonstiges"}]}
TESTS_OK2 = {"dateien": [{"name": "test_akzeptanz_m2.py", "inhalt": GEN_TEST
                          + "\n\ndef test_plus_null():\n    from mathe import plus\n    assert plus(0, 0) == 0\n"}]}
AENDERN = {"entscheidung": "aendern", "hinweis": "Bitte auch negative Zahlen"}


class SchemaPlaner(Planer):
    """Merkt sich zusätzlich, mit welchem Schema jeder Planungsagent aufgerufen wurde."""

    def __init__(self, **antworten):
        super().__init__(**antworten)
        self.schemas: dict[str, list[dict]] = {}

    def __call__(self, name, prompt, cwd, schema, **kw):
        self.schemas.setdefault(name, []).append(schema)
        return super().__call__(name, prompt, cwd, schema, **kw)


def _frage(erg):
    return erg["__interrupt__"][0].value


def test_erste_pruefung_unveraendert(s4):
    repo, aufgaben = s4
    graph, planer = _graph(aufgaben, SchemaPlaner(spec_pruefer=[PRUEF_PUNKT]))
    frage = _frage(_start(graph, repo))
    assert "Nachprüfung" not in planer.prompts["spec_pruefer"][0]
    assert planer.schemas["spec_pruefer"] == [SPEC_PRUEF_K_SCHEMA] and planer.schemas["spec_codex"] == [SPEC_PRUEF_K_SCHEMA]
    assert frage["nachpruefung"] is False
    assert frage["einordnung"]["ausloesend"] == [{"pruefer": "claude", "schwere": "major",
                                                   "aussage": "Negative Zahlen fehlen", "herkunft": "erstpruefung"}]
    assert [v["fassung"] for v in frage["verlauf"]] == [1]


def test_nachpruefung_nach_aendern(s4):
    repo, aufgaben = s4
    planer = SchemaPlaner(spec_schreiben=[SPEC, SPEC2], spec_pruefer=[PRUEF_PUNKT, NACH_OK],
                          spec_codex=[PRUEF_OK, NACH_OK])
    graph, planer = _graph(aufgaben, planer)
    _start(graph, repo)
    frage = _frage(_weiter(graph, AENDERN))
    for name in ("spec_pruefer", "spec_codex"):
        zweiter = planer.prompts[name][1]
        assert "## Nachprüfung" in zweiter and "1. [claude, major] Negative Zahlen fehlen" in zweiter
        assert "+Negative Zahlen sind erlaubt." in zweiter
        assert planer.schemas[name][1] == NACHPRUEF_SCHEMA
    assert frage["nachpruefung"] is True
    assert frage["einordnung"]["ausloesend"] == [] and frage["einordnung"]["alte"][0]["status"] == "geloest"
    assert [(v["fassung"], v["nachgebessert"]) for v in frage["verlauf"]] == [(1, False), (2, False)]


def test_schreiber_bekommt_nur_ausloesende(s4):
    repo, aufgaben = s4
    graph, planer = _graph(aufgaben, Planer(spec_pruefer=[PRUEF_PUNKT, NACH_MIX, NACH_OK],
                                            spec_codex=[PRUEF_OK, NACH_OK]))  # ohne Bewertung wäre Punkt 1 offen
    _start(graph, repo)
    frage = _frage(_weiter(graph, AENDERN))
    assert [p["aussage"] for p in frage["einordnung"]["ausloesend"]] == ["Neu kaputt"]
    assert [p["aussage"] for p in frage["einordnung"]["liste"]] == ["Stand schon so", "Negative Zahlen fehlen"]
    _weiter(graph, {"entscheidung": "aendern", "hinweis": "Korrektur zurücknehmen"})
    dritter = planer.prompts["spec_schreiben"][2]
    assert "Neu kaputt" in dritter and "Stand schon so" not in dritter and "Negative Zahlen fehlen" not in dritter
    assert "1. [claude, major] Neu kaputt" in planer.prompts["spec_pruefer"][2]


def test_alter_codex_punkt_offen_bleibt_einwand(s4):
    repo, aufgaben = s4
    graph, _ = _graph(aufgaben, Planer(spec_codex=[CODEX_MAJOR, CODEX_OFFEN]))
    _start(graph, repo)
    frage = _frage(_weiter(graph, {"entscheidung": "aendern", "hinweis": "Idempotenz klären"}))
    einwand = "Codex (GPT) meldet major weiter offen: Idempotenz widerspricht der ./-Regel"
    assert frage["einwaende"] == [einwand]
    erg = _weiter(graph, {"entscheidung": "freigeben"})
    assert _halt(graph) == ("spec_freigabe",) and "meldet major weiter offen" in _frage(erg)["hinweis"]


def test_sonstiges_codex_major_bleibt_einwand(s4):
    repo, aufgaben = s4
    graph, _ = _graph(aufgaben, Planer(spec_pruefer=[PRUEF_PUNKT, NACH_OK], spec_codex=[PRUEF_OK, CODEX_SONSTIGES]))
    _start(graph, repo)
    frage = _frage(_weiter(graph, AENDERN))
    assert frage["einwaende"] == ["Codex (GPT) meldet major: Alt übersehen"]
    assert [p["aussage"] for p in frage["einordnung"]["liste"]] == ["Alt übersehen", "Negative Zahlen fehlen"]
    assert frage["einordnung"]["ausloesend"] == []


def test_nachbessern_prueft_gegen_vorige_tests(s4):
    repo, aufgaben = s4
    graph, planer = _graph(aufgaben, Planer(akzeptanz_schreiben=[{"dateien": [{"name": "test_akzeptanz_m2.py",
                                                                                "inhalt": GEN_TEST}]}, TESTS_OK2]))
    _start(graph, repo)
    frage = _frage(_weiter(graph, {"entscheidung": "tests_nachbessern", "hinweis": "Null prüfen"}))
    zweiter = planer.prompts["spec_pruefer"][1]
    assert "spec: unverändert" in zweiter and "+def test_plus_null():" in zweiter
    assert frage["nachpruefung"] is True and frage["spec_runde"] == 0
    assert [(v["fassung"], v["nachgebessert"]) for v in frage["verlauf"]] == [(1, False), (1, True)]


def test_aendern_ohne_einordnung_alter_lauf(s4):
    """Ein Lauf aus 6b-2 hat keine spec_einordnung im State: „ändern“ nimmt dann alle Prüfpunkte wie bisher."""
    repo, aufgaben = s4
    graph, planer = _graph(aufgaben, Planer(spec_pruefer=[PRUEF_PUNKT, NACH_OK]))
    _start(graph, repo)
    graph.update_state(CFG, {"spec_einordnung": None, "spec_verlauf": []})
    _weiter(graph, AENDERN)
    assert _halt(graph) == ("spec_freigabe",)
    assert "Negative Zahlen fehlen" in planer.prompts["spec_schreiben"][1]
    assert "1. [claude, major] Negative Zahlen fehlen" in planer.prompts["spec_pruefer"][1]


def test_spec_prompt_bremse():
    erst = spec_prompt("w", [], None, None, [])
    assert "Sonderregel" in erst and "Gesamtsicht" not in erst
    neu = spec_prompt("w", [], "anders", "# alte Spec", [])
    assert "Gesamtsicht" in neu and "keine neue Sonderregel" in neu


NACH_LEER = {"verdict": "PASS", "punkte": [], "alte_punkte": []}


def test_codex_sonstiges_sperre_ueberlebt_nachbessern(s4):
    """Codex-Verifier 6c (V1): Ein Codex-Major auf der Liste reist als Sperrpunkt mit, bis Codex ihn als gelöst
    meldet. Er löst keine Runde aus, bleibt aber Einwand (auch nach „Tests nachbessern“ ohne Begründung)."""
    repo, aufgaben = s4
    graph, planer = _graph(aufgaben, Planer(spec_pruefer=[PRUEF_PUNKT, NACH_OK, NACH_OK],
                                            spec_codex=[PRUEF_OK, CODEX_SONSTIGES, NACH_LEER]))
    _start(graph, repo)
    assert _frage(_weiter(graph, AENDERN))["einwaende"] == ["Codex (GPT) meldet major: Alt übersehen"]
    frage = _frage(_weiter(graph, {"entscheidung": "tests_nachbessern", "hinweis": "Null prüfen"}))
    assert "1. [codex, major] Alt übersehen" in planer.prompts["spec_codex"][2]
    assert frage["einwaende"] == ["Codex (GPT) meldet major weiter offen: Alt übersehen"]
    assert frage["einordnung"]["ausloesend"] == []  # Sperre ja, neue Runde nein
    assert [p["aussage"] for p in frage["einordnung"]["liste"]] == ["Alt übersehen"]


def test_codex_ausfall_in_nachpruefung_haelt_die_sperre(s4):
    """Codex-Verifier 6c (V2): Fällt Codex bei der Nachprüfung aus, hat er den alten Major nicht als gelöst bestätigt."""
    repo, aufgaben = s4
    graph, _ = _graph(aufgaben, Planer(spec_pruefer=[PRUEF_OK, NACH_OK], spec_codex=[CODEX_MAJOR, None]))
    _start(graph, repo)
    frage = _frage(_weiter(graph, {"entscheidung": "aendern", "hinweis": "Idempotenz klären"}))
    assert frage["einwaende"] == ["Codex (GPT) hat major nicht nachgeprüft: Idempotenz widerspricht der ./-Regel"]
    _weiter(graph, {"entscheidung": "freigeben"})
    assert _halt(graph) == ("spec_freigabe",)
