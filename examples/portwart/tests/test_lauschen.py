import subprocess
from types import SimpleNamespace

import pytest

from portwart import lauschen
from portwart.lauschen import LauschFehler, lies_netstat


def test_windows_nutzt_systemroot_ohne_path(monkeypatch, tmp_path):
    system32 = tmp_path / "System32"
    system32.mkdir()
    exe = system32 / "netstat.exe"
    exe.write_bytes(b"")
    monkeypatch.setattr(lauschen.os, "name", "nt")
    monkeypatch.setenv("SystemRoot", str(tmp_path))

    def verboten(*a, **k):
        raise AssertionError("PATH-Suche verboten")

    monkeypatch.setattr(lauschen.shutil, "which", verboten)
    aufrufe = []

    def fake_run(cmd, **kw):
        aufrufe.append(cmd)
        return SimpleNamespace(returncode=0, stdout="TCP 0.0.0.0:1 0.0.0.0:0 X".encode())

    monkeypatch.setattr(lauschen.subprocess, "run", fake_run)
    assert "TCP" in lies_netstat()
    assert aufrufe == [[str(exe), "-an"]]


def test_windows_datei_fehlt(monkeypatch, tmp_path):
    monkeypatch.setattr(lauschen.os, "name", "nt")
    monkeypatch.setenv("SystemRoot", str(tmp_path))
    monkeypatch.setattr(lauschen.shutil, "which", lambda n: "netstat.bat")
    with pytest.raises(LauschFehler):
        lies_netstat()


def test_windows_standard_systemroot(monkeypatch):
    monkeypatch.setattr(lauschen.os, "name", "nt")
    monkeypatch.delenv("SystemRoot", raising=False)
    monkeypatch.setattr(lauschen.Path, "is_file", lambda self: True)
    pfad = lauschen._programm().replace(chr(92), "/").lower()
    assert pfad == "c:/windows/system32/netstat.exe"


def test_posix_which(monkeypatch):
    monkeypatch.setattr(lauschen.os, "name", "posix")
    monkeypatch.setattr(lauschen.shutil, "which", lambda n: "/bin/netstat")
    assert lauschen._programm() == "/bin/netstat"


def test_posix_fehlt(monkeypatch):
    monkeypatch.setattr(lauschen.os, "name", "posix")
    monkeypatch.setattr(lauschen.shutil, "which", lambda n: None)
    with pytest.raises(LauschFehler):
        lies_netstat()


def _posix(monkeypatch, run):
    monkeypatch.setattr(lauschen.os, "name", "posix")
    monkeypatch.setattr(lauschen.shutil, "which", lambda n: "/bin/netstat")
    monkeypatch.setattr(lauschen.subprocess, "run", run)


def test_rueckgabecode(monkeypatch):
    _posix(monkeypatch, lambda c, **k: SimpleNamespace(returncode=1, stdout=b""))
    with pytest.raises(LauschFehler):
        lies_netstat()


def test_oserror(monkeypatch):
    def run(c, **k):
        raise OSError("kaputt")

    _posix(monkeypatch, run)
    with pytest.raises(LauschFehler):
        lies_netstat()


def test_dekodiert_mit_replace(monkeypatch):
    _posix(monkeypatch, lambda c, **k: SimpleNamespace(returncode=0, stdout=b"ABH\xd6REN"))
    assert lies_netstat() == "ABH\ufffdREN"


def test_fehler_ist_runtimeerror():
    assert issubclass(LauschFehler, RuntimeError)
