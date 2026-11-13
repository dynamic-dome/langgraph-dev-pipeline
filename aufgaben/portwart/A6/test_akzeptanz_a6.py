"""Akzeptanztests A6 (Ordner von drift ausschließen), erzeugt vom Test-Schreiber im Lauf 20261020-184036
(nach „Tests nachbessern“ auf Fables Rat), von Dominic im Leitstand freigegeben (20.10.). Unverändert übernommen.
"""
"""Akzeptanztests A6: Ordner von drift ausschliessen."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
MELDUNG = "'ausschluss' muss eine Liste von nicht leeren Texten sein"


# ---------------------------------------------------------------- Helfer

def _datei(basis, rel, text="port = 9999\n"):
    p = Path(basis) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def _toml(tmp_path, ports, ausschluss=None, name="ports.toml"):
    """ports: Liste (port, projekt, pfad|None); ausschluss: roher TOML-Wert."""
    teile = []
    if ausschluss is not None:
        teile.append(f"ausschluss = {ausschluss}\n")
    for port, projekt, pfad in ports:
        teile.append(f'[[port]]\nport = {port}\nprojekt = "{projekt}"\n')
        if pfad is not None:
            teile.append(f'pfad = "{pfad}"\n')
    p = Path(tmp_path) / name
    p.write_text("\n".join(teile), encoding="utf-8")
    return p


def _cli(tmp_path, *args):
    return subprocess.run(
        [sys.executable, "-m", "portwart", *args],
        cwd=tmp_path,
        env=dict(os.environ, PYTHONPATH=str(REPO), PYTHONIOENCODING="utf-8"),
        capture_output=True, text=True, encoding="utf-8", timeout=60,
    )


def _funde(d, projekt):
    return sorted((f.datei, f.port, f.zeile) for f in d.funde[projekt])


def _dateien(d, projekt):
    return sorted(f.datei for f in d.funde[projekt])


def _projekt_layout(tmp_path):
    """proj/ mit Hauptdatei (Port 8000) und mehreren Fund-Ordnern."""
    _datei(tmp_path, "proj/main.py", "port = 8000\n")
    _datei(tmp_path, "proj/berichte/r.txt", "port = 9001\n")
    _datei(tmp_path, "proj/mess/m.txt", "port = 9002\n")
    _datei(tmp_path, "proj/data/d.json", "port = 9003\n")


# ------------------------------------------------------- lade_ausschluss

def test_lade_ausschluss_rohwerte_in_reihenfolge(tmp_path):
    from portwart.liste import lade_ausschluss
    p = _toml(tmp_path, [(8000, "proj", None)],
              "['b', './a/', 'b', 'X\\y', ' z ']")
    assert lade_ausschluss(p) == ["b", "./a/", "b", "X\\y", " z "]


def test_lade_ausschluss_fehlt_gibt_leere_liste(tmp_path):
    from portwart.liste import lade_ausschluss
    p = _toml(tmp_path, [(8000, "proj", None)])
    assert lade_ausschluss(p) == []


@pytest.mark.parametrize("wert", [
    '"berichte"', "5", "[1]", '["a", ""]', '["  "]', '[["a"]]', "{ a = 1 }",
])
def test_lade_ausschluss_ungueltig(tmp_path, wert):
    from portwart.liste import ListenFehler, lade_ausschluss
    p = _toml(tmp_path, [(8000, "proj", None)], wert)
    with pytest.raises(ListenFehler) as ei:
        lade_ausschluss(p)
    assert str(ei.value) == MELDUNG


def test_lade_ausschluss_dateifehler_wie_lade(tmp_path):
    from portwart.liste import ListenFehler, lade, lade_ausschluss
    fehlt = tmp_path / "gibt-es-nicht.toml"
    with pytest.raises(ListenFehler) as e1:
        lade_ausschluss(fehlt)
    assert str(e1.value) == f"Datei nicht gefunden: {fehlt}"
    kaputt = tmp_path / "kaputt.toml"
    kaputt.write_text("ausschluss = [\n", encoding="utf-8")
    with pytest.raises(ListenFehler) as e2:
        lade_ausschluss(kaputt)
    with pytest.raises(ListenFehler) as e3:
        lade(kaputt)
    assert str(e2.value).startswith(f"kein gültiges TOML in {kaputt}: ")
    assert str(e2.value) == str(e3.value)


def test_lade_ausschluss_nicht_lesbar_wie_lade(tmp_path):
    from portwart.liste import ListenFehler, lade, lade_ausschluss
    ordner = tmp_path / "ordner"
    ordner.mkdir()
    with pytest.raises(ListenFehler) as e1:
        lade_ausschluss(ordner)
    with pytest.raises(ListenFehler) as e2:
        lade(ordner)
    assert str(e1.value).startswith(f"Datei nicht lesbar: {ordner}: ")
    assert str(e1.value) == str(e2.value)


def test_lade_ignoriert_ungueltiges_ausschluss(tmp_path):
    from portwart.liste import Eintrag, lade
    p = _toml(tmp_path, [(8000, "proj", "proj")], '[1, ""]')
    assert lade(p) == [Eintrag(8000, "proj", "", "proj")]


# ------------------------------------------------ normalisiere_ausschluss

@pytest.mark.parametrize("roh, erwartet", [
    ("berichte", "berichte"),
    ("berichte/", "berichte"),
    ("./analysis", "analysis"),
    (".\\analysis", "analysis"),
    ("analysis\\data", "analysis/data"),
    ("analysis/data///", "analysis/data"),
    ("./analysis/data/", "analysis/data"),
    ("a\\b\\", "a/b"),
    ("*.json", "*.json"),
    ("Berichte", "Berichte"),
    (" a ", " a "),
])
def test_normalisiere_ausschluss(roh, erwartet):
    from portwart.drift import normalisiere_ausschluss
    assert normalisiere_ausschluss(roh) == erwartet
    assert normalisiere_ausschluss(erwartet) == erwartet


def test_normalisiere_ausschluss_entfernt_fuehrendes_punkt_slash_nur_einmal():
    from portwart.drift import normalisiere_ausschluss
    assert normalisiere_ausschluss("././a") == "./a"


@pytest.mark.parametrize("roh", ["", "  ", "./", "/", ".\\", "//", 5, None, ["a"]])
def test_normalisiere_ausschluss_ungueltig(roh):
    from portwart.drift import DriftFehler, normalisiere_ausschluss
    with pytest.raises(DriftFehler) as ei:
        normalisiere_ausschluss(roh)
    assert str(ei.value) == MELDUNG


# ------------------------------------------------------ durchsuche_liste

def _proj_baum(tmp_path):
    _datei(tmp_path, "proj/code.txt")
    _datei(tmp_path, "proj/berichte/a.txt")
    _datei(tmp_path, "proj/src/berichte/b.txt")
    _datei(tmp_path, "proj/src/main.txt")


def test_name_in_jeder_tiefe_pfad_modus(tmp_path):
    from portwart.drift import durchsuche_liste
    from portwart.liste import Eintrag
    _proj_baum(tmp_path)
    ein = [Eintrag(8000, "proj", "", "proj")]
    ohne = durchsuche_liste(ein, tmp_path)
    assert _dateien(ohne, "proj") == [
        "proj/berichte/a.txt", "proj/code.txt",
        "proj/src/berichte/b.txt", "proj/src/main.txt"]
    mit = durchsuche_liste(ein, tmp_path, ausschluss=["berichte"])
    assert _dateien(mit, "proj") == ["proj/code.txt", "proj/src/main.txt"]


def test_name_ist_gross_kleinschreibungsabhaengig(tmp_path):
    from portwart.drift import durchsuche_liste
    from portwart.liste import Eintrag
    _datei(tmp_path, "proj/berichte/a.txt")
    _datei(tmp_path, "proj/main.txt")
    ein = [Eintrag(8000, "proj", "", "proj")]
    d = durchsuche_liste(ein, tmp_path, ausschluss=["BERICHTE"])
    assert _dateien(d, "proj") == ["proj/berichte/a.txt", "proj/main.txt"]


def test_rohe_eintraege_werden_normalisiert(tmp_path):
    from portwart.drift import durchsuche_liste
    from portwart.liste import Eintrag
    _datei(tmp_path, "proj/main.txt")
    _datei(tmp_path, "proj/berichte/a.txt")
    _datei(tmp_path, "proj/src/gen/g.txt")
    ein = [Eintrag(8000, "proj", "", "proj")]
    d = durchsuche_liste(ein, tmp_path,
                         ausschluss=("./berichte/", "src\\gen\\"))
    assert _dateien(d, "proj") == ["proj/main.txt"]


def test_pfad_eintrag_nur_ab_projektordner(tmp_path):
    from portwart.drift import durchsuche_liste
    from portwart.liste import Eintrag
    _datei(tmp_path, "proj/analysis/data/x.json")
    _datei(tmp_path, "proj/other/analysis/data/x.json")
    _datei(tmp_path, "proj/analysis/keep.txt")
    ein = [Eintrag(8000, "proj", "", "proj")]
    d = durchsuche_liste(ein, tmp_path, ausschluss=["analysis/data"])
    assert _dateien(d, "proj") == [
        "proj/analysis/keep.txt", "proj/other/analysis/data/x.json"]


def test_pfad_eintrag_relativ_zum_aufgeloesten_projektordner(tmp_path):
    from portwart.drift import durchsuche_liste
    from portwart.liste import Eintrag
    _datei(tmp_path, "sub/proj/data/x.txt")
    _datei(tmp_path, "sub/proj/main.txt")
    ein = [Eintrag(8000, "proj", "", "sub/proj")]
    nicht = durchsuche_liste(ein, tmp_path, ausschluss=["sub/proj/data"])
    assert len(nicht.funde["proj"]) == 2
    trifft = durchsuche_liste(ein, tmp_path, ausschluss=["data"])
    assert [f.port for f in trifft.funde["proj"]] == [9999]
    assert len(trifft.funde["proj"]) == 1


def test_pfad_eintrag_trifft_keine_dateien(tmp_path):
    from portwart.drift import durchsuche_liste
    from portwart.liste import Eintrag
    _datei(tmp_path, "proj/sub/data")
    ein = [Eintrag(8000, "proj", "", "proj")]
    d = durchsuche_liste(ein, tmp_path, ausschluss=["sub/data"])
    assert _dateien(d, "proj") == ["proj/sub/data"]


def test_name_trifft_auch_dateien_nicht(tmp_path):
    from portwart.drift import durchsuche_liste
    from portwart.liste import Eintrag
    _datei(tmp_path, "proj/berichte")
    ein = [Eintrag(8000, "proj", "", "proj")]
    d = durchsuche_liste(ein, tmp_path, ausschluss=["berichte"])
    assert _dateien(d, "proj") == ["proj/berichte"]


def test_name_nimmt_projektordner_eines_pfad_eintrags_nicht_aus(tmp_path):
    from portwart.drift import durchsuche_liste
    from portwart.liste import Eintrag
    _datei(tmp_path, "berichte/x.txt")
    ein = [Eintrag(8000, "berichte", "", "berichte")]
    d = durchsuche_liste(ein, tmp_path, ausschluss=["berichte"])
    assert _dateien(d, "berichte") == ["berichte/x.txt"]


def test_wurzel_modus_name_direkt_unter_wurzel_und_tiefer(tmp_path):
    from portwart.drift import durchsuche_liste
    _datei(tmp_path, "w/berichte/x.txt")
    _datei(tmp_path, "w/app/a.txt")
    _datei(tmp_path, "w/app/berichte/b.txt")
    ohne = durchsuche_liste([], tmp_path, tmp_path / "w")
    assert sorted(ohne.funde) == ["app", "berichte"]
    d = durchsuche_liste([], tmp_path, tmp_path / "w", ausschluss=["berichte"])
    assert sorted(d.funde) == ["app"]
    assert _dateien(d, "app") == ["app/a.txt"]


def test_wurzel_modus_pfad_eintrag_ab_wurzel_projekt(tmp_path):
    from portwart.drift import durchsuche_liste
    _datei(tmp_path, "w/app/analysis/data/x.json")
    _datei(tmp_path, "w/app/other/analysis/data/y.json")
    _datei(tmp_path, "w/app/main.txt")
    d = durchsuche_liste([], tmp_path, tmp_path / "w",
                         ausschluss=["analysis/data"])
    assert _dateien(d, "app") == [
        "app/main.txt", "app/other/analysis/data/y.json"]
    # ein Pfad mit Projektnamen davor trifft nichts
    d2 = durchsuche_liste([], tmp_path, tmp_path / "w",
                          ausschluss=["app/analysis/data"])
    assert len(d2.funde["app"]) == 3


def test_feste_ausschluesse_bleiben_wirksam(tmp_path):
    from portwart.drift import durchsuche_liste
    from portwart.liste import Eintrag
    _datei(tmp_path, "proj/node_modules/n.txt")
    _datei(tmp_path, "proj/src/__pycache__/p.txt")
    _datei(tmp_path, "proj/berichte/a.txt")
    _datei(tmp_path, "proj/main.txt")
    ein = [Eintrag(8000, "proj", "", "proj")]
    d = durchsuche_liste(ein, tmp_path, ausschluss=["berichte"])
    assert _dateien(d, "proj") == ["proj/main.txt"]
    d2 = durchsuche_liste(ein, tmp_path, ausschluss=["zzz", "mehr/pfad"])
    assert _dateien(d2, "proj") == ["proj/berichte/a.txt", "proj/main.txt"]


def test_wildcard_ist_nur_ein_name(tmp_path):
    from portwart.drift import durchsuche_liste
    from portwart.liste import Eintrag
    _datei(tmp_path, "proj/x.json")
    _datei(tmp_path, "proj/sub/y.json")
    ein = [Eintrag(8000, "proj", "", "proj")]
    d = durchsuche_liste(ein, tmp_path, ausschluss=["*.json", "sub/*"])
    assert _dateien(d, "proj") == ["proj/sub/y.json", "proj/x.json"]


@pytest.mark.parametrize("schlecht", ["", "  ", "./", "/", 5])
def test_ungueltiger_ausschluss_loest_driftfehler_aus(tmp_path, schlecht):
    from portwart.drift import DriftFehler, durchsuche_liste
    from portwart.liste import Eintrag
    _datei(tmp_path, "proj/main.txt")
    ein = [Eintrag(8000, "proj", "", "proj")]
    with pytest.raises(DriftFehler) as ei:
        durchsuche_liste(ein, tmp_path, ausschluss=["berichte", schlecht])
    assert str(ei.value) == MELDUNG


def test_ungueltiger_ausschluss_im_wurzel_modus(tmp_path):
    from portwart.drift import DriftFehler, durchsuche_liste
    _datei(tmp_path, "w/app/a.txt")
    with pytest.raises(DriftFehler) as ei:
        durchsuche_liste([], tmp_path, tmp_path / "w", ausschluss=[""])
    assert str(ei.value) == MELDUNG


def test_standard_ohne_ausschluss_unveraendert(tmp_path):
    from portwart.drift import durchsuche, durchsuche_liste
    from portwart.liste import Eintrag
    _proj_baum(tmp_path)
    ein = [Eintrag(8000, "proj", "", "proj")]
    a = durchsuche_liste(ein, tmp_path)
    b = durchsuche_liste(ein, tmp_path, None, ())
    assert a == b
    assert len(a.funde["proj"]) == 4
    assert sorted(durchsuche(tmp_path / "proj")) == ["berichte", "src"]


# ------------------------------------------------------------------- CLI

def _ausgabe(r):
    return r.stdout.splitlines()


def test_cli_ohne_ausschluss_meldet_alle(tmp_path):
    _projekt_layout(tmp_path)
    _toml(tmp_path, [(8000, "proj", "proj")])
    r = _cli(tmp_path, "drift")
    assert r.returncode == 1
    assert _ausgabe(r) == [
        "unbekannt 9001 proj proj/berichte/r.txt:1",
        "unbekannt 9002 proj proj/mess/m.txt:1",
        "unbekannt 9003 proj proj/data/d.json:1",
    ]


def test_cli_ausschluss_aus_datei(tmp_path):
    _projekt_layout(tmp_path)
    _toml(tmp_path, [(8000, "proj", "proj")], '["berichte"]')
    r = _cli(tmp_path, "drift")
    assert r.returncode == 1
    assert r.stderr == ""
    assert len(_ausgabe(r)) == 2
    assert "9001" not in r.stdout
    assert "9002" in r.stdout and "9003" in r.stdout


def test_cli_option_allein_und_wiederholt(tmp_path):
    _projekt_layout(tmp_path)
    _toml(tmp_path, [(8000, "proj", "proj")])
    r = _cli(tmp_path, "drift", "--ausschliessen", "mess")
    assert r.returncode == 1
    assert "9002" not in r.stdout
    assert "9001" in r.stdout and "9003" in r.stdout
    r2 = _cli(tmp_path, "drift", "--ausschliessen", "mess/",
              "--ausschliessen", "./data")
    assert r2.returncode == 1
    assert _ausgabe(r2) == [l for l in _ausgabe(r) if "9001" in l]


def test_cli_vereinigung_datei_und_option_gibt_kein_drift(tmp_path):
    _projekt_layout(tmp_path)
    _toml(tmp_path, [(8000, "proj", "proj")], '["berichte"]')
    r = _cli(tmp_path, "drift", "--ausschliessen", "mess",
             "--ausschliessen", "data")
    assert (r.returncode, r.stdout, r.stderr) == (0, "kein Drift\n", "")


def test_cli_pfad_ausschluss_ueber_option(tmp_path):
    _datei(tmp_path, "proj/main.py", "port = 8000\n")
    _datei(tmp_path, "proj/analysis/data/x.json", "port = 9100\n")
    _datei(tmp_path, "proj/other/analysis/data/x.json", "port = 9200\n")
    _toml(tmp_path, [(8000, "proj", "proj")])
    r = _cli(tmp_path, "drift", "--ausschliessen", "analysis\\data")
    assert r.returncode == 1
    assert len(_ausgabe(r)) == 1
    assert _ausgabe(r)[0].startswith("unbekannt 9200 proj ")
    assert _ausgabe(r)[0].endswith("other/analysis/data/x.json:1")


def test_cli_wurzel_modus_name_direkt_unter_wurzel(tmp_path):
    _datei(tmp_path, "w/app/main.py", "port = 8000\n")
    _datei(tmp_path, "w/berichte/x.txt", "port = 9001\n")
    _toml(tmp_path, [(8000, "app", None)])
    r0 = _cli(tmp_path, "drift", "w")
    assert r0.returncode == 1
    assert _ausgabe(r0) == ["unbekannt 9001 berichte berichte/x.txt:1"]
    r = _cli(tmp_path, "drift", "w", "--ausschliessen", "berichte/")
    assert (r.returncode, r.stdout, r.stderr) == (0, "kein Drift\n", "")


def test_cli_nicht_existierender_ausschluss_ist_ok(tmp_path):
    _datei(tmp_path, "proj/main.py", "port = 8000\n")
    _toml(tmp_path, [(8000, "proj", "proj")], '["gibt/es/nicht"]')
    r = _cli(tmp_path, "drift", "--ausschliessen", "auch-nicht")
    assert (r.returncode, r.stdout, r.stderr) == (0, "kein Drift\n", "")


@pytest.mark.parametrize("wert", [
    '"berichte"', "5", "[1]", '["a", ""]', '["  "]', '[["a"]]', '["./"]', '["/"]',
])
def test_cli_ungueltiges_ausschluss_in_datei(tmp_path, wert):
    _projekt_layout(tmp_path)
    _toml(tmp_path, [(8000, "proj", "proj")], wert)
    r = _cli(tmp_path, "drift")
    assert r.returncode == 2
    assert r.stdout == ""
    assert r.stderr == f"Fehler: {MELDUNG}\n"


@pytest.mark.parametrize("wert", ["", "   ", "./", "/", ".\\"])
def test_cli_ungueltiger_optionswert(tmp_path, wert):
    _projekt_layout(tmp_path)
    _toml(tmp_path, [(8000, "proj", "proj")])
    r = _cli(tmp_path, "drift", "--ausschliessen", "berichte",
             "--ausschliessen", wert)
    assert r.returncode == 2
    assert r.stdout == ""
    assert r.stderr == f"Fehler: {MELDUNG}\n"


def test_cli_ungueltige_datei_ist_fehler_trotz_gueltiger_option(tmp_path):
    _projekt_layout(tmp_path)
    _toml(tmp_path, [(8000, "proj", "proj")], "[1]")
    r = _cli(tmp_path, "drift", "--ausschliessen", "berichte")
    assert r.returncode == 2
    assert r.stdout == ""
    assert r.stderr == f"Fehler: {MELDUNG}\n"


def test_cli_uebrige_fehler_bleiben(tmp_path):
    r = _cli(tmp_path, "drift", "--ausschliessen", "x")
    assert r.returncode == 2
    assert r.stdout == ""
    assert r.stderr.startswith("Fehler: Datei nicht gefunden: ")
    _toml(tmp_path, [(8000, "proj", "proj")])
    r2 = _cli(tmp_path, "drift", "gibt-es-nicht", "--ausschliessen", "x")
    assert r2.returncode == 2
    assert r2.stdout == ""
    assert r2.stderr.startswith("Fehler: Wurzelordner nicht gefunden: ")


def test_cli_pruefen_abgleich_frei_ignorieren_ungueltiges_ausschluss(tmp_path):
    _toml(tmp_path, [(8000, "proj", None), (8001, "proj2", None)],
          name="gut.toml")
    _toml(tmp_path, [(8000, "proj", None), (8001, "proj2", None)],
          '[1, ""]', name="schlecht.toml")
    (tmp_path / "netstat.txt").write_text("", encoding="utf-8")
    faelle = [
        ["pruefen"],
        ["abgleich", "--netstat-datei", "netstat.txt"],
        ["frei", "8000-8005", "--anzahl", "2", "--netstat-datei",
         "netstat.txt"],
    ]
    for fall in faelle:
        gut = _cli(tmp_path, *fall, "--datei", "gut.toml")
        schlecht = _cli(tmp_path, *fall, "--datei", "schlecht.toml")
        assert schlecht.returncode == gut.returncode, fall
        assert schlecht.returncode in (0, 1), fall
        assert schlecht.stdout == gut.stdout, fall
        assert schlecht.stderr == "" == gut.stderr, fall
    p = _cli(tmp_path, "pruefen", "--datei", "schlecht.toml")
    assert (p.returncode, p.stdout) == (0, "keine doppelten Ports\n")
