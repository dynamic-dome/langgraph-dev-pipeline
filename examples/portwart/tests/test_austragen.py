import builtins
import dataclasses
import os
import tomllib

import pytest

from portwart import austragen as modul
from portwart import liste as liste_modul
from portwart.__main__ import main
from portwart.austragen import AustragFehler, trage_aus
from portwart.eintragen import EintragFehler, anzeige_text, baue_block, trage_ein
from portwart.liste import Eintrag, ListenFehler, lade

VERKLEINERN = "Liste kann nicht durch Entfernen eines [[port]]-Blocks verkleinert werden"

BASIS = (
    "# Kommentar\n"
    "[[port]]\nport = 8766\nprojekt = \"wiki-inselwelt\"\n\n"
    "# noch einer\n"
    "[[port]]\nport = 8767\nprojekt = \"signal-dashboard\"\nzweck = \"Signale\"\n\n"
    "[[port]]\nport = 8770\nprojekt = \"job-radar\"\npfad = \"../job\"\n"
)

DREI = (
    "[[port]]\nport = 8765\nprojekt = \"a\"\nzweck = \"za\"\npfad = \"pa\"\n\n"
    "[[port]]\nport = 8766\nprojekt = \"b\"\n\n"
    "[[port]]\nport = 8767\nprojekt = \"c\"\nzweck = \"zc\"\npfad = \"pc\"\n"
)


@pytest.fixture
def liste(tmp_path):
    p = tmp_path / "ports.toml"
    p.write_bytes(BASIS.encode())
    return p


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


def cli(capsys, *argv):
    code = main(list(argv))
    o = capsys.readouterr()
    return code, o.out, o.err


# --- Erfolg und Blockpositionen ---

def test_erfolg_bytes(liste, spion):
    e = trage_aus(liste, "signal-dashboard")
    assert e == Eintrag(8767, "signal-dashboard", "Signale", None)
    assert liste.read_bytes() == (
        "# Kommentar\n"
        "[[port]]\nport = 8766\nprojekt = \"wiki-inselwelt\"\n\n"
        "# noch einer\n"
        "\n"
        "[[port]]\nport = 8770\nprojekt = \"job-radar\"\npfad = \"../job\"\n"
    ).encode()
    assert len(spion) == 1
    assert rest(liste.parent) == ["ports.toml"]


def test_erster_block(liste):
    e = trage_aus(liste, "wiki-inselwelt")
    assert e == Eintrag(8766, "wiki-inselwelt", "", None)
    assert liste.read_bytes() == (
        "# Kommentar\n\n# noch einer\n"
        "[[port]]\nport = 8767\nprojekt = \"signal-dashboard\"\nzweck = \"Signale\"\n\n"
        "[[port]]\nport = 8770\nprojekt = \"job-radar\"\npfad = \"../job\"\n"
    ).encode()


def test_letzter_block(liste):
    e = trage_aus(liste, "job-radar")
    assert e == Eintrag(8770, "job-radar", "", "../job")
    assert liste.read_bytes() == (
        "# Kommentar\n"
        "[[port]]\nport = 8766\nprojekt = \"wiki-inselwelt\"\n\n"
        "# noch einer\n"
        "[[port]]\nport = 8767\nprojekt = \"signal-dashboard\"\nzweck = \"Signale\"\n"
    ).encode()


def test_kopf_erste_zeile(tmp_path):
    p = schreibe(tmp_path, DREI)
    assert trage_aus(p, "a") == Eintrag(8765, "a", "za", "pa")
    assert p.read_bytes() == (
        "\n"
        "[[port]]\nport = 8766\nprojekt = \"b\"\n\n"
        "[[port]]\nport = 8767\nprojekt = \"c\"\nzweck = \"zc\"\npfad = \"pc\"\n"
    ).encode()


def test_einzelblock_kommentare_bleiben(tmp_path):
    p = schreibe(tmp_path, "# oben\n[[port]]\n# zwischen\nport = 1\n\n"
                           "projekt = \"a\" # dahinter\n# unten\n")
    assert trage_aus(p, "a") == Eintrag(1, "a", "", None)
    assert p.read_bytes() == b"# oben\n# zwischen\n\n# unten\n"
    assert lade(p) == []
    assert rest(tmp_path) == ["ports.toml"]


def test_block_ohne_zeilenende(tmp_path):
    p = schreibe(tmp_path, "[[port]]\nport = 1\nprojekt = \"a\"\n\n"
                           "[[port]]\nport = 2\nprojekt = \"b\"")
    trage_aus(p, "b")
    assert p.read_bytes() == b"[[port]]\nport = 1\nprojekt = \"a\"\n"


def test_kopf_mit_leerraum_und_kommentar(tmp_path):
    p = schreibe(tmp_path, "[[port]]\nport = 1\nprojekt = \"a\"\n\n"
                           "  [[ port ]]  # mein Block\nport = 2\nprojekt = \"b\"\n")
    trage_aus(p, "b")
    assert p.read_bytes() == b"[[port]]\nport = 1\nprojekt = \"a\"\n"


def test_nur_eine_leerzeile_davor(tmp_path):
    p = schreibe(tmp_path, "[[port]]\nport = 1\nprojekt = \"a\"\n\n\n"
                           "[[port]]\nport = 2\nprojekt = \"b\"\n\n# ende\n")
    trage_aus(p, "b")
    assert p.read_bytes() == b"[[port]]\nport = 1\nprojekt = \"a\"\n\n\n# ende\n"


# --- Zeilenenden ---

def test_crlf(tmp_path):
    inhalt = (
        "[[port]]\r\nport = 1\r\nprojekt = \"a\"\r\n"
        "\r\n"
        "[[port]]\r\nport = 2\r\nprojekt = \"b\"\r\n"
        "  \t\r\n"
        "[[port]]\r\nport = 3\r\nprojekt = \"c\"\r\n# ende\r\n"
    )
    p = schreibe(tmp_path, inhalt)
    trage_aus(p, "b")
    assert p.read_bytes() == (
        "[[port]]\r\nport = 1\r\nprojekt = \"a\"\r\n"
        "  \t\r\n"
        "[[port]]\r\nport = 3\r\nprojekt = \"c\"\r\n# ende\r\n"
    ).encode()
    trage_aus(p, "c")
    assert p.read_bytes() == b"[[port]]\r\nport = 1\r\nprojekt = \"a\"\r\n# ende\r\n"


def test_einzelnes_cr_ist_inhalt():
    zeilen = modul._zeilen(b"a = 1\r\n\r\n#x\r\n\r")
    assert zeilen == [b"a = 1\r\n", b"\r\n", b"#x\r\n", b"\r"]
    assert modul._klassifiziere(zeilen) == ["wert", "leer", "kommentar", "wert"]
    assert modul._klassifiziere([b"[[port]]\r\n", b"[[port]]\r"]) == ["kopf", "tabelle"]
    assert modul._zeilen(b"") == []


# --- Rundlauf ---

def test_rundlauf_mit_zeilenende(liste):
    alt = liste.read_bytes()
    trage_ein(liste, "neu", 9100, "z", "p")
    assert trage_aus(liste, "neu") == Eintrag(9100, "neu", "z", "p")
    assert liste.read_bytes() == alt


def test_rundlauf_crlf(tmp_path):
    alt = b"[[port]]\r\nport = 1\r\nprojekt = \"a\"\r\n"
    p = schreibe(tmp_path, alt)
    trage_ein(p, "b", 2)
    trage_aus(p, "b")
    assert p.read_bytes() == alt


def test_rundlauf_ohne_zeilenende(tmp_path):
    p = schreibe(tmp_path, b"# x")
    trage_ein(p, "n", 1)
    trage_aus(p, "n")
    assert p.read_bytes() == b"# x\n"


def test_rundlauf_leer(tmp_path):
    p = schreibe(tmp_path, b"")
    trage_ein(p, "n", 1, "")
    assert p.read_bytes() == baue_block("n", 1, "").encode()
    assert trage_aus(p, "n") == Eintrag(1, "n", "", None)
    assert p.read_bytes() == b""
    assert rest(tmp_path) == ["ports.toml"]


def test_rundlauf_mehrfach(liste):
    alt = liste.read_bytes()
    trage_ein(liste, "x", 9100)
    trage_ein(liste, "y", 9101)
    trage_aus(liste, "y")
    trage_aus(liste, "x")
    assert liste.read_bytes() == alt
    with pytest.raises(EintragFehler):
        trage_ein(liste, "job-radar", 1)


# --- Namensprüfung ---

@pytest.mark.parametrize("name", ["x", "Job-Radar", " job-radar", "job-radar ", "", " "])
def test_name_unbekannt(liste, nie, name):
    alt = liste.read_bytes()
    with pytest.raises(AustragFehler) as ei:
        trage_aus(liste, name)
    assert str(ei.value) == f"Name '{name}' nicht gefunden"
    assert liste.read_bytes() == alt
    assert rest(liste.parent) == ["ports.toml"]


def test_name_roh_in_meldung(liste):
    with pytest.raises(AustragFehler) as ei:
        trage_aus(liste, "a\nb")
    assert str(ei.value) == "Name 'a\nb' nicht gefunden"


@pytest.mark.parametrize("ports,msg", [
    ((8770, 8771, 8770), "Ports 8770, 8771"),
    ((8771, 8770), "Ports 8771, 8770"),
    ((8770, 8770), "Ports 8770"),
])
def test_name_mehrfach(tmp_path, nie, ports, msg):
    inhalt = "".join(f'[[port]]\nport = {p}\nprojekt = "job-radar"\n' for p in ports)
    inhalt += '[[port]]\nport = 1\nprojekt = "x"\n'
    p = schreibe(tmp_path, inhalt)
    with pytest.raises(AustragFehler) as ei:
        trage_aus(p, "job-radar")
    assert str(ei.value) == f"Name 'job-radar' ist mehrfach eingetragen: {msg}"
    assert p.read_text() == inhalt
    assert rest(tmp_path) == ["ports.toml"]


def test_name_vor_dateiform(tmp_path, nie):
    inhalt = 'port = [{port = 8766, projekt = "wiki"}]\n'
    p = schreibe(tmp_path, inhalt)
    with pytest.raises(AustragFehler) as ei:
        trage_aus(p, "x")
    assert str(ei.value) == "Name 'x' nicht gefunden"
    with pytest.raises(AustragFehler) as ei:
        trage_aus(p, "wiki")
    assert str(ei.value) == VERKLEINERN
    assert p.read_text() == inhalt
    assert rest(tmp_path) == ["ports.toml"]


# --- Durchreichen aus dem anfänglichen Laden ---

def test_laden_wird_durchgereicht(tmp_path):
    with pytest.raises(ListenFehler, match="^Datei nicht gefunden: "):
        trage_aus(tmp_path / "fehlt.toml", "x")
    assert rest(tmp_path) == []
    p = schreibe(tmp_path, "[[")
    with pytest.raises(ListenFehler, match="^kein gültiges TOML in "):
        trage_aus(p, "x")
    p.write_bytes(b"\xff\xfe")
    with pytest.raises(UnicodeDecodeError):
        trage_aus(p, "x")
    p.write_bytes(b"[[port]]\nport = 1\n")
    with pytest.raises(ListenFehler, match="^Eintrag 1: Pflichtfeld 'projekt' fehlt$"):
        trage_aus(p, "x")
    assert rest(tmp_path) == ["ports.toml"]


def _oeffnen_verboten(monkeypatch, ziel):
    def f(datei, *a, **k):
        if os.path.abspath(datei) == os.path.abspath(ziel):
            raise PermissionError("verboten")
        return builtins.open(datei, *a, **k)
    monkeypatch.setattr(liste_modul, "open", f, raising=False)


def test_anfaengliches_oeffnen_scheitert(liste, monkeypatch, nie):
    alt = liste.read_bytes()
    _oeffnen_verboten(monkeypatch, liste)
    with pytest.raises(ListenFehler) as ei:
        trage_aus(liste, "job-radar")
    assert not isinstance(ei.value, AustragFehler)
    assert str(ei.value) == f"Datei nicht lesbar: {liste}: verboten"
    assert liste.read_bytes() == alt
    assert rest(liste.parent) == ["ports.toml"]


# --- Sonderzeichen ---

VOR = '[[port]]\nport = 8765\nprojekt = "vor"\nzweck = "v # [ \' \\""\n'
NACH = '\n[[port]]\nport = 8767\nprojekt = "nach"\nzweck = "n"\n'


@pytest.mark.parametrize("koerper,zweck", [
    ('port = 8766\nprojekt = "m"\nzweck = "a[b # c"\n', "a[b # c"),
    ('port = 8766 # it\'s\nprojekt = "m"\n', ""),
    ('port = 8766\nprojekt = "m"\nzweck = \'x"y # z\'\n', 'x"y # z'),
    ('port = 8766\nprojekt = "m"\nzweck = "sag \\"hi\\" # nicht Kommentar"\n',
     'sag "hi" # nicht Kommentar'),
    ('port = 8766\nprojekt = "m"\nzweck = "a]b"\n', "a]b"),
    ('port = 8766\nprojekt = "m" # [[port]] [ " \'\n', ""),
    ('port = 8766\nprojekt = "m"\nzweck = \'a[\' # \' [ "\n', "a["),
    ('port = 8766\nprojekt = "m"\nzweck = "\\\\"\n', "\\"),
    ('port = 8766\nprojekt = "m"\nzweck = ""\n', ""),
    ('port = 8766\nprojekt = "m"\nzweck = """a[b\'#"""\n', "a[b'#"),
    ('port = 8766\nprojekt = "m"\nzweck = \'\'\'a"[\'\'\'\n', 'a"['),
    ('"port" = 8766\n\'projekt\' = "m"\n', ""),
])
def test_sonderzeichen(tmp_path, spion, koerper, zweck):
    p = schreibe(tmp_path, VOR + "\n[[port]]\n" + koerper + NACH)
    assert trage_aus(p, "m") == Eintrag(8766, "m", zweck, None)
    assert p.read_bytes() == (VOR + NACH).encode()
    assert len(spion) == 1
    assert rest(tmp_path) == ["ports.toml"]


# --- Mehrzeilige Werte ---

ARR_VOR = '[[port]]\nport = 8765\nprojekt = "vor"\n'
ARR_NACH = '\n[[port]]\nport = 8767\nprojekt = "nach"\n'


@pytest.mark.parametrize("block,bleibt", [
    # Array-Fall aus der Aufgabe
    ('# davor\n[[port]]\nport = 8766\nprojekt = "arr"\ntags = [\n  "x",\n  "y",\n'
     '  # Kommentar im Array\n  "z",\n]\n',
     '# davor\n  # Kommentar im Array\n'),
    # Leerzeile und Kommentare mit Klammern im Array, verschachteltes Array
    ('\n[[port]]\nport = 8766\ntags = [\n  "x",\n\n  # [[port]] ]\n  # [\n'
     '  [1, "]"],\n  [[2],\n   3]]\nprojekt = "arr"\n',
     '\n  # [[port]] ]\n  # [\n'),
    # Array mit Kommentar hinter Elementen
    ('\n[[port]]\nport = 8766\nprojekt = "arr"\ntags = [ # [\n  "a#", # ]\n  \'[\',\n] # x\n',
     ''),
    # Literal-Fall
    ("\n[[port]]\nport = 8766\nprojekt = \"arr\"\nzweck = '''\na\n# kein Kommentar\n\nb'''\n",
     ''),
    # Basis-Fall mit Escape und Leerraumzeile
    ('\n[[port]]\nport = 8766\nprojekt = "arr"\nzweck = """\na\n# kein\n\n  \nb \\""" c"""\n'
     '# echter Kommentar\n',
     '# echter Kommentar\n'),
    # Zeichenkette mit Schluss-Anführungszeichen im Inhalt
    ('\n[[port]]\nport = 8766\nprojekt = "arr"\nzweck = \'\'\'\nx\n\'\'\'\'\'\n',
     ''),
    # Zeilenfortsetzung mit Backslash
    ('\n[[port]]\nport = 8766\nprojekt = "arr"\nzweck = """a \\\n  [[port]]\n"""\n',
     ''),
])
def test_mehrzeilige_werte_sind_wertinhalt(tmp_path, spion, block, bleibt):
    p = schreibe(tmp_path, ARR_VOR + block + ARR_NACH)
    alt = lade(p)
    assert trage_aus(p, "arr") == alt[1]
    assert p.read_bytes() == (ARR_VOR + bleibt + ARR_NACH).encode()
    assert lade(p) == [alt[0], alt[2]]
    assert len(spion) == 1
    assert rest(tmp_path) == ["ports.toml"]


def test_mehrzeilige_werte_klassifikation():
    zeilen = modul._zeilen(
        b"[[port]]\nzweck = '''\n\n# x\n[[port]]\nb'''\n\n# k\ntags = [\n\n# [\n]\n[a]\n"
    )
    assert modul._klassifiziere(zeilen) == [
        "kopf", "wert", "string", "string", "string", "string", "leer",
        "kommentar", "wert", "leer", "kommentar", "wert", "tabelle",
    ]


KL_VOR = '[[port]]\nport = 8765\nprojekt = "vor"\n'
KL_L = ('\n[[port]]\nport = 8766\nprojekt = "l"\nzweck = """\na\n[[port]]\nb"""\n'
        'pfad = "p/l"\n')
KL_NACH = '\n[[port]]\nport = 8767\nprojekt = "nach"\nzweck = "z"\n'


@pytest.mark.parametrize("name,eintrag,restbytes", [
    ("l", Eintrag(8766, "l", "a\n[[port]]\nb", "p/l"), KL_VOR + KL_NACH),
    ("nach", Eintrag(8767, "nach", "z", None), KL_VOR + KL_L),
    ("vor", Eintrag(8765, "vor", "", None), KL_L + KL_NACH),
])
def test_kopfaehnliche_zeile_in_zeichenkette_nie_falsch(tmp_path, spion, name, eintrag,
                                                       restbytes):
    p = schreibe(tmp_path, KL_VOR + KL_L + KL_NACH)
    assert trage_aus(p, name) == eintrag
    assert p.read_bytes() == restbytes.encode()
    assert len(spion) == 1
    assert rest(tmp_path) == ["ports.toml"]


# --- Ablehnung nicht unterstützter Formen ---

@pytest.mark.parametrize("inhalt,name", [
    ('[["port"]]\nport = 1\nprojekt = "a"\n', "a"),
    ('[[port]]\nport = 1\nprojekt = "a"\n[["port"]]\nport = 2\nprojekt = "b"\n', "a"),
    ('[[port]]\nport = 1\nprojekt = "a"\n[[\'port\']]\nport = 2\nprojekt = "b"\n', "b"),
    ('port = [{port = 8766, projekt = "wiki"}]\n', "wiki"),
])
def test_nicht_entfernbar(tmp_path, nie, inhalt, name):
    p = schreibe(tmp_path, inhalt)
    with pytest.raises(AustragFehler) as ei:
        trage_aus(p, name)
    assert str(ei.value) == VERKLEINERN
    assert p.read_text() == inhalt
    assert rest(tmp_path) == ["ports.toml"]


# --- Untertabellen-Erkennung ---

@pytest.mark.parametrize("text,soll", [
    (b"[port.meta]", True),
    (b"[[port.sub]]", True),
    (b"[port.a.b]", True),
    (b"[ port . meta ]", True),
    (b"[ port . meta ]  # x", True),
    (b"\t[port.meta]", True),
    (b'[port."a.b"]', True),
    (b"[port.'x']", True),
    (b"[[port.\"a\".'b'.c]]", True),
    (b"[port.meta]# x", True),
    (b"[[ port . sub ]] # y", True),
    (b"[andere]", False),
    (b"[port]", False),
    (b"[[port]]", False),
    (b"[port ]", False),
    (b'["port".meta]', False),
    (b"[['port'.sub]]", False),
    (b"[portx.meta]", False),
    (b"[andere.port]", False),
    (b"[port.]", False),
    (b"[port..x]", False),
    (b"[port.meta", False),
    (b"[port.meta]]", False),
    (b"[[port.meta]", False),
    (b"[port.meta] x", False),
    (b"[port.a b]", False),
])
def test_ist_untertabelle(text, soll):
    assert modul._ist_untertabelle(text) is soll


def test_untertabelle_bleibt_tabelle():
    zeilen = modul._zeilen(
        b"[[port]]\n[port.meta]\n[[port.sub]]\n[ port . a ] # x\r\n"
        b"z = '''\n[port.meta]\n[[port]]\n'''\nt = [\n[port.x],\n]\n"
    )
    assert modul._klassifiziere(zeilen) == [
        "kopf", "tabelle", "tabelle", "tabelle",
        "wert", "string", "string", "string", "wert", "wert", "wert",
    ]


# --- Untertabellen ---

SPEC_A = '[[port]]\nport = 8765\nprojekt = "a"\n\n'
SPEC_B = ('[[port]]\nport = 8766\nprojekt = "b"\n\n[port.meta]\nx = 1\n\n'
          '[[port.sub]]\ny = 2\n\n[[port.sub]]\ny = 3\n\n')
SPEC_C = '[[port]]\nport = 8767\nprojekt = "c"\n'


def _daten(p):
    return tomllib.loads(p.read_bytes().decode())


def test_untertabellen_beispiel(tmp_path, spion):
    p = schreibe(tmp_path, SPEC_A + SPEC_B + SPEC_C)
    assert trage_aus(p, "b") == Eintrag(8766, "b", "", None)
    assert p.read_bytes() == (
        '[[port]]\nport = 8765\nprojekt = "a"\n\n[[port]]\nport = 8767\nprojekt = "c"\n'
    ).encode()
    assert lade(p) == [Eintrag(8765, "a"), Eintrag(8767, "c")]
    assert len(spion) == 1
    assert rest(tmp_path) == ["ports.toml"]


def _e(n, p, meta):
    s = f'[[port]]\nport = {p}\nprojekt = "{n}"\n'
    return s + (f'\n[port.meta]\nm = "{n}"\n' if meta else "")


@pytest.mark.parametrize("name,soll", [
    ("a", "\n" + _e("b", 2, True) + "\n" + _e("c", 3, True)),
    ("b", _e("a", 1, True) + "\n" + _e("c", 3, True)),
    ("c", _e("a", 1, True) + "\n" + _e("b", 2, True)),
])
def test_untertabelle_positionen(tmp_path, spion, name, soll):
    inhalt = _e("a", 1, True) + "\n" + _e("b", 2, True) + "\n" + _e("c", 3, True)
    p = schreibe(tmp_path, inhalt)
    alt = lade(p)
    i = [e.projekt for e in alt].index(name)
    assert trage_aus(p, name) == alt[i]
    assert p.read_bytes() == soll.encode()
    assert lade(p) == alt[:i] + alt[i + 1:]
    daten = _daten(p)["port"]
    assert [d["meta"]["m"] for d in daten] == [e.projekt for e in lade(p)]
    assert len(spion) == 1
    assert rest(tmp_path) == ["ports.toml"]


def test_untertabelle_letzter_eintrag(tmp_path, spion):
    p = schreibe(tmp_path, _e("a", 1, False) + "\n" + _e("b", 2, True))
    trage_aus(p, "b")
    assert p.read_bytes() == b'[[port]]\nport = 1\nprojekt = "a"\n'
    assert len(spion) == 1


def test_untertabelle_einziger_eintrag(tmp_path, spion):
    p = schreibe(tmp_path, '[[port]]\nport = 8765\nprojekt = "a"\n[port.meta]\nx = 1\n')
    assert trage_aus(p, "a") == Eintrag(8765, "a")
    assert p.read_bytes() == b""
    assert lade(p) == []
    assert len(spion) == 1
    assert rest(tmp_path) == ["ports.toml"]


UT_A = '[[port]]\nport = 1\nprojekt = "a"\n'
UT_C = '[[port]]\nport = 3\nprojekt = "c"\n'


@pytest.mark.parametrize("unter", [
    '[[port.sub]]\ny = 1\n[[port.sub]]\ny = 2\n\n[[port.sub]]\ny = 3\n',
    '[port.a.b]\nz = 1\n',
    '[port.a]\n[port.a.b]\nz = 1\n',
    '[ port . meta ]  # x\nz = 1\n',
    '[port."a.b"]\nz = 1\n',
    "[port.'x']\nz = 1\n",
    '[port.meta]\ntags = [\n  [1],\n  [2, 3],\n# [x]\n]\n',
    "[port.meta]\ntext = '''\n[[port]]\n[x]\n'''\n",
    '[port.meta]\ntext = """\n[[port]]\n[x]\n"""\n',
])
def test_untertabelle_formen(tmp_path, spion, unter):
    b = '[[port]]\nport = 2\nprojekt = "b"\n' + unter
    p = schreibe(tmp_path, UT_A + "\n" + b + "\n" + UT_C)
    assert trage_aus(p, "b") == Eintrag(2, "b")
    soll = UT_A + "\n" + UT_C
    if "# [x]" in unter:
        soll = UT_A + "# [x]\n\n" + UT_C
    assert p.read_bytes() == soll.encode()
    assert lade(p) == [Eintrag(1, "a"), Eintrag(3, "c")]
    assert len(spion) == 1
    assert rest(tmp_path) == ["ports.toml"]


NB_A = '[[port]]\nport = 1\nprojekt = "a"\n\n[port.meta]\nx = 1\n\n[[port.sub]]\ny = 1\n'
NB_B = '[[port]]\nport = 2\nprojekt = "b"\n'
NB_C = '[[port]]\nport = 3\nprojekt = "c"\n[port.meta]\nx = 3\n'


def test_nachbar_behaelt_untertabellen(tmp_path, spion):
    p = schreibe(tmp_path, NB_A + NB_B + NB_C)
    vorher = _daten(p)["port"]
    assert trage_aus(p, "b") == Eintrag(2, "b")
    assert p.read_bytes() == (NB_A + NB_C).encode()
    assert _daten(p)["port"] == [vorher[0], vorher[2]]
    assert len(spion) == 1


def test_fremde_tabelle_bleibt(tmp_path, spion):
    andere = '[andere]\nk = 1\n[andere.tief]\nm = 2\n'
    p = schreibe(tmp_path, UT_A + '[[port]]\nport = 2\nprojekt = "b"\n[port.meta]\nx = 1\n'
                 + andere)
    assert trage_aus(p, "b") == Eintrag(2, "b")
    assert p.read_bytes() == (UT_A + andere).encode()
    assert _daten(p) == {"port": [{"port": 1, "projekt": "a"}],
                         "andere": {"k": 1, "tief": {"m": 2}}}
    assert len(spion) == 1


def test_fremde_tabelle_direkt_hinter_eintrag(tmp_path, spion):
    p = schreibe(tmp_path, UT_A + '[andere]\nk = 1\n' + UT_C)
    trage_aus(p, "a")
    assert p.read_bytes() == ('[andere]\nk = 1\n' + UT_C).encode()


def test_untertabelle_kommentare_bleiben(tmp_path, spion):
    p = schreibe(tmp_path, '[[port]]\nport=1\nprojekt="a"\n# Meta\n[port.meta]\nx = 1\n# Ende\n')
    trage_aus(p, "a")
    assert p.read_bytes() == b"# Meta\n# Ende\n"


def test_untertabelle_leerzeilen(tmp_path, spion):
    p = schreibe(tmp_path, '[[port]]\nport=1\nprojekt="a"\n\n\n[port.meta]\n\nx = 1\n\n')
    trage_aus(p, "a")
    assert p.read_bytes() == b"\n\n\n"


def test_untertabelle_crlf(tmp_path, spion):
    b = '[[port]]\nport = 2\nprojekt = "b"\n[ port . meta ]  # c\nx = 1\n'
    inhalt = (UT_A + "\n" + b + "\n" + UT_C).replace("\n", "\r\n")
    p = schreibe(tmp_path, inhalt)
    trage_aus(p, "b")
    assert p.read_bytes() == (UT_A + "\n" + UT_C).replace("\n", "\r\n").encode()


def test_untertabelle_ohne_zeilenende(tmp_path, spion):
    p = schreibe(tmp_path, UT_A + '\n[[port]]\nport = 2\nprojekt = "b"\n[port.meta]\nx = 1')
    trage_aus(p, "b")
    assert p.read_bytes() == UT_A.encode()


UNKLAR = (UT_A + '[[port]]\nport = 2\nprojekt = "b"\n["port".meta]\nx = 1\n' + UT_C)


@pytest.mark.parametrize("name,soll", [
    ("a", '[[port]]\nport = 2\nprojekt = "b"\n["port".meta]\nx = 1\n' + UT_C),
    ("c", UT_A + '[[port]]\nport = 2\nprojekt = "b"\n["port".meta]\nx = 1\n'),
])
def test_unklare_untertabelle_bei_anderem_eintrag(tmp_path, spion, name, soll):
    p = schreibe(tmp_path, UNKLAR)
    trage_aus(p, name)
    assert p.read_bytes() == soll.encode()
    assert len(spion) == 1


def test_rundlauf_mit_untertabellen(tmp_path):
    alt = (NB_A + NB_B + NB_C).encode()
    p = schreibe(tmp_path, alt)
    trage_ein(p, "neu", 9100, "z", "p")
    assert trage_aus(p, "neu") == Eintrag(9100, "neu", "z", "p")
    assert p.read_bytes() == alt


# --- Datenprüfung ---

@pytest.mark.parametrize("inhalt,name", [
    (UT_A + '[[port]]\nport = 2\nprojekt = "b"\n[andere]\nz = 1\n[port.meta]\nx = 1\n', "b"),
    (UT_A + '[andere]\nz = 1\n[port.meta]\nx = 1\n[[port]]\nport = 2\nprojekt = "b"\n', "a"),
    (UNKLAR, "b"),
    (UT_A + '["port".meta]\nx = 1\n', "a"),
    (UT_A + "[['port'.sub]]\nx = 1\n", "a"),
    (UT_A + '[[port]]\nport = 2\nprojekt = "b"\n[[\'port\'.sub]]\nx = 1\n', "b"),
    (UT_A + '[andere]\nz = 1\n[port.meta]\nx = 1\n', "a"),
])
def test_untertabelle_abgelehnt(tmp_path, nie, inhalt, name):
    p = schreibe(tmp_path, inhalt)
    with pytest.raises(AustragFehler) as ei:
        trage_aus(p, name)
    assert str(ei.value) == VERKLEINERN
    assert p.read_text() == inhalt
    assert rest(tmp_path) == ["ports.toml"]


MANIP = UT_A + NB_B + UT_C + '[port.meta]\nx = 1\n'


@pytest.mark.parametrize("aendern", [
    lambda b: b.replace(b"x = 1", b"x = 2"),
    lambda b: b + b"[neu]\nq = 1\n",
])
def test_tempdatei_manipuliert(tmp_path, monkeypatch, nie, aendern):
    p = schreibe(tmp_path, MANIP)
    datei = str(p)
    echt = lade
    gesehen = []

    def wrapper(pfad):
        gesehen.append(pfad)
        r = echt(pfad)
        if pfad != datei:
            with open(pfad, "rb") as f:
                roh = f.read()
            with open(pfad, "wb") as f:
                f.write(aendern(roh))
        return r

    monkeypatch.setattr(modul, "lade", wrapper)
    with pytest.raises(AustragFehler) as ei:
        trage_aus(datei, "b")
    assert str(ei.value) == VERKLEINERN
    assert p.read_text() == MANIP
    assert rest(tmp_path) == ["ports.toml"]
    assert len([g for g in gesehen if g != datei]) == 1


def test_tempdatei_wird_geparst(tmp_path, monkeypatch, spion):
    p = schreibe(tmp_path, MANIP)
    echt = tomllib.loads
    texte = []
    monkeypatch.setattr(modul.tomllib, "loads", lambda s, **k: (texte.append(s), echt(s, **k))[1])
    trage_aus(p, "b")
    monkeypatch.undo()
    assert MANIP in texte
    assert p.read_text() in texte
    assert len(spion) == 1


@pytest.mark.parametrize("ersatz", ["fehler", "abweichend"])
def test_parsen_der_tempdatei(tmp_path, monkeypatch, nie, ersatz):
    p = schreibe(tmp_path, MANIP)
    echt = tomllib.loads

    def f(s, **k):
        if s == MANIP:
            return echt(s, **k)
        if ersatz == "fehler":
            raise tomllib.TOMLDecodeError("kaputt")
        d = echt(s, **k)
        d["extra"] = 1
        return d

    monkeypatch.setattr(modul.tomllib, "loads", f)
    with pytest.raises(AustragFehler) as ei:
        trage_aus(p, "b")
    monkeypatch.undo()
    assert str(ei.value) == VERKLEINERN
    assert p.read_text() == MANIP
    assert rest(tmp_path) == ["ports.toml"]


def test_daten_strenger_vergleich():
    assert modul._gleich({"a": [1, float("nan")]}, {"a": [1, float("nan")]})
    assert not modul._gleich({"a": 1}, {"a": True})
    assert not modul._gleich({"a": 0.0}, {"a": -0.0})
    assert not modul._gleich([1], [1, 2])
    assert not modul._gleich({"a": 1}, {"b": 1})


def _tief(n, blatt):
    d = blatt
    for _ in range(n):
        d = {"x": d}
    return d


def test_daten_vergleich_beliebig_tief():
    n = 5000
    assert modul._gleich(_tief(n, {"z": 1}), _tief(n, {"z": 1}))
    assert not modul._gleich(_tief(n, {"z": 1}), _tief(n, {"z": 2}))
    assert not modul._gleich(_tief(n, {"z": 1}), _tief(n, {"z": 1.0}))


TIEF = "[port." + ".".join(["x"] * 600) + "]\nz = 1\n"


@pytest.mark.parametrize("inhalt,name,soll", [
    # Bleibender Eintrag mit tiefer Untertabelle (Befund)
    (UT_A + TIEF + "\n" + NB_B, "b", UT_A + TIEF),
    (NB_B + "\n" + UT_A + TIEF, "b", "\n" + UT_A + TIEF),
    # Zu entfernender Eintrag mit tiefer Untertabelle
    (UT_A + TIEF + "\n" + NB_B, "a", "\n" + NB_B),
], ids=["bleibt-vorn", "bleibt-hinten", "entfernt"])
def test_tiefe_untertabelle(tmp_path, spion, inhalt, name, soll):
    p = schreibe(tmp_path, inhalt)
    alt = lade(p)
    vorher = _daten(p)["port"]
    i = [e.projekt for e in alt].index(name)
    assert trage_aus(p, name) == alt[i]
    assert p.read_bytes() == soll.encode()
    assert lade(p) == alt[:i] + alt[i + 1:]
    assert modul._gleich(_daten(p)["port"], vorher[:i] + vorher[i + 1:])
    assert len(spion) == 1
    assert rest(tmp_path) == ["ports.toml"]


def test_tiefe_untertabelle_abweichung_abgelehnt(tmp_path, monkeypatch, nie):
    inhalt = UT_A + TIEF + "\n" + NB_B
    p = schreibe(tmp_path, inhalt)
    echt = tomllib.loads

    def f(s, **k):
        d = echt(s, **k)
        if s != inhalt:
            blatt = d["port"][0]
            while "x" in blatt:
                blatt = blatt["x"]
            blatt["z"] = 2
        return d

    monkeypatch.setattr(modul.tomllib, "loads", f)
    with pytest.raises(AustragFehler) as ei:
        trage_aus(p, "b")
    monkeypatch.undo()
    assert str(ei.value) == VERKLEINERN
    assert p.read_text() == inhalt
    assert rest(tmp_path) == ["ports.toml"]


# --- Reload-Sicherung ---

def _fall(nr, r):
    if nr == 1:
        return [dataclasses.replace(r[0], zweck="anders"), r[1]]
    if nr == 2:
        return [r[0], dataclasses.replace(r[1], port=9999)]
    if nr == 3:
        return [dataclasses.replace(r[0], projekt="anders"), r[1]]
    if nr == 4:
        return [r[0], dataclasses.replace(r[1], pfad="abweichend/pfad")]
    if nr == 5:
        raise ListenFehler("kaputt")
    if nr == 6:
        return r[:-1]
    if nr == 7:
        return r + [Eintrag(9000, "extra", "", None)]
    if nr == 8:
        return [r[1], r[0]]
    if nr == 9:
        raise OSError("weg")
    raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "kaputt")


@pytest.mark.parametrize("nr", range(1, 11))
def test_reload_sicherung(tmp_path, monkeypatch, nie, nr):
    p = schreibe(tmp_path, DREI)
    datei = str(p)
    echt = lade
    alt = echt(datei)
    erwartet = [alt[0], alt[2]]
    assert len(set(erwartet)) == 2
    gesehen = []

    def wrapper(pfad):
        gesehen.append(pfad)
        if pfad == datei:
            return echt(pfad)
        r = echt(pfad)
        assert r == erwartet
        return _fall(nr, r)

    monkeypatch.setattr(modul, "lade", wrapper)
    with pytest.raises(AustragFehler) as ei:
        trage_aus(datei, "b")
    assert str(ei.value) == VERKLEINERN
    assert p.read_text() == DREI
    assert rest(tmp_path) == ["ports.toml"]
    andere = [g for g in gesehen if g != datei]
    assert gesehen[0] == datei and len(andere) == 1
    assert os.path.dirname(os.path.abspath(andere[0])) == str(tmp_path)


def test_reload_wird_genutzt(tmp_path, monkeypatch, spion):
    p = schreibe(tmp_path, DREI)
    gesehen = []
    echt = lade
    monkeypatch.setattr(modul, "lade", lambda pfad: (gesehen.append(pfad), echt(pfad))[1])
    trage_aus(str(p), "b")
    assert len(gesehen) == 2 and gesehen[0] == str(p) and gesehen[1] != str(p)
    assert len(spion) == 1


# --- Schreibfehler ---

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
    elif wo == "fdopen":
        def f(*a, **k):
            raise OSError("fd")
        monkeypatch.setattr(os, "fdopen", f)
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


@pytest.mark.parametrize("wo,grund", [
    ("mkstemp", "mk"), ("write", "wr"), ("close", "cl"), ("replace", "rp"), ("fdopen", "fd"),
])
def test_schreibfehler(liste, monkeypatch, wo, grund):
    alt = liste.read_bytes()
    _kaputt(monkeypatch, wo)
    with pytest.raises(AustragFehler) as ei:
        trage_aus(liste, "job-radar")
    monkeypatch.undo()
    assert str(ei.value) == f"Datei nicht schreibbar: {liste}: {grund}"
    assert liste.read_bytes() == alt
    assert rest(liste.parent) == ["ports.toml"]


def test_schreibfehler_beim_lesen(liste, monkeypatch):
    alt = liste.read_bytes()
    _kaputt(monkeypatch, "read")
    with pytest.raises(AustragFehler) as ei:
        trage_aus(liste, "job-radar")
    monkeypatch.undo()
    assert str(ei.value) == f"Datei nicht schreibbar: {liste}: rd"
    assert liste.read_bytes() == alt
    assert rest(liste.parent) == ["ports.toml"]


def test_fdopen_fehler_schliesst_fd(liste, monkeypatch):
    geschlossen = []
    echt = os.close
    def f(*a, **k):
        raise OSError("fd")
    monkeypatch.setattr(os, "fdopen", f)
    monkeypatch.setattr(os, "close", lambda fd: (geschlossen.append(fd), echt(fd)))
    with pytest.raises(AustragFehler, match="nicht schreibbar"):
        trage_aus(liste, "job-radar")
    monkeypatch.undo()
    assert len(geschlossen) == 1
    assert rest(liste.parent) == ["ports.toml"]


def test_tempdatei_im_zielordner(liste, spion):
    trage_aus(liste, "job-radar")
    assert len(spion) == 1
    src, dst = spion[0]
    assert os.path.dirname(os.path.abspath(src)) == str(liste.parent)
    assert dst == liste


def test_loeschfehler_wird_verschluckt(liste, monkeypatch):
    def f(*a, **k):
        raise OSError("rp")
    monkeypatch.setattr(os, "replace", f)
    monkeypatch.setattr(os, "remove", lambda p: (_ for _ in ()).throw(OSError("rm")))
    with pytest.raises(AustragFehler, match="rp$"):
        trage_aus(liste, "job-radar")
    monkeypatch.undo()
    for x in liste.parent.iterdir():
        if x.name != "ports.toml":
            x.unlink()


# --- CLI ---

def test_cli_erfolg(liste, capsys):
    assert cli(capsys, "austragen", "signal-dashboard", "--datei", str(liste)) == (
        0, "ausgetragen signal-dashboard 8767\n", "")
    assert lade(liste) == [Eintrag(8766, "wiki-inselwelt"), Eintrag(8770, "job-radar", "", "../job")]
    assert rest(liste.parent) == ["ports.toml"]


def test_cli_steuerzeichen(liste, capsys):
    trage_ein(liste, "a\nb\x01", 9100)
    alt = liste.read_bytes()
    code, out, err = cli(capsys, "austragen", "a\nb", "--datei", str(liste))
    assert (code, out, err) == (2, "", "Fehler: Name 'a\\nb' nicht gefunden\n")
    assert liste.read_bytes() == alt
    assert cli(capsys, "austragen", "a\nb\x01", "--datei", str(liste)) == (
        0, "ausgetragen a\\nb\\u0001 9100\n", "")
    assert liste.read_bytes() == BASIS.encode()
    assert anzeige_text("a\nb\x01") == "a\\nb\\u0001"


def test_cli_standarddatei(tmp_path, capsys, monkeypatch):
    schreibe(tmp_path, BASIS)
    monkeypatch.chdir(tmp_path)
    assert cli(capsys, "austragen", "job-radar") == (0, "ausgetragen job-radar 8770\n", "")


def _cli_fehler(capsys, p, name, msg, start=False):
    alt = p.read_bytes() if p.exists() else None
    code, out, err = cli(capsys, "austragen", name, "--datei", str(p))
    assert code == 2 and out == ""
    if start:
        assert err.startswith(f"Fehler: {msg}")
    else:
        assert err == f"Fehler: {msg}\n"
    assert err.count("\n") == 1 and err.endswith("\n")
    if alt is not None:
        assert p.read_bytes() == alt
        assert rest(p.parent) == [p.name]


def test_cli_fehler(tmp_path, capsys):
    p = tmp_path / "ports.toml"
    _cli_fehler(capsys, p, "x", f"Datei nicht gefunden: {p}")
    assert not p.exists()
    p.write_text(BASIS)
    _cli_fehler(capsys, p, "x", "Name 'x' nicht gefunden")
    p.write_text('port = [{port = 8766, projekt = "wiki"}]\n')
    _cli_fehler(capsys, p, "x", "Name 'x' nicht gefunden")
    _cli_fehler(capsys, p, "wiki", VERKLEINERN)
    p.write_text('[[port]]\nport=8770\nprojekt="job-radar"\n[[port]]\nport=8771\nprojekt="job-radar"\n')
    _cli_fehler(capsys, p, "job-radar",
                "Name 'job-radar' ist mehrfach eingetragen: Ports 8770, 8771")
    p.write_text("[[")
    _cli_fehler(capsys, p, "x", f"kein gültiges TOML in {p}: ", start=True)
    p.write_text("[[port]]\nport = 1\n")
    _cli_fehler(capsys, p, "x", "Eintrag 1: Pflichtfeld 'projekt' fehlt")
    p.write_bytes(b"\xff\xfe")
    _cli_fehler(capsys, p, "x", f"Liste ist kein gültiges TOML: {p}: ", start=True)


def test_cli_untertabelle(tmp_path, capsys):
    p = schreibe(tmp_path, '[[port]]\nport = 8765\nprojekt = "a"\n[port.meta]\nx = 1\n')
    assert cli(capsys, "austragen", "a", "--datei", str(p)) == (0, "ausgetragen a 8765\n", "")
    assert p.read_bytes() == b""
    assert rest(tmp_path) == ["ports.toml"]


def test_cli_untertabelle_abgelehnt(tmp_path, capsys):
    p = schreibe(tmp_path, '[[port]]\nport = 1\nprojekt = "a"\n[[port]]\nport = 2\nprojekt = "b"\n'
                           '[andere]\nz = 1\n[port.meta]\nx = 1\n')
    _cli_fehler(capsys, p, "b", VERKLEINERN)


def test_cli_reload_abweichung(tmp_path, capsys, monkeypatch):
    p = schreibe(tmp_path, DREI)
    echt = lade
    monkeypatch.setattr(modul, "lade",
                        lambda pfad: echt(pfad) if pfad == str(p) else echt(pfad)[:1])
    _cli_fehler(capsys, p, "b", VERKLEINERN)


def test_cli_oeffnen_scheitert(liste, capsys, monkeypatch):
    _oeffnen_verboten(monkeypatch, liste)
    _cli_fehler(capsys, liste, "job-radar", f"Datei nicht lesbar: {liste}: verboten")


def test_cli_schreibfehler(liste, capsys, monkeypatch):
    alt = liste.read_bytes()
    _kaputt(monkeypatch, "replace")
    code, out, err = cli(capsys, "austragen", "job-radar", "--datei", str(liste))
    monkeypatch.undo()
    assert (code, out, err) == (2, "", f"Fehler: Datei nicht schreibbar: {liste}: rp\n")
    assert liste.read_bytes() == alt and rest(liste.parent) == ["ports.toml"]


def test_cli_argparse_fehler_exit_2(capsys):
    for argv in (["austragen"], ["austragen", "x", "--unbekannt"], ["austragen", "a", "b"]):
        with pytest.raises(SystemExit) as ei:
            main(argv)
        assert ei.value.code == 2


def test_andere_befehle_unveraendert(liste, capsys):
    assert cli(capsys, "pruefen", "--datei", str(liste)) == (0, "keine doppelten Ports\n", "")
    assert cli(capsys, "eintragen", "n", "9100", "--datei", str(liste)) == (
        0, "eingetragen n 9100\n", "")
    assert cli(capsys, "austragen", "n", "--datei", str(liste)) == (0, "ausgetragen n 9100\n", "")
    assert liste.read_bytes() == BASIS.encode()
