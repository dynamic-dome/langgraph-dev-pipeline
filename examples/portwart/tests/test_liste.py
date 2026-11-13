import subprocess
import sys
from pathlib import Path

import pytest

from portwart.liste import Eintrag, ListenFehler, doppelte, lade

ROOT = Path(__file__).resolve().parent.parent


def schreibe(tmp_path, text):
    p = tmp_path / "p.toml"
    p.write_text(text, encoding="utf-8")
    return p


def test_lade_ok(tmp_path):
    p = schreibe(tmp_path, '[[port]]\nport=1\nprojekt="a"\n[[port]]\nport=65535\nprojekt="b"\nzweck="x"\n')
    assert lade(str(p)) == [Eintrag(1, "a", ""), Eintrag(65535, "b", "x")]


def test_leer(tmp_path):
    assert lade(schreibe(tmp_path, "")) == []


@pytest.mark.parametrize("text", [
    "[[port]\n", '[[port]]\nprojekt="a"\n', "[[port]]\nport=1\n",
    '[[port]]\nport=true\nprojekt="a"\n', '[[port]]\nport="1"\nprojekt="a"\n',
    '[[port]]\nport=0\nprojekt="a"\n', '[[port]]\nport=65536\nprojekt="a"\n',
    '[[port]]\nport=1\nprojekt=""\n',
])
def test_fehler(tmp_path, text):
    with pytest.raises(ListenFehler):
        lade(schreibe(tmp_path, text))


def test_fehlt(tmp_path):
    with pytest.raises(ListenFehler):
        lade(tmp_path / "nix.toml")


def test_doppelte():
    e = [Eintrag(1, "b", ""), Eintrag(1, "a", ""), Eintrag(2, "a", ""), Eintrag(2, "a", "")]
    assert doppelte(e) == {1: ["a", "b"]}


def cli(*args):
    return subprocess.run([sys.executable, "-m", "portwart", *args], cwd=ROOT,
                          capture_output=True, text=True)


def test_cli_kollision():
    r = cli("pruefen")
    assert r.returncode == 1
    assert r.stdout.strip() == "Port 8080 doppelt: bildarchiv, dashboard"  # Beispielliste in examples/


def test_cli_ok(tmp_path):
    r = cli("pruefen", "--datei", str(schreibe(tmp_path, "")))
    assert (r.returncode, r.stdout.strip()) == (0, "keine doppelten Ports")


def test_cli_fehler(tmp_path):
    r = cli("pruefen", "--datei", str(tmp_path / "nix"))
    assert r.returncode == 2 and r.stdout == "" and r.stderr.startswith("Fehler: ")
