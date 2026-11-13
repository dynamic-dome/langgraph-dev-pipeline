"""Akzeptanztests A9: Austragen mit Untertabellen."""
import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

VERKLEINERN = "Liste kann nicht durch Entfernen eines [[port]]-Blocks verkleinert werden"

A = '[[port]]\nport = 8765\nprojekt = "a"\n\n'
B = '[[port]]\nport = 8766\nprojekt = "b"\n\n'
C = '[[port]]\nport = 8767\nprojekt = "c"\n'


# --- Hilfen ---

@pytest.fixture
def nie(monkeypatch):
    def f(*a, **k):
        raise AssertionError("os.replace darf nicht aufgerufen werden")
    monkeypatch.setattr(os, "replace", f)


@pytest.fixture
def spion(monkeypatch):
    echt = os.replace
    aufrufe = []

    def f(src, dst):
        aufrufe.append((src, dst))
        echt(src, dst)
    monkeypatch.setattr(os, "replace", f)
    return aufrufe


def rest(ordner):
    return sorted(x.name for x in ordner.iterdir())


def schreibe(tmp_path, inhalt, name="ports.toml"):
    p = tmp_path / name
    p.write_bytes(inhalt.encode() if isinstance(inhalt, str) else inhalt)
    return p


def ohne_eintrag(daten, i):
    neu = dict(daten)
    liste = daten["port"][:i] + daten["port"][i + 1:]
    if liste:
        neu["port"] = liste
    else:
        neu.pop("port")
    return neu


def starte(tmp_path, *args):
    return subprocess.run(
        [sys.executable, "-m", "portwart", *args],
        cwd=tmp_path,
        env=dict(os.environ, PYTHONPATH=str(REPO), PYTHONIOENCODING="utf-8"),
        capture_output=True, text=True, encoding="utf-8", timeout=60,
    )


# --- Erfolg: Eintrag mit Untertabellen ---

def test_mitte_mit_meta_und_sub_spec_beispiel(tmp_path, spion):
    from portwart.austragen import trage_aus
    from portwart.liste import Eintrag, lade
    inhalt = (
        '[[port]]\nport = 8765\nprojekt = "a"\n\n'
        '[[port]]\nport = 8766\nprojekt = "b"\n\n[port.meta]\nx = 1\n\n'
        '[[port.sub]]\ny = 2\n\n[[port.sub]]\ny = 3\n\n'
        '[[port]]\nport = 8767\nprojekt = "c"\n'
    )
    p = schreibe(tmp_path, inhalt)
    assert trage_aus(p, "b") == Eintrag(8766, "b", "", None)
    assert p.read_bytes() == (A + C).encode()
    assert lade(p) == [Eintrag(8765, "a"), Eintrag(8767, "c")]
    assert len(spion) == 1
    assert rest(tmp_path) == ["ports.toml"]


def test_letzter_eintrag_mit_meta(tmp_path):
    from portwart.austragen import trage_aus
    p = schreibe(tmp_path, A + B + '[port.meta]\nx = 1\n')
    trage_aus(p, "b")
    assert p.read_bytes() == b'[[port]]\nport = 8765\nprojekt = "a"\n'
    assert rest(tmp_path) == ["ports.toml"]


def test_erster_eintrag_mit_meta(tmp_path):
    from portwart.austragen import trage_aus
    from portwart.liste import Eintrag, lade
    p = schreibe(tmp_path, '[[port]]\nport = 8765\nprojekt = "a"\n[port.meta]\nx = 1\n\n' + C)
    assert trage_aus(p, "a") == Eintrag(8765, "a", "", None)
    assert p.read_bytes() == ("\n" + C).encode()
    assert lade(p) == [Eintrag(8767, "c")]


@pytest.mark.parametrize("inhalt", [
    '[[port]]\nport = 8765\nprojekt = "a"\n[port.meta]\nx = 1\n',
    '[[port]]\nport = 8765\nprojekt = "a"\n\n[port.meta]\nx = 1\n',
])
def test_einziger_eintrag_mit_meta_wird_leer(tmp_path, spion, inhalt):
    from portwart.austragen import trage_aus
    from portwart.liste import Eintrag, lade
    p = schreibe(tmp_path, inhalt)
    assert trage_aus(p, "a") == Eintrag(8765, "a", "", None)
    assert p.read_bytes() == b""
    assert lade(p) == []
    assert len(spion) == 1
    assert rest(tmp_path) == ["ports.toml"]


def test_mehrere_sub_und_tiefe_tabelle_nachbarn_bleiben(tmp_path):
    from portwart.austragen import trage_aus
    from portwart.liste import Eintrag, lade
    a = A + '[port.meta]\nm = 1\n\n'
    b = (
        '[[port]]\nport = 8766\nprojekt = "b"\n\n'
        '[[port.sub]]\ny = 1\n\n[[port.sub]]\ny = 2\n\n[port.a.b]\nz = 3\n\n'
    )
    c = C + '\n[port.meta]\nm = 3\n'
    inhalt = a + b + c
    p = schreibe(tmp_path, inhalt)
    vorher = tomllib.loads(inhalt)
    assert trage_aus(p, "b") == Eintrag(8766, "b", "", None)
    assert p.read_bytes() == (a + c).encode()
    assert tomllib.loads(p.read_text()) == ohne_eintrag(vorher, 1)
    assert tomllib.loads(p.read_text())["port"][1]["meta"] == {"m": 3}
    assert lade(p) == [Eintrag(8765, "a"), Eintrag(8767, "c")]


def test_leerraum_kommentar_und_crlf(tmp_path):
    from portwart.austragen import trage_aus
    lf = (
        A + B + '[ port . meta ]  # c\nx = 1\n\n' + C
    )
    p = schreibe(tmp_path, lf.replace("\n", "\r\n"))
    trage_aus(p, "b")
    assert p.read_bytes() == (A + C).replace("\n", "\r\n").encode()
    assert rest(tmp_path) == ["ports.toml"]


def test_quotierte_teile_und_leerraum_in_doppelklammern(tmp_path):
    from portwart.austragen import trage_aus
    b = (
        '[[port]]\nport = 8766\nprojekt = "b"\n\n'
        '[port."a.b"]\nx = 1\n\n[port.\'x\']\ny = 2\n\n'
        '[[ port . sub ]]\nz = 3\n\n'
    )
    inhalt = A + b + C
    p = schreibe(tmp_path, inhalt)
    vorher = tomllib.loads(inhalt)
    trage_aus(p, "b")
    assert p.read_bytes() == (A + C).encode()
    assert tomllib.loads(p.read_text()) == ohne_eintrag(vorher, 1)


def test_mehrzeilige_werte_in_untertabelle(tmp_path, spion):
    from portwart.austragen import trage_aus
    from portwart.liste import Eintrag, lade
    b = (
        '[[port]]\nport = 8766\nprojekt = "b"\n\n[port.meta]\n'
        'tags = [\n  "x",\n  [1, 2],\n]\n'
        "note = '''\n[[port]]\n[x]\n'''\n"
    )
    p = schreibe(tmp_path, A + b + "\n" + C)
    assert trage_aus(p, "b") == Eintrag(8766, "b", "", None)
    assert p.read_bytes() == (A + C).encode()
    assert lade(p) == [Eintrag(8765, "a"), Eintrag(8767, "c")]
    assert len(spion) == 1


@pytest.mark.parametrize("name,erwartet", [
    ("b", None),
    ("a", "\n"),
])
def test_nachbar_mit_untertabellen_bleibt_unberuehrt(tmp_path, name, erwartet):
    from portwart.austragen import trage_aus
    a = A + '[port.meta]\nx = 1\n\n[[port.sub]]\ny = 2\n\n'
    b = B
    c = C + '\n[port.meta]\nx = 3\n'
    inhalt = a + b + c
    p = schreibe(tmp_path, inhalt)
    vorher = tomllib.loads(inhalt)
    trage_aus(p, name)
    if name == "b":
        assert p.read_bytes() == (a + c).encode()
        assert tomllib.loads(p.read_text()) == ohne_eintrag(vorher, 1)
    else:
        # Kopf, Wertzeilen, Untertabellen samt je einer Leerzeile davor weg;
        # die Leerzeile nach y = 2 bleibt stehen
        assert p.read_bytes() == (erwartet + b + c).encode()
        assert tomllib.loads(p.read_text()) == ohne_eintrag(vorher, 0)


def test_fremde_tabelle_direkt_dahinter_bleibt(tmp_path):
    from portwart.austragen import trage_aus
    inhalt = A + '[[port]]\nport = 8766\nprojekt = "b"\n[port.meta]\nx = 1\n[andere]\nk = 1\n'
    p = schreibe(tmp_path, inhalt)
    vorher = tomllib.loads(inhalt)
    trage_aus(p, "b")
    assert p.read_bytes() == (
        b'[[port]]\nport = 8765\nprojekt = "a"\n[andere]\nk = 1\n'
    )
    assert tomllib.loads(p.read_text()) == ohne_eintrag(vorher, 1)
    assert tomllib.loads(p.read_text())["andere"] == {"k": 1}


@pytest.mark.parametrize("inhalt,erwartet", [
    ('[[port]]\nport=1\nprojekt="a"\n# Meta\n[port.meta]\nx = 1\n# Ende\n',
     b"# Meta\n# Ende\n"),
    ('[[port]]\nport = 1\nprojekt = "a"\n\n\n[port.meta]\nx = 1\n\n# k\n',
     b"\n\n# k\n"),
])
def test_kommentare_und_leerzeilen_bleiben(tmp_path, inhalt, erwartet):
    from portwart.austragen import trage_aus
    p = schreibe(tmp_path, inhalt)
    trage_aus(p, "a")
    assert p.read_bytes() == erwartet


def test_letzte_zeile_ohne_zeilenende(tmp_path):
    from portwart.austragen import trage_aus
    p = schreibe(tmp_path, A + '[[port]]\nport = 8766\nprojekt = "b"\n[port.meta]\nx = 1')
    trage_aus(p, "b")
    assert p.read_bytes() == b'[[port]]\nport = 8765\nprojekt = "a"\n'


# --- Ablehnung ---

REJEKT = [
    # Untertabelle hinter [andere] gehört TOML-gemäß zu b (letzter Eintrag)
    (A + B + '[andere]\nk = 1\n\n[port.meta]\nx = 1\n', "b"),
    # nach dem Entfernen von a steht [port.meta] vor dem nächsten [[port]]
    (A + '[andere]\nk = 1\n\n[port.meta]\nx = 1\n\n[[port]]\nport = 8766\nprojekt = "b"\n',
     "a"),
    # quotierter Erstteil direkt hinter dem Eintrag, Vorgänger vorhanden
    (A + '[[port]]\nport = 8766\nprojekt = "b"\n["port".meta]\nx = 1\n', "b"),
    # quotierter Erstteil beim einzigen Eintrag
    ('[[port]]\nport = 1\nprojekt = "a"\n["port".meta]\nx = 1\n', "a"),
    # einziger Eintrag, Untertabelle hinter fremder Tabelle
    ('[[port]]\nport = 1\nprojekt = "a"\n\n[andere]\nk = 1\n\n[port.meta]\nx = 1\n', "a"),
    # quotierter Erstteil bei Array-Untertabelle
    (A + "[[port]]\nport = 8766\nprojekt = \"b\"\n[['port'.sub]]\ny = 1\n", "b"),
]


@pytest.mark.parametrize("inhalt,name", REJEKT)
def test_unklare_untertabellen_werden_abgelehnt(tmp_path, nie, inhalt, name):
    from portwart.austragen import AustragFehler, trage_aus
    p = schreibe(tmp_path, inhalt)
    with pytest.raises(AustragFehler) as ei:
        trage_aus(p, name)
    assert str(ei.value) == VERKLEINERN
    assert p.read_bytes() == inhalt.encode()
    assert rest(tmp_path) == ["ports.toml"]


@pytest.mark.parametrize("name,erwartet", [
    ("a", "\n" + '[[port]]\nport = 8766\nprojekt = "b"\n["port".meta]\nx = 1\n\n' + C),
    ("c", A + '[[port]]\nport = 8766\nprojekt = "b"\n["port".meta]\nx = 1\n'),
])
def test_unklare_untertabelle_eines_anderen_eintrags_stoert_nicht(tmp_path, name, erwartet):
    from portwart.austragen import trage_aus
    inhalt = (
        A + '[[port]]\nport = 8766\nprojekt = "b"\n["port".meta]\nx = 1\n\n' + C
    )
    p = schreibe(tmp_path, inhalt)
    vorher = tomllib.loads(inhalt)
    trage_aus(p, name)
    assert p.read_bytes() == erwartet.encode()
    i = {"a": 0, "c": 2}[name]
    assert tomllib.loads(p.read_text()) == ohne_eintrag(vorher, i)


def test_genau_ein_lade_auf_tempdatei_bei_untertabelle(tmp_path, monkeypatch, spion):
    from portwart.austragen import trage_aus
    from portwart.liste import lade as echt
    modul = sys.modules["portwart.austragen"]
    gesehen = []
    monkeypatch.setattr(modul, "lade", lambda pfad: (gesehen.append(str(pfad)), echt(pfad))[1])
    p = schreibe(tmp_path, A + B + '[port.meta]\nx = 1\n\n' + C)
    trage_aus(str(p), "b")
    assert len(gesehen) == 2 and gesehen[0] == str(p) and gesehen[1] != str(p)
    assert os.path.dirname(os.path.abspath(gesehen[1])) == str(tmp_path)
    assert len(spion) == 1
    assert p.read_bytes() == (A + C).encode()


# --- Unverändertes ---

def test_klassifizierung_unveraendert():
    from portwart.austragen import _klassifiziere, _zeilen
    zeilen = _zeilen(b"[[port]]\n[port.meta]\n[[port.sub]]\nx = 1\n\n# k\n")
    assert _klassifiziere(zeilen) == ["kopf", "tabelle", "tabelle", "wert", "leer", "kommentar"]


def test_rundlauf_mit_trage_ein_nach_untertabelle(tmp_path):
    from portwart.austragen import trage_aus
    from portwart.eintragen import trage_ein
    from portwart.liste import Eintrag
    alt = A + '[[port]]\nport = 8766\nprojekt = "b"\n[port.meta]\nx = 1\n'
    p = schreibe(tmp_path, alt)
    trage_ein(p, "neu", 9100, "z", "p")
    assert trage_aus(p, "neu") == Eintrag(9100, "neu", "z", "p")
    assert p.read_bytes() == alt.encode()


# --- CLI ---

def test_cli_erfolg_mit_untertabellen_standarddatei(tmp_path):
    inhalt = A + B + '[port.meta]\nx = 1\n\n[[port.sub]]\ny = 2\n\n' + C
    p = schreibe(tmp_path, inhalt)
    r = starte(tmp_path, "austragen", "b")
    assert (r.returncode, r.stdout, r.stderr) == (0, "ausgetragen b 8766\n", "")
    assert p.read_bytes() == (A + C).encode()
    assert rest(tmp_path) == ["ports.toml"]


def test_cli_einziger_eintrag_mit_meta(tmp_path):
    p = schreibe(tmp_path, '[[port]]\nport = 8765\nprojekt = "a"\n[port.meta]\nx = 1\n')
    r = starte(tmp_path, "austragen", "a", "--datei", str(p))
    assert (r.returncode, r.stdout, r.stderr) == (0, "ausgetragen a 8765\n", "")
    assert p.read_bytes() == b""


def test_cli_ablehnung_unklare_untertabelle(tmp_path):
    inhalt = A + B + '[andere]\nk = 1\n\n[port.meta]\nx = 1\n'
    p = schreibe(tmp_path, inhalt)
    r = starte(tmp_path, "austragen", "b", "--datei", str(p))
    assert r.returncode == 2
    assert r.stdout == ""
    assert r.stderr == f"Fehler: {VERKLEINERN}\n"
    assert p.read_bytes() == inhalt.encode()
    assert rest(tmp_path) == ["ports.toml"]
