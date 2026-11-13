"""Testlauf im Worktree: eigene Tests des Implementierers, danach getrennt die unabhängigen Akzeptanztests.

Die Akzeptanztests liegen außerhalb des Zielrepos (aufgaben/<repo>/<id>/). Sie werden frisch nach tests/_akzeptanz/
kopiert (was der Agent dort abgelegt hat, fliegt vorher raus) und danach wieder entfernt.

Zwei pytest-Läufe, weil der Worktree dem Agenten gehört:
1. Eigene Tests mit dem Testbefehl des Zielrepos, so wie der Agent sie kennt (seine conftest/pytest.ini gelten).
2. Akzeptanztests abgeschirmt: --noconftest, eine leere Konfiguration aus dem Temp-Ordner (-c), --rootdir fest.
   So kann keine conftest.py oder pytest.ini des Agenten Akzeptanztests abwählen oder umbiegen (Codex S1, Befund 1).
   Zusätzlich muss die Zahl der gesammelten Akzeptanztests stimmen: Sie wird vorher in einem leeren Ordner ohne
   jeden Code des Agenten ermittelt (_erwartete_anzahl). Akzeptanztests dürfen den Code des Ziels deshalb erst
   in den Testfunktionen importieren, nicht oben im Modul.
Gezählt wird aus dem JUnit-XML, und die Exit-Codes beider Läufe zählen mit (Codex S1, Befund 2).
Ab Stufe 2 laufen die Akzeptanztests aller bisherigen Aufgaben mit (Regression): akzeptanz_dirs ist eine Liste.
"""
import os
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from entwicklung.worktree import AKZEPTANZ_ORDNER

AUSZUG_ZEILEN = 20  # je Lauf


def _leer() -> dict:
    return {"gesammelt": 0, "bestanden": 0, "fehlgeschlagen": 0, "fehler": 0, "uebersprungen": 0}


def _zaehle(junit: Path) -> dict:
    """Zahlen aus dem JUnit-XML, dazu die Skip-Gründe (Stufe 7: nur `plattform: …` gilt als dokumentiert)."""
    z = {**_leer(), "skip_gruende": []}
    if not junit.exists() or junit.stat().st_size == 0:
        z["fehler"] = 1
        return z
    for fall in ET.parse(junit).getroot().iter("testcase"):
        fehler = fall.find("error")
        if fehler is not None and fehler.get("message") == "collection failure":
            z["fehler"] += 1  # Modul ließ sich nicht sammeln: kein Test, aber ein Fehler
            continue
        z["gesammelt"] += 1
        if fall.find("failure") is not None:
            z["fehlgeschlagen"] += 1
        elif fehler is not None:
            z["fehler"] += 1
        elif fall.find("skipped") is not None:
            z["uebersprungen"] += 1
            z["skip_gruende"].append(fall.find("skipped").get("message") or "")
        else:
            z["bestanden"] += 1
    return z


def _umgebung() -> dict:
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
    # Testcode des Implementierers braucht keine Schlüssel der Agenten (Codex-Review Export SEC-003)
    for name in ("PYTEST_ADDOPTS", "PYTEST_PLUGINS", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        env.pop(name, None)
    return env


def _pytest(cmd: list[str], cwd: Path, timeout: int) -> tuple[int | None, str, dict]:
    """Ein pytest-Lauf mit JUnit-XML im Temp-Ordner. Kein .pytest_cache, kein __pycache__ im Worktree."""
    with tempfile.TemporaryDirectory(prefix="lab2-junit-") as tmp:
        junit = Path(tmp) / "junit.xml"
        try:
            lauf = subprocess.run([*cmd, "-p", "no:cacheprovider", f"--junitxml={junit}"], cwd=cwd,
                                  capture_output=True, text=True, encoding="utf-8", errors="replace",
                                  timeout=timeout, env=_umgebung())
        except subprocess.TimeoutExpired:
            return None, f"Timeout nach {timeout} s", {**_leer(), "fehler": 1}
        except OSError as e:
            return None, f"Testbefehl nicht startbar: {e}", {**_leer(), "fehler": 1}
        return lauf.returncode, (lauf.stdout or "") + (lauf.stderr or ""), _zaehle(junit)


def _abgeschirmt(python: str, rootdir: Path, ini: Path) -> list[str]:
    return [python, "-m", "pytest", "-q", "--noconftest", "-c", str(ini), f"--rootdir={rootdir}"]


def _akzeptanz_dateien(akzeptanz_dirs: list[Path]) -> list[Path]:
    """Alle Testdateien der Ordner; gleiche Dateinamen würden sich in tests/_akzeptanz überschreiben."""
    dateien, namen = [], {}
    for ordner in akzeptanz_dirs:
        for datei in sorted(ordner.glob("*.py")):
            if datei.name in namen:
                raise ValueError(f"Akzeptanztest {datei.name} doppelt: {namen[datei.name]} und {ordner}")
            namen[datei.name] = ordner
            dateien.append(datei)
    return dateien


def _erwartete_anzahl(akzeptanz_dirs: list[Path], konfig: dict, timeout: int) -> int | None:
    """Wie viele Akzeptanztests es geben muss, gesammelt ohne jeden Code des Agenten. None, wenn das scheitert."""
    with tempfile.TemporaryDirectory(prefix="lab2-erwartet-") as tmp:
        basis = Path(tmp)
        ziel = basis / AKZEPTANZ_ORDNER
        ziel.mkdir(parents=True)
        for datei in _akzeptanz_dateien(akzeptanz_dirs):
            shutil.copy2(datei, ziel / datei.name)
        ini = basis / "leer.ini"
        ini.write_text("[pytest]\n", encoding="utf-8")
        try:
            lauf = subprocess.run([*_abgeschirmt(konfig["python"], basis, ini), "--collect-only", "-p",
                                   "no:cacheprovider", AKZEPTANZ_ORDNER], cwd=basis, capture_output=True,
                                  text=True, encoding="utf-8", errors="replace", timeout=timeout, env=_umgebung())
        except (subprocess.TimeoutExpired, OSError):
            return None
        if lauf.returncode != 0:
            return None
        return sum(1 for zeile in lauf.stdout.splitlines() if "::" in zeile)


class AusserhalbFehler(ValueError):
    """tests/_akzeptanz zeigt über einen Verweis (Symlink, Junction) aus dem Worktree heraus."""


def _im_worktree(worktree: Path, ziel: Path) -> None:
    """Vor rmtree/mkdir: Kein Teil des Wegs darf ein Verweis sein, das Ziel muss im Worktree liegen
    (Codex-Review Export SEC-002: tests/ als Junction nach außen hätte rmtree dort ausgelöst)."""
    weg = worktree
    for teil in ziel.relative_to(worktree).parts:
        weg = weg / teil
        if weg.is_symlink() or (hasattr(weg, "is_junction") and weg.is_junction()):
            raise AusserhalbFehler(f"{weg} ist ein Verweis und führt außerhalb des Worktrees")
    if ziel.exists() and not ziel.resolve().is_relative_to(worktree.resolve()):
        raise AusserhalbFehler(f"{ziel} liegt außerhalb des Worktrees")


def _kopiere_akzeptanz(worktree: Path, akzeptanz_dirs: list[Path]) -> Path:
    ziel = worktree / AKZEPTANZ_ORDNER
    _im_worktree(worktree, ziel)
    dateien = _akzeptanz_dateien(akzeptanz_dirs)  # wirft vor jedem Kopieren, wenn ein Name doppelt ist
    if ziel.exists():
        shutil.rmtree(ziel)
    if dateien:
        ziel.mkdir(parents=True)
        for datei in dateien:
            shutil.copy2(datei, ziel / datei.name)
    return ziel


def _auszug(titel: str, ausgabe: str) -> str:
    return "\n".join([f"--- {titel} ---", *ausgabe.strip().splitlines()[-AUSZUG_ZEILEN:]])


def _abgelehnt(grund: str) -> dict:
    ergebnis = {**_leer(), "fehler": 1, "skip_gruende": []}
    ergebnis.update(akzeptanz={"gesammelt": 0, "bestanden": 0, "erwartet": None, "uebersprungen": 0, "fehler": 1},
                    rc={"eigene": None, "akzeptanz": None}, auszug=f"--- Testlauf abgelehnt ---\n{grund}", gruen=False)
    return ergebnis


def fuehre_tests_aus(worktree: Path, konfig: dict, akzeptanz_dirs: list[Path], timeout: int = 300) -> dict:
    _akzeptanz_dateien(akzeptanz_dirs)  # doppelte Namen vor jedem Lauf melden
    try:
        akzeptanz_ziel = _kopiere_akzeptanz(worktree, [])  # was der Agent dort abgelegt hat, fliegt raus
    except AusserhalbFehler as e:
        return _abgelehnt(str(e))
    rc_eigene, aus_eigene, eigene = _pytest([konfig["python"], *konfig["testbefehl"]], worktree, timeout)
    rc_akz, aus_akz, akz, erwartet = None, "keine Akzeptanztests", _leer(), None
    verweis = None  # ein Verweis, der erst beim Aufräumen auffällt, macht den Lauf trotzdem rot (Codex Runde 2)
    if akzeptanz_dirs:
        erwartet = _erwartete_anzahl(akzeptanz_dirs, konfig, timeout)
        try:
            try:
                _kopiere_akzeptanz(worktree, akzeptanz_dirs)
            except AusserhalbFehler as e:  # der Agent hat tests/ inzwischen umgebogen: nichts kopieren, nicht grün
                return _abgelehnt(str(e))
            with tempfile.TemporaryDirectory(prefix="lab2-ini-") as tmp:
                ini = Path(tmp) / "leer.ini"
                ini.write_text("[pytest]\n", encoding="utf-8")
                rc_akz, aus_akz, akz = _pytest([*_abgeschirmt(konfig["python"], worktree, ini), AKZEPTANZ_ORDNER],
                                               worktree, timeout)
        finally:
            try:  # auch beim Aufräumen nie durch einen Verweis hindurch löschen
                _im_worktree(worktree, akzeptanz_ziel)
                if akzeptanz_ziel.exists():
                    shutil.rmtree(akzeptanz_ziel)
            except AusserhalbFehler as e:
                verweis = str(e)  # nicht löschen, den Verweis stehen lassen, den Lauf unten ablehnen
    if verweis:
        return _abgelehnt(verweis)
    ergebnis = {schluessel: eigene[schluessel] + akz[schluessel] for schluessel in _leer()}
    ergebnis["skip_gruende"] = eigene.get("skip_gruende", []) + akz.get("skip_gruende", [])
    ergebnis["akzeptanz"] = {"gesammelt": akz["gesammelt"], "bestanden": akz["bestanden"], "erwartet": erwartet,
                             "uebersprungen": akz["uebersprungen"], "fehler": akz["fehler"]}
    ergebnis["rc"] = {"eigene": rc_eigene, "akzeptanz": rc_akz}
    ergebnis["auszug"] = _auszug("eigene Tests", aus_eigene) + "\n" + _auszug("Akzeptanztests", aus_akz)
    ergebnis["gruen"] = (eigene["gesammelt"] > 0 and rc_eigene == 0 and rc_akz == 0
                         and ergebnis["fehlgeschlagen"] == 0 and ergebnis["fehler"] == 0
                         and erwartet is not None and akz["gesammelt"] == erwartet > 0
                         and akz["bestanden"] == akz["gesammelt"])
    return ergebnis
