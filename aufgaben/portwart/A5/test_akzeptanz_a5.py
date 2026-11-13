"""Akzeptanztests A5 (Pfad je Eintrag), erzeugt vom Test-Schreiber der Pipeline im Lauf 20261020-164410
(Spec-Fassung 2), von Dominic im Leitstand freigegeben (20.10.). Unverändert übernommen.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _toml(tmp_path, eintraege, name="ports.toml"):
    teile = []
    for e in eintraege:
        zeilen = ["[[port]]"]
        for k, v in e.items():
            zeilen.append(f"{k} = {json.dumps(v)}")
        teile.append("\n".join(zeilen))
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n\n".join(teile) + "\n", encoding="utf-8")
    return p


def _cli(tmp_path, *args):
    return subprocess.run(
        [sys.executable, "-m", "portwart", *args],
        cwd=tmp_path,
        env=dict(os.environ, PYTHONPATH=str(REPO), PYTHONIOENCODING="utf-8"),
        capture_output=True, text=True, encoding="utf-8", timeout=60,
    )


def _code(ordner, rel="a.py", text="port = 9000\n"):
    f = Path(ordner) / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text, encoding="utf-8")
    return f


def _sperre(monkeypatch, ziel, fehler=PermissionError):
    """scandir/listdir auf genau diesen Ordner wirft PermissionError."""
    ziel = os.path.normcase(os.path.normpath(str(ziel)))
    echt_scandir, echt_listdir = os.scandir, os.listdir

    def pruefe(p):
        if isinstance(p, (str, bytes, os.PathLike)):
            if os.path.normcase(os.path.normpath(os.fsdecode(p))) == ziel:
                raise fehler("gesperrt")

    def scandir(p="."):
        pruefe(p)
        return echt_scandir(p)

    def listdir(p="."):
        pruefe(p)
        return echt_listdir(p)

    monkeypatch.setattr(os, "scandir", scandir)
    monkeypatch.setattr(os, "listdir", listdir)


# ---------------------------------------------------------------- liste

def test_eintrag_pfad_standard_none_und_rohtext(tmp_path):
    from portwart.liste import Eintrag, lade
    assert Eintrag(1, "a", "z").pfad is None
    assert Eintrag(1, "a", "z", "p").pfad == "p"
    p = _toml(tmp_path, [{"port": 8000, "projekt": "a"},
                         {"port": 8001, "projekt": "b", "pfad": " ./x/../y "}])
    e = lade(p)
    assert e[0].pfad is None
    assert e[1].pfad == " ./x/../y "
    assert e[1] == Eintrag(8001, "b", "", " ./x/../y ")


@pytest.mark.parametrize("wert", [5, "", "  "])
def test_lade_pfad_ungueltig(tmp_path, wert):
    from portwart.liste import ListenFehler, lade
    p = _toml(tmp_path, [{"port": 8000, "projekt": "a"},
                         {"port": 8001, "projekt": "b", "pfad": wert}])
    with pytest.raises(ListenFehler) as e:
        lade(p)
    assert str(e.value) == "Eintrag 2: 'pfad' muss ein nicht leerer Text sein"


def test_lade_zweck_vor_pfad_und_keine_pfadpruefung(tmp_path):
    from portwart.liste import ListenFehler, lade
    p = _toml(tmp_path, [{"port": 8000, "projekt": "a", "zweck": 5, "pfad": 5}])
    with pytest.raises(ListenFehler, match="'zweck' muss ein Text sein"):
        lade(p)
    # Nicht existierende und widersprüchliche Pfade sind für lade kein Fehler
    p = _toml(tmp_path, [{"port": 8000, "projekt": "a", "pfad": "/gibt/es/nicht"},
                         {"port": 8001, "projekt": "a", "pfad": "anders"}])
    assert [e.pfad for e in lade(p)] == ["/gibt/es/nicht", "anders"]


# ---------------------------------------------------------------- durchsuche_liste

def test_pfad_scan_projektname_als_praefix_und_leere_liste(tmp_path):
    from portwart.drift import Durchsuchung, Fund, durchsuche_liste
    from portwart.liste import Eintrag
    _code(tmp_path / "ordner_x", "src/b.py", "x\nport = 9000\n")
    _code(tmp_path / "ordner_x", "a.py", "port = 9001\n")
    (tmp_path / "leer").mkdir()
    erg = durchsuche_liste(
        [Eintrag(8000, "wiki", "", str(tmp_path / "ordner_x")),
         Eintrag(8001, "nix", "", str(tmp_path / "leer"))],
        tmp_path)
    assert isinstance(erg, Durchsuchung)
    assert erg.funde == {
        "wiki": [Fund(9001, "wiki/a.py", 1), Fund(9000, "wiki/src/b.py", 2)],
        "nix": [],
    }
    assert erg.fehlend == []


def test_relative_pfade_gegen_basis_und_gleichheit(tmp_path):
    from portwart.drift import Fund, durchsuche_liste
    from portwart.liste import Eintrag
    _code(tmp_path / "basis" / "a")
    erg = durchsuche_liste(
        [Eintrag(1, "p", "", "./a"), Eintrag(2, "p", "", "a"),
         Eintrag(3, "p", "", "x/../a/")],
        tmp_path / "basis")
    assert erg.funde == {"p": [Fund(9000, "p/a.py", 1)]}
    assert erg.fehlend == []


def test_tilde_wird_expandiert(tmp_path, monkeypatch):
    from portwart.drift import Fund, durchsuche_liste
    from portwart.liste import Eintrag
    home = tmp_path / "home"
    _code(home / "proj")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    erg = durchsuche_liste([Eintrag(1, "p", "", "~/proj")], tmp_path / "leer")
    assert erg.funde == {"p": [Fund(9000, "p/a.py", 1)]}
    assert erg.fehlend == []


def test_widerspruch_meldung_und_p1_p2(tmp_path):
    from portwart.drift import DriftFehler, durchsuche_liste
    from portwart.liste import Eintrag
    for n in ("a", "b", "c"):
        (tmp_path / n).mkdir()
    liste = [Eintrag(1, "ok", "", "a"), Eintrag(2, "ok", "", "./a"),
             Eintrag(3, "p", "", "./a"), Eintrag(4, "p", "", "a"),
             Eintrag(5, "p", "", "b"), Eintrag(6, "p", "", "c")]
    with pytest.raises(DriftFehler) as e:
        durchsuche_liste(liste, tmp_path)
    assert str(e.value) == "Projekt p hat verschiedene Pfade: ./a, b"


def test_widerspruch_erstes_projekt_in_listenreihenfolge(tmp_path):
    from portwart.drift import DriftFehler, durchsuche_liste
    from portwart.liste import Eintrag
    liste = [Eintrag(1, "x", "", "a"), Eintrag(2, "y", "", "a"),
             Eintrag(3, "y", "", "b"), Eintrag(4, "x", "", "c")]
    with pytest.raises(DriftFehler) as e:
        durchsuche_liste(liste, tmp_path)
    assert str(e.value) == "Projekt y hat verschiedene Pfade: a, b"


def test_wurzelfehler_vor_widerspruch(tmp_path):
    from portwart.drift import DriftFehler, durchsuche_liste
    from portwart.liste import Eintrag
    liste = [Eintrag(1, "p", "", "a"), Eintrag(2, "p", "", "b")]
    with pytest.raises(DriftFehler, match="Wurzelordner nicht gefunden"):
        durchsuche_liste(liste, tmp_path, tmp_path / "nein")
    (tmp_path / "datei").write_text("x")
    with pytest.raises(DriftFehler, match="Wurzel ist kein Ordner"):
        durchsuche_liste(liste, tmp_path, tmp_path / "datei")


def test_fehlende_pfade_sortiert_und_andere_werden_gescannt(tmp_path):
    from portwart.drift import Fund, PfadFehlt, durchsuche_liste
    from portwart.liste import Eintrag
    _code(tmp_path / "gut")
    (tmp_path / "datei").write_text("port = 1")
    liste = [Eintrag(1, "zeta", "", "nein"), Eintrag(2, "zeta", "", "./nein"),
             Eintrag(3, "gut", "", "gut"),
             Eintrag(4, "alpha", "", "datei"),
             Eintrag(5, "mitte", "", "a\x00b")]
    erg = durchsuche_liste(liste, tmp_path)
    assert erg.funde == {"gut": [Fund(9000, "gut/a.py", 1)]}
    assert erg.fehlend == [PfadFehlt("alpha", "datei"),
                           PfadFehlt("mitte", "a\x00b"),
                           PfadFehlt("zeta", "nein")] or erg.fehlend == [
        PfadFehlt("alpha", "datei"), PfadFehlt("mitte", "a\x00b"),
        PfadFehlt("zeta", "nein")]


def test_fehlend_pfadtext_des_ersten_eintrags_mit_pfad(tmp_path):
    from portwart.drift import PfadFehlt, durchsuche_liste
    from portwart.liste import Eintrag
    erg = durchsuche_liste(
        [Eintrag(1, "p"), Eintrag(2, "p", "", "./weg"), Eintrag(3, "p", "", "weg")],
        tmp_path)
    assert erg.fehlend == [PfadFehlt("p", "./weg")]
    assert erg.funde == {}


def test_pfadordner_nicht_lesbar_permissionerror(tmp_path, monkeypatch):
    from portwart.drift import Fund, PfadFehlt, durchsuche_liste
    from portwart.liste import Eintrag
    _code(tmp_path / "gesperrt")
    _code(tmp_path / "offen")
    _sperre(monkeypatch, tmp_path / "gesperrt")
    erg = durchsuche_liste(
        [Eintrag(1, "g", "", "gesperrt"), Eintrag(2, "o", "", "offen")], tmp_path)
    assert erg.fehlend == [PfadFehlt("g", "gesperrt")]
    assert erg.funde == {"o": [Fund(9000, "o/a.py", 1)]}


def test_unterordner_nicht_lesbar_still_uebersprungen(tmp_path, monkeypatch):
    from portwart.drift import Fund, durchsuche_liste
    from portwart.liste import Eintrag
    _code(tmp_path / "p" / "sperr")
    _code(tmp_path / "p", "ok.py", "port = 9100\n")
    _sperre(monkeypatch, tmp_path / "p" / "sperr")
    erg = durchsuche_liste([Eintrag(1, "p", "", "p")], tmp_path)
    assert erg.funde == {"p": [Fund(9100, "p/ok.py", 1)]}
    assert erg.fehlend == []


def test_pfadordner_mit_ausgeschlossenem_namen_wird_gescannt(tmp_path):
    from portwart.drift import Fund, durchsuche_liste
    from portwart.liste import Eintrag
    _code(tmp_path / "build")
    _code(tmp_path / "build" / "node_modules", "x.py", "port = 1234\n")
    erg = durchsuche_liste([Eintrag(1, "p", "", "build")], tmp_path)
    assert erg.funde == {"p": [Fund(9000, "p/a.py", 1)]}


def test_eintrag_ohne_pfad_uebernimmt_pfad_des_projekts(tmp_path):
    from portwart.drift import Fund, durchsuche_liste
    from portwart.liste import Eintrag
    _code(tmp_path / "code")
    erg = durchsuche_liste(
        [Eintrag(1, "p"), Eintrag(2, "p", "", "code"), Eintrag(3, "p")], tmp_path)
    assert erg.funde == {"p": [Fund(9000, "p/a.py", 1)]}
    assert erg.fehlend == []


def test_ohne_wurzel_projekte_ohne_pfad_nicht_gescannt(tmp_path):
    from portwart.drift import durchsuche_liste
    from portwart.liste import Eintrag
    _code(tmp_path / "wiki")
    erg = durchsuche_liste([Eintrag(1, "wiki")], tmp_path)
    assert erg.funde == {}
    assert erg.fehlend == []
    erg = durchsuche_liste([], tmp_path)
    assert erg.funde == {} and erg.fehlend == []


def test_wurzel_unterordner_ohne_eintrag_und_ausnahme_fuer_pfadprojekte(tmp_path):
    from portwart.drift import Fund, PfadFehlt, durchsuche_liste
    from portwart.liste import Eintrag
    w = tmp_path / "w"
    _code(w / "fremd", "f.py", "port = 7777\n")
    _code(w / "altlast", "x.py", "port = 6666\n")   # Name = Projekt mit fehlendem Pfad
    _code(w / "mitpfad", "x.py", "port = 5555\n")   # Name = Projekt mit gültigem Pfad
    _code(w / "ohnepfad", "o.py", "port = 4444\n")  # Eintrag ohne Pfad: über Namen
    _code(w / "build", "b.py", "port = 3333\n")     # ausgeschlossen
    _code(tmp_path / "echt", "e.py", "port = 8888\n")
    erg = durchsuche_liste(
        [Eintrag(1, "altlast", "", "gibtsnicht"), Eintrag(2, "mitpfad", "", "echt"),
         Eintrag(3, "ohnepfad")],
        tmp_path, w)
    assert erg.funde == {
        "fremd": [Fund(7777, "fremd/f.py", 1)],
        "mitpfad": [Fund(8888, "mitpfad/e.py", 1)],
        "ohnepfad": [Fund(4444, "ohnepfad/o.py", 1)],
    }
    assert erg.fehlend == [PfadFehlt("altlast", "gibtsnicht")]


def test_durchsuche_bleibt_wie_bisher(tmp_path):
    from portwart.drift import Fund, durchsuche
    _code(tmp_path / "wiki", "a.py", "port = 9000\n")
    (tmp_path / "leer").mkdir()
    assert durchsuche(tmp_path) == {"leer": [], "wiki": [Fund(9000, "wiki/a.py", 1)]}


# ---------------------------------------------------------------- drift / zeilen

def test_drift_fehlend_und_zeilen_reihenfolge():
    from portwart.drift import DriftErgebnis, Fund, PfadFehlt, drift, zeilen
    from portwart.liste import Eintrag
    erg = drift([Eintrag(8000, "wiki")], {"wiki": [Fund(9000, "wiki/a.py", 1)]},
                [PfadFehlt("b", "pb"), PfadFehlt("a", "pa")])
    assert erg.fehlend == [PfadFehlt("a", "pa"), PfadFehlt("b", "pb")]
    assert zeilen(erg) == [
        "unbekannt 9000 wiki wiki/a.py:1",
        "abweichend wiki LISTE=8000 CODE=9000 wiki/a.py:1",
        "pfad-fehlt a pa",
        "pfad-fehlt b pb",
    ]
    assert DriftErgebnis([], []).fehlend == []
    assert drift([Eintrag(1, "x")], {}).fehlend == []


# ---------------------------------------------------------------- CLI

def test_cli_ohne_argumente_prueft_nur_eintraege_mit_pfad(tmp_path):
    _code(tmp_path / "proj")
    _code(tmp_path / "wiki2", "x.py", "port = 4242\n")
    _toml(tmp_path, [{"port": 8000, "projekt": "wiki", "pfad": "proj"},
                     {"port": 8001, "projekt": "wiki2"}])
    r = _cli(tmp_path, "drift")
    assert r.returncode == 1, r.stderr
    assert r.stdout.splitlines() == [
        "unbekannt 9000 wiki wiki/a.py:1",
        "abweichend wiki LISTE=8000 CODE=9000 wiki/a.py:1",
    ]
    assert r.stderr == ""


def test_cli_ohne_argumente_kein_pfad_kein_drift(tmp_path):
    _toml(tmp_path, [{"port": 8000, "projekt": "wiki"}])
    r = _cli(tmp_path, "drift")
    assert (r.returncode, r.stdout) == (0, "kein Drift\n")


def test_cli_ohne_argumente_fehlende_liste_exit2(tmp_path):
    r = _cli(tmp_path, "drift")
    assert r.returncode == 2
    assert r.stdout == "" and r.stderr.startswith("Fehler: ")


def test_cli_pfad_fehlt_nur_exit1_und_text_wie_in_liste(tmp_path):
    _code(tmp_path / "gut", "a.py", "port = 8001\n")
    _toml(tmp_path, [{"port": 8000, "projekt": "weg", "pfad": "./nicht/da"},
                     {"port": 8001, "projekt": "gut", "pfad": "gut"}])
    r = _cli(tmp_path, "drift")
    assert r.returncode == 1
    assert r.stdout == "pfad-fehlt weg ./nicht/da\n"
    assert r.stderr == ""


def test_cli_pfad_ist_datei_exit1(tmp_path):
    (tmp_path / "datei.txt").write_text("port = 1")
    _toml(tmp_path, [{"port": 8000, "projekt": "p", "pfad": "datei.txt"}])
    r = _cli(tmp_path, "drift")
    assert (r.returncode, r.stdout) == (1, "pfad-fehlt p datei.txt\n")


def test_cli_widerspruch_exit2_ohne_stdout(tmp_path):
    _toml(tmp_path, [{"port": 8000, "projekt": "p", "pfad": "./a"},
                     {"port": 8001, "projekt": "p", "pfad": "a"},
                     {"port": 8002, "projekt": "p", "pfad": "b"}])
    r = _cli(tmp_path, "drift")
    assert r.returncode == 2
    assert r.stdout == ""
    assert r.stderr.strip() == "Fehler: Projekt p hat verschiedene Pfade: ./a, b"


def test_cli_widerspruch_und_fehlende_wurzel_meldet_wurzel(tmp_path):
    _toml(tmp_path, [{"port": 8000, "projekt": "p", "pfad": "a"},
                     {"port": 8001, "projekt": "p", "pfad": "b"}])
    r = _cli(tmp_path, "drift", "gibtsnicht")
    assert r.returncode == 2 and r.stdout == ""
    assert r.stderr.startswith("Fehler: Wurzelordner nicht gefunden")
    assert "verschiedene Pfade" not in r.stderr


def test_cli_wurzel_kein_ordner_exit2(tmp_path):
    _toml(tmp_path, [])
    (tmp_path / "f").write_text("x")
    r = _cli(tmp_path, "drift", "f")
    assert r.returncode == 2 and r.stdout == ""
    assert r.stderr.startswith("Fehler: Wurzel ist kein Ordner")


def test_cli_wurzel_und_pfad_kombiniert(tmp_path):
    w = tmp_path / "w"
    _code(w / "fremd", "f.py", "port = 7777\n")
    _code(tmp_path / "echt", "e.py", "port = 8000\n")
    _toml(tmp_path, [{"port": 8000, "projekt": "mit", "pfad": "echt"},
                     {"port": 8001, "projekt": "weg", "pfad": "nein"}])
    r = _cli(tmp_path, "drift", "w")
    assert r.returncode == 1
    assert r.stdout.splitlines() == [
        "unbekannt 7777 fremd fremd/f.py:1",
        "pfad-fehlt weg nein",
    ]


def test_cli_relativer_pfad_gilt_ab_ordner_der_liste(tmp_path):
    _code(tmp_path / "code" / "wiki")
    _toml(tmp_path, [{"port": 8000, "projekt": "wiki", "pfad": "../code/wiki"}],
          name="liste/p.toml")
    r = _cli(tmp_path, "drift", "--datei", "liste/p.toml")
    assert r.returncode == 1, r.stderr
    assert r.stdout.splitlines() == [
        "unbekannt 9000 wiki wiki/a.py:1",
        "abweichend wiki LISTE=8000 CODE=9000 wiki/a.py:1",
    ]


@pytest.mark.parametrize("wert", [5, "", "  "])
def test_alle_befehle_ungueltiges_pfad_exit2(tmp_path, wert):
    _toml(tmp_path, [{"port": 8000, "projekt": "p", "pfad": wert}])
    (tmp_path / "n.txt").write_text("")
    for args in (["pruefen"], ["abgleich", "--netstat-datei", "n.txt"],
                 ["frei", "8000-8010", "--netstat-datei", "n.txt"], ["drift"]):
        r = _cli(tmp_path, *args)
        assert r.returncode == 2, (args, r.stdout, r.stderr)
        assert r.stdout == "" and r.stderr.startswith("Fehler: "), args


def test_pruefen_abgleich_frei_ignorieren_fehlende_und_widerspruechliche_pfade(tmp_path):
    mit = tmp_path / "mit"
    ohne = tmp_path / "ohne"
    for d in (mit, ohne):
        d.mkdir()
    basis = [{"port": 8000, "projekt": "a"}, {"port": 8000, "projekt": "b"},
             {"port": 8001, "projekt": "a"}, {"port": 8002, "projekt": "c"}]
    pfade = ["/gibt/es/nicht", "x", "y", "z"]
    _toml(ohne, basis)
    _toml(mit, [dict(e, pfad=p) for e, p in zip(basis, pfade)])
    netstat = ("  TCP    0.0.0.0:8001    0.0.0.0:0    LISTENING    1234\n"
               "  TCP    0.0.0.0:8003    0.0.0.0:0    LISTENING    1235\n")
    for d in (mit, ohne):
        (d / "n.txt").write_text(netstat)
    for args in (["pruefen"], ["abgleich", "--netstat-datei", "n.txt"],
                 ["abgleich", "--alle", "--netstat-datei", "n.txt"],
                 ["frei", "8000-8010", "--anzahl", "3", "--netstat-datei", "n.txt"]):
        a, b = _cli(mit, *args), _cli(ohne, *args)
        assert (a.returncode, a.stdout, a.stderr) == (b.returncode, b.stdout, b.stderr), args
        assert a.stdout != ""
