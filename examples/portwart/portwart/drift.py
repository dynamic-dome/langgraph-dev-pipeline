"""Port-Angaben im Code finden und mit der Liste vergleichen (nur lesend)."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path


class DriftFehler(ValueError):
    """Der Wurzelordner fehlt, ist kein Ordner oder nicht lesbar,
    oder ein Projekt hat verschiedene Pfade."""


@dataclass(frozen=True)
class Fund:
    port: int
    datei: str
    zeile: int


@dataclass(frozen=True)
class Unbekannt:
    port: int
    projekt: str
    datei: str
    zeile: int


@dataclass(frozen=True)
class Abweichung:
    projekt: str
    liste: list[int]
    code: list[int]
    datei: str
    zeile: int


@dataclass(frozen=True)
class PfadFehlt:
    projekt: str
    pfad: str


@dataclass(frozen=True)
class Durchsuchung:
    funde: dict[str, list[Fund]]
    fehlend: list[PfadFehlt]


@dataclass(frozen=True)
class DriftErgebnis:
    unbekannt: list[Unbekannt]
    abweichend: list[Abweichung]
    fehlend: list[PfadFehlt] = field(default_factory=list)


_ZAHL = r"([1-9][0-9]*)(?!\w)(?!\.\d)"
_MUSTER = [
    re.compile(
        r"(?<!\w)(?:[^\W_]+_)*port[\"']?[ \t]*[=:][ \t]*[\"']?"
        + _ZAHL,
        re.IGNORECASE,
    ),
    re.compile(r"--port(?:=|[ \t]+)" + _ZAHL, re.IGNORECASE),
    re.compile(
        r"(?<![\w.])(?:localhost|127\.0\.0\.1|0\.0\.0\.0):" + _ZAHL,
        re.IGNORECASE,
    ),
    re.compile(r"://[^\s/:@]+:" + _ZAHL, re.IGNORECASE),
]

_AUSGESCHLOSSEN = {
    ".git", "node_modules", ".venv", "__pycache__", "dist", "build",
    "arbeit", ".pytest_cache",
}
_MAX_BYTES = 1_048_576


def finde_ports(text: str) -> list[tuple[int, int]]:
    treffer: set[tuple[int, int]] = set()
    for nr, zeile in enumerate(re.split(r"\r\n|\r|\n", text), 1):
        for muster in _MUSTER:
            for m in muster.finditer(zeile):
                ziffern = m.group(1)
                if len(ziffern) <= 5 and 1 <= int(ziffern) <= 65535:
                    treffer.add((nr, int(ziffern)))
    return sorted(treffer)


def _lies(pfad: str) -> str | None:
    try:
        if os.stat(pfad).st_size > _MAX_BYTES:
            return None
        with open(pfad, "rb") as f:
            roh = f.read(_MAX_BYTES + 1)
    except OSError:
        return None
    if len(roh) > _MAX_BYTES or b"\x00" in roh:
        return None
    try:
        return roh.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None


_AUSSCHLUSS_MELDUNG = "'ausschluss' muss eine Liste von nicht leeren Texten sein"


def normalisiere_ausschluss(eintrag: str) -> str:
    if not isinstance(eintrag, str) or not eintrag.strip():
        raise DriftFehler(_AUSSCHLUSS_MELDUNG)
    text = eintrag.replace("\\", "/")
    # Vertrag: ein führendes "./" wird genau einmal entfernt. Bei mehreren
    # führenden "./" ist die Funktion deshalb bewusst nicht idempotent.
    if text.startswith("./"):
        text = text[2:]
    text = text.rstrip("/")
    if not text.strip():
        raise DriftFehler(_AUSSCHLUSS_MELDUNG)
    return text


def _durchlaufe(ordner: str, praefix: str, funde: list[Fund],
                namen=frozenset(), pfade_aus=frozenset(), rel_ordner: str = "") -> None:
    try:
        with os.scandir(ordner) as it:
            eintraege = list(it)
    except OSError:
        return
    for e in eintraege:
        rel = f"{praefix}/{e.name}"
        try:
            ist_ordner = e.is_dir(follow_symlinks=False)
            ist_datei = not ist_ordner and e.is_file()
        except OSError:
            continue
        if ist_ordner:
            unter = f"{rel_ordner}/{e.name}" if rel_ordner else e.name
            if (e.name not in _AUSGESCHLOSSEN and e.name not in namen
                    and unter not in pfade_aus):
                _durchlaufe(e.path, rel, funde, namen, pfade_aus, unter)
        elif ist_datei:
            text = _lies(e.path)
            if text is None:
                continue
            for zeile, port in finde_ports(text):
                funde.append(Fund(port, rel, zeile))


def _pruefe_wurzel(wurzel) -> list:
    pfad = Path(wurzel)
    try:
        vorhanden = pfad.exists()
        ist_ordner = vorhanden and pfad.is_dir()
    except (OSError, ValueError) as e:
        raise DriftFehler(f"Wurzelordner nicht lesbar: {wurzel}: {e}") from None
    if not vorhanden:
        raise DriftFehler(f"Wurzelordner nicht gefunden: {wurzel}")
    if not ist_ordner:
        raise DriftFehler(f"Wurzel ist kein Ordner: {wurzel}")
    try:
        with os.scandir(pfad) as it:
            return list(it)
    except OSError as e:
        raise DriftFehler(f"Wurzelordner nicht lesbar: {wurzel}: {e}") from None


def _scanne_ordner(pfad: str, praefix: str, namen=frozenset(),
                   pfade_aus=frozenset()) -> list[Fund]:
    funde: list[Fund] = []
    _durchlaufe(pfad, praefix, funde, namen, pfade_aus)
    funde.sort(key=lambda f: (f.datei, f.zeile, f.port))
    return funde


def _scanne_wurzel(eintraege: list, ausgenommen=frozenset(), namen=frozenset(),
                   pfade_aus=frozenset()) -> dict[str, list[Fund]]:
    ergebnis: dict[str, list[Fund]] = {}
    for e in sorted(eintraege, key=lambda x: x.name):
        try:
            if not e.is_dir(follow_symlinks=False):
                continue
        except OSError:
            continue
        if e.name in _AUSGESCHLOSSEN or e.name in ausgenommen:
            continue
        if e.name in namen:
            continue
        ergebnis[e.name] = _scanne_ordner(e.path, e.name, namen, pfade_aus)
    return ergebnis


def durchsuche(wurzel) -> dict[str, list[Fund]]:
    return _scanne_wurzel(_pruefe_wurzel(wurzel))


def _aufloesen(text: str, basis) -> str:
    p = os.path.expanduser(text)
    if not os.path.isabs(p):
        p = os.path.join(os.fspath(basis), p)
    return os.path.normpath(p)


def durchsuche_liste(eintraege, basis, wurzel=None, ausschluss=()) -> Durchsuchung:
    normal = [normalisiere_ausschluss(a) for a in ausschluss]
    namen = frozenset(a for a in normal if "/" not in a)
    pfade_aus = frozenset(a for a in normal if "/" in a)
    wurzel_eintraege = _pruefe_wurzel(wurzel) if wurzel is not None else None
    pfade: dict[str, tuple[str, str]] = {}  # projekt -> (text, schluessel)
    for e in eintraege:
        if e.pfad is None:
            continue
        try:
            schluessel = os.path.normcase(_aufloesen(e.pfad, basis))
        except ValueError:
            schluessel = e.pfad
        if e.projekt not in pfade:
            pfade[e.projekt] = (e.pfad, schluessel)
        elif pfade[e.projekt][1] != schluessel:
            raise DriftFehler(
                f"Projekt {e.projekt} hat verschiedene Pfade: "
                f"{pfade[e.projekt][0]}, {e.pfad}"
            )
    funde: dict[str, list[Fund]] = {}
    fehlend: list[PfadFehlt] = []
    for projekt, (text, _) in pfade.items():
        try:
            ordner = _aufloesen(text, basis)
            if not os.path.isdir(ordner):
                raise OSError("kein Ordner")
            with os.scandir(ordner) as it:
                for _ in it:
                    pass
        except (OSError, ValueError):
            fehlend.append(PfadFehlt(projekt, text))
            continue
        funde[projekt] = _scanne_ordner(ordner, projekt, namen, pfade_aus)
    if wurzel_eintraege is not None:
        funde.update(_scanne_wurzel(wurzel_eintraege, set(pfade), namen, pfade_aus))
    fehlend.sort(key=lambda x: x.projekt)
    return Durchsuchung(funde, fehlend)


def drift(eintraege, funde: dict[str, list[Fund]], fehlend=()) -> DriftErgebnis:
    eintraege = list(eintraege)
    listenports = {e.port for e in eintraege}
    unbekannt = [
        Unbekannt(f.port, projekt, f.datei, f.zeile)
        for projekt, liste in funde.items()
        for f in liste
        if f.port not in listenports
    ]
    unbekannt.sort(key=lambda u: (u.port, u.projekt, u.datei, u.zeile))

    je_projekt: dict[str, set[int]] = {}
    for e in eintraege:
        je_projekt.setdefault(e.projekt, set()).add(e.port)
    abweichend = []
    for projekt in sorted(je_projekt):
        liste = funde.get(projekt)
        if not liste:
            continue
        ports = je_projekt[projekt]
        code = {f.port for f in liste}
        if ports & code:
            continue
        erste = min(liste, key=lambda f: (f.datei, f.zeile, f.port))
        abweichend.append(
            Abweichung(projekt, sorted(ports), sorted(code), erste.datei, erste.zeile)
        )
    return DriftErgebnis(
        unbekannt, abweichend, sorted(fehlend, key=lambda x: x.projekt)
    )


def zeilen(ergebnis: DriftErgebnis) -> list[str]:
    aus = [
        f"unbekannt {u.port} {u.projekt} {u.datei}:{u.zeile}"
        for u in ergebnis.unbekannt
    ]
    for a in ergebnis.abweichend:
        liste = ",".join(str(p) for p in a.liste)
        code = ",".join(str(p) for p in a.code)
        aus.append(f"abweichend {a.projekt} LISTE={liste} CODE={code} {a.datei}:{a.zeile}")
    for f in sorted(ergebnis.fehlend, key=lambda x: x.projekt):
        aus.append(f"pfad-fehlt {f.projekt} {f.pfad}")
    return aus
