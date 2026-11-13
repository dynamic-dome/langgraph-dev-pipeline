import pytest

from portwart.__main__ import main
from portwart.drift import DriftFehler, durchsuche_liste, normalisiere_ausschluss
from portwart.liste import Eintrag, ListenFehler, lade, lade_ausschluss

MELDUNG = "'ausschluss' muss eine Liste von nicht leeren Texten sein"


def schreibe(pfad, text):
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(text, encoding="utf-8")


def dateien(d):
    return sorted(f.datei for liste in d.funde.values() for f in liste)


# --- lade_ausschluss ---

def test_lade_ausschluss_fehlt(tmp_path):
    schreibe(tmp_path / "p.toml", "")
    assert lade_ausschluss(tmp_path / "p.toml") == []


def test_lade_ausschluss_roh(tmp_path):
    schreibe(tmp_path / "p.toml", 'ausschluss = ["./a/", "a", "a"]\n')
    assert lade_ausschluss(tmp_path / "p.toml") == ["./a/", "a", "a"]


@pytest.mark.parametrize("wert", ['"x"', "[1]", "[{a=1}]", '[""]', '["  "]'])
def test_lade_ausschluss_ungueltig(tmp_path, wert):
    schreibe(tmp_path / "p.toml", f"ausschluss = {wert}\n")
    with pytest.raises(ListenFehler) as e:
        lade_ausschluss(tmp_path / "p.toml")
    assert str(e.value) == MELDUNG
    assert lade(tmp_path / "p.toml") == []


def test_lade_ausschluss_dateifehler(tmp_path):
    with pytest.raises(ListenFehler, match="Datei nicht gefunden"):
        lade_ausschluss(tmp_path / "nix.toml")
    schreibe(tmp_path / "k.toml", "= =")
    with pytest.raises(ListenFehler, match="kein gültiges TOML in"):
        lade_ausschluss(tmp_path / "k.toml")
    with pytest.raises(ListenFehler, match="Datei nicht lesbar"):
        lade_ausschluss(tmp_path)


# --- normalisiere_ausschluss ---

def test_normalisiere():
    assert normalisiere_ausschluss("a\\b") == "a/b"
    assert normalisiere_ausschluss("./analysis") == "analysis"
    assert normalisiere_ausschluss("berichte///") == "berichte"
    assert normalisiere_ausschluss(".//x") == "/x"
    assert normalisiere_ausschluss("Ab/C") == "Ab/C"
    assert normalisiere_ausschluss("*.json") == "*.json"
    assert normalisiere_ausschluss(" a ") == " a "
    n = normalisiere_ausschluss("./a\\b/")
    assert normalisiere_ausschluss(n) == n


def test_normalisiere_fuehrendes_punkt_slash_nur_einmal():
    # Vertrag "einmal entfernen" hat Vorrang; mehrere "./" bleiben teilweise stehen.
    assert normalisiere_ausschluss("././berichte") == "./berichte"


@pytest.mark.parametrize("wert", ["", "  ", "./", "/", "./ ", " /", None, 5])
def test_normalisiere_fehler(wert):
    with pytest.raises(DriftFehler) as e:
        normalisiere_ausschluss(wert)
    assert str(e.value) == MELDUNG


# --- durchsuche_liste ---

def baue(tmp_path):
    w = tmp_path / "w"
    for rel in ["proj/berichte/a.py", "proj/a/b/berichte/b.py", "proj/a/x.py",
                "proj/analysis/data/x.json", "proj/other/analysis/data/x.json",
                "berichte/z.py", "node_modules/n.py", "proj/arbeit/q.py"]:
        schreibe(w / rel, "port = 1234\n")
    return w


def test_name_jede_tiefe_und_wurzel(tmp_path):
    w = baue(tmp_path)
    d = durchsuche_liste([], tmp_path, w, ["berichte"])
    assert dateien(d) == [
        "proj/a/x.py", "proj/analysis/data/x.json",
        "proj/other/analysis/data/x.json",
    ]
    assert "berichte" not in d.funde
    d = durchsuche_liste([], tmp_path, w)
    assert "berichte" in d.funde


def test_pfad_wurzel_modus(tmp_path):
    w = baue(tmp_path)
    for schreibweise in ["analysis/data", "analysis\\data", "./analysis/data/"]:
        d = durchsuche_liste([], tmp_path, w, [schreibweise])
        fs = dateien(d)
        assert "proj/analysis/data/x.json" not in fs
        assert "proj/other/analysis/data/x.json" in fs


def test_pfad_modus(tmp_path):
    w = baue(tmp_path)
    e = [Eintrag(1234, "p", pfad=str(w / "proj"))]
    d = durchsuche_liste(e, tmp_path, None, ["analysis/data"])
    fs = dateien(d)
    assert "p/analysis/data/x.json" not in fs
    assert "p/other/analysis/data/x.json" in fs
    d = durchsuche_liste(e, tmp_path, None, ["proj"])
    assert dateien(d)  # Projektordner selbst bleibt


def test_pfad_trifft_keine_datei(tmp_path):
    w = tmp_path / "w"
    schreibe(w / "proj/a/x.py", "port = 1234\n")
    d = durchsuche_liste([], tmp_path, w, ["a/x.py"])
    assert dateien(d) == ["proj/a/x.py"]


def test_gross_klein_und_wildcard(tmp_path):
    w = baue(tmp_path)
    ohne = dateien(durchsuche_liste([], tmp_path, w))
    assert dateien(durchsuche_liste([], tmp_path, w, ["Berichte", "*.json"])) == ohne
    assert dateien(durchsuche_liste([], tmp_path, w, ["nirgends"])) == ohne
    assert dateien(durchsuche_liste([], tmp_path, w, ())) == ohne


def test_feste_ausschluesse_bleiben(tmp_path):
    w = baue(tmp_path)
    fs = dateien(durchsuche_liste([], tmp_path, w, ["a"]))
    assert not any("node_modules" in f or "arbeit" in f for f in fs)


@pytest.mark.parametrize("wert", ["", "./", None])
def test_ungueltig_vor_wurzel(tmp_path, wert):
    with pytest.raises(DriftFehler) as e:
        durchsuche_liste([], tmp_path, tmp_path / "fehlt", [wert])
    assert str(e.value) == MELDUNG


# --- CLI ---

def cli(tmp_path, capsys, toml, *args, wurzel=True):
    schreibe(tmp_path / "ports.toml", toml)
    argv = ["drift"] + ([str(tmp_path / "w")] if wurzel else [])
    code = main(argv + ["--datei", str(tmp_path / "ports.toml"), *args])
    o = capsys.readouterr()
    return code, o.out, o.err


BASIS = '[[port]]\nport = 1\nprojekt = "proj"\n'


def test_cli_datei_option_union(tmp_path, capsys):
    baue(tmp_path)
    code, out, _ = cli(tmp_path, capsys, BASIS)
    assert code == 1 and "berichte/z.py" in out
    code, out, _ = cli(tmp_path, capsys, 'ausschluss = ["berichte"]\n' + BASIS)
    assert "berichte/" not in out and "proj/a/x.py" in out
    code, out, _ = cli(tmp_path, capsys, BASIS, "--ausschliessen", "berichte")
    assert "berichte/" not in out
    code, out, _ = cli(tmp_path, capsys, 'ausschluss = ["berichte"]\n' + BASIS,
                       "--ausschliessen", "a", "--ausschliessen", "analysis/data")
    assert "proj/a/" not in out and "berichte/" not in out
    assert "proj/analysis/data" not in out
    assert "proj/other/analysis/data/x.json" in out
    assert "node_modules" not in out and "arbeit" not in out


def test_cli_alles_ausgeschlossen(tmp_path, capsys):
    schreibe(tmp_path / "w/proj/d/x.py", "port = 1234\n")
    code, out, _ = cli(tmp_path, capsys, BASIS, "--ausschliessen", "proj")
    assert (code, out) == (0, "kein Drift\n")


def test_cli_pfad_modus(tmp_path, capsys):
    schreibe(tmp_path / "w/proj/analysis/data/x.json", "port = 1234\n")
    schreibe(tmp_path / "w/proj/y.py", "port = 1234\n")
    toml = BASIS + 'pfad = "w/proj"\n'
    code, out, _ = cli(tmp_path, capsys, toml, "--ausschliessen", "analysis/data",
                       wurzel=False)
    assert code == 1
    assert out == ("unbekannt 1234 proj proj/y.py:1\n"
                   "abweichend proj LISTE=1 CODE=1234 proj/y.py:1\n")


@pytest.mark.parametrize("toml,args", [
    ('ausschluss = "x"\n', []),
    ("ausschluss = [1]\n", []),
    ('ausschluss = [" "]\n', []),
    ("", ["--ausschliessen", ""]),
    ("", ["--ausschliessen", "  "]),
    ("", ["--ausschliessen", "./"]),
    ("", ["--ausschliessen", "/"]),
])
def test_cli_fehler(tmp_path, capsys, toml, args):
    baue(tmp_path)
    code, out, err = cli(tmp_path, capsys, toml + BASIS, *args)
    assert code == 2 and out == ""
    assert err == f"Fehler: {MELDUNG}\n"


def test_cli_andere_fehler(tmp_path, capsys):
    code = main(["drift", str(tmp_path), "--datei", str(tmp_path / "nix.toml"),
                 "--ausschliessen", ""])
    err = capsys.readouterr().err
    assert code == 2 and err.startswith("Fehler: Datei nicht gefunden")


def test_andere_befehle_ignorieren_ausschluss(tmp_path, capsys):
    schreibe(tmp_path / "ports.toml", 'ausschluss = 5\n' + BASIS)
    schreibe(tmp_path / "n.txt", "  TCP    0.0.0.0:5000    0.0.0.0:0    LISTENING    1\n")
    d = ["--datei", str(tmp_path / "ports.toml")]
    assert main(["pruefen", *d]) == 0
    assert main(["abgleich", *d, "--netstat-datei", str(tmp_path / "n.txt")]) in (0, 1)
    assert main(["frei", "2000-2005", *d, "--netstat-datei", str(tmp_path / "n.txt")]) == 0
    assert "Fehler" not in capsys.readouterr().err
