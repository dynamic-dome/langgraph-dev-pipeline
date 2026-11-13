"""Unabhängige Akzeptanztests für A1. Der Implementierer sieht sie nicht.

Die Pipeline kopiert diese Datei erst zum Testlauf nach <worktree>/tests/_akzeptanz/.
"""
import dataclasses
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _schreibe(tmp_path, text, name="ports.toml"):
    pfad = tmp_path / name
    pfad.write_text(text, encoding="utf-8")
    return pfad


def _cli(*args, cwd):
    env = dict(os.environ, PYTHONPATH=str(REPO), PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, "-m", "portwart", *args], cwd=cwd, env=env,
                          capture_output=True, text=True, encoding="utf-8", timeout=60)


ZWEI_DOPPELT = """
[[port]]
port = 8770
projekt = "tool-tracker"

[[port]]
port = 8766
projekt = "wiki-inselwelt"
zweck = "Inselwelt"

[[port]]
port = 8770
projekt = "job-radar"

[[port]]
port = 7171
projekt = "b"

[[port]]
port = 7171
projekt = "a"
"""


def test_lade_reihenfolge_und_felder(tmp_path):
    from portwart.liste import Eintrag, lade
    eintraege = lade(_schreibe(tmp_path, ZWEI_DOPPELT))
    assert [e.port for e in eintraege] == [8770, 8766, 8770, 7171, 7171]
    assert eintraege[1] == Eintrag(port=8766, projekt="wiki-inselwelt", zweck="Inselwelt")
    assert eintraege[0].zweck == ""


def test_eintrag_ist_frozen(tmp_path):
    from portwart.liste import lade
    e = lade(_schreibe(tmp_path, ZWEI_DOPPELT))[0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        e.port = 1


def test_lade_nimmt_str_pfad(tmp_path):
    from portwart.liste import lade
    assert len(lade(str(_schreibe(tmp_path, ZWEI_DOPPELT)))) == 5


def test_leere_datei_ergibt_leere_liste(tmp_path):
    from portwart.liste import lade
    assert lade(_schreibe(tmp_path, "# nur ein Kommentar\n")) == []


def test_doppelte(tmp_path):
    from portwart.liste import doppelte, lade
    assert doppelte(lade(_schreibe(tmp_path, ZWEI_DOPPELT))) == {
        7171: ["a", "b"], 8770: ["job-radar", "tool-tracker"]}


def test_gleiches_projekt_zweimal_ist_keine_kollision():
    from portwart.liste import Eintrag, doppelte
    assert doppelte([Eintrag(9000, "x", ""), Eintrag(9000, "x", "zweiter Zweck")]) == {}
    assert doppelte([Eintrag(9000, "x", ""), Eintrag(9000, "y", ""), Eintrag(9000, "x", "")]) == {9000: ["x", "y"]}


@pytest.mark.parametrize("text", [
    '[[port]]\nport = 0\nprojekt = "a"\n',
    '[[port]]\nport = 65536\nprojekt = "a"\n',
    '[[port]]\nport = "8080"\nprojekt = "a"\n',
    '[[port]]\nport = true\nprojekt = "a"\n',
    '[[port]]\nprojekt = "a"\n',
    '[[port]]\nport = 8080\n',
    '[[port]]\nport = 8080\nprojekt = ""\n',
    '[[port]\nport = 8080\n',
], ids=["null", "zu-gross", "text", "bool", "ohne-port", "ohne-projekt", "projekt-leer", "kaputt"])
def test_ungueltige_listen(tmp_path, text):
    from portwart.liste import ListenFehler, lade
    assert issubclass(ListenFehler, ValueError)
    with pytest.raises(ListenFehler):
        lade(_schreibe(tmp_path, text))


def test_fehlende_datei(tmp_path):
    from portwart.liste import ListenFehler, lade
    with pytest.raises(ListenFehler):
        lade(tmp_path / "gibt-es-nicht.toml")


def test_grenzwerte_erlaubt(tmp_path):
    from portwart.liste import lade
    text = '[[port]]\nport = 1\nprojekt = "a"\n\n[[port]]\nport = 65535\nprojekt = "b"\n'
    assert [e.port for e in lade(_schreibe(tmp_path, text))] == [1, 65535]


def test_cli_kollisionen(tmp_path):
    _schreibe(tmp_path, ZWEI_DOPPELT)
    r = _cli("pruefen", cwd=tmp_path)
    assert r.returncode == 1, r.stderr
    assert r.stdout.strip().splitlines() == [
        "Port 7171 doppelt: a, b", "Port 8770 doppelt: job-radar, tool-tracker"]


def test_cli_ohne_kollision(tmp_path):
    pfad = _schreibe(tmp_path, '[[port]]\nport = 8080\nprojekt = "a"\n', name="andere.toml")
    r = _cli("pruefen", "--datei", str(pfad), cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "keine doppelten Ports"


def test_cli_fehler(tmp_path):
    _schreibe(tmp_path, '[[port]]\nport = 0\nprojekt = "a"\n')
    r = _cli("pruefen", cwd=tmp_path)
    assert r.returncode == 2
    assert r.stderr.strip().startswith("Fehler: ")
    assert r.stdout.strip() == ""
