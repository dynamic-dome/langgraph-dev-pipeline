"""Unabhängige Akzeptanztests für A8: portwart austragen."""
import builtins
import dataclasses
import io
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

VERKLEINERN = "Liste kann nicht durch Entfernen eines [[port]]-Blocks verkleinert werden"


def z(*zeilen, ende="\n"):
    return ("\n".join(zeilen) + ende).encode("utf-8")


KOPF = ["# Portliste", "# zweite Zeile", ""]
A = ["[[port]]", "port = 8765", 'projekt = "alpha"', 'zweck = "Erster"']
B = ["[[port]]", "port = 8766", 'projekt = "beta"', 'pfad = "../beta"']
C = ["[[port]]", "port = 8767", 'projekt = "gamma"']
BASIS = z(*KOPF, *A, "", *B, "", *C)


# ---------------------------------------------------------------- Helfer

def schreibe(tmp_path, daten, name="ports.toml"):
    ziel = tmp_path / name
    ziel.write_bytes(daten)
    return ziel


def lies(pfad):
    with io.open(pfad, "rb") as f:
        return f.read()


def ordner(tmp_path):
    return sorted(os.listdir(tmp_path))


def nie(*args, **kwargs):
    raise AssertionError("os.replace darf nicht aufgerufen werden")


def spion(monkeypatch):
    aufrufe = []
    echt = os.replace

    def replace(quelle, ziel):
        aufrufe.append((quelle, ziel))
        return echt(quelle, ziel)

    monkeypatch.setattr(os, "replace", replace)
    return aufrufe


def cli(tmp_path, *argv):
    return subprocess.run(
        [sys.executable, "-m", "portwart", *argv],
        cwd=tmp_path,
        env=dict(os.environ, PYTHONPATH=str(REPO), PYTHONIOENCODING="utf-8"),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )


def felder(eintraege):
    return [(e.port, e.projekt, e.zweck, e.pfad) for e in eintraege]


# ---------------------------------------------------------------- Erfolg

def test_erfolg_mitte_bytes_rueckgabe_ein_replace(tmp_path, monkeypatch):
    from portwart.austragen import trage_aus
    from portwart.liste import Eintrag, lade

    ziel = schreibe(tmp_path, BASIS)
    aufrufe = spion(monkeypatch)
    ergebnis = trage_aus(str(ziel), "beta")
    assert ergebnis == Eintrag(8766, "beta", "", "../beta")
    assert lies(ziel) == z(*KOPF, *A, "", *C)
    assert len(aufrufe) == 1
    assert ordner(tmp_path) == ["ports.toml"]
    assert [e.projekt for e in lade(ziel)] == ["alpha", "gamma"]


@pytest.mark.parametrize("name, port, zweck, pfad, erwartet", [
    ("alpha", 8765, "Erster", None, z(*KOPF, *B, "", *C)),
    ("beta", 8766, "", "../beta", z(*KOPF, *A, "", *C)),
    ("gamma", 8767, "", None, z(*KOPF, *A, "", *B)),
])
def test_erster_mittlerer_letzter_block(tmp_path, name, port, zweck, pfad, erwartet):
    from portwart.austragen import trage_aus
    from portwart.liste import Eintrag

    ziel = schreibe(tmp_path, BASIS)
    assert trage_aus(str(ziel), name) == Eintrag(port, name, zweck, pfad)
    assert lies(ziel) == erwartet
    assert ordner(tmp_path) == ["ports.toml"]


def test_kommentare_ueber_unter_zwischen_bleiben(tmp_path):
    from portwart.austragen import trage_aus

    daten = z(
        "# oben",
        "[[port]]",
        "# über port",
        "port = 8765",
        "# zwischen",
        "",
        'projekt = "a"',
        "  # eingerückt",
        "",
        "# unter dem Block",
        "[[port]]",
        "port = 8766",
        'projekt = "b"',
    )
    ziel = schreibe(tmp_path, daten)
    trage_aus(str(ziel), "a")
    assert lies(ziel) == z(
        "# oben",
        "# über port",
        "# zwischen",
        "",
        "  # eingerückt",
        "",
        "# unter dem Block",
        "[[port]]",
        "port = 8766",
        'projekt = "b"',
    )


def test_einzelblock_behaelt_kommentare_und_liste_leer(tmp_path):
    from portwart.austragen import trage_aus
    from portwart.liste import lade

    daten = z("# kopf", "", "[[port]]", "port = 8765", 'projekt = "a"', "# schluss")
    ziel = schreibe(tmp_path, daten)
    trage_aus(str(ziel), "a")
    assert lies(ziel) == z("# kopf", "# schluss")
    assert lade(ziel) == []


def test_anderer_tabellenkopf_nach_dem_block_bleibt(tmp_path, monkeypatch):
    from portwart.austragen import trage_aus
    from portwart.liste import Eintrag, lade

    daten = b'# Kopf\n\n[[port]]\nport = 8765\nprojekt = "a"\n[andere]\nx = 1\n'
    ziel = schreibe(tmp_path, daten)
    aufrufe = spion(monkeypatch)
    assert trage_aus(str(ziel), "a") == Eintrag(8765, "a", "", None)
    assert lies(ziel) == b"# Kopf\n[andere]\nx = 1\n"
    assert len(aufrufe) == 1
    assert lade(str(ziel)) == []
    assert ordner(tmp_path) == ["ports.toml"]


@pytest.mark.parametrize("name, erwartet", [
    ("b", z("[[port]]", "port = 8765", 'projekt = "a"', ende="\n")),
    ("a", z("", "[[port]]", "port = 8766", 'projekt = "b"', ende="")),
])
def test_block_am_dateiende_ohne_zeilenende(tmp_path, name, erwartet):
    from portwart.austragen import trage_aus

    daten = z("[[port]]", "port = 8765", 'projekt = "a"', "",
              "[[port]]", "port = 8766", 'projekt = "b"', ende="")
    ziel = schreibe(tmp_path, daten)
    trage_aus(str(ziel), name)
    assert lies(ziel) == erwartet


@pytest.mark.parametrize("vorzeile", [b"\r\n", b"  \t\r\n"])
def test_crlf_leerzeile_vor_dem_kopf(tmp_path, vorzeile):
    from portwart.austragen import trage_aus

    ba = b'[[port]]\r\nport = 8765\r\nprojekt = "a"\r\n'
    bb = b'[[port]]\r\nport = 8766\r\nprojekt = "b"\r\n'
    bc = b'[[port]]\nport = 8767\nprojekt = "c"\n'
    daten = b"# kopf\r\n" + vorzeile + ba + b"\r\n" + bb + b"\n" + bc
    ziel = schreibe(tmp_path, daten)
    trage_aus(str(ziel), "a")
    assert lies(ziel) == b"# kopf\r\n" + b"\r\n" + bb + b"\n" + bc


# ---------------------------------------------------------------- Rundlauf

@pytest.mark.parametrize("orig, erwartet", [
    (BASIS, BASIS),
    (BASIS[:-1], BASIS),
    (b"", b""),
    (b"# nur Kommentar", b"# nur Kommentar\n"),
    (b"# nur Kommentar\n", b"# nur Kommentar\n"),
])
def test_rundlauf_eintragen_austragen(tmp_path, orig, erwartet):
    from portwart.austragen import trage_aus
    from portwart.eintragen import trage_ein
    from portwart.liste import Eintrag

    ziel = schreibe(tmp_path, orig)
    trage_ein(str(ziel), "neu", 9001, "Zweck", "../neu")
    assert lies(ziel) != orig or orig == b""  # eintragen hat etwas geschrieben
    assert trage_aus(str(ziel), "neu") == Eintrag(9001, "neu", "Zweck", "../neu")
    assert lies(ziel) == erwartet
    assert ordner(tmp_path) == ["ports.toml"]


# ---------------------------------------------------------------- Namen

@pytest.mark.parametrize("name", ["x", "Beta", "BETA", " beta", "beta ", ""])
def test_name_unbekannt_exakt(tmp_path, monkeypatch, name):
    from portwart.austragen import AustragFehler, trage_aus

    ziel = schreibe(tmp_path, BASIS)
    monkeypatch.setattr(os, "replace", nie)
    with pytest.raises(AustragFehler) as ei:
        trage_aus(str(ziel), name)
    assert str(ei.value) == f"Name '{name}' nicht gefunden"
    assert lies(ziel) == BASIS
    assert ordner(tmp_path) == ["ports.toml"]


@pytest.mark.parametrize("daten, erwartet", [
    (z("[[port]]", "port = 8770", 'projekt = "job-radar"', "",
       "[[port]]", "port = 8771", 'projekt = "job-radar"'),
     "Ports 8770, 8771"),
    (z("[[port]]", "port = 8770", 'projekt = "job-radar"', "",
       "[[port]]", "port = 8775", 'projekt = "anders"', "",
       "[[port]]", "port = 8771", 'projekt = "job-radar"', "",
       "[[port]]", "port = 8770", 'projekt = "job-radar"'),
     "Ports 8770, 8771"),
    (z("[[port]]", "port = 8770", 'projekt = "job-radar"', "",
       "[[port]]", "port = 8770", 'projekt = "job-radar"'),
     "Ports 8770"),
])
def test_name_mehrfach(tmp_path, monkeypatch, daten, erwartet):
    from portwart.austragen import AustragFehler, trage_aus

    ziel = schreibe(tmp_path, daten)
    monkeypatch.setattr(os, "replace", nie)
    with pytest.raises(AustragFehler) as ei:
        trage_aus(str(ziel), "job-radar")
    assert str(ei.value) == f"Name 'job-radar' ist mehrfach eingetragen: {erwartet}"
    assert lies(ziel) == daten
    assert ordner(tmp_path) == ["ports.toml"]


# ---------------------------------------------------------------- Zeilenerkennung

def test_sonderzeichen_in_strings_und_kommentaren(tmp_path):
    from portwart.austragen import trage_aus
    from portwart.liste import Eintrag

    a = ["[[port]]", "port = 8765 # it's", 'projekt = "alpha"', 'zweck = "a[b # c"']
    b = ["[[port]]", 'port = 8766 # it\'s [[port]] "', 'projekt = "beta" # ] [',
         "zweck = 'x\"y # z'", 'pfad = "p # [ \'"', 'tags = ["]", \'[\']']
    c = ["[[port]]", "port = 8767", 'projekt = "gamma"',
         'zweck = "sag \\"hi\\" # nicht Kommentar"', "pfad = 'C:\\x # ['"]
    bloecke = {"alpha": a, "beta": b, "gamma": c}
    erwartete = {
        "alpha": Eintrag(8765, "alpha", "a[b # c", None),
        "beta": Eintrag(8766, "beta", 'x"y # z', "p # [ '"),
        "gamma": Eintrag(8767, "gamma", 'sag "hi" # nicht Kommentar', "C:\\x # ["),
    }
    daten = z("# kopf", "", *a, "", *b, "", *c)
    for name, entfernt in bloecke.items():
        ziel = schreibe(tmp_path, daten)
        assert trage_aus(str(ziel), name) == erwartete[name]
        zeilen = ["# kopf"]
        for n, blk in bloecke.items():
            if n != name:
                zeilen += ["", *blk]
        assert lies(ziel) == z(*zeilen), name
        assert ordner(tmp_path) == ["ports.toml"]


@pytest.mark.parametrize("name", ["arr", "vor", "nach"])
def test_mehrzeilige_werte_sind_wertinhalt(tmp_path, name):
    from portwart.austragen import trage_aus
    from portwart.liste import Eintrag

    vor = ["[[port]]", "port = 8765", 'projekt = "vor"']
    arr = ["[[port]]", "port = 8766", 'projekt = "arr"', "tags = [", '  "x",', '  "y",',
           "  # Kommentar im Array", "", "  # [[port]] ] [", '  "z",', "]"]
    nach = ["[[port]]", "port = 8767", 'projekt = "nach"']
    daten = z(*vor, "# davor", *arr, *nach)
    reste = ["  # Kommentar im Array", "", "  # [[port]] ] ["]
    erwartet = {
        "arr": z(*vor, "# davor", *reste, *nach),
        "vor": z("# davor", *arr, *nach),
        "nach": z(*vor, "# davor", *arr),
    }[name]
    ports = {"arr": 8766, "vor": 8765, "nach": 8767}
    ziel = schreibe(tmp_path, daten)
    assert trage_aus(str(ziel), name) == Eintrag(ports[name], name, "", None)
    assert lies(ziel) == erwartet
    assert ordner(tmp_path) == ["ports.toml"]


@pytest.mark.parametrize("q", ['"""', "'''"])
def test_mehrzeilige_zeichenkette_ist_wertinhalt(tmp_path, q):
    from portwart.austragen import trage_aus
    from portwart.liste import Eintrag

    vor = ["[[port]]", "port = 8765", 'projekt = "vor"']
    mitte = ["[[port]]", "port = 8766", 'projekt = "lit"',
             f"zweck = {q}", "a", "# kein Kommentar", "", f"b{q}"]
    nach = ["[[port]]", "port = 8767", 'projekt = "nach"']
    daten = z("# kopf", "", *vor, "", *mitte, "# nach dem Wert", "", *nach)
    ziel = schreibe(tmp_path, daten)
    assert trage_aus(str(ziel), "lit") == Eintrag(
        8766, "lit", "a\n# kein Kommentar\n\nb", None)
    assert lies(ziel) == z("# kopf", "", *vor, "# nach dem Wert", "", *nach)


def test_kopfaehnliche_zeile_in_zeichenkette_nie_falsch(tmp_path, monkeypatch):
    from portwart.austragen import trage_aus
    from portwart.liste import Eintrag

    vor = ["[[port]]", "port = 8765", 'projekt = "vor"']
    l = ["[[port]]", "port = 8766", 'projekt = "l"',
         'zweck = """', "a", "[[port]]", 'b"""']
    nach = ["[[port]]", "port = 8767", 'projekt = "nach"']
    daten = z("# Liste", *vor, "", *l, "", *nach)
    faelle = [
        ("l", Eintrag(8766, "l", "a\n[[port]]\nb", None),
         z("# Liste", *vor, "", *nach)),
        ("nach", Eintrag(8767, "nach", "", None),
         z("# Liste", *vor, "", *l)),
        ("vor", Eintrag(8765, "vor", "", None),
         z("# Liste", "", *l, "", *nach)),
    ]
    aufrufe = spion(monkeypatch)
    for name, eintrag, erwartet in faelle:
        aufrufe.clear()
        ziel = schreibe(tmp_path, daten)
        assert trage_aus(str(ziel), name) == eintrag, name
        assert lies(ziel) == erwartet, name
        assert len(aufrufe) == 1, name
        assert ordner(tmp_path) == ["ports.toml"], name


# ---------------------------------------------------------------- Ablehnung

INLINE = z('port = [{port = 8766, projekt = "wiki"}]')
QUOTED = z('[["port"]]', "port = 8765", 'projekt = "a"')
GEMISCHT = z("[[port]]", "port = 8765", 'projekt = "a"', "",
             '[["port"]]', "port = 8766", 'projekt = "b"')


@pytest.mark.parametrize("daten, name", [
    (QUOTED, "a"),
    (GEMISCHT, "a"),
    (GEMISCHT, "b"),
    (INLINE, "wiki"),
])
def test_ablehnung_nicht_unterstuetzter_formen(tmp_path, monkeypatch, daten, name):
    from portwart.austragen import AustragFehler, trage_aus

    ziel = schreibe(tmp_path, daten)
    monkeypatch.setattr(os, "replace", nie)
    with pytest.raises(AustragFehler) as ei:
        trage_aus(str(ziel), name)
    assert str(ei.value) == VERKLEINERN
    assert lies(ziel) == daten
    assert ordner(tmp_path) == ["ports.toml"]


def test_namenspruefung_vor_dateiform(tmp_path, monkeypatch):
    from portwart.austragen import AustragFehler, trage_aus

    ziel = schreibe(tmp_path, INLINE)
    monkeypatch.setattr(os, "replace", nie)
    with pytest.raises(AustragFehler) as ei:
        trage_aus(str(ziel), "x")
    assert str(ei.value) == "Name 'x' nicht gefunden"
    with pytest.raises(AustragFehler) as ei:
        trage_aus(str(ziel), "wiki")
    assert str(ei.value) == VERKLEINERN
    assert lies(ziel) == INLINE
    assert ordner(tmp_path) == ["ports.toml"]


@pytest.mark.parametrize("modus", [
    "zweck", "port", "projekt", "pfad", "listenfehler",
    "fehlt", "zusatz", "vertauscht", "oserror", "unicode",
])
def test_reload_sicherung_unabhaengig_von_kopfzaehlung(tmp_path, monkeypatch, modus):
    from portwart.austragen import AustragFehler, trage_aus
    from portwart.liste import Eintrag, ListenFehler, lade as echt

    daten = z("[[port]]", "port = 8765", 'projekt = "a"', 'zweck = "eins"', "",
              "[[port]]", "port = 8766", 'projekt = "b"', "",
              "[[port]]", "port = 8767", 'projekt = "c"', 'pfad = "../c"')
    ziel = schreibe(tmp_path, daten)
    datei = str(ziel)
    alt = echt(datei)
    erwartet = [e for e in alt if e.projekt != "b"]
    assert len(erwartet) == 2 and erwartet[0] != erwartet[1]
    aufrufe = []
    echte = []  # echte Ergebnisse von lade(tmp) vor jeder Manipulation

    def lade_(pfad):
        aufrufe.append(pfad)
        if os.fspath(pfad) == os.fspath(datei):
            return echt(pfad)
        if modus == "listenfehler":
            raise ListenFehler("kaputt")
        if modus == "oserror":
            raise OSError(5, "kaputt")
        if modus == "unicode":
            raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "kaputt")
        real = echt(pfad)
        echte.append(list(real))
        if modus == "zweck":
            return [dataclasses.replace(real[0], zweck=real[0].zweck + "!"), real[1]]
        if modus == "port":
            return [real[0], dataclasses.replace(real[1], port=real[1].port + 1)]
        if modus == "projekt":
            return [dataclasses.replace(real[0], projekt="anderer"), real[1]]
        if modus == "pfad":
            return [real[0], dataclasses.replace(real[1], pfad="abweichend/pfad")]
        if modus == "fehlt":
            return real[:-1]
        if modus == "zusatz":
            return real + [Eintrag(9000, "zusatz")]
        if modus == "vertauscht":
            return [real[1], real[0]]
        raise AssertionError(modus)

    monkeypatch.setattr("portwart.austragen.lade", lade_)
    monkeypatch.setattr(os, "replace", nie)
    with pytest.raises(AustragFehler) as ei:
        trage_aus(datei, "b")
    assert str(ei.value) == VERKLEINERN
    # Testaufbau nachweisen: das echte Temp-Ergebnis war korrekt, bevor manipuliert wurde
    if modus not in ("listenfehler", "oserror", "unicode"):
        assert len(echte) >= 1
        for real in echte:
            assert len(real) == len(erwartet)
            assert felder(real) == felder(erwartet)
    assert lies(ziel) == daten
    assert ordner(tmp_path) == ["ports.toml"]
    assert os.fspath(aufrufe[0]) == os.fspath(datei)
    andere = [p for p in aufrufe if os.fspath(p) != os.fspath(datei)]
    assert andere
    zielordner = os.path.normcase(os.path.dirname(os.path.abspath(datei)))
    for p in andere:
        assert os.path.normcase(os.path.dirname(os.path.abspath(p))) == zielordner


# test_reload_port_meta und test_reload_port_meta_cli (Ablehnung bei [port.meta]) sind durch A9 abgelöst:
# Seit A9 trägt `austragen` den Eintrag samt Untertabellen aus (siehe aufgaben/portwart/A9).


# ---------------------------------------------------------------- Lade-/Schreibfehler

def test_lade_fehler_werden_durchgereicht(tmp_path, monkeypatch):
    from portwart.austragen import AustragFehler, trage_aus
    from portwart.liste import ListenFehler

    monkeypatch.setattr(os, "replace", nie)
    fehlt = tmp_path / "fehlt.toml"
    with pytest.raises(ListenFehler) as ei:
        trage_aus(str(fehlt), "a")
    assert not isinstance(ei.value, AustragFehler)
    assert str(ei.value) == f"Datei nicht gefunden: {fehlt}"

    kaputt = schreibe(tmp_path, b"[[port\n", "kaputt.toml")
    with pytest.raises(ListenFehler) as ei:
        trage_aus(str(kaputt), "a")
    assert str(ei.value).startswith(f"kein gültiges TOML in {kaputt}: ")

    latin = schreibe(tmp_path, b'[[port]]\nport = 1\nprojekt = "\xff"\n', "latin.toml")
    with pytest.raises(UnicodeDecodeError):
        trage_aus(str(latin), "a")
    assert lies(kaputt) == b"[[port\n"
    assert ordner(tmp_path) == ["kaputt.toml", "latin.toml"]


def _oeffnen_scheitert(monkeypatch, ziel, fehler):
    echt = builtins.open

    def open_(datei, mode="r", *args, **kwargs):
        if mode == "rb" and not isinstance(datei, int) and Path(datei) == Path(ziel):
            raise fehler
        return echt(datei, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", open_)


def test_anfaengliches_oeffnen_scheitert(tmp_path, monkeypatch):
    from portwart.austragen import AustragFehler, trage_aus
    from portwart.liste import ListenFehler

    ziel = schreibe(tmp_path, BASIS)
    fehler = PermissionError(13, "Zugriff verweigert")
    _oeffnen_scheitert(monkeypatch, ziel, fehler)
    monkeypatch.setattr(os, "replace", nie)
    with pytest.raises(ListenFehler) as ei:
        trage_aus(str(ziel), "beta")
    assert not isinstance(ei.value, AustragFehler)
    assert str(ei.value) == f"Datei nicht lesbar: {Path(ziel)}: {fehler}"
    monkeypatch.undo()
    assert lies(ziel) == BASIS
    assert ordner(tmp_path) == ["ports.toml"]


def test_anfaengliches_oeffnen_scheitert_cli(tmp_path, monkeypatch, capsys):
    from portwart.__main__ import main

    ziel = schreibe(tmp_path, BASIS)
    fehler = PermissionError(13, "Zugriff verweigert")
    _oeffnen_scheitert(monkeypatch, ziel, fehler)
    monkeypatch.setattr(os, "replace", nie)
    rc = main(["austragen", "beta", "--datei", str(ziel)])
    aus = capsys.readouterr()
    assert rc == 2
    assert aus.out == ""
    assert aus.err == f"Fehler: Datei nicht lesbar: {Path(ziel)}: {fehler}\n"
    monkeypatch.undo()
    assert lies(ziel) == BASIS
    assert ordner(tmp_path) == ["ports.toml"]


class _Datei:
    """Datei-Attrappe, deren write oder close genau das übergebene Fehlerobjekt wirft."""

    def __init__(self, echt, modus, fehler):
        self.echt = echt
        self.modus = modus
        self.fehler = fehler

    def write(self, daten):
        if self.modus == "write":
            raise self.fehler
        return self.echt.write(daten)

    def close(self):
        self.echt.close()  # die echte Datei wird immer zuerst geschlossen
        if self.modus == "close":
            raise self.fehler

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def __getattr__(self, name):
        return getattr(self.echt, name)


@pytest.mark.parametrize("wo", ["mkstemp", "write", "close", "replace", "read", "fdopen"])
def test_schreibfehler(tmp_path, monkeypatch, wo):
    from portwart.austragen import AustragFehler, Path as AuPath, trage_aus

    ziel = schreibe(tmp_path, BASIS)
    datei = str(ziel)
    fehler = OSError(28, f"Fehler bei {wo}")

    def wirf(*args, **kwargs):
        raise fehler

    if wo == "mkstemp":
        monkeypatch.setattr(tempfile, "mkstemp", wirf)
    elif wo in ("write", "close"):
        echt_fdopen = os.fdopen
        monkeypatch.setattr(
            os, "fdopen",
            lambda fd, *a, **k: _Datei(echt_fdopen(fd, *a, **k), wo, fehler))
    elif wo == "replace":
        monkeypatch.setattr(os, "replace", wirf)
    elif wo == "read":
        monkeypatch.setattr(AuPath, "read_bytes", wirf)
    else:
        monkeypatch.setattr(os, "fdopen", wirf)
    with pytest.raises(AustragFehler) as ei:
        trage_aus(datei, "beta")
    assert str(ei.value) == f"Datei nicht schreibbar: {datei}: {fehler}"
    monkeypatch.undo()
    assert lies(ziel) == BASIS
    assert ordner(tmp_path) == ["ports.toml"]


def test_fdopen_fehler_schliesst_fd(tmp_path, monkeypatch):
    from portwart.austragen import AustragFehler, trage_aus

    ziel = schreibe(tmp_path, BASIS)
    fds = []
    geschlossen = []
    echt_mkstemp = tempfile.mkstemp
    echt_close = os.close

    def mkstemp(*args, **kwargs):
        fd, pfad = echt_mkstemp(*args, **kwargs)
        fds.append(fd)
        return fd, pfad

    def close(fd):
        geschlossen.append(fd)
        return echt_close(fd)

    def wirf(*args, **kwargs):
        raise OSError(24, "zu viele Dateien")

    monkeypatch.setattr(tempfile, "mkstemp", mkstemp)
    monkeypatch.setattr(os, "fdopen", wirf)
    monkeypatch.setattr(os, "close", close)
    with pytest.raises(AustragFehler) as ei:
        trage_aus(str(ziel), "beta")
    assert str(ei.value).startswith(f"Datei nicht schreibbar: {ziel}: ")
    assert len(fds) == 1
    assert fds[0] in geschlossen
    monkeypatch.undo()
    assert lies(ziel) == BASIS
    assert ordner(tmp_path) == ["ports.toml"]


# ---------------------------------------------------------------- CLI

def test_cli_erfolg_mit_vorgabedatei(tmp_path):
    ziel = schreibe(tmp_path, BASIS)
    r = cli(tmp_path, "austragen", "gamma")
    assert r.returncode == 0
    assert r.stdout == "ausgetragen gamma 8767\n"
    assert r.stderr == ""
    assert lies(ziel) == z(*KOPF, *A, "", *B)
    assert ordner(tmp_path) == ["ports.toml"]


def test_cli_erfolg_mit_datei_option(tmp_path):
    ziel = schreibe(tmp_path, BASIS, "andere.toml")
    r = cli(tmp_path, "austragen", "beta", "--datei", str(ziel))
    assert (r.returncode, r.stdout, r.stderr) == (0, "ausgetragen beta 8766\n", "")
    assert lies(ziel) == z(*KOPF, *A, "", *C)


def test_cli_name_mit_steuerzeichen(tmp_path):
    daten = z("[[port]]", "port = 8765", 'projekt = "t\\u0001x"')
    ziel = schreibe(tmp_path, daten)
    r = cli(tmp_path, "austragen", "a\u0001b")
    assert r.returncode == 2
    assert r.stdout == ""
    assert r.stderr == "Fehler: Name 'a\\u0001b' nicht gefunden\n"
    assert lies(ziel) == daten
    r = cli(tmp_path, "austragen", "t\u0001x")
    assert (r.returncode, r.stderr) == (0, "")
    assert r.stdout == "ausgetragen t\\u0001x 8765\n"


DOPPELT = z("[[port]]", "port = 8770", 'projekt = "job-radar"', "",
            "[[port]]", "port = 8771", 'projekt = "job-radar"')


@pytest.mark.parametrize("inhalt, name, meldung", [
    (BASIS, "x", "Name 'x' nicht gefunden"),
    (BASIS, "Beta", "Name 'Beta' nicht gefunden"),
    (DOPPELT, "job-radar",
     "Name 'job-radar' ist mehrfach eingetragen: Ports 8770, 8771"),
    (None, "x", "Datei nicht gefunden: {p}"),
    (z("[[port]]", "port = 8765"), "x", "Eintrag 1: Pflichtfeld 'projekt' fehlt"),
    (INLINE, "x", "Name 'x' nicht gefunden"),
    (INLINE, "wiki", VERKLEINERN),
    (QUOTED, "a", VERKLEINERN),
    (GEMISCHT, "b", VERKLEINERN),
])
def test_cli_fehlerzeilen(tmp_path, inhalt, name, meldung):
    ziel = tmp_path / "ports.toml"
    if inhalt is not None:
        ziel.write_bytes(inhalt)
    r = cli(tmp_path, "austragen", name, "--datei", str(ziel))
    assert r.returncode == 2
    assert r.stdout == ""
    assert r.stderr == "Fehler: " + meldung.replace("{p}", str(ziel)) + "\n"
    if inhalt is not None:
        assert lies(ziel) == inhalt
        assert ordner(tmp_path) == ["ports.toml"]
    else:
        assert ordner(tmp_path) == []


def test_cli_toml_und_utf8_fehler(tmp_path):
    kaputt = schreibe(tmp_path, b"[[port\n", "kaputt.toml")
    r = cli(tmp_path, "austragen", "a", "--datei", str(kaputt))
    assert r.returncode == 2 and r.stdout == ""
    assert r.stderr.startswith(f"Fehler: kein gültiges TOML in {kaputt}: ")
    assert r.stderr.count("\n") == 1 and r.stderr.endswith("\n")

    roh = b'[[port]]\nport = 1\nprojekt = "\xff"\n'
    latin = schreibe(tmp_path, roh, "latin.toml")
    try:
        roh.decode()
    except UnicodeDecodeError as e:
        grund = str(e)
    r = cli(tmp_path, "austragen", "a", "--datei", str(latin))
    assert r.returncode == 2 and r.stdout == ""
    assert r.stderr == f"Fehler: Liste ist kein gültiges TOML: {latin}: {grund}\n"
    assert lies(kaputt) == b"[[port\n" and lies(latin) == roh
    assert ordner(tmp_path) == ["kaputt.toml", "latin.toml"]


def test_cli_argparse_fehler_exit_2(tmp_path, capsys):
    from portwart.__main__ import main

    ziel = str(tmp_path / "ports.toml")
    for argv in (["austragen"],
                 ["austragen", "--datei", ziel],
                 ["austragen", "a", "--unbekannt"],
                 ["austragen", "a", "b"]):
        with pytest.raises(SystemExit) as ei:
            main(argv)
        assert ei.value.code == 2, argv
    capsys.readouterr()
    assert ordner(tmp_path) == []


def test_bestehende_befehle_unveraendert(tmp_path):
    from portwart.eintragen import baue_block

    ziel = schreibe(tmp_path, BASIS)
    r = cli(tmp_path, "eintragen", "neu", "8900")
    assert (r.returncode, r.stdout, r.stderr) == (0, "eingetragen neu 8900\n", "")
    assert lies(ziel) == BASIS + baue_block("neu", 8900).encode("utf-8")
    r = cli(tmp_path, "pruefen")
    assert (r.returncode, r.stdout, r.stderr) == (0, "keine doppelten Ports\n", "")
