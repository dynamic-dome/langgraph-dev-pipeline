import dataclasses
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

from entwicklung import cli, pfade, worktree
from entwicklung.graph import Abhaengigkeiten, baue_graph_s1

GIT = shutil.which("git")
AUFGABE = "# M1: plus\n`mathe.plus(a, b)` gibt die Summe zurück.\n"
AKZEPTANZ = ("def test_a1():\n    from mathe import plus\n    assert plus(2, 2) == 4\n\n\n"
             "def test_a2():\n    from mathe import plus\n    assert plus(-1, 1) == 0\n")
EIGENER_TEST = "from mathe import plus\n\n\ndef test_plus():\n    assert plus(1, 2) == 3\n"


def _git(cwd, *args):
    return subprocess.run([GIT, *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", check=True).stdout


@pytest.fixture
def umgebung(tmp_path):
    repo = tmp_path / "mini"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "test@lab2")
    _git(repo, "config", "user.name", "test")
    (repo / "README.md").write_text("mini\n", encoding="utf-8")
    (repo / "entwicklung.toml").write_text(
        f'python = "{Path(sys.executable).as_posix()}"\ntestbefehl = ["-m", "pytest", "-q"]\n', encoding="utf-8")
    _git(repo, "add", "README.md", "entwicklung.toml")
    _git(repo, "commit", "-q", "-m", "init")
    aufgaben = tmp_path / "aufgaben"
    (aufgaben / "mini" / "M1").mkdir(parents=True)
    (aufgaben / "mini" / "M1.md").write_text(AUFGABE, encoding="utf-8")
    (aufgaben / "mini" / "M1" / "test_ak.py").write_text(AKZEPTANZ, encoding="utf-8")
    return repo, aufgaben


def _fake(code="def plus(a, b):\n    return a + b\n", ok=True, extra=None, prompts=None):
    def implementierer(prompt, wt, python, modell="sonnet", timeout=600, effort=None, runner=None):
        if prompts is not None:
            prompts.append(prompt)
        (wt / "mathe.py").write_text(code, encoding="utf-8")
        (wt / "tests").mkdir(exist_ok=True)
        (wt / "tests" / "test_mathe.py").write_text(EIGENER_TEST, encoding="utf-8")
        if extra:
            extra(wt)
        return {"ok": ok, "zusammenfassung": "mathe.py gebaut" if ok else "", "rc": 0 if ok else 1,
                "dauer_s": 0.1, "fehler": None if ok else "Timeout nach 600 s", "turns": 3,
                "verweigerungen": ["Bash: git commit -m x"]}
    return implementierer


def _abh(aufgaben, **kw):
    return Abhaengigkeiten(implementierer=kw.pop("implementierer", _fake()), aufgaben_dir=aufgaben,
                           weitere_geschuetzte=[], jetzt=lambda: datetime(2026, 10, 19, 12, 0, 0), **kw)


def _lauf(repo, abh, **eingabe):
    return baue_graph_s1(abh).invoke({"repo": str(repo), "aufgabe_id": "M1", **eingabe})


def test_gruen(umgebung):
    repo, aufgaben = umgebung
    erg = _lauf(repo, _abh(aufgaben))
    assert erg["status"] == "gruen"
    assert erg["lauf_id"] == "20261019-120000"
    assert erg["testergebnis"]["akzeptanz"] == {"gesammelt": 2, "bestanden": 2, "erwartet": 2, "uebersprungen": 0, "fehler": 0}
    assert erg["geaenderte_dateien"] == ["mathe.py", "tests/test_mathe.py"]
    assert _git(repo, "log", "-1", "--format=%H", "lauf/20261019-120000").strip() == erg["sicherung"]
    assert _git(repo, "status", "--porcelain") == ""
    bericht = Path(erg["bericht_pfad"])
    assert bericht.parent == pfade.berichte_dir()
    assert "gruen" in bericht.read_text(encoding="utf-8")
    daten = json.loads(bericht.with_suffix(".json").read_text(encoding="utf-8"))
    assert daten["status"] == "gruen" and daten["agent"]["verweigerungen"] == ["Bash: git commit -m x"]


def test_rot(umgebung):
    repo, aufgaben = umgebung
    erg = _lauf(repo, _abh(aufgaben, implementierer=_fake(code="def plus(a, b):\n    return a + b + (a == 2)\n")))
    assert erg["status"] == "rot"
    assert erg["testergebnis"]["akzeptanz"] == {"gesammelt": 2, "bestanden": 1, "erwartet": 2, "uebersprungen": 0, "fehler": 0}


def test_grenzverletzung(umgebung):
    repo, aufgaben = umgebung
    boese = _fake(extra=lambda wt: (repo / "boese.py").write_text("x\n", encoding="utf-8"))
    erg = _lauf(repo, _abh(aufgaben, implementierer=boese))
    assert erg["status"] == "grenzverletzung"
    assert erg.get("testergebnis") is None
    assert any("boese.py" in v for v in erg["grenzverletzungen"])
    assert "boese.py" in Path(erg["bericht_pfad"]).read_text(encoding="utf-8")


def test_grenzverletzung_in_weiterem_repo(umgebung, tmp_path):
    repo, aufgaben = umgebung
    lab = tmp_path / "lab"
    lab.mkdir()
    _git(lab, "init", "-q")
    boese = _fake(extra=lambda wt: (lab / "notiz.md").write_text("x\n", encoding="utf-8"))
    abh = dataclasses.replace(_abh(aufgaben, implementierer=boese), weitere_geschuetzte=[lab])
    erg = _lauf(repo, abh)
    assert erg["status"] == "grenzverletzung"
    assert erg["grenzverletzungen"] == ["lab: notiz.md neu oder verändert"]


def test_per_gitignore_versteckte_datei_ist_grenzverletzung(umgebung):
    repo, aufgaben = umgebung

    def verstecken(wt):
        (wt / ".gitignore").write_text("mathe.py\n", encoding="utf-8")

    erg = _lauf(repo, _abh(aufgaben, implementierer=_fake(extra=verstecken)))
    assert erg["status"] == "grenzverletzung"
    assert erg["grenzverletzungen"] == ["Worktree: mathe.py per .gitignore versteckt, nicht gesichert"]


def test_agent_fehler(umgebung):
    repo, aufgaben = umgebung
    erg = _lauf(repo, _abh(aufgaben, implementierer=_fake(ok=False)))
    assert erg["status"] == "agent_fehler"
    assert erg.get("testergebnis") is None
    assert "Timeout" in Path(erg["bericht_pfad"]).read_text(encoding="utf-8")


def test_absturz_des_implementierers_wird_agent_fehler(umgebung):
    repo, aufgaben = umgebung

    def kaputt(*a, **k):
        raise RuntimeError("kaputt")

    erg = _lauf(repo, _abh(aufgaben, implementierer=kaputt))
    assert erg["status"] == "agent_fehler"
    assert "kaputt" in erg["agent"]["fehler"]


def test_prompt_enthaelt_aufgabe_aber_keine_akzeptanztests(umgebung):
    repo, aufgaben = umgebung
    prompts = []
    _lauf(repo, _abh(aufgaben, implementierer=_fake(prompts=prompts)))
    assert AUFGABE.strip() in prompts[0]
    assert "test_a2" not in prompts[0]
    assert "-m pytest -q" in prompts[0]


def test_vorbereiten_sammelt_vorherige_aufgaben(umgebung):
    repo, aufgaben = umgebung
    for nr in (2, 10):
        (aufgaben / "mini" / f"M{nr}.md").write_text(f"# M{nr}\n", encoding="utf-8")
        (aufgaben / "mini" / f"M{nr}").mkdir()
        (aufgaben / "mini" / f"M{nr}" / f"test_ak_m{nr}.py").write_text("def test_x():\n    pass\n",
                                                                      encoding="utf-8")
    (aufgaben / "mini" / "X1").mkdir()
    erg = baue_graph_s1(_abh(aufgaben)).invoke({"repo": str(repo), "aufgabe_id": "M2"})
    assert [Path(d).name for d in erg["akzeptanz_dirs"]] == ["M1", "M2"]
    assert erg["basis"] == _git(repo, "rev-parse", "main").strip()
    assert erg["testergebnis"]["akzeptanz"]["erwartet"] == 3


def test_unbekannte_aufgabe(umgebung):
    repo, aufgaben = umgebung
    with pytest.raises(FileNotFoundError, match="M9"):
        baue_graph_s1(_abh(aufgaben)).invoke({"repo": str(repo), "aufgabe_id": "M9"})


def test_cli_lauf(umgebung, capsys):
    repo, aufgaben = umgebung
    rc = cli.main(["lauf", "--repo", str(repo), "--aufgabe", "M1", "--stufe", "1"], abh=_abh(aufgaben))
    aus = capsys.readouterr().out
    assert rc == 0
    assert "gruen" in aus and "Bericht:" in aus and "Akzeptanz 2/2" in aus


def test_cli_live(umgebung, capsys):
    repo, aufgaben = umgebung
    rc = cli.main(["lauf", "--repo", str(repo), "--aufgabe", "M1", "--live", "--stufe", "1"], abh=_abh(aufgaben))
    aus = capsys.readouterr().out
    assert rc == 0
    for knoten in ("vorbereiten", "implementieren", "grenzen_pruefen", "tests_ausfuehren", "bericht"):
        assert knoten in aus


def test_cli_rot_exit_1(umgebung):
    repo, aufgaben = umgebung
    abh = _abh(aufgaben, implementierer=_fake(code="def plus(a, b):\n    return 0\n"))
    assert cli.main(["lauf", "--repo", str(repo), "--aufgabe", "M1", "--stufe", "1"], abh=abh) == 1


def test_cli_kein_fable(umgebung):
    repo, aufgaben = umgebung
    with pytest.raises(SystemExit):
        cli.main(["lauf", "--repo", str(repo), "--aufgabe", "M1", "--modell", "fable", "--stufe", "1"], abh=_abh(aufgaben))


def test_cli_aufraeumen(umgebung, capsys):
    repo, aufgaben = umgebung
    cli.main(["lauf", "--repo", str(repo), "--aufgabe", "M1", "--stufe", "1"], abh=_abh(aufgaben))
    wt = pfade.arbeit_dir() / "mini-20261019-120000"
    assert wt.exists()
    assert cli.main(["aufraeumen", "--alle"]) == 0
    assert not wt.exists()
    assert "lauf/20261019-120000" in _git(repo, "branch", "--list", "lauf/*")


def test_cli_aufraeumen_behaelt_juengsten(umgebung):
    repo, aufgaben = umgebung
    erster = worktree.anlegen(repo, "20261019-100000")
    zweiter = worktree.anlegen(repo, "20261019-110000")
    assert cli.main(["aufraeumen"]) == 0
    assert not erster.exists() and zweiter.exists()
