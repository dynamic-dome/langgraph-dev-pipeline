import pytest

from portwart.__main__ import main
from portwart.drift import (
    DriftErgebnis, DriftFehler, Fund, durchsuche, drift, finde_ports, zeilen,
)
from portwart.liste import Eintrag


def ports(text):
    return [p for _, p in finde_ports(text)]


@pytest.mark.parametrize("text", [
    "PORT=8766", "export PORT=8766", "port = 8766", "port: 8766",
    '"port": 8766', "web_port = 8766", "DB_PORT=8766", "port='8766'",
    "--port 8766", "--port=8766", "x localhost:8766", "127.0.0.1:8766",
    "0.0.0.0:8766", "http://example.com:8766/x", "postgres://u:p@h:1/d 8766 port=8766",
])
def test_treffer(text):
    assert 8766 in ports(text)


@pytest.mark.parametrize("text", [
    "12:30", "report = 5", "transport: 80", '{"a":8080}', "port=0",
    "port=65536", "port=08766", "port=8766abc", "port=8766_x", "port=80.5",
    "xlocalhost:80", "a.localhost:80", "_port=80", "://:80",
    "port=80ä", "port=80９", "port=80.９", "äport=80",
    "port=" + "9" * 5000,
])
def test_kein_treffer(text):
    assert finde_ports(text) == []


def test_wurzel_zugriffsfehler(tmp_path, monkeypatch):
    from pathlib import Path

    def kaputt(self):
        raise PermissionError("gesperrt")

    monkeypatch.setattr(Path, "exists", kaputt)
    with pytest.raises(DriftFehler, match="nicht lesbar"):
        durchsuche(tmp_path)


def test_zeilen_und_dedupe():
    assert finde_ports("a\r\nport=2\rport=1 port=1\nport=3\n") == [
        (2, 2), (3, 1), (4, 3)]


def baue(tmp_path):
    (tmp_path / "wiki" / "src").mkdir(parents=True)
    (tmp_path / "wiki" / "src" / "app.py").write_text("x\nport = 9000\n")
    for n in ("node_modules", ".git", "build", "arbeit", "dist", "__pycache__"):
        (tmp_path / "wiki" / n).mkdir()
        (tmp_path / "wiki" / n / "a.txt").write_text("port=1111")
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "a.txt").write_text("port=1111")
    (tmp_path / "leer").mkdir()
    (tmp_path / "datei.txt").write_text("port=2222")
    return tmp_path


def test_durchsuche(tmp_path):
    w = baue(tmp_path)
    (w / "wiki" / "bin.dat").write_bytes(b"port=3333\x00")
    (w / "wiki" / "latin.txt").write_bytes("port=4444 ä".encode("latin-1"))
    (w / "wiki" / "gross.txt").write_text("port=5555\n" + "x" * 1_048_576)
    (w / "wiki" / "bom.txt").write_bytes(b"\xef\xbb\xbfport=6666")
    assert durchsuche(w) == {
        "leer": [],
        "wiki": [Fund(6666, "wiki/bom.txt", 1),
                 Fund(9000, "wiki/src/app.py", 2)],
    }
    assert durchsuche(str(w)) == durchsuche(w)


def test_durchsuche_fehler(tmp_path):
    with pytest.raises(DriftFehler, match="nicht gefunden"):
        durchsuche(tmp_path / "nein")
    (tmp_path / "f").write_text("x")
    with pytest.raises(DriftFehler, match="kein Ordner"):
        durchsuche(tmp_path / "f")


def test_drift_faelle():
    liste = [Eintrag(8767, "sig"), Eintrag(8770, "job"), Eintrag(8771, "job"),
             Eintrag(8000, "ok"), Eintrag(8001, "ok"), Eintrag(9, "weg"),
             Eintrag(7000, "andere")]
    funde = {
        "sig": [Fund(8766, "sig/run.bat", 3), Fund(8766, "sig/a.py", 9)],
        "job": [Fund(8771, "job/c.py", 1), Fund(5, "job/c.py", 2)],
        "ok": [Fund(8000, "ok/x", 1), Fund(8002, "ok/x", 2)],
        "wiki": [Fund(9000, "wiki/b", 5), Fund(9000, "wiki/a", 12),
                 Fund(7000, "wiki/a", 1)],
        "leer": [],
        "andere": [Fund(8000, "andere/x", 4)],
    }
    erg = drift(liste, funde)
    assert [(u.port, u.projekt, u.datei, u.zeile) for u in erg.unbekannt] == [
        (5, "job", "job/c.py", 2), (8002, "ok", "ok/x", 2), (8766, "sig", "sig/a.py", 9),
        (8766, "sig", "sig/run.bat", 3), (9000, "wiki", "wiki/a", 12),
        (9000, "wiki", "wiki/b", 5)]
    assert zeilen(erg)[-2:] == [
        "abweichend andere LISTE=7000 CODE=8000 andere/x:4",
        "abweichend sig LISTE=8767 CODE=8766 sig/a.py:9",
    ]
    assert zeilen(erg)[0] == "unbekannt 5 job job/c.py:2"


def test_abweichung_mehrere():
    erg = drift([Eintrag(8770, "job")],
                {"job": [Fund(8002, "job/config.py", 7), Fund(8001, "job/config.py", 7)]})
    assert zeilen(erg) == [
        "unbekannt 8001 job job/config.py:7",
        "unbekannt 8002 job job/config.py:7",
        "abweichend job LISTE=8770 CODE=8001,8002 job/config.py:7"]
    assert zeilen(DriftErgebnis([], [])) == []


def liste_datei(tmp_path, inhalt):
    p = tmp_path / "l.toml"
    p.write_text(inhalt)
    return p


def test_cli(tmp_path, capsys):
    w = tmp_path / "w"
    (w / "wiki").mkdir(parents=True)
    code = w / "wiki" / "a.py"
    code.write_text("port = 8000\n")
    lt = liste_datei(tmp_path, '[[port]]\nport = 8000\nprojekt = "wiki"\n')
    vorher = (lt.read_bytes(), code.read_bytes())
    assert main(["drift", str(w), "--datei", str(lt)]) == 0
    assert capsys.readouterr().out == "kein Drift\n"

    code.write_text("port = 9000\n")
    vorher = (lt.read_bytes(), code.read_bytes())
    assert main(["drift", str(w), "--datei", str(lt)]) == 1
    assert capsys.readouterr().out.splitlines() == [
        "unbekannt 9000 wiki wiki/a.py:1",
        "abweichend wiki LISTE=8000 CODE=9000 wiki/a.py:1"]
    assert (lt.read_bytes(), code.read_bytes()) == vorher


def test_cli_leer(tmp_path, capsys):
    (tmp_path / "w").mkdir()
    lt = liste_datei(tmp_path, "")
    assert main(["drift", str(tmp_path / "w"), "--datei", str(lt)]) == 0
    assert capsys.readouterr().out == "kein Drift\n"


def test_cli_fehler(tmp_path, capsys):
    (tmp_path / "w").mkdir()
    lt = liste_datei(tmp_path, "")
    for argv in (["drift", str(tmp_path / "w"), "--datei", str(tmp_path / "x")],
                 ["drift", str(tmp_path / "nein"), "--datei", str(lt)],
                 ["drift", str(lt), "--datei", str(lt)]):
        assert main(argv) == 2
        o = capsys.readouterr()
        assert o.out == "" and o.err.startswith("Fehler: ")
    bad = liste_datei(tmp_path, "[[port")
    assert main(["drift", str(tmp_path / "w"), "--datei", str(bad)]) == 2
    capsys.readouterr()
    nutf = tmp_path / "latin.toml"
    nutf.write_bytes(b'# \xe4\xf6\n')
    assert main(["drift", str(tmp_path / "w"), "--datei", str(nutf)]) == 2
    o = capsys.readouterr()
    assert o.out == "" and o.err.startswith("Fehler: ")
