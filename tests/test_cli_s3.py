from pathlib import Path

from entwicklung import cli, pfade, speicher, worktree
from entwicklung.graph import baue_graph_s3
from tests.test_graph_s1 import _abh, umgebung  # noqa: F401  (umgebung ist eine Fixture)
from tests.test_graph_s2 import _codex, _pruefer
from tests.test_graph_s3 import FALSCH, RICHTIG, Implementierer


def _abh3(aufgaben, impl):
    return _abh(aufgaben, implementierer=impl, pruefer=_pruefer(), codex=_codex())


def _lauf(repo, abh, *extra):
    return cli.main(["lauf", "--repo", str(repo), "--aufgabe", "M1", "--stufe", "3", *extra], abh=abh)


def _wartend(abh):
    cp = speicher.oeffne_checkpointer()
    graph = baue_graph_s3(abh, checkpointer=cp)
    return speicher.wartende_laeufe(cp, lambda stufe: graph)


def test_lauf_haelt_an_exit_3(umgebung, capsys):
    repo, aufgaben = umgebung
    abh = _abh3(aufgaben, Implementierer(FALSCH))
    assert _lauf(repo, abh) == 3
    aus = capsys.readouterr().out
    assert "wartet" in aus and "fortsetzen --entscheidung" in aus and "Runde 2" in aus
    assert _wartend(abh) == ["lauf-20261019-120000"]


def test_fortsetzen_annehmen(umgebung, capsys):
    repo, aufgaben = umgebung
    abh = _abh3(aufgaben, Implementierer(FALSCH))
    _lauf(repo, abh)
    assert cli.main(["fortsetzen", "--entscheidung", "annehmen"], abh=abh) == 1
    aus = capsys.readouterr().out
    assert "angenommen" in aus and "Bericht:" in aus
    assert _wartend(abh) == []


def test_fortsetzen_weiter_dann_gruen(umgebung, capsys):
    repo, aufgaben = umgebung
    abh = _abh3(aufgaben, Implementierer(FALSCH, FALSCH, FALSCH, RICHTIG))
    _lauf(repo, abh)
    assert cli.main(["fortsetzen", "--entscheidung", "weiter", "--live"], abh=abh) == 0
    aus = capsys.readouterr().out
    assert "fix_runde" in aus and "gruen" in aus


def test_fortsetzen_ohne_wartenden_lauf(umgebung, capsys):
    repo, aufgaben = umgebung
    abh = _abh3(aufgaben, Implementierer(RICHTIG))
    assert _lauf(repo, abh) == 0
    assert cli.main(["fortsetzen", "--entscheidung", "annehmen"], abh=abh) == 1
    assert "Kein Lauf wartet" in capsys.readouterr().out


def test_fortsetzen_mit_thread(umgebung):
    repo, aufgaben = umgebung
    abh = _abh3(aufgaben, Implementierer(FALSCH))
    _lauf(repo, abh)
    _lauf(repo, abh)
    assert _wartend(abh) == ["lauf-20261019-120000-2", "lauf-20261019-120000"]
    assert cli.main(["fortsetzen", "--entscheidung", "abbrechen", "--thread", "lauf-20261019-120000"], abh=abh) == 1
    assert _wartend(abh) == ["lauf-20261019-120000-2"]


def test_fortsetzen_unbekannter_thread(umgebung, capsys):
    repo, aufgaben = umgebung
    abh = _abh3(aufgaben, Implementierer(FALSCH))
    _lauf(repo, abh)
    assert cli.main(["fortsetzen", "--entscheidung", "weiter", "--thread", "lauf-gibtsnicht"], abh=abh) == 1
    assert "wartet nicht" in capsys.readouterr().out
    assert _wartend(abh) == ["lauf-20261019-120000"]


def test_live_zeigt_runden_und_halt(umgebung, capsys):
    repo, aufgaben = umgebung
    assert _lauf(repo, _abh3(aufgaben, Implementierer(FALSCH)), "--live", "--max-runden", "1") == 3
    aus = capsys.readouterr().out
    assert "fix_runde" in aus and "⏸" in aus


def test_stufe_2_weiter_lauffaehig(umgebung):
    repo, aufgaben = umgebung
    assert _lauf(repo, _abh3(aufgaben, Implementierer(RICHTIG)), "--stufe", "2") == 0


def test_bericht_mit_runden(umgebung):
    repo, aufgaben = umgebung
    abh = _abh3(aufgaben, Implementierer(FALSCH, RICHTIG))
    assert _lauf(repo, abh) == 0
    from entwicklung import pfade
    text = sorted(pfade.berichte_dir().glob("*.md"))[-1].read_text(encoding="utf-8")
    assert "## Runden" in text and "Runde 0:" in text and "Runde 1:" in text


def test_aufraeumen_behaelt_wartenden_lauf(umgebung, capsys):
    repo, aufgaben = umgebung
    abh = _abh3(aufgaben, Implementierer(FALSCH))
    assert _lauf(repo, abh) == 3
    wartend = pfade.arbeit_dir() / "mini-20261019-120000"
    juenger = worktree.anlegen(repo, "20261019-130000")
    assert cli.main(["aufraeumen", "--alle"]) == 0
    assert wartend.exists() and not juenger.exists()
    assert "wartet auf eine Entscheidung" in capsys.readouterr().out
    assert cli.main(["fortsetzen", "--entscheidung", "annehmen"], abh=abh) == 1  # weiter fortsetzbar
