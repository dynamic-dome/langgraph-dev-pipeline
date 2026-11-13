import os
import tomllib

import pytest

from portwart import eintragen as modul
from portwart.__main__ import main
from portwart.eintragen import (
    EintragFehler, anzeige_text, baue_block, toml_text, trage_ein,
)
from portwart.liste import Eintrag, ListenFehler, lade

BASIS = (
    "# Kommentar\n"
    "[[port]]\nport = 8766\nprojekt = \"wiki-inselwelt\"\n\n"
    "# noch einer\n"
    "[[port]]\nport = 8770\nprojekt = \"job-radar\"\n"
)


@pytest.fixture
def liste(tmp_path):
    p = tmp_path / "ports.toml"
    p.write_bytes(BASIS.encode())
    return p


def rest(ordner):
    return sorted(x.name for x in ordner.iterdir())


def test_toml_text():
    assert toml_text('a\\b"c\n\r\t\b\f\x01\x7fä') == '"a\\\\b\\"c\\n\\r\\t\\b\\f\\u0001\\u007fä"'
    for s in ["C:\\a", 'x"y', "a\nb", "\x00\x1f", "äöü"]:
        assert tomllib.loads("a = " + toml_text(s))["a"] == s


def test_anzeige_text():
    assert anzeige_text("a\nb\r\t\b\f\x01\x7f\\ä") == "a\\nb\\r\\t\\b\\f\\u0001\\u007f\\ä"


def test_baue_block():
    assert baue_block("x", 9000, pfad="C:\\a") == '\n[[port]]\nport = 9000\nprojekt = "x"\npfad = "C:\\\\a"\n'
    assert baue_block("x", 1, "", "p") == '\n[[port]]\nport = 1\nprojekt = "x"\nzweck = ""\npfad = "p"\n'
    assert baue_block("x", 1) == '\n[[port]]\nport = 1\nprojekt = "x"\n'


def test_erfolg_bytes(liste):
    alt = liste.read_bytes()
    e = trage_ein(liste, "neu", 1, "z", "p")
    assert e == Eintrag(1, "neu", "z", "p")
    assert liste.read_bytes() == alt + baue_block("neu", 1, "z", "p").encode()
    assert lade(liste)[-1] == e
    assert rest(liste.parent) == ["ports.toml"]


def test_ohne_zeilenende_und_leer_und_crlf(tmp_path):
    p = tmp_path / "a.toml"
    p.write_bytes(b"# x")
    trage_ein(p, "n", 65535)
    assert p.read_bytes() == b"# x\n" + baue_block("n", 65535).encode()
    p.write_bytes(b"")
    trage_ein(p, "n", 5, zweck="")
    assert p.read_bytes() == baue_block("n", 5, "").encode()
    p.write_bytes(b"[[port]]\r\nport = 1\r\nprojekt = \"a\"\r\n")
    trage_ein(p, "b", 2)
    assert p.read_bytes().startswith(b"[[port]]\r\nport = 1\r\nprojekt = \"a\"\r\n\n[[port]]\n")


@pytest.mark.parametrize("args,msg", [
    (("", 1), "Name darf nicht leer sein"),
    (("  ", "x"), "Name darf nicht leer sein"),
    (("n", "9100"), "Port muss eine ganze Zahl sein"),
    (("n", True), "Port muss eine ganze Zahl sein"),
    (("n", 0), "Port 0 liegt außerhalb von 1-65535"),
    (("n", 70000, 5, ""), "Port 70000 liegt außerhalb von 1-65535"),
    (("n", 9100, 5), "Zweck muss ein Text sein"),
    (("n", 9100, None, " "), "Pfad muss ein nicht leerer Text sein"),
    (("n", 9100, None, 5), "Pfad muss ein nicht leerer Text sein"),
    (("n", 9100, 5, ""), "Zweck muss ein Text sein"),
    (("job-radar", 8766, None, ""), "Pfad muss ein nicht leerer Text sein"),
    (("job-radar", 8766), "Name 'job-radar' gibt es schon"),
    (("wiki", 8766), "Port 8766 ist schon vergeben: wiki-inselwelt"),
])
def test_ablehnung(liste, args, msg):
    alt = liste.read_bytes()
    with pytest.raises(EintragFehler) as ei:
        trage_ein(liste, *args)
    assert str(ei.value) == msg
    assert liste.read_bytes() == alt
    assert rest(liste.parent) == ["ports.toml"]


def test_name_grossklein(liste):
    trage_ein(liste, "Job-Radar", 9100)
    trage_ein(liste, " job-radar", 9101)


def test_portkonflikt_dedupliziert(tmp_path):
    p = tmp_path / "a.toml"
    p.write_text('[[port]]\nport=1\nprojekt="z"\n[[port]]\nport=1\nprojekt="a"\n'
                 '[[port]]\nport=1\nprojekt="z"\n')
    with pytest.raises(EintragFehler, match="^Port 1 ist schon vergeben: z, a$"):
        trage_ein(p, "n", 1)
    trage_ein(p, "n", 2)


def test_doppelung_verhindert_nichts(tmp_path):
    p = tmp_path / "a.toml"
    p.write_text('[[port]]\nport=8770\nprojekt="a"\n[[port]]\nport=8770\nprojekt="b"\n')
    trage_ein(p, "c", 9)


def test_laden_vor_pruefung(tmp_path):
    with pytest.raises(ListenFehler):
        trage_ein(tmp_path / "fehlt.toml", "", 0)
    assert rest(tmp_path) == []
    p = tmp_path / "k.toml"
    p.write_bytes(b"\xff\xfe")
    with pytest.raises(UnicodeDecodeError):
        trage_ein(p, "n", 1)


@pytest.mark.parametrize("inhalt", ["port = []\n", 'port = [{port = 8766, projekt = "wiki"}]\n'])
def test_nicht_erweiterbar(tmp_path, monkeypatch, inhalt):
    p = tmp_path / "a.toml"
    p.write_text(inhalt)
    def nie(*a):
        raise AssertionError
    monkeypatch.setattr(os, "replace", nie)
    with pytest.raises(EintragFehler) as ei:
        trage_ein(p, "n", 9100)
    assert str(ei.value) == "Liste kann nicht durch einen [[port]]-Block erweitert werden"
    assert p.read_text() == inhalt
    assert rest(tmp_path) == ["a.toml"]


def test_tempdatei_im_zielordner(liste, monkeypatch):
    echt = os.replace
    gesehen = []
    def ersatz(src, dst):
        gesehen.append(os.path.dirname(os.path.abspath(src)))
        echt(src, dst)
    monkeypatch.setattr(os, "replace", ersatz)
    trage_ein(liste, "n", 9100)
    assert gesehen == [str(liste.parent)]


def _kaputt(monkeypatch, wo):
    if wo == "mkstemp":
        def f(*a, **k):
            raise OSError("mk")
        monkeypatch.setattr(modul.tempfile, "mkstemp", f)
    elif wo == "replace":
        def f(*a, **k):
            raise OSError("rp")
        monkeypatch.setattr(os, "replace", f)
    elif wo == "read":
        def f(self):
            raise OSError("rd")
        monkeypatch.setattr(modul.Path, "read_bytes", f)
    else:
        echt = os.fdopen
        class F:
            def __init__(self, f): self.f = f
            def __enter__(self): return self
            def __exit__(self, *a): self.f.close()
            def write(self, d):
                if wo == "write":
                    raise OSError("wr")
                return self.f.write(d)
            def close(self):
                self.f.close()
                if wo == "close":
                    raise OSError("cl")
        def fd(*a, **k):
            return F(echt(*a, **k))
        monkeypatch.setattr(os, "fdopen", fd)
        if wo == "close":
            F.__exit__ = lambda self, *a: self.close()


@pytest.mark.parametrize("wo", ["mkstemp", "write", "close", "replace", "read"])
def test_schreibfehler(liste, monkeypatch, wo):
    alt = liste.read_bytes()
    _kaputt(monkeypatch, wo)
    with pytest.raises(EintragFehler, match="^Datei nicht schreibbar: "):
        trage_ein(liste, "n", 9100)
    monkeypatch.undo()
    assert liste.read_bytes() == alt
    assert rest(liste.parent) == ["ports.toml"]


def test_fdopen_fehler_schliesst_fd(liste, monkeypatch):
    geschlossen = []
    echt = os.close
    def f(*a, **k):
        raise OSError("fd")
    monkeypatch.setattr(os, "fdopen", f)
    monkeypatch.setattr(os, "close", lambda fd: (geschlossen.append(fd), echt(fd)))
    with pytest.raises(EintragFehler, match="nicht schreibbar"):
        trage_ein(liste, "n", 9100)
    monkeypatch.undo()
    assert len(geschlossen) == 1
    assert rest(liste.parent) == ["ports.toml"]


def cli(capsys, *argv):
    code = main(list(argv))
    o = capsys.readouterr()
    return code, o.out, o.err


def test_cli_erfolg(liste, capsys):
    assert cli(capsys, "eintragen", "neuer-dienst", "9100", "--datei", str(liste)) == (
        0, "eingetragen neuer-dienst 9100\n", "")
    code, out, err = cli(capsys, "eintragen", "b", "+9100", "--datei", str(liste))
    assert code == 2 and out == "" and err == "Fehler: Port 9100 ist schon vergeben: neuer-dienst\n"
    for text in ["+9101", " 9101 ", "9_101"]:
        assert cli(capsys, "eintragen", f"n{text}", text, "--datei", str(liste))[1] == f"eingetragen n{text} 9101\n"
        liste.write_bytes(BASIS.encode())
    cli(capsys, "eintragen", "z", "65535", "--zweck", "", "--pfad", "C:\\x", "--datei", str(liste))
    assert lade(liste)[-1] == Eintrag(65535, "z", "", "C:\\x")


def test_cli_name_mit_umbruch(liste, capsys):
    code, out, err = cli(capsys, "eintragen", "a\nb", "9100", "--datei", str(liste))
    assert (code, out, err) == (0, "eingetragen a\\nb 9100\n", "")
    assert lade(liste)[-1].projekt == "a\nb"
    alt = liste.read_bytes()
    code, out, err = cli(capsys, "eintragen", "a\nb", "9101", "--datei", str(liste))
    assert (code, out, err) == (2, "", "Fehler: Name 'a\\nb' gibt es schon\n")
    code, out, err = cli(capsys, "eintragen", "q", "9100", "--datei", str(liste))
    assert (code, out, err) == (2, "", "Fehler: Port 9100 ist schon vergeben: a\\nb\n")
    assert liste.read_bytes() == alt


@pytest.mark.parametrize("argv,msg", [
    (["n", "8766"], "Port 8766 ist schon vergeben: wiki-inselwelt"),
    (["job-radar", "9100"], "Name 'job-radar' gibt es schon"),
    (["n", "70000"], "Port 70000 liegt außerhalb von 1-65535"),
    (["n", "0"], "Port 0 liegt außerhalb von 1-65535"),
    (["n", "abc"], "Port muss eine ganze Zahl sein: 'abc'"),
    (["n", "9.5"], "Port muss eine ganze Zahl sein: '9.5'"),
    (["n", ""], "Port muss eine ganze Zahl sein: ''"),
    ([" ", "9100"], "Name darf nicht leer sein"),
    (["n", "9100", "--pfad", " "], "Pfad muss ein nicht leerer Text sein"),
])
def test_cli_ablehnung(liste, capsys, argv, msg):
    alt = liste.read_bytes()
    code, out, err = cli(capsys, "eintragen", *argv, "--datei", str(liste))
    assert (code, out, err) == (2, "", f"Fehler: {msg}\n")
    assert liste.read_bytes() == alt
    assert rest(liste.parent) == ["ports.toml"]


def test_cli_liste_problem(tmp_path, capsys):
    p = tmp_path / "x.toml"
    code, out, err = cli(capsys, "eintragen", "n", "abc", "--datei", str(p))
    assert (code, out, err) == (2, "", f"Fehler: Datei nicht gefunden: {p}\n")
    assert not p.exists()
    p.write_text("port = []\n")
    code, out, err = cli(capsys, "eintragen", "n", "9100", "--datei", str(p))
    assert err == "Fehler: Liste kann nicht durch einen [[port]]-Block erweitert werden\n"
    p.write_text("[[")
    assert cli(capsys, "eintragen", "n", "9100", "--datei", str(p))[0] == 2
    p.write_bytes(b"\xff")
    code, out, err = cli(capsys, "eintragen", "n", "9100", "--datei", str(p))
    assert code == 2 and out == "" and err.startswith(f"Fehler: Liste ist kein gültiges TOML: {p}: ")
    assert err.count("\n") == 1


def test_cli_schreibfehler(liste, capsys, monkeypatch):
    alt = liste.read_bytes()
    _kaputt(monkeypatch, "replace")
    code, out, err = cli(capsys, "eintragen", "n", "9100", "--datei", str(liste))
    assert code == 2 and out == "" and err.startswith("Fehler: Datei nicht schreibbar: ")
    monkeypatch.undo()
    assert liste.read_bytes() == alt and rest(liste.parent) == ["ports.toml"]


def test_cli_argparse(capsys):
    with pytest.raises(SystemExit) as ei:
        main(["eintragen", "x"])
    assert ei.value.code == 2
    with pytest.raises(SystemExit) as ei:
        main(["eintragen", "x", "1", "--unbekannt"])
    assert ei.value.code == 2
