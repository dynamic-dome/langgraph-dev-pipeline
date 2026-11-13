import os

import pytest

from portwart.__main__ import main
from portwart.drift import (
    DriftErgebnis, DriftFehler, Durchsuchung, PfadFehlt, drift,
    durchsuche, durchsuche_liste, zeilen,
)
from portwart.liste import Eintrag, ListenFehler, lade


def _toml(tmp_path, eintraege, name="ports.toml"):
    teile = []
    for e in eintraege:
        zeilen_ = ["[[port]]"]
        for k, v in e.items():
            zeilen_.append(f"{k} = {v!r}" if not isinstance(v, str)
                           else f'{k} = "{v}"')
        teile.append("\n".join(zeilen_))
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n\n".join(teile) + "\n", encoding="utf-8")
    return p


def _code(ordner, text="port = 9000\n", datei="app.py"):
    ordner.mkdir(parents=True, exist_ok=True)
    (ordner / datei).write_text(text)


# --- liste ---

def test_eintrag_pfad_standard():
    assert Eintrag(8000, "wiki").pfad is None
    assert Eintrag(8000, "wiki", "x").pfad is None


def test_lade_pfad_roh(tmp_path):
    p = _toml(tmp_path, [{"port": 8000, "projekt": "a", "pfad": " ./a b "},
                         {"port": 8001, "projekt": "b"}])
    e = lade(p)
    assert e[0].pfad == " ./a b " and e[1].pfad is None


@pytest.mark.parametrize("wert", ['""', '"  "', "5"])
def test_lade_pfad_ungueltig(tmp_path, wert):
    p = tmp_path / "l.toml"
    p.write_text(f'[[port]]\nport = 1\nprojekt = "a"\n[[port]]\nport = 2\n'
                 f'projekt = "b"\npfad = {wert}\n')
    with pytest.raises(ListenFehler) as e:
        lade(p)
    assert str(e.value) == "Eintrag 2: 'pfad' muss ein nicht leerer Text sein"


def test_lade_zweck_vor_pfad(tmp_path):
    p = tmp_path / "l.toml"
    p.write_text('[[port]]\nport = 1\nprojekt = "a"\nzweck = 3\npfad = 5\n')
    with pytest.raises(ListenFehler, match="'zweck'"):
        lade(p)


def test_lade_prueft_pfad_nicht(tmp_path):
    p = _toml(tmp_path, [{"port": 1, "projekt": "a", "pfad": "nix"},
                         {"port": 2, "projekt": "a", "pfad": "anders"}])
    assert len(lade(p)) == 2


# --- drift-Typen ---

def test_typen():
    assert DriftErgebnis([], []).fehlend == []
    assert DriftErgebnis([], []).fehlend is not DriftErgebnis([], []).fehlend
    with pytest.raises(Exception):
        PfadFehlt("a", "b").projekt = "x"
    with pytest.raises(Exception):
        Durchsuchung({}, []).funde = {}
    assert PfadFehlt("p", "./a") == PfadFehlt("p", "./a")


def test_drift_fehlend_und_zeilen():
    f = (PfadFehlt("b", "x y"), PfadFehlt("a", "./y"))
    r = drift([], {}, f)
    assert [x.projekt for x in r.fehlend] == ["a", "b"]
    assert zeilen(r) == ["pfad-fehlt a ./y", "pfad-fehlt b x y"]


# --- durchsuche_liste ---

def test_scan_projektname_praefix(tmp_path):
    _code(tmp_path / "ordner" / "sub")
    _code(tmp_path / "leer")
    e = [Eintrag(1, "proj", "", "ordner"), Eintrag(2, "l", "", "./leer")]
    d = durchsuche_liste(e, tmp_path)
    assert [(f.datei, f.zeile, f.port) for f in d.funde["proj"]] == [
        ("proj/sub/app.py", 1, 9000)]
    assert d.funde["l"] == [] or d.funde["l"][0].datei.startswith("l/")
    assert d.fehlend == []


def test_scan_leer_und_ausgeschlossen(tmp_path):
    (tmp_path / "p").mkdir()
    _code(tmp_path / "build")
    _code(tmp_path / "x" / "node_modules")
    d = durchsuche_liste([Eintrag(1, "p", "", "p"), Eintrag(2, "b", "", "build"),
                          Eintrag(3, "x", "", "x")], tmp_path)
    assert d.funde["p"] == []
    assert len(d.funde["b"]) == 1 and d.funde["b"][0].datei == "b/app.py"
    assert d.funde["x"] == []


def test_widerspruch(tmp_path):
    e = [Eintrag(1, "p", "", "./a"), Eintrag(2, "p", "", "a"),
         Eintrag(3, "p", "", "b"), Eintrag(4, "p", "", "c")]
    with pytest.raises(DriftFehler) as ex:
        durchsuche_liste(e, tmp_path)
    assert str(ex.value) == "Projekt p hat verschiedene Pfade: ./a, b"


def test_widerspruch_erstes_projekt(tmp_path):
    e = [Eintrag(1, "a", "", "x"), Eintrag(2, "b", "", "x"),
         Eintrag(3, "b", "", "y"), Eintrag(4, "a", "", "z")]
    with pytest.raises(DriftFehler, match="Projekt b "):
        durchsuche_liste(e, tmp_path)


def test_wurzel_vor_widerspruch(tmp_path):
    e = [Eintrag(1, "p", "", "a"), Eintrag(2, "p", "", "b")]
    with pytest.raises(DriftFehler, match="Wurzelordner nicht gefunden"):
        durchsuche_liste(e, tmp_path, tmp_path / "nein")
    (tmp_path / "f").write_text("x")
    with pytest.raises(DriftFehler, match="Wurzel ist kein Ordner"):
        durchsuche_liste([], tmp_path, tmp_path / "f")


def test_pfad_uebernehmen(tmp_path):
    _code(tmp_path / "a")
    e = [Eintrag(1, "p"), Eintrag(2, "p", "", "a")]
    d = durchsuche_liste(e, tmp_path)
    assert len(d.funde["p"]) == 1
    d = durchsuche_liste([Eintrag(1, "p"), Eintrag(2, "p", "", "nix")], tmp_path)
    assert d.fehlend == [PfadFehlt("p", "nix")]


def test_pfad_fehlt_varianten(tmp_path):
    _code(tmp_path / "ok")
    (tmp_path / "datei").write_text("x")
    e = [Eintrag(1, "z", "", "nix"), Eintrag(2, "z", "", "nix"),
         Eintrag(3, "d", "", "datei"), Eintrag(4, "n", "", "a\0b"),
         Eintrag(5, "ok", "", "ok")]
    d = durchsuche_liste(e, tmp_path)
    assert [f.projekt for f in d.fehlend] == ["d", "n", "z"]
    assert list(d.funde) == ["ok"]


def test_pfad_permission(tmp_path, monkeypatch):
    _code(tmp_path / "gesperrt")
    _code(tmp_path / "ok")
    echt = os.scandir

    def scan(p):
        if os.path.basename(os.fspath(p)) == "gesperrt":
            raise PermissionError("x")
        return echt(p)

    monkeypatch.setattr(os, "scandir", scan)
    d = durchsuche_liste([Eintrag(1, "g", "", "gesperrt"),
                          Eintrag(2, "ok", "", "ok")], tmp_path)
    assert d.fehlend == [PfadFehlt("g", "gesperrt")] and list(d.funde) == ["ok"]


def test_pfad_permission_beim_iterieren(tmp_path, monkeypatch):
    _code(tmp_path / "gesperrt")
    _code(tmp_path / "ok")
    echt = os.scandir

    class Kaputt:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def __iter__(self):
            return self

        def __next__(self):
            raise PermissionError("x")

    def scan(p):
        if os.path.basename(os.fspath(p)) == "gesperrt":
            return Kaputt()
        return echt(p)

    monkeypatch.setattr(os, "scandir", scan)
    d = durchsuche_liste([Eintrag(1, "g", "", "gesperrt"),
                          Eintrag(2, "ok", "", "ok")], tmp_path)
    assert d.fehlend == [PfadFehlt("g", "gesperrt")] and list(d.funde) == ["ok"]


def test_unterordner_nicht_lesbar_still(tmp_path, monkeypatch):
    _code(tmp_path / "p" / "sub")
    echt = os.scandir

    def scan(p):
        if os.path.basename(os.fspath(p)) == "sub":
            raise PermissionError("x")
        return echt(p)

    monkeypatch.setattr(os, "scandir", scan)
    d = durchsuche_liste([Eintrag(1, "p", "", "p")], tmp_path)
    assert d == Durchsuchung({"p": []}, [])


def test_tilde(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    _code(tmp_path / "h")
    d = durchsuche_liste([Eintrag(1, "p", "", "~/h")], tmp_path / "andere")
    assert len(d.funde["p"]) == 1


def test_wurzel_gemischt(tmp_path):
    w = tmp_path / "w"
    _code(w / "fremd", "port = 7777\n")
    _code(w / "alt", "port = 5000\n")
    _code(w / "mitpfad", "port = 6000\n")
    _code(w / "build", "port = 6001\n")
    e = [Eintrag(1, "alt"), Eintrag(2, "mitpfad", "", "nix")]
    d = durchsuche_liste(e, tmp_path, w)
    assert sorted(d.funde) == ["alt", "fremd"]
    assert d.fehlend == [PfadFehlt("mitpfad", "nix")]


def test_ohne_wurzel(tmp_path):
    _code(tmp_path / "alt")
    assert durchsuche_liste([Eintrag(1, "alt")], tmp_path) == Durchsuchung({}, [])
    assert durchsuche_liste([], tmp_path) == Durchsuchung({}, [])


def test_durchsuche_unveraendert(tmp_path):
    _code(tmp_path / "a")
    assert list(durchsuche(tmp_path)) == ["a"]


# --- CLI ---

def test_cli_ohne_argumente(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["drift"]) == 2
    o = capsys.readouterr()
    assert o.out == "" and o.err.startswith("Fehler: ")
    _toml(tmp_path, [{"port": 1, "projekt": "a"}])
    assert main(["drift"]) == 0
    assert capsys.readouterr().out == "kein Drift\n"
    _code(tmp_path / "p")
    _toml(tmp_path, [{"port": 1, "projekt": "a", "pfad": "p"}])
    assert main(["drift"]) == 1
    assert capsys.readouterr().out == (
        "unbekannt 9000 a a/app.py:1\n"
        "abweichend a LISTE=1 CODE=9000 a/app.py:1\n")


def test_cli_relativ_zur_liste(tmp_path, monkeypatch, capsys):
    _code(tmp_path / "liste" / "code")
    p = _toml(tmp_path, [{"port": 1, "projekt": "a", "pfad": "code"}],
              name="liste/p.toml")
    monkeypatch.chdir(tmp_path)
    assert main(["drift", "--datei", str(p)]) == 1
    assert "abweichend a" in capsys.readouterr().out


def test_cli_reihenfolge_und_pfad_fehlt(tmp_path, capsys):
    w = tmp_path / "w"
    _code(w / "fremd", "port = 7777\n")
    _code(tmp_path / "a", "port = 9000\n")
    p = _toml(tmp_path, [{"port": 1, "projekt": "a", "pfad": "a"},
                         {"port": 2, "projekt": "z", "pfad": "../nix"}])
    assert main(["drift", str(w), "--datei", str(p)]) == 1
    assert capsys.readouterr().out.splitlines() == [
        "unbekannt 7777 fremd fremd/app.py:1",
        "unbekannt 9000 a a/app.py:1",
        "abweichend a LISTE=1 CODE=9000 a/app.py:1",
        "pfad-fehlt z ../nix",
    ]
    p = _toml(tmp_path, [{"port": 9000, "projekt": "z", "pfad": "nix"}])
    assert main(["drift", "--datei", str(p)]) == 1
    assert capsys.readouterr().out == "pfad-fehlt z nix\n"


@pytest.mark.parametrize("pfad", ['""', '"  "', "5"])
def test_cli_ungueltiges_pfadfeld(tmp_path, capsys, pfad):
    p = tmp_path / "l.toml"
    p.write_text(f'[[port]]\nport = 1\nprojekt = "a"\npfad = {pfad}\n')
    for befehl in (["pruefen"], ["drift"], ["abgleich", "--netstat-datei", str(p)],
                   ["frei", "2000-3000", "--netstat-datei", str(p)]):
        assert main(befehl + ["--datei", str(p)]) == 2
        o = capsys.readouterr()
        assert o.out == "" and o.err.startswith("Fehler: ")


def test_cli_wurzel_und_widerspruch_exit2(tmp_path, capsys):
    p = _toml(tmp_path, [{"port": 1, "projekt": "a", "pfad": "x"},
                         {"port": 2, "projekt": "a", "pfad": "y"}])
    assert main(["drift", str(tmp_path / "nein"), "--datei", str(p)]) == 2
    o = capsys.readouterr()
    assert o.out == "" and "Wurzelordner nicht gefunden" in o.err
    assert main(["drift", "--datei", str(p)]) == 2
    o = capsys.readouterr()
    assert o.out == "" and "hat verschiedene Pfade: x, y" in o.err


def test_andere_befehle_ignorieren_pfad(tmp_path, capsys):
    mit = _toml(tmp_path, [{"port": 5000, "projekt": "a", "pfad": "nix"},
                           {"port": 5000, "projekt": "b", "pfad": "x"},
                           {"port": 5001, "projekt": "b", "pfad": "y"}],
                name="mit.toml")
    ohne = _toml(tmp_path, [{"port": 5000, "projekt": "a"},
                            {"port": 5000, "projekt": "b"},
                            {"port": 5001, "projekt": "b"}], name="ohne.toml")
    ns = tmp_path / "ns.txt"
    ns.write_text("  TCP    0.0.0.0:5000    0.0.0.0:0    LISTENING    1\n"
                  "  TCP    0.0.0.0:5009    0.0.0.0:0    LISTENING    1\n")
    for befehl in (["pruefen"], ["abgleich", "--netstat-datei", str(ns)],
                   ["frei", "5000-5010", "--anzahl", "3", "--netstat-datei", str(ns)]):
        code1 = main(befehl + ["--datei", str(mit)])
        o1 = capsys.readouterr()
        code2 = main(befehl + ["--datei", str(ohne)])
        o2 = capsys.readouterr()
        assert (code1, o1.out, o1.err) == (code2, o2.out, o2.err)
