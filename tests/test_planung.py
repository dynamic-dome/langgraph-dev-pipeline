import pytest

from entwicklung import pfade, planung
from entwicklung.strukturiert import passt

SCHNITTSTELLEN = [{"modul": "portwart.drift", "namen": ["DriftFehler", "finde_ports"]},
                  {"modul": "portwart.liste", "namen": ["Eintrag"]}]

GUT = '''"""Akzeptanztests A4."""
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def test_finde(tmp_path):
    from portwart.drift import finde_ports
    from portwart.liste import Eintrag
    assert finde_ports(tmp_path) == []


def test_cli(tmp_path):
    r = subprocess.run([sys.executable, "-m", "portwart", "drift", str(tmp_path)], capture_output=True)
    assert r.returncode == 0
'''


def _datei(inhalt=GUT, name="test_akzeptanz_a4.py"):
    return [{"name": name, "inhalt": inhalt}]


def test_pruefe_akzeptanz_ok():
    assert planung.pruefe_akzeptanz(_datei(), SCHNITTSTELLEN, "A4") == []


def test_import_auf_modulebene_abgelehnt():
    gruende = planung.pruefe_akzeptanz(_datei("from portwart.drift import finde_ports\n\n\ndef test_x():\n"
                                              "    assert finde_ports\n"), SCHNITTSTELLEN, "A4")
    assert any("Modulebene" in g and "portwart.drift" in g for g in gruende)


@pytest.mark.parametrize("zeile", ["from portwart.drift import geheim", "from portwart.frei import freie_ports",
                                   "import portwart.drift", "from portwart import drift"])
def test_name_ausserhalb_der_spec_abgelehnt(zeile):
    inhalt = f"def test_x():\n    {zeile}\n    assert True\n"
    gruende = planung.pruefe_akzeptanz(_datei(inhalt), SCHNITTSTELLEN, "A4")
    assert gruende and any("Schnittstelle" in g for g in gruende)


def test_falscher_dateiname_und_syntaxfehler():
    assert any("Dateiname" in g for g in planung.pruefe_akzeptanz(_datei(name="tests.py"), SCHNITTSTELLEN, "A4"))
    assert any("Dateiname" in g for g in planung.pruefe_akzeptanz(_datei(name="../test_akzeptanz_a4.py"),
                                                                   SCHNITTSTELLEN, "A4"))
    zwei = _datei() + _datei(name="test_akzeptanz_a4b.py")
    assert any("genau eine" in g for g in planung.pruefe_akzeptanz(zwei, SCHNITTSTELLEN, "A4"))
    assert any("Syntax" in g for g in planung.pruefe_akzeptanz(_datei("def test_x(:\n"), SCHNITTSTELLEN, "A4"))


def test_ohne_testfunktion_abgelehnt():
    gruende = planung.pruefe_akzeptanz(_datei("import pytest\n\n\ndef hilfe():\n    pass\n"), SCHNITTSTELLEN, "A4")
    assert any("Testfunktion" in g for g in gruende)


def test_fremdes_paket_auf_modulebene_abgelehnt():
    gruende = planung.pruefe_akzeptanz(_datei("import requests\n\n\ndef test_x():\n    assert 1\n"),
                                       SCHNITTSTELLEN, "A4")
    assert any("requests" in g for g in gruende)


def test_lege_ab_nur_unter_berichte(tmp_path):
    ordner = pfade.berichte_dir() / "20261020-090000"
    akz = planung.lege_ab(ordner, "# Spec\n", _datei(), "A4")
    assert akz == ordner / "akzeptanz" / "A4"
    assert (akz / "test_akzeptanz_a4.py").read_text(encoding="utf-8") == GUT
    assert (ordner / "spec.md").read_text(encoding="utf-8") == "# Spec\n"
    with pytest.raises(ValueError):
        planung.lege_ab(pfade.berichte_dir() / "x", "s", _datei(name="..\\boese.py"), "A4")


def test_lege_ab_ersetzt_alten_versuch():
    ordner = pfade.berichte_dir() / "20261020-090001"
    planung.lege_ab(ordner, "alt", _datei(name="test_akzeptanz_a4.py"), "A4")
    (ordner / "akzeptanz" / "A4" / "test_alt.py").write_text("x", encoding="utf-8")
    akz = planung.lege_ab(ordner, "neu", _datei(), "A4")
    assert sorted(p.name for p in akz.iterdir()) == ["test_akzeptanz_a4.py"]


def test_prompts_enthalten_regeln():
    klaerung = [{"fragen": ["Welche Dateiarten?"], "antwort": "nur .py und .toml"}]
    p = planung.spec_prompt("Drift finden", klaerung, aenderung="Exit-Code 1 bei Drift", vorige_spec="# alt",
                            pruefpunkte=[{"pruefer": "codex", "schwere": "major", "aussage": "CLI fehlt"}])
    assert "nur .py und .toml" in p and "Exit-Code 1 bei Drift" in p and "CLI fehlt" in p and "# alt" in p
    a = planung.akzeptanz_prompt("# Spec", SCHNITTSTELLEN, "A4", gruende=["Import auf Modulebene"])
    assert "portwart.drift: DriftFehler, finde_ports" in a and "test_akzeptanz_a4.py" in a
    assert "Import auf Modulebene" in a and "parents[2]" in a
    assert "pytest.skip" in a and "simulier" in a
    k = planung.klaer_prompt("Drift finden", klaerung, runde=1, max_runden=3)
    assert "Drift finden" in k and "nur .py und .toml" in k and "1 von 3" in k
    s = planung.spec_pruef_prompt("Drift finden", klaerung, "# Spec", {"test_akzeptanz_a4.py": "def test_x(): ..."})
    assert "# Spec" in s and "def test_x" in s and "nur .py und .toml" in s


@pytest.mark.parametrize("schema,beispiel", [
    (planung.KLAER_SCHEMA, {"klar": True, "verstaendnis": "x", "fragen": []}),
    (planung.SPEC_SCHEMA, {"spec": "# S", "schnittstellen": [], "annahmen": [], "komplexitaet": "mittel",
                           "komplexitaet_grund": "ein Befehl"}),
    (planung.SPEC_PRUEF_K_SCHEMA, {"verdict": "PASS", "punkte": [], "komplexitaet": "schwer",
                                   "komplexitaet_grund": "Dateivertrag"}),
    (planung.AKZEPTANZ_SCHEMA, {"dateien": []}),
    (planung.SPEC_PRUEF_SCHEMA, {"verdict": "PASS", "punkte": []}),
    (planung.PLAN_SCHEMA, {"plan": "# P", "dateien": []}),
])
def test_schemas_streng_und_passend(schema, beispiel):
    """Codex verlangt mit --output-schema strenge Schemas: alle Felder Pflicht, keine zusätzlichen."""
    def streng(s):
        if s.get("type") == "object":
            assert s["additionalProperties"] is False and set(s["required"]) == set(s["properties"])
            for teil in s["properties"].values():
                streng(teil)
        if s.get("type") == "array":
            streng(s["items"])
    streng(schema)
    assert passt(beispiel, schema)


@pytest.mark.parametrize("zeile", [
    "import importlib\n    importlib.import_module('portwart.drift')",
    "from importlib import import_module",
    "__import__('portwart.drift')",
    "from portwart.drift import finde_ports\n    finde_ports.__globals__['geheim']",
    "from portwart.drift import finde_ports\n    getattr(finde_ports, '__globals__')",
    "eval('1')",
])
def test_dynamische_zugriffe_abgelehnt(zeile):
    """Codex F2: Umwege an der Importprüfung vorbei."""
    inhalt = f"def test_x():\n    {zeile}\n    assert True\n"
    gruende = planung.pruefe_akzeptanz(_datei(inhalt), SCHNITTSTELLEN, "A4")
    assert any("dynamisch" in g for g in gruende), gruende


def test_path_file_bleibt_erlaubt():
    assert planung.pruefe_akzeptanz(_datei(), SCHNITTSTELLEN, "A4") == []


PLAN = """# Plan A4
## Schritt 1: portwart/drift.py
Test zuerst: tests/test_drift.py prüft finde_ports und DriftFehler.
## Schritt 2: liste
Eintrag aus portwart.liste wird nur gelesen.
"""


def test_pruefe_plan_ok():
    assert planung.pruefe_plan(PLAN, ["portwart/drift.py", "tests/test_drift.py"], SCHNITTSTELLEN) == []


def test_plan_ohne_schnittstelle():
    gruende = planung.pruefe_plan(PLAN.replace("DriftFehler", "Fehlerklasse"), [], SCHNITTSTELLEN)
    assert any("portwart.drift.DriftFehler" in g for g in gruende)
    gruende = planung.pruefe_plan("# Plan\nnichts\n", [], [{"modul": "portwart.frei", "namen": []}])
    assert any("portwart.frei" in g for g in gruende)
    assert any("leer" in g for g in planung.pruefe_plan("  \n", [], []))


@pytest.mark.parametrize("datei", ["ports.toml", "tests/_akzeptanz/x.py", "tests\\_akzeptanz\\x.py", "../x.py",
                                   "C:/x.py", "/etc/x.py"])
def test_plan_dateien_ausserhalb_des_rahmens(datei):
    gruende = planung.pruefe_plan(PLAN, [datei], SCHNITTSTELLEN)
    assert any(datei in g for g in gruende), gruende


def test_plan_prompts():
    p = planung.plan_prompt("# Spec A4", SCHNITTSTELLEN, aenderung="erst die CLI", voriger_plan="# alter Plan",
                            pruefpunkte=[{"pruefer": "codex", "schwere": "major", "aussage": "Schritt 3 fehlt"}])
    for teil in ("# Spec A4", "erst die CLI", "# alter Plan", "Schritt 3 fehlt", "portwart.drift: DriftFehler"):
        assert teil in p, teil
    q = planung.plan_pruef_prompt("# Spec A4", "# Plan", ["portwart/drift.py"])
    assert "# Spec A4" in q and "# Plan" in q and "portwart/drift.py" in q


def test_akzeptanz_prompt_nachbessern():
    a = planung.akzeptanz_prompt("# Spec", SCHNITTSTELLEN, "A4", [], vorige={"test_akzeptanz_a4.py": "def test_alt(): ..."},
                                 hinweis="Datei ohne Endung testen")
    assert "def test_alt" in a and "Datei ohne Endung testen" in a and "Vorrang" in a


def test_lege_plan_ab():
    ordner = pfade.berichte_dir() / "20261020-140000"
    pfad = planung.lege_plan_ab(ordner, "# Plan\n")
    assert pfad == ordner / "plan.md" and pfad.read_text(encoding="utf-8") == "# Plan\n"
