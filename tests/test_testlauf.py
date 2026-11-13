import sys
from pathlib import Path

import pytest

from entwicklung import konfig, testlauf

EIGENER_TEST = "from mathe import plus\n\n\ndef test_plus():\n    assert plus(1, 2) == 3\n"
AKZEPTANZ_GRUEN = ("def test_a1():\n    from mathe import plus\n    assert plus(2, 2) == 4\n\n\n"
                   "def test_a2():\n    from mathe import plus\n    assert plus(0, 0) == 0\n")
AKZEPTANZ_ROT = ("def test_a1():\n    from mathe import plus\n    assert plus(2, 2) == 4\n\n\n"
                 "def test_a2():\n    from mathe import plus\n    assert plus(2, 2) == 5\n")


@pytest.fixture
def wt(tmp_path):
    w = tmp_path / "wt"
    (w / "tests").mkdir(parents=True)
    (w / "mathe.py").write_text("def plus(a, b):\n    return a + b\n", encoding="utf-8")
    (w / "tests" / "test_mathe.py").write_text(EIGENER_TEST, encoding="utf-8")
    return w


@pytest.fixture
def kfg():
    return {"python": sys.executable, "testbefehl": ["-m", "pytest", "-q"]}


def _akzeptanz(tmp_path, text):
    ordner = tmp_path / "akz"
    ordner.mkdir(exist_ok=True)
    (ordner / "test_ak.py").write_text(text, encoding="utf-8")
    return ordner


def test_gruen(wt, kfg, tmp_path):
    e = testlauf.fuehre_tests_aus(wt, kfg, [_akzeptanz(tmp_path, AKZEPTANZ_GRUEN)])
    assert e["gruen"] is True
    assert (e["gesammelt"], e["bestanden"], e["fehlgeschlagen"], e["fehler"]) == (3, 3, 0, 0)
    assert e["akzeptanz"] == {"gesammelt": 2, "bestanden": 2, "erwartet": 2, "uebersprungen": 0, "fehler": 0}


def test_roter_akzeptanztest(wt, kfg, tmp_path):
    e = testlauf.fuehre_tests_aus(wt, kfg, [_akzeptanz(tmp_path, AKZEPTANZ_ROT)])
    assert e["gruen"] is False
    assert e["fehlgeschlagen"] == 1
    assert e["akzeptanz"] == {"gesammelt": 2, "bestanden": 1, "erwartet": 2, "uebersprungen": 0, "fehler": 0}
    assert "test_a2" in e["auszug"]


def test_importfehler_ist_nicht_gruen(wt, kfg, tmp_path):
    e = testlauf.fuehre_tests_aus(wt, kfg, [_akzeptanz(tmp_path, "import gibtsnicht\n\n\ndef test_a():\n    pass\n")])
    assert e["gruen"] is False
    assert e["akzeptanz"]["gesammelt"] == 0
    assert e["fehler"] >= 1


def test_manipulierte_akzeptanz_wird_ersetzt(wt, kfg, tmp_path):
    eigen = wt / "tests" / "_akzeptanz"
    eigen.mkdir()
    (eigen / "test_ak.py").write_text("def test_a1():\n    assert True\n", encoding="utf-8")
    (eigen / "test_zusatz.py").write_text("def test_z():\n    assert True\n", encoding="utf-8")
    e = testlauf.fuehre_tests_aus(wt, kfg, [_akzeptanz(tmp_path, AKZEPTANZ_ROT)])
    assert e["gruen"] is False
    assert e["akzeptanz"] == {"gesammelt": 2, "bestanden": 1, "erwartet": 2, "uebersprungen": 0, "fehler": 0}


ABWAEHLEN = """
def pytest_collection_modifyitems(config, items):
    items[:] = [i for i in items if "test_a2" not in i.nodeid]
"""


@pytest.mark.parametrize("ort", ["conftest.py", "tests/conftest.py"])
def test_conftest_des_agenten_waehlt_keine_akzeptanztests_ab(wt, kfg, tmp_path, ort):
    (wt / ort).write_text(ABWAEHLEN, encoding="utf-8")
    e = testlauf.fuehre_tests_aus(wt, kfg, [_akzeptanz(tmp_path, AKZEPTANZ_ROT)])
    assert e["gruen"] is False
    assert e["akzeptanz"]["gesammelt"] == 2


def test_pytest_ini_des_agenten_wirkt_nicht_auf_akzeptanz(wt, kfg, tmp_path):
    (wt / "pytest.ini").write_text('[pytest]\naddopts = -k "not test_a2"\n', encoding="utf-8")
    e = testlauf.fuehre_tests_aus(wt, kfg, [_akzeptanz(tmp_path, AKZEPTANZ_ROT)])
    assert e["gruen"] is False
    assert e["akzeptanz"]["gesammelt"] == 2


def test_exitcode_zaehlt(wt, kfg, tmp_path):
    (wt / "conftest.py").write_text("def pytest_sessionfinish(session, exitstatus):\n    session.exitstatus = 3\n",
                                    encoding="utf-8")
    e = testlauf.fuehre_tests_aus(wt, kfg, [_akzeptanz(tmp_path, AKZEPTANZ_GRUEN)])
    assert e["bestanden"] == 3
    assert e["gruen"] is False


def test_weniger_akzeptanztests_als_erwartet_nicht_gruen(wt, kfg, tmp_path, monkeypatch):
    monkeypatch.setattr(testlauf, "_erwartete_anzahl", lambda akz, konfig, timeout: 3)
    e = testlauf.fuehre_tests_aus(wt, kfg, [_akzeptanz(tmp_path, AKZEPTANZ_GRUEN)])
    assert e["akzeptanz"] == {"gesammelt": 2, "bestanden": 2, "erwartet": 3, "uebersprungen": 0, "fehler": 0}
    assert e["gruen"] is False


def _ordner(tmp_path, name, dateien):
    ordner = tmp_path / name
    ordner.mkdir()
    for datei, text in dateien.items():
        (ordner / datei).write_text(text, encoding="utf-8")
    return ordner


def test_mehrere_akzeptanzordner(wt, kfg, tmp_path):
    a1 = _ordner(tmp_path, "A1", {"test_ak_a1.py": AKZEPTANZ_GRUEN})
    a2 = _ordner(tmp_path, "A2", {"test_ak_a2.py": "def test_b():\n    from mathe import plus\n    assert plus(1, 1) == 2\n"})
    e = testlauf.fuehre_tests_aus(wt, kfg, [a1, a2])
    assert e["gruen"] is True
    assert e["akzeptanz"] == {"gesammelt": 3, "bestanden": 3, "erwartet": 3, "uebersprungen": 0, "fehler": 0}


def test_doppelter_dateiname_valueerror(wt, kfg, tmp_path):
    a1 = _ordner(tmp_path, "A1", {"test_ak.py": AKZEPTANZ_GRUEN})
    a2 = _ordner(tmp_path, "A2", {"test_ak.py": AKZEPTANZ_GRUEN})
    with pytest.raises(ValueError, match="test_ak.py"):
        testlauf.fuehre_tests_aus(wt, kfg, [a1, a2])
    assert not (wt / "tests" / "_akzeptanz").exists()


def test_regression_rot(wt, kfg, tmp_path):
    a1 = _ordner(tmp_path, "A1", {"test_ak_a1.py": AKZEPTANZ_ROT})
    a2 = _ordner(tmp_path, "A2", {"test_ak_a2.py": "def test_b():\n    assert True\n"})
    e = testlauf.fuehre_tests_aus(wt, kfg, [a1, a2])
    assert e["gruen"] is False
    assert e["akzeptanz"] == {"gesammelt": 3, "bestanden": 2, "erwartet": 3, "uebersprungen": 0, "fehler": 0}


def test_raeumt_auf(wt, kfg, tmp_path):
    testlauf.fuehre_tests_aus(wt, kfg, [_akzeptanz(tmp_path, AKZEPTANZ_GRUEN)])
    assert not (wt / "tests" / "_akzeptanz").exists()
    assert not (wt / ".pytest_cache").exists()
    assert not list(wt.rglob("__pycache__"))


def test_ohne_akzeptanztests_nicht_gruen(wt, kfg):
    e = testlauf.fuehre_tests_aus(wt, kfg, [])
    assert e["bestanden"] == 1
    assert e["gruen"] is False


def test_keine_tests_nicht_gruen(tmp_path, kfg):
    leer = tmp_path / "leer"
    leer.mkdir()
    e = testlauf.fuehre_tests_aus(leer, kfg, [])
    assert e["gesammelt"] == 0
    assert e["gruen"] is False


def test_timeout(wt, kfg, tmp_path):
    (wt / "tests" / "test_langsam.py").write_text("import time\n\n\ndef test_l():\n    time.sleep(30)\n",
                                                  encoding="utf-8")
    e = testlauf.fuehre_tests_aus(wt, kfg, [_akzeptanz(tmp_path, AKZEPTANZ_GRUEN)], timeout=3)
    assert e["gruen"] is False
    assert "Timeout" in e["auszug"]
    assert not (wt / "tests" / "_akzeptanz").exists()


def test_zielkonfig(tmp_path):
    (tmp_path / "entwicklung.toml").write_text(
        'python = "C:/py/python.exe"\ntestbefehl = ["-m", "pytest", "-q"]\n', encoding="utf-8")
    assert konfig.lade_zielkonfig(tmp_path) == {"python": "C:/py/python.exe", "testbefehl": ["-m", "pytest", "-q"]}


@pytest.mark.parametrize("text", [None, 'python = "x"\n', 'python = 1\ntestbefehl = ["-m"]\n',
                                  'python = "x"\ntestbefehl = "-m pytest"\n', "kaputt ="])
def test_zielkonfig_fehler(tmp_path, text):
    if text is not None:
        (tmp_path / "entwicklung.toml").write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="entwicklung.toml"):
        konfig.lade_zielkonfig(tmp_path)


def test_uebersprungener_akzeptanztest_gezaehlt(wt, kfg, tmp_path):
    """Lauf 20261020-120157: ein Symlink-Test sprang auf diesem Rechner aus. Das muss sichtbar sein."""
    text = AKZEPTANZ_GRUEN + "\n\ndef test_a3():\n    import pytest\n    pytest.skip('hier nicht möglich')\n"
    e = testlauf.fuehre_tests_aus(wt, kfg, [_akzeptanz(tmp_path, text)])
    assert e["gruen"] is False
    assert e["akzeptanz"] == {"gesammelt": 3, "bestanden": 2, "erwartet": 3, "uebersprungen": 1, "fehler": 0}


def test_setup_fehler_im_akzeptanztest_gezaehlt(wt, kfg, tmp_path):
    """Codex F4: ein Test mit fehlender Fixture läuft nie, er darf nicht wie ein roter aussehen."""
    text = AKZEPTANZ_GRUEN + "\n\ndef test_a3(gibt_es_nicht):\n    assert True\n"
    e = testlauf.fuehre_tests_aus(wt, kfg, [_akzeptanz(tmp_path, text)])
    assert e["akzeptanz"]["fehler"] == 1 and e["akzeptanz"]["bestanden"] == 2


def _verweis(link: Path, ziel: Path) -> None:
    """Junction unter Windows (ohne Adminrechte), sonst Symlink."""
    import os
    if os.name == "nt":
        import _winapi
        _winapi.CreateJunction(str(ziel), str(link))
    else:
        link.symlink_to(ziel, target_is_directory=True)


def test_akzeptanzordner_hinter_verweis_wird_nicht_angefasst(wt, kfg, tmp_path):
    """Codex-Review Export SEC-002: tests/ als Junction nach außen darf kein rmtree außerhalb auslösen."""
    import shutil
    fremd = tmp_path / "fremd"
    (fremd / "_akzeptanz").mkdir(parents=True)
    (fremd / "_akzeptanz" / "wichtig.txt").write_text("bleibt\n", encoding="utf-8")
    shutil.rmtree(wt / "tests")
    _verweis(wt / "tests", fremd)
    e = testlauf.fuehre_tests_aus(wt, kfg, [_akzeptanz(tmp_path, AKZEPTANZ_GRUEN)])
    assert (fremd / "_akzeptanz" / "wichtig.txt").read_text(encoding="utf-8") == "bleibt\n"
    assert e["gruen"] is False and "außerhalb des Worktrees" in e["auszug"]


def test_testlauf_ohne_anthropic_schluessel(monkeypatch):
    """Codex-Review Export SEC-003: Testcode des Implementierers bekommt keine Anthropic-Schlüssel."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "y")
    env = testlauf._umgebung()
    assert "ANTHROPIC_API_KEY" not in env and "ANTHROPIC_AUTH_TOKEN" not in env


def test_verweis_waehrend_eigener_tests_loescht_nicht_aussen(wt, kfg, tmp_path):
    """Der eigene Testcode legt tests/_akzeptanz erst während seines Laufs als Junction nach außen an: weder das
    Kopieren noch das Aufräumen danach darf dort etwas löschen."""
    fremd = tmp_path / "fremd2"
    fremd.mkdir()
    (fremd / "wichtig.txt").write_text("bleibt\n", encoding="utf-8")
    ziel = str(fremd).replace("\\", "/")
    (wt / "tests" / "test_verweis.py").write_text(
        "import os\nfrom pathlib import Path\n\n\ndef test_lege_verweis_an():\n"
        "    link = Path(__file__).parent / '_akzeptanz'\n"
        "    if os.name == 'nt':\n        import _winapi\n"
        f"        _winapi.CreateJunction('{ziel}', str(link))\n"
        f"    else:\n        link.symlink_to('{ziel}', target_is_directory=True)\n", encoding="utf-8")
    e = testlauf.fuehre_tests_aus(wt, kfg, [_akzeptanz(tmp_path, AKZEPTANZ_GRUEN)])
    assert (fremd / "wichtig.txt").read_text(encoding="utf-8") == "bleibt\n"
    assert e["gruen"] is False and "außerhalb des Worktrees" in e["auszug"]


def test_verweis_erst_beim_aufraeumen_macht_rot(wt, kfg, tmp_path, monkeypatch):
    """Codex Runde 2: Taucht der Verweis erst nach dem Akzeptanzlauf auf (Aufräumen), darf der Lauf nicht grün sein."""
    echt, aufrufe = testlauf._im_worktree, []

    def erst_beim_aufraeumen(worktree, ziel):
        aufrufe.append(ziel)
        if len(aufrufe) == 3:  # 1. Leeren vorab, 2. Kopieren, 3. Aufräumen
            raise testlauf.AusserhalbFehler(f"{ziel} ist ein Verweis und führt außerhalb des Worktrees")
        return echt(worktree, ziel)

    monkeypatch.setattr(testlauf, "_im_worktree", erst_beim_aufraeumen)
    e = testlauf.fuehre_tests_aus(wt, kfg, [_akzeptanz(tmp_path, AKZEPTANZ_GRUEN)])
    assert len(aufrufe) == 3 and e["gruen"] is False and "außerhalb des Worktrees" in e["auszug"]
