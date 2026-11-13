import pytest

from portwart.__main__ import main
from portwart.frei import BereichsFehler, freie_ports, parse_bereich
from portwart.liste import Eintrag

NETSTAT = "  TCP    0.0.0.0:8701    0.0.0.0:0    LISTENING\n"


def test_parse():
    assert parse_bereich(" 8700-8799 ") == (8700, 8799)
    for s in ["8700", "a-b", "8799-8700", "0-10", "8700-70000", "-1-5", "1-2-3"]:
        with pytest.raises(BereichsFehler):
            parse_bereich(s)


def test_freie():
    e = [Eintrag(8700, "a")]
    assert freie_ports(e, {8701}, 8700, 8703) == [8702, 8703]
    with pytest.raises(BereichsFehler):
        freie_ports(e, set(), 5, 1)


@pytest.fixture
def dateien(tmp_path):
    t = tmp_path / "p.toml"
    t.write_text('[[port]]\nport = 8700\nprojekt = "a"\n')
    n = tmp_path / "n.txt"
    n.write_text(NETSTAT)
    return ["--datei", str(t), "--netstat-datei", str(n)]


def test_cli(dateien, capsys):
    assert main(["frei", "8700-8710", "--anzahl", "2", *dateien]) == 0
    assert capsys.readouterr().out == "8702\n8703\n"
    assert main(["frei", "8700-8701", *dateien]) == 1
    assert capsys.readouterr().out == "kein freier Port in 8700-8701\n"
    assert main(["frei", "8700-8702", "--anzahl", "5", *dateien]) == 0
    assert capsys.readouterr().out == "8702\n"


def test_cli_fehler(dateien, capsys):
    for arg in (["x"], ["8700-8710", "--anzahl", "0"]):
        assert main(["frei", *arg, *dateien]) == 2
        c = capsys.readouterr()
        assert c.out == "" and c.err.startswith("Fehler: ")
    assert main(["frei", "1-5", "--datei", "gibtsnicht.toml"]) == 2
    assert main(["frei", "1-5", *dateien[:2], "--netstat-datei", "nix"]) == 2


def test_cli_bereich_mit_minus(dateien, capsys):
    for arg in ("-1-5", "-5-1", "-1"):
        assert main(["frei", arg, *dateien]) == 2
        c = capsys.readouterr()
        assert c.out == "" and c.err.startswith("Fehler: ")
        assert len(c.err.splitlines()) == 1
    assert main(["frei", *dateien, "-1-5"]) == 2
    assert len(capsys.readouterr().err.splitlines()) == 1


def test_cli_weitere_ungueltige_bereiche(dateien, capsys):
    for arg in (["-a-b"], ["--1-5"], ["--", "-1-5"], ["9" * 5000 + "-65535"]):
        assert main(["frei", *arg, *dateien]) == 2
        c = capsys.readouterr()
        assert c.out == "" and c.err.startswith("Fehler: ")
        assert len(c.err.splitlines()) == 1


def test_lange_ziffernfolge():
    with pytest.raises(BereichsFehler):
        parse_bereich("9" * 5000 + "-65535")
    assert parse_bereich("0008700-08799") == (8700, 8799)
