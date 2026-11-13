"""Demo-Modus: ein kompletter Lauf an examples/portwart mit Fake-Agenten, ohne Abo."""
import shutil
import subprocess
from pathlib import Path

from entwicklung import agenten, cli, demo, pfade


def _git(cwd, *args):
    return subprocess.run([shutil.which("git"), *args], cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", check=True).stdout


def test_umgebung_ist_frisches_repo(tmp_path):
    repo, aufgaben = demo.baue_umgebung(tmp_path / "demo")
    assert repo.name == "portwart" and (repo / ".git").exists()
    assert _git(repo, "status", "--porcelain") == "" and _git(repo, "branch", "--show-current").strip() == "main"
    assert (aufgaben / "portwart" / "D1.md").is_file()
    assert "python" in (repo / "entwicklung.toml").read_text(encoding="utf-8")


def test_durchlauf_bis_zum_merge(tmp_path):
    ergebnis = demo.durchlauf(tmp_path / "demo")
    repo = tmp_path / "demo" / "portwart"
    assert ergebnis["status"] == "gruen" and ergebnis["abschluss"]["merge_commit"] == _git(repo, "rev-parse",
                                                                                            "HEAD").strip()
    assert (repo / "portwart" / "anzahl.py").is_file()
    assert (tmp_path / "demo" / "aufgaben" / "portwart" / "D1" / "test_akzeptanz_d1.py").is_file()
    assert ergebnis["testergebnis"]["gruen"] and ergebnis["testergebnis"]["akzeptanz"]["gesammelt"] >= 1
    assert Path(ergebnis["bericht_pfad"]).is_relative_to(pfade.berichte_dir())
    assert [h for h, _ in ergebnis["haltepunkte"]] == ["spec_freigabe", "plan_freigabe", "abschluss_freigabe"]
    assert agenten._TESTSPERRE is True  # echte Agenten bleiben gesperrt


def test_cli_demo_durchlauf(capsys, monkeypatch, tmp_path):
    monkeypatch.setattr(demo, "temp_ordner", lambda: tmp_path / "cli-demo")
    assert cli.main(["demo", "--durchlauf"]) == 0
    aus = capsys.readouterr().out
    assert "spec_freigabe" in aus and "abschluss_freigabe" in aus and "gemergt" in aus.lower()


def test_beispiel_ohne_private_inhalte():
    beispiel = pfade.projekt_dir() / "examples" / "portwart"
    for datei in beispiel.rglob("*"):
        if datei.is_file() and "__pycache__" not in datei.parts:
            text = datei.read_text(encoding="utf-8", errors="replace")
            for verboten in ("domes", "DCO", "C:/Users", "C:\\Users"):
                assert verboten not in text, (datei, verboten)
