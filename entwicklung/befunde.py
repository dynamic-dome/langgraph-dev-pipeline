"""Befunde sammeln: Prüferberichte durch einen Befund-Filter schicken, zusammenführen, bewerten.

Der Filter prüft jeden Befund an der Quelle (steht das Zitat wirklich im geprüften Commit?) und sortiert ihn in
Töpfe. Nur `candidates` (Zitat gefunden) mit Schwere blocker/major lösen eine Fix-Runde aus; dazu jeder Befund
des deterministischen Funktionsprüfers. Ab Stufe 3 entscheidet `fix_noetig`, ob es eine Fix-Runde gibt.
Ausnahme (Gate Stufe 3, 20.10.): Ein `major` von Clean Code allein löst nur aus, wenn ein zweiter Prüfer dieselbe
Stelle meldet. Sonst ist er `gebremst` und steht nur im Bericht (Schwere-Inflation, Lauf 20261019-225712).
Filter: fusion-harness, wenn es eingerichtet ist (lokal.toml oder ENTWICKLUNG_FUSION_HARNESS; nur als Subprozess,
nie verändert), sonst der eingebaute Filter `filtere_eingebaut`: Zitat im geprüften Commit (Leerraum egal),
Pfad im Diff, Schwere. Welcher Filter lief, steht als `befund_filter` im Ergebnis und im Bericht.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from entwicklung import lokal
TOEPFE = ("candidates", "quote_missing", "speculation", "side", "out_of_scope")
REIHENFOLGE = {"deterministisch": 0, **{t: i + 1 for i, t in enumerate(TOEPFE)}}
SCHWERE = {"blocker": 0, "major": 1, "minor": 2}
NAHE = 3  # Zeilen Abstand, die noch als „dieselbe Stelle“ gelten (die Prüfer zeigen selten auf dieselbe Zeile)
BELEGT = ("candidates", "side")  # Töpfe, deren Zitat im Code gefunden wurde


def filter_wahl() -> tuple[Path | None, str]:
    """(Pfad zu fusion_harness.py oder None, Name für den Bericht)."""
    fh = lokal.einstellungen()["fusion_harness"]
    if fh is None:
        return None, "eingebaut (fusion-harness nicht eingerichtet)"
    if not fh.is_file():
        return None, f"eingebaut (fusion-harness nicht gefunden: {fh.name})"
    return fh, "fusion-harness"


def _norm(text: str) -> str:
    return " ".join(str(text).split())


def _inhalt(worktree: Path, rev: str, pfad: str) -> str | None:
    """Datei im geprüften Commit; None, wenn es sie dort nicht gibt. Hängt git, ist der Bericht nicht verwertbar."""
    try:
        lauf = subprocess.run([shutil.which("git") or "git", "show", f"{rev}:{pfad}"], cwd=worktree,
                              capture_output=True, timeout=60)
    except subprocess.TimeoutExpired:
        raise ValueError("eingebauter Filter: git show Timeout nach 60 s") from None
    except OSError as e:
        raise ValueError(f"eingebauter Filter: git nicht startbar: {e}") from None
    return lauf.stdout.decode("utf-8", errors="replace") if lauf.returncode == 0 else None


def filtere_eingebaut(bericht: dict, worktree: Path, rev: str, geaendert: list[str]) -> dict:
    """Einfacher Filter ohne fusion-harness. Kein Zitat im Commit → quote_missing; außerhalb des Diffs →
    out_of_scope; minor → side; sonst candidates. Spekulation erkennt er nicht (das kann fusion-harness)."""
    from entwicklung.pruefer import schema_ok
    if not schema_ok(bericht):
        raise ValueError("Bericht entspricht nicht dem Schema (eingebauter Filter)")
    toepfe = {t: [] for t in TOEPFE}
    for f in bericht["findings"]:
        inhalt = _inhalt(worktree, rev, f["path"])
        zitat = _norm(f["quote"])
        if not zitat or inhalt is None or zitat not in _norm(inhalt):
            toepfe["quote_missing"].append(f)
        elif geaendert and f["path"] not in geaendert:
            toepfe["out_of_scope"].append(f)
        elif f["severity"] == "minor":
            toepfe["side"].append(f)
        else:
            toepfe["candidates"].append(f)
    toepfe["not_checkable"] = list(bericht.get("not_checkable") or [])
    return toepfe


def filtere(bericht: dict, worktree: Path, rev: str, geaendert: list[str]) -> dict:
    fh, _ = filter_wahl()
    if fh is None:
        return filtere_eingebaut(bericht, worktree, rev, geaendert)
    with tempfile.TemporaryDirectory(prefix="lab2-befunde-") as tmp:
        datei = Path(tmp) / "bericht.json"
        datei.write_text(json.dumps(bericht, ensure_ascii=False), encoding="utf-8")
        cmd = [sys.executable, str(fh), "--json", "befunde", str(datei), "--repo", str(worktree),
               "--rev", rev]
        if geaendert:
            cmd += ["--changed", *geaendert]
        try:
            lauf = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                  timeout=120, env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        except subprocess.TimeoutExpired:
            raise ValueError("fusion-harness: Timeout nach 120 s") from None
        except OSError as e:
            raise ValueError(f"fusion-harness nicht startbar: {e}") from None
    if lauf.returncode == 4:
        raise ValueError("Bericht entspricht nicht dem Schema (fusion-harness rc 4)")
    zeilen = lauf.stdout.splitlines()
    if lauf.returncode not in (0, 2) or "{" not in zeilen:
        raise ValueError(f"fusion-harness ohne verwertbares Ergebnis (rc {lauf.returncode}): {lauf.stderr[:200]}")
    return json.loads("\n".join(zeilen[zeilen.index("{"):]))


def _eintrag(pruefer: str, topf: str, f: dict) -> dict:
    ausloesend = topf == "deterministisch" or (topf == "candidates" and f["severity"] in ("blocker", "major"))
    return {"pruefer": [pruefer], "topf": topf, "severity": f["severity"], "kind": f["kind"], "path": f["path"],
            "line": f["line"], "claim": f["claim"], "ausloesend": ausloesend}


def sammle(pruefberichte: list[dict], worktree: Path, rev: str, geaendert: list[str]) -> dict:
    eintraege: list[dict] = []
    nicht_verwertbar, nicht_pruefbar = [], []
    for p in pruefberichte:
        name = p["pruefer"]
        if not p.get("ok"):
            nicht_verwertbar.append({"pruefer": name, "fehler": p.get("fehler") or "unbekannt"})
            continue
        if name == "funktion":  # deterministisch, gezählt statt behauptet: kein Filter nötig
            eintraege += [_eintrag(name, "deterministisch", f) for f in p["bericht"]["findings"]]
            continue
        try:
            toepfe = filtere(p["bericht"], worktree, rev, geaendert)
        except ValueError as e:
            nicht_verwertbar.append({"pruefer": name, "fehler": str(e)})
            continue
        for topf in TOEPFE:
            eintraege += [_eintrag(name, topf, f) for f in toepfe.get(topf, [])]
        nicht_pruefbar += [{"pruefer": name, "was": n.get("what", "?"), "warum": n.get("why", "?")}
                           for n in toepfe.get("not_checkable", [])]
    befunde = _zusammenfuehren(_zweite_stimme(eintraege))
    befunde.sort(key=lambda b: (not b["ausloesend"], REIHENFOLGE[b["topf"]], SCHWERE.get(b["severity"], 9),
                                b["path"], b["line"]))
    return {"befunde": befunde, "nicht_verwertbar": nicht_verwertbar, "nicht_pruefbar": nicht_pruefbar,
            "fix_noetig": any(b["ausloesend"] for b in befunde), "befund_filter": filter_wahl()[1]}


def _stelle(e: dict) -> int | None:
    zeile = e.get("line")
    return zeile if isinstance(zeile, int) and not isinstance(zeile, bool) and zeile > 0 else None


def _zweite_stimme(eintraege: list[dict]) -> list[dict]:
    """Bremst ein major, das nur Clean Code meldet und kein anderer Modell-Prüfer an derselben Stelle bestätigt.

    Läuft auf den Rohbefunden, **vor** dem Zusammenführen: Dort hat jeder Eintrag genau einen Prüfer und seinen
    eigenen Topf. Nach dem Zusammenführen wüsste man nicht mehr, ob die zweite Stimme ein belegtes Zitat hatte.
    """
    stimmen = [e for e in eintraege if e["pruefer"][0] in ("security", "codex") and e["topf"] in BELEGT
               and _stelle(e) is not None]
    for e in eintraege:
        e["gebremst"] = False
        if e["pruefer"] != ["clean_code"] or e["topf"] != "candidates" or e["severity"] != "major":
            continue
        zeile = _stelle(e)
        e["gebremst"] = zeile is None or not any(
            s["path"] == e["path"] and abs(s["line"] - zeile) <= NAHE for s in stimmen)
        if e["gebremst"]:
            e["ausloesend"] = False
    return eintraege


def _zusammenfuehren(eintraege: list[dict]) -> list[dict]:
    """Gleicher Befund von mehreren Prüfern: einmal, mit allen Prüfern, im wichtigsten Topf."""
    nach_schluessel: dict[tuple, dict] = {}
    for e in eintraege:
        schluessel = (e["path"], e["line"], " ".join(e["claim"].lower().split()))
        alt = nach_schluessel.get(schluessel)
        if alt is None:
            nach_schluessel[schluessel] = e
            continue
        alt["pruefer"] = sorted(set(alt["pruefer"]) | set(e["pruefer"]))
        if (REIHENFOLGE[e["topf"]], SCHWERE.get(e["severity"], 9)) < (REIHENFOLGE[alt["topf"]],
                                                                       SCHWERE.get(alt["severity"], 9)):
            alt.update(topf=e["topf"], severity=e["severity"], kind=e["kind"])
        alt["ausloesend"] = alt["ausloesend"] or e["ausloesend"]
        alt["gebremst"] = (alt["gebremst"] or e["gebremst"]) and not alt["ausloesend"]
    return list(nach_schluessel.values())
