"""Freie Ports in einem Bereich finden."""
from __future__ import annotations


class BereichsFehler(ValueError):
    """Ungültiger Portbereich."""


def _zahl(text: str) -> int:
    text = text.strip()
    if not (text.isascii() and text.isdigit()):
        raise BereichsFehler(f"keine ganze Zahl: {text!r}")
    ziffern = text.lstrip("0")
    if len(ziffern) > 5:
        raise BereichsFehler(f"Port liegt außerhalb von 1-65535: {text[:12]!r}...")
    return int(ziffern or "0")


def _pruefe(von, bis) -> None:
    for n in (von, bis):
        if isinstance(n, bool) or not isinstance(n, int):
            raise BereichsFehler(f"Port muss eine ganze Zahl sein: {n!r}")
        if not 1 <= n <= 65535:
            raise BereichsFehler(f"Port {n} liegt außerhalb von 1-65535")
    if von > bis:
        raise BereichsFehler(f"Bereich verkehrt herum: {von}-{bis}")


def parse_bereich(text: str) -> tuple[int, int]:
    teile = text.strip().split("-")
    if len(teile) != 2:
        raise BereichsFehler(f"Bereich muss die Form VON-BIS haben: {text!r}")
    von, bis = _zahl(teile[0]), _zahl(teile[1])
    _pruefe(von, bis)
    return von, bis


def freie_ports(eintraege, lauschend, von: int, bis: int) -> list[int]:
    _pruefe(von, bis)
    belegt = {e.port for e in eintraege} | set(lauschend)
    return [p for p in range(von, bis + 1) if p not in belegt]
