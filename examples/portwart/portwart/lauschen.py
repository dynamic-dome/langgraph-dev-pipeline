"""Auslesen der lauschenden TCP-Ports aus netstat."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


class LauschFehler(RuntimeError):
    """netstat fehlt oder lieferte einen Fehler."""


def lauschende_ports(netstat_text: str) -> set[int]:
    ports: set[int] = set()
    for zeile in netstat_text.splitlines():
        felder = zeile.split()
        if len(felder) < 3 or felder[0].upper() not in ("TCP", "TCPV6"):
            continue
        if not felder[2].endswith(":0"):
            continue
        nummer = felder[1].rsplit(":", 1)[-1]
        if nummer.isascii() and nummer.isdigit():
            ports.add(int(nummer))
    return ports


def _programm() -> str:
    if os.name == "nt":
        wurzel = os.environ.get("SystemRoot") or "C:\\Windows"
        pfad = Path(wurzel) / "System32" / "netstat.exe"
        if not pfad.is_file():
            raise LauschFehler(f"netstat nicht gefunden: {pfad}")
        return str(pfad)
    pfad = shutil.which("netstat")
    if not pfad:
        raise LauschFehler("netstat nicht gefunden")
    return pfad


def lies_netstat() -> str:
    programm = _programm()
    try:
        r = subprocess.run([programm, "-an"], capture_output=True, check=False)
    except OSError as e:
        raise LauschFehler(f"netstat nicht startbar: {e}") from None
    if r.returncode != 0:
        raise LauschFehler(f"netstat endete mit Code {r.returncode}")
    return r.stdout.decode(errors="replace")
