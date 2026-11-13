"""Akzeptanztests A7: portwart eintragen."""
import os
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

BASIS = (
    "# Kommentar mit Umlaut äöü\n"
    "[[port]]\n"
    "port = 8766\n"
    'projekt = "wiki-inselwelt"\n'
    'zweck = "Wiki"\n'
    "\n"
    "# Noch ein Kommentar\n"
    "[[port]]\n"
    "port = 8770\n"
    'projekt = "job-radar"\n'
).encode("utf-8")


def _cli(tmp_path, *args):
    return subprocess.run(
        [sys.executable, "-m", "portwart", *args],
        cwd=tmp_path,
        env=dict(os.environ, PYTHONPATH=str(REPO), PYTHONIOENCODING="utf-8"),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )


def _liste(tmp_path, inhalt=BASIS, name="ports.toml"):
    p = tmp_path / name
    p.write_bytes(inhalt)
    return p


def _nur(tmp_path):
    return sorted(x.name for x in tmp_path.iterdir())


def _fehler_cli(tmp_path, meldung, *args):
    r = _cli(tmp_path, "eintragen", *args)
    assert r.returncode == 2
    assert r.stdout == ""
    assert r.stderr.splitlines() == [meldung]
    return r


# ---------- reine Funktionen ----------

def test_baue_block_format():
    from portwart.eintragen import baue_block
    assert baue_block("x", 9000, pfad="C:\\a") == (
        '\n[[port]]\nport = 9000\nprojekt = "x"\npfad = "C:\\\\a"\n')
    assert baue_block("x", 9000) == '\n[[port]]\nport = 9000\nprojekt = "x"\n'
    assert baue_block("x", 9000, zweck="", pfad="p") == (
        '\n[[port]]\nport = 9000\nprojekt = "x"\nzweck = ""\npfad = "p"\n')


def test_toml_text_escapes_und_roundtrip():
    from portwart.eintragen import toml_text
    assert toml_text('a"b') == '"a\\"b"'
    assert toml_text("a\\b") == '"a\\\\b"'
    assert toml_text("a\nb\tc\rd") == '"a\\nb\\tc\\rd"'
    assert toml_text("ä") == '"ä"'
    alle = "".join(chr(i) for i in range(0x20)) + "\x7f" + 'x"\\y äöü€'
    t = toml_text(alle)
    assert "\n" not in t and "\x00" not in t and "\x7f" not in t
    assert tomllib.loads("a = " + t)["a"] == alle


def test_anzeige_text():
    from portwart.eintragen import anzeige_text
    assert anzeige_text("a\nb\rc\td\be\ff") == "a\\nb\\rc\\td\\be\\ff"
    assert anzeige_text("\x01") == "\\u0001"
    assert anzeige_text("\x7f") == "\\u007f"
    assert anzeige_text("\x1f") == "\\u001f"
    assert anzeige_text("a\\b äöü") == "a\\b äöü"


# ---------- trage_ein: Erfolg ----------

def test_trage_ein_erfolg_bytes_und_rueckgabe(tmp_path):
    from portwart.eintragen import trage_ein
    from portwart.liste import Eintrag, lade
    d = _liste(tmp_path)
    e = trage_ein(d, "neu", 9100, zweck="Z", pfad="C:\\x")
    assert e == Eintrag(9100, "neu", "Z", "C:\\x")
    neu = d.read_bytes()
    assert neu.startswith(BASIS)
    assert neu[len(BASIS):] == (
        '\n[[port]]\nport = 9100\nprojekt = "neu"\nzweck = "Z"\npfad = "C:\\\\x"\n'
    ).encode()
    assert lade(d)[-1] == e
    assert len(lade(d)) == 3
    assert _nur(tmp_path) == ["ports.toml"]


def test_trage_ein_ohne_zweck_pfad_und_leerer_zweck(tmp_path):
    from portwart.eintragen import trage_ein
    from portwart.liste import Eintrag
    d = _liste(tmp_path)
    assert trage_ein(str(d), "a", 9101) == Eintrag(9101, "a", "", None)
    assert trage_ein(d, "b", 9102, zweck="") == Eintrag(9102, "b", "", None)
    t = d.read_bytes()
    assert t.endswith(b'\n[[port]]\nport = 9102\nprojekt = "b"\nzweck = ""\n')
    assert b'projekt = "a"\n\n[[port]]' in t


def test_trage_ein_fehlender_zeilenumbruch(tmp_path):
    from portwart.eintragen import trage_ein
    roh = BASIS.rstrip(b"\n")
    d = _liste(tmp_path, roh)
    trage_ein(d, "neu", 9100)
    assert d.read_bytes() == roh + b'\n\n[[port]]\nport = 9100\nprojekt = "neu"\n'


def test_trage_ein_leere_datei(tmp_path):
    from portwart.eintragen import trage_ein
    d = _liste(tmp_path, b"")
    trage_ein(d, "neu", 9100)
    assert d.read_bytes() == b'\n[[port]]\nport = 9100\nprojekt = "neu"\n'


def test_trage_ein_crlf_bestand_bleibt(tmp_path):
    from portwart.eintragen import trage_ein
    roh = b'[[port]]\r\nport = 8766\r\nprojekt = "w"\r\n'
    d = _liste(tmp_path, roh)
    trage_ein(d, "neu", 9100)
    assert d.read_bytes() == roh + b'\n[[port]]\nport = 9100\nprojekt = "neu"\n'


def test_escaping_roundtrip_ueber_lade(tmp_path):
    from portwart.eintragen import trage_ein
    from portwart.liste import lade
    d = _liste(tmp_path)
    e = trage_ein(d, 'na"me\\x', 9100, zweck='sag "hi"\\', pfad="C:\\Users\\a b\\")
    assert lade(d)[-1] == e
    assert lade(d)[-1].projekt == 'na"me\\x'
    assert lade(d)[-1].pfad == "C:\\Users\\a b\\"


# ---------- trage_ein: Ablehnungen ----------

def _abgelehnt(tmp_path, meldung, *args, inhalt=BASIS, **kw):
    from portwart.eintragen import EintragFehler, trage_ein
    d = _liste(tmp_path, inhalt)
    with pytest.raises(EintragFehler) as ei:
        trage_ein(d, *args, **kw)
    assert str(ei.value) == meldung
    assert d.read_bytes() == inhalt
    assert _nur(tmp_path) == ["ports.toml"]


def test_ablehnungen_einzeln(tmp_path):
    _abgelehnt(tmp_path, "Name darf nicht leer sein", "  ", 9100)
    _abgelehnt(tmp_path, "Name darf nicht leer sein", "", 9100)
    _abgelehnt(tmp_path, "Port muss eine ganze Zahl sein", "x", True)
    _abgelehnt(tmp_path, "Port muss eine ganze Zahl sein", "x", "9100")
    _abgelehnt(tmp_path, "Port 0 liegt außerhalb von 1-65535", "x", 0)
    _abgelehnt(tmp_path, "Port 65536 liegt außerhalb von 1-65535", "x", 65536)
    _abgelehnt(tmp_path, "Zweck muss ein Text sein", "x", 9100, zweck=5)
    _abgelehnt(tmp_path, "Pfad muss ein nicht leerer Text sein", "x", 9100, pfad=" ")
    _abgelehnt(tmp_path, "Pfad muss ein nicht leerer Text sein", "x", 9100, pfad=3)
    _abgelehnt(tmp_path, "Name 'job-radar' gibt es schon", "job-radar", 9100)
    _abgelehnt(tmp_path, "Port 8766 ist schon vergeben: wiki-inselwelt", "x", 8766)


def test_name_exakt_ohne_trimmen_und_gross_klein(tmp_path):
    from portwart.eintragen import trage_ein
    d = _liste(tmp_path)
    trage_ein(d, "Job-Radar", 9100)
    trage_ein(d, " job-radar", 9101)
    from portwart.liste import lade
    assert [e.projekt for e in lade(d)][-2:] == ["Job-Radar", " job-radar"]


def test_reihenfolge_der_pruefungen(tmp_path):
    # Name leer vor Port ungültig
    _abgelehnt(tmp_path, "Name darf nicht leer sein", "", 70000, zweck=1, pfad="")
    # Port ungültig vor Zweck/Pfad
    _abgelehnt(tmp_path, "Port 0 liegt außerhalb von 1-65535", "x", 0, zweck=1, pfad="")
    # Zweck vor Pfad
    _abgelehnt(tmp_path, "Zweck muss ein Text sein", "x", 9100, zweck=1, pfad="")
    # Pfad vor Name vorhanden
    _abgelehnt(tmp_path, "Pfad muss ein nicht leerer Text sein",
               "job-radar", 8766, pfad="  ")
    # Name vorhanden vor Port vergeben
    _abgelehnt(tmp_path, "Name 'job-radar' gibt es schon", "job-radar", 8766)


def test_laden_vor_eingabepruefung(tmp_path):
    from portwart.eintragen import trage_ein
    from portwart.liste import ListenFehler
    with pytest.raises(ListenFehler):
        trage_ein(tmp_path / "fehlt.toml", "", 70000)
    assert _nur(tmp_path) == []
    d = _liste(tmp_path, b"das ist [kein toml")
    with pytest.raises(ListenFehler):
        trage_ein(d, "  ", 9100)
    assert d.read_bytes() == b"das ist [kein toml"
    d.write_bytes(b"# \xff\xfe\n")
    with pytest.raises(UnicodeDecodeError):
        trage_ein(d, "x", 9100)
    assert d.read_bytes() == b"# \xff\xfe\n"


def test_portkonflikt_z_a_z(tmp_path):
    inhalt = b"".join(
        b'[[port]]\nport = 9000\nprojekt = "%s"\n' % n for n in (b"z", b"a", b"z"))
    _abgelehnt(tmp_path, "Port 9000 ist schon vergeben: z, a", "neu", 9000,
               inhalt=inhalt)


def test_vorhandene_doppelung_blockiert_nicht(tmp_path):
    from portwart.eintragen import trage_ein
    from portwart.liste import lade
    inhalt = (BASIS + b'\n[[port]]\nport = 8770\nprojekt = "zweiter"\n')
    d = _liste(tmp_path, inhalt)
    trage_ein(d, "neu", 9100)
    assert d.read_bytes().startswith(inhalt)
    assert lade(d)[-1].port == 9100
    _abgelehnt(tmp_path, "Port 8770 ist schon vergeben: job-radar, zweiter",
               "x", 8770, inhalt=inhalt)


@pytest.mark.parametrize("inhalt", [
    b"port = []\n",
    b'port = [{port = 8766, projekt = "wiki"}]\n',
])
def test_nicht_erweiterbar(tmp_path, monkeypatch, inhalt):
    from portwart.eintragen import EintragFehler, trage_ein
    aufrufe = []
    echt = os.replace
    monkeypatch.setattr(os, "replace", lambda a, b: (aufrufe.append(a), echt(a, b)))
    d = _liste(tmp_path, inhalt)
    with pytest.raises(EintragFehler) as ei:
        trage_ein(d, "neu", 9100)
    assert str(ei.value) == "Liste kann nicht durch einen [[port]]-Block erweitert werden"
    assert aufrufe == []
    assert d.read_bytes() == inhalt
    assert _nur(tmp_path) == ["ports.toml"]


# ---------- Atomarität / Schreibfehler ----------

def test_tempdatei_liegt_im_zielordner(tmp_path, monkeypatch):
    from portwart.eintragen import trage_ein
    quellen = []
    echt = os.replace

    def spion(a, b):
        quellen.append((Path(a), Path(b)))
        return echt(a, b)

    monkeypatch.setattr(os, "replace", spion)
    d = _liste(tmp_path)
    trage_ein(d, "neu", 9100)
    assert len(quellen) == 1
    src, dst = quellen[0]
    assert src.parent.resolve() == tmp_path.resolve()
    assert src.name != d.name
    assert dst.resolve() == d.resolve()
    assert _nur(tmp_path) == ["ports.toml"]


class _Datei:
    def __init__(self, f, modus):
        self._f, self._modus = f, modus

    def write(self, daten):
        if self._modus == "write":
            raise OSError("Platte voll")
        return self._f.write(daten)

    def close(self):
        self._f.close()
        if self._modus == "close":
            raise OSError("close kaputt")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()
        return False

    def __getattr__(self, n):
        return getattr(self._f, n)


def _schreibfehler(tmp_path, monkeypatch, wo):
    from portwart.eintragen import EintragFehler, trage_ein
    d = _liste(tmp_path)
    if wo == "mkstemp":
        def kaputt(*a, **k):
            raise OSError("kein Platz")
        monkeypatch.setattr(tempfile, "mkstemp", kaputt)
    elif wo in ("write", "close"):
        echt = os.fdopen
        monkeypatch.setattr(os, "fdopen",
                            lambda fd, *a, **k: _Datei(echt(fd, *a, **k), wo))
    else:
        def kaputt(a, b):
            raise OSError("gesperrt")
        monkeypatch.setattr(os, "replace", kaputt)
    with pytest.raises(EintragFehler) as ei:
        trage_ein(d, "neu", 9100)
    assert str(ei.value).startswith("Datei nicht schreibbar: ")
    assert d.read_bytes() == BASIS
    assert _nur(tmp_path) == ["ports.toml"]


@pytest.mark.parametrize("wo", ["mkstemp", "write", "close", "replace"])
def test_schreibfehler(tmp_path, monkeypatch, wo):
    _schreibfehler(tmp_path, monkeypatch, wo)


# ---------- CLI ----------

def test_cli_erfolg_mit_und_ohne_optionen(tmp_path):
    from portwart.liste import Eintrag, lade
    d = _liste(tmp_path)
    r = _cli(tmp_path, "eintragen", "neuer-dienst", "9100")
    assert (r.returncode, r.stdout, r.stderr) == (0, "eingetragen neuer-dienst 9100\n", "")
    r = _cli(tmp_path, "eintragen", "zwei", "9101", "--zweck", "Z Z",
             "--pfad", "C:\\a\\b")
    assert (r.returncode, r.stdout, r.stderr) == (0, "eingetragen zwei 9101\n", "")
    r = _cli(tmp_path, "eintragen", "drei", "9102", "--zweck", "")
    assert r.returncode == 0
    neu = d.read_bytes()
    assert neu.startswith(BASIS)
    assert neu.endswith(b'\n[[port]]\nport = 9102\nprojekt = "drei"\nzweck = ""\n')
    assert lade(d)[-3:] == [Eintrag(9100, "neuer-dienst", "", None),
                            Eintrag(9101, "zwei", "Z Z", "C:\\a\\b"),
                            Eintrag(9102, "drei", "", None)]


@pytest.mark.parametrize("text,port", [
    ("1", 1), ("65535", 65535), ("+9100", 9100), (" 9100 ", 9100), ("9_100", 9100),
])
def test_cli_portformen(tmp_path, text, port):
    from portwart.liste import lade
    d = _liste(tmp_path)
    r = _cli(tmp_path, "eintragen", "neu", text)
    assert (r.returncode, r.stdout, r.stderr) == (0, f"eingetragen neu {port}\n", "")
    assert lade(d)[-1].port == port


@pytest.mark.parametrize("args,meldung", [
    (("x", "8766"), "Fehler: Port 8766 ist schon vergeben: wiki-inselwelt"),
    (("job-radar", "9100"), "Fehler: Name 'job-radar' gibt es schon"),
    (("x", "70000"), "Fehler: Port 70000 liegt außerhalb von 1-65535"),
    (("x", "0"), "Fehler: Port 0 liegt außerhalb von 1-65535"),
    (("x", "abc"), "Fehler: Port muss eine ganze Zahl sein: 'abc'"),
    (("x", "9.5"), "Fehler: Port muss eine ganze Zahl sein: '9.5'"),
    (("x", ""), "Fehler: Port muss eine ganze Zahl sein: ''"),
    ((("  ", "9100")), "Fehler: Name darf nicht leer sein"),
    (("x", "9100", "--pfad", "  "), "Fehler: Pfad muss ein nicht leerer Text sein"),
    (("x", "-5"), "Fehler: Port -5 liegt außerhalb von 1-65535"),
])
def test_cli_ablehnungen(tmp_path, args, meldung):
    d = _liste(tmp_path)
    _fehler_cli(tmp_path, meldung, *args)
    assert d.read_bytes() == BASIS
    assert _nur(tmp_path) == ["ports.toml"]


def test_cli_liste_vor_port_und_fehlende_datei(tmp_path):
    _fehler_cli(tmp_path, "Fehler: Datei nicht gefunden: fehlt.toml",
                "x", "abc", "--datei", "fehlt.toml")
    _fehler_cli(tmp_path, "Fehler: Datei nicht gefunden: ports.toml", "", "abc")
    assert _nur(tmp_path) == []


def test_cli_ungueltige_liste_und_nicht_utf8(tmp_path):
    from portwart.liste import ListenFehler, lade
    d = _liste(tmp_path, b"das ist [kein toml")
    with pytest.raises(ListenFehler) as ei:
        lade(d)
    r = _cli(tmp_path, "eintragen", "x", "9100")
    assert r.returncode == 2 and r.stdout == ""
    assert r.stderr.startswith("Fehler: ")
    assert len(r.stderr.splitlines()) == 1
    assert d.read_bytes() == b"das ist [kein toml"
    d.write_bytes(b"# \xff\xfe\n")
    r = _cli(tmp_path, "eintragen", "x", "9100")
    assert r.returncode == 2 and r.stdout == ""
    assert r.stderr.startswith("Fehler: Liste ist kein gültiges TOML: ports.toml: ")
    assert d.read_bytes() == b"# \xff\xfe\n"
    assert _nur(tmp_path) == ["ports.toml"]


def test_cli_nicht_erweiterbar(tmp_path):
    for inhalt in (b"port = []\n", b'port = [{port = 8766, projekt = "wiki"}]\n'):
        d = _liste(tmp_path, inhalt)
        _fehler_cli(tmp_path,
                    "Fehler: Liste kann nicht durch einen [[port]]-Block erweitert werden",
                    "neu", "9100")
        assert d.read_bytes() == inhalt
        assert _nur(tmp_path) == ["ports.toml"]


def test_cli_name_mit_zeilenumbruch_erfolg(tmp_path):
    from portwart.liste import lade
    d = _liste(tmp_path)
    r = _cli(tmp_path, "eintragen", "a\nb", "9100")
    assert r.returncode == 0 and r.stderr == ""
    assert r.stdout == "eingetragen a\\nb 9100\n"
    assert len(r.stdout.splitlines()) == 1
    assert lade(d)[-1].projekt == "a\nb"


def test_cli_konflikt_mit_zeilenumbruch_im_vorhandenen_namen(tmp_path):
    inhalt = b'[[port]]\nport = 8766\nprojekt = "a\\nb"\n'
    d = _liste(tmp_path, inhalt)
    _fehler_cli(tmp_path, "Fehler: Port 8766 ist schon vergeben: a\\nb", "x", "8766")
    _fehler_cli(tmp_path, "Fehler: Name 'a\\nb' gibt es schon", "a\nb", "9100")
    assert d.read_bytes() == inhalt
    assert _nur(tmp_path) == ["ports.toml"]


def test_cli_argparse_fehler_exit_2(tmp_path):
    _liste(tmp_path)
    for args in ((["eintragen"]), (["eintragen", "nur-name"]),
                 (["eintragen", "x", "9100", "--unbekannt"])):
        r = _cli(tmp_path, *args)
        assert r.returncode == 2
        assert r.stdout == ""
        assert r.stderr != ""
    assert (tmp_path / "ports.toml").read_bytes() == BASIS


def test_bestehende_befehle_unveraendert(tmp_path):
    _liste(tmp_path)
    r = _cli(tmp_path, "pruefen")
    assert (r.returncode, r.stdout, r.stderr) == (0, "keine doppelten Ports\n", "")
    r = _cli(tmp_path, "frei", "abc")
    assert r.returncode == 2 and r.stdout == ""
    assert r.stderr.startswith("Fehler: ")
