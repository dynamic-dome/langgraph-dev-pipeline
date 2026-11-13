import shutil
import subprocess
from pathlib import Path

import pytest

from entwicklung import pfade, worktree

GIT = shutil.which("git")


def _git(cwd, *args):
    return subprocess.run([GIT, *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", check=True).stdout


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "zielrepo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    _git(r, "config", "user.email", "test@lab2")
    _git(r, "config", "user.name", "test")
    (r / "README.md").write_text("hallo\n", encoding="utf-8")
    (r / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
    _git(r, "add", "README.md", ".gitignore")
    _git(r, "commit", "-q", "-m", "init")
    return r


def test_anlegen_unter_arbeit_mit_branch(repo):
    wt = worktree.anlegen(repo, "20261019-120000")
    assert wt == pfade.arbeit_dir() / "zielrepo-20261019-120000"
    assert (wt / "README.md").exists()
    assert _git(wt, "branch", "--show-current").strip() == "lauf/20261019-120000"


def test_geaenderte_dateien(repo):
    wt = worktree.anlegen(repo, "a")
    (wt / "neu.py").write_text("x = 1\n", encoding="utf-8")
    (wt / "tests").mkdir()
    (wt / "tests" / "test_neu.py").write_text("def test_x(): pass\n", encoding="utf-8")
    (wt / "README.md").write_text("geändert\n", encoding="utf-8")
    assert worktree.geaenderte_dateien(wt) == ["README.md", "neu.py", "tests/test_neu.py"]


def test_zweiter_lauf_gleiche_id_bekommt_suffix(repo):
    erster = worktree.anlegen(repo, "gleich")
    zweiter = worktree.anlegen(repo, "gleich")
    assert zweiter != erster
    assert zweiter.name == "zielrepo-gleich-2"
    assert _git(zweiter, "branch", "--show-current").strip() == "lauf/gleich-2"
    assert (erster / "README.md").exists()


def test_schreiben_ins_hauptrepo_ist_grenzverletzung(repo, tmp_path):
    anderes = tmp_path / "lab"
    anderes.mkdir()
    _git(anderes, "init", "-q")
    vorher = {"zielrepo": worktree.stand(repo), "lab": worktree.stand(anderes)}
    (repo / "boese.py").write_text("x\n", encoding="utf-8")
    nachher = {"zielrepo": worktree.stand(repo), "lab": worktree.stand(anderes)}
    verletzungen = worktree.grenzverletzungen(vorher, nachher)
    assert len(verletzungen) == 1
    assert "zielrepo" in verletzungen[0] and "boese.py" in verletzungen[0]


def test_erneute_aenderung_an_schon_geaenderter_datei_faellt_auf(repo):
    (repo / "README.md").write_text("vorher schon geändert\n", encoding="utf-8")
    vorher = {"zielrepo": worktree.stand(repo)}
    (repo / "README.md").write_text("vom Agenten überschrieben\n", encoding="utf-8")
    nachher = {"zielrepo": worktree.stand(repo)}
    assert worktree.grenzverletzungen(vorher, nachher) != []


def test_arbeit_ordner_im_zielrepo_ist_nicht_ausgenommen(repo):
    vorher = {"zielrepo": worktree.stand(repo)}
    (repo / "arbeit").mkdir()
    (repo / "arbeit" / "fremd.py").write_text("x\n", encoding="utf-8")
    assert worktree.grenzverletzungen(vorher, {"zielrepo": worktree.stand(repo)}) == [
        "zielrepo: arbeit/fremd.py neu oder verändert"]


def test_versteckte_dateien(repo):
    wt = worktree.anlegen(repo, "versteckt")
    (wt / ".gitignore").write_text("__pycache__/\ngeheim.py\n", encoding="utf-8")
    (wt / "geheim.py").write_text("x = 1\n", encoding="utf-8")
    (wt / "__pycache__").mkdir()
    (wt / "__pycache__" / "x.pyc").write_bytes(b"0")
    (wt / ".pytest_cache").mkdir()
    (wt / ".pytest_cache" / "v").write_text("x", encoding="utf-8")
    assert worktree.versteckte_dateien(wt) == ["geheim.py"]


def test_entfernen_verweigert_versteckte_dateien(repo):
    wt = worktree.anlegen(repo, "versteckt2")
    (wt / ".gitignore").write_text("__pycache__/\ngeheim.py\n", encoding="utf-8")
    (wt / "geheim.py").write_text("x = 1\n", encoding="utf-8")
    worktree.sichern(wt, "sichern")
    with pytest.raises(worktree.WorktreeFehler, match="geheim.py"):
        worktree.entfernen(repo, wt)
    assert (wt / "geheim.py").exists()


def test_unveraendert_keine_verletzung(repo):
    (repo / "README.md").write_text("dirty, aber gleich\n", encoding="utf-8")
    vorher = {"zielrepo": worktree.stand(repo)}
    assert worktree.grenzverletzungen(vorher, {"zielrepo": worktree.stand(repo)}) == []


def test_sichern_committet_ohne_akzeptanz(repo):
    wt = worktree.anlegen(repo, "s")
    (wt / "neu.py").write_text("x = 1\n", encoding="utf-8")
    (wt / "tests" / "_akzeptanz").mkdir(parents=True)
    (wt / "tests" / "_akzeptanz" / "test_a.py").write_text("def test_a(): pass\n", encoding="utf-8")
    sha = worktree.sichern(wt, "lauf s: Implementierer")
    assert sha and len(sha) >= 7
    assert _git(wt, "show", "--name-only", "--format=", "HEAD").split() == ["neu.py"]
    assert _git(repo, "log", "-1", "--format=%s", "lauf/s").strip() == "lauf s: Implementierer"


def test_kopf_und_diff(repo):
    wt = worktree.anlegen(repo, "diff")
    basis = worktree.kopf(wt)
    assert basis == _git(repo, "rev-parse", "main").strip()
    (wt / "neu.py").write_text("x = 1\n", encoding="utf-8")
    ziel = worktree.sichern(wt, "neu")
    d = worktree.diff(wt, basis, ziel)
    assert "+++ b/neu.py" in d and "+x = 1" in d


def test_sichern_ohne_aenderung_gibt_none(repo):
    wt = worktree.anlegen(repo, "leer")
    assert worktree.sichern(wt, "nichts") is None


def test_sichern_nimmt_geloeschte_datei_mit(repo):
    wt = worktree.anlegen(repo, "del")
    (wt / "README.md").unlink()
    worktree.sichern(wt, "löschen")
    assert "README.md" not in _git(wt, "ls-files")


def test_entfernen_ohne_force_branch_bleibt(repo):
    wt = worktree.anlegen(repo, "weg")
    (wt / "neu.py").write_text("x = 1\n", encoding="utf-8")
    worktree.sichern(wt, "sichern")
    (wt / "__pycache__").mkdir()
    (wt / "__pycache__" / "x.pyc").write_bytes(b"0")
    worktree.entfernen(repo, wt)
    assert not wt.exists()
    assert "lauf/weg" in _git(repo, "branch", "--list", "lauf/weg")


def test_entfernen_verweigert_ungesicherte_arbeit(repo):
    wt = worktree.anlegen(repo, "dirty")
    (wt / "neu.py").write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(worktree.WorktreeFehler):
        worktree.entfernen(repo, wt)
    assert (wt / "neu.py").exists()
