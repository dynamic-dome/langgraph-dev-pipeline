"""git-Worktrees für den Implementierer und die Nachkontrolle.

Der Implementierer arbeitet nur in einem eigenen Worktree unter arbeit/ (Branch lauf/<id>). Er selbst darf kein git;
die Pipeline sichert sein Ergebnis mit sichern() als Commit auf dem Lauf-Branch. Danach ist der Worktree sauber
und lässt sich ohne --force entfernen; der Branch bleibt als Sicherung stehen.

Die Nachkontrolle vergleicht stand() der geschützten Repos vor und nach dem Agentenaufruf. stand() nimmt den
Datei-Inhalt mit auf, damit auch eine zweite Änderung an einer schon geänderten Datei auffällt.
"""
import hashlib
import shutil
import subprocess
from pathlib import Path

from entwicklung import pfade

AKZEPTANZ_ORDNER = "tests/_akzeptanz"
PIPELINE_AUTOR = ["-c", "user.name=entwicklung-pipeline", "-c", "user.email=pipeline@langgraph-lab-2.local"]


class WorktreeFehler(RuntimeError):
    """Ein git-Schritt für den Worktree ist gescheitert."""


def _git(cwd: Path, *args: str, pruefen: bool = True) -> subprocess.CompletedProcess:
    exe = shutil.which("git")
    if not exe:
        raise WorktreeFehler("git nicht gefunden")
    lauf = subprocess.run([exe, *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace")
    if pruefen and lauf.returncode != 0:
        raise WorktreeFehler(f"git {' '.join(args)}: {lauf.stderr.strip()[:300]}")
    return lauf


def _branch_existiert(repo: Path, branch: str) -> bool:
    return _git(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}", pruefen=False).returncode == 0


def anlegen(repo: Path, lauf_id: str) -> Path:
    """Neuer Worktree <arbeit>/<repo>-<lauf_id> auf Branch lauf/<lauf_id>. Gibt es beides schon: Suffix -2, -3 …"""
    basis = pfade.arbeit_dir()
    kennung, n = lauf_id, 1
    while (basis / f"{repo.name}-{kennung}").exists() or _branch_existiert(repo, f"lauf/{kennung}"):
        n += 1
        kennung = f"{lauf_id}-{n}"
    ziel = pfade.pruefe_schreibziel(basis / f"{repo.name}-{kennung}")
    _git(repo, "worktree", "add", "-q", "-b", f"lauf/{kennung}", str(ziel))
    return ziel


def _status_eintraege(repo: Path) -> list[tuple[str, str]]:
    """(XY, Pfad) aus git status -z; Umbenennungen liefern nur den neuen Pfad."""
    roh = _git(repo, "status", "--porcelain=v1", "-uall", "-z").stdout
    teile = roh.split("\0")
    eintraege, i = [], 0
    while i < len(teile):
        teil = teile[i]
        i += 1
        if not teil:
            continue
        xy, pfad = teil[:2], teil[3:]
        if "R" in xy or "C" in xy:
            i += 1  # der nächste Teil ist der alte Pfad
        eintraege.append((xy, pfad))
    return eintraege


def _inhalt(datei: Path) -> str:
    return hashlib.sha1(datei.read_bytes()).hexdigest()[:12] if datei.is_file() else "-"


def stand(repo: Path) -> list[str]:
    """Sortierte Zeilen 'XY<TAB>pfad<TAB>inhalt' aller nicht ignorierten Änderungen."""
    return sorted(f"{xy}\t{pfad}\t{_inhalt(repo / pfad)}" for xy, pfad in _status_eintraege(repo))


def geaenderte_dateien(worktree: Path) -> list[str]:
    """Vom Implementierer geänderte Pfade (relativ, sortiert), ohne die hineinkopierten Akzeptanztests."""
    return sorted(p for _, p in _status_eintraege(worktree) if not p.startswith(AKZEPTANZ_ORDNER + "/"))


def _ist_cache(pfad: str) -> bool:
    teile = pfad.split("/")
    return "__pycache__" in teile or ".pytest_cache" in teile or pfad.endswith(".pyc")


def versteckte_dateien(worktree: Path) -> list[str]:
    """Ignorierte Dateien außer Caches. Der Agent darf .gitignore ändern; was er so versteckt, sichert sichern()
    nicht mit, und git worktree remove würde es ohne Rückfrage löschen."""
    roh = _git(worktree, "status", "--porcelain=v1", "--ignored", "-uall", "-z").stdout
    return sorted(e[3:] for e in roh.split("\0") if e.startswith("!! ") and not _ist_cache(e[3:]))


def grenzverletzungen(vorher: dict[str, list[str]], nachher: dict[str, list[str]]) -> list[str]:
    """Ein Satz je Pfad, der sich in einem geschützten Repo zwischen vorher und nachher verändert hat."""
    saetze = []
    for name in sorted(set(vorher) | set(nachher)):
        alt = {z.split("\t")[1]: z for z in vorher.get(name, [])}
        neu = {z.split("\t")[1]: z for z in nachher.get(name, [])}
        for pfad in sorted(set(alt) | set(neu)):
            if alt.get(pfad) == neu.get(pfad):
                continue
            art = "neu oder verändert" if pfad in neu else "zurückgesetzt oder gelöscht"
            saetze.append(f"{name}: {pfad} {art}")
    return saetze


def sichern(worktree: Path, nachricht: str) -> str | None:
    """Committet die Arbeit des Implementierers auf dem Lauf-Branch. None, wenn es nichts zu sichern gibt."""
    dateien = geaenderte_dateien(worktree)
    if not dateien:
        return None
    _git(worktree, "add", "-A", "--", *dateien)
    _git(worktree, *PIPELINE_AUTOR, "commit", "-q", "--no-verify", "-m", nachricht)
    return _git(worktree, "rev-parse", "HEAD").stdout.strip()


def kopf(worktree: Path) -> str:
    return _git(worktree, "rev-parse", "HEAD").stdout.strip()


def dateien_seit(worktree: Path, basis: str) -> list[str]:
    """Alle Pfade, die der Lauf seit basis geändert hat (über alle gesicherten Runden)."""
    namen = _git(worktree, "diff", "--name-only", "-z", basis, "HEAD").stdout.split("\0")
    return sorted(n for n in namen if n and not n.startswith(AKZEPTANZ_ORDNER + "/"))


def diff(worktree: Path, basis: str, ziel: str) -> str:
    """Was der Lauf geändert hat, als Text für die Prüfer."""
    return _git(worktree, "diff", f"{basis}..{ziel}").stdout


def exportiere(worktree: Path, ziel: Path) -> Path:
    """Committeter Stand (HEAD) als Kopie ohne git, z. B. für die Probe der erzeugten Tests: Was dort läuft und
    schreibt, landet nie im Worktree des Implementierers."""
    import io
    import zipfile
    roh = subprocess.run([shutil.which("git") or "git", "archive", "--format=zip", "HEAD"], cwd=worktree,
                         capture_output=True, check=True).stdout
    ziel.mkdir(parents=True, exist_ok=True)
    zipfile.ZipFile(io.BytesIO(roh)).extractall(ziel)
    return ziel


def entfernen(repo: Path, worktree: Path) -> None:
    """git worktree remove ohne --force: ungesicherte Arbeit lässt git den Abbau verweigern. Branch bleibt."""
    aufgeloest = worktree.resolve()
    if pfade.arbeit_dir() not in aufgeloest.parents:
        raise WorktreeFehler(f"{aufgeloest} liegt nicht unter {pfade.arbeit_dir()}")
    versteckt = versteckte_dateien(aufgeloest)
    if versteckt:
        raise WorktreeFehler(f"ungesicherte, per .gitignore versteckte Dateien: {', '.join(versteckt[:5])}")
    _git(repo, "worktree", "remove", str(aufgeloest))


def zweig(repo: Path) -> str:
    """Aktuell ausgecheckter Zweig ("" bei losgelöstem HEAD)."""
    return _git(repo, "branch", "--show-current").stdout.strip()


def merge_ff(repo: Path, branch: str, basis: str, zweig_beim_start: str, erwartet: str | None = None) -> str:
    """Lokaler Fast-Forward von branch in den Hauptzweig (Stufe 7). Gibt den neuen HEAD zurück.

    Nur, wenn das Ziel-Repo noch so dasteht wie beim Start: derselbe Zweig, sauber, HEAD == basis. Dann ist der
    gemergte Stand genau der geprüfte, und ein zweiter Testlauf entfällt. `erwartet`: der geprüfte Commit; steht der
    Branch inzwischen woanders, wird nicht gemergt (Codex-Verifier S7-01). Gemergt wird der Commit, nicht der Name.
    Sonst WorktreeFehler mit Grund, und das Repo bleibt unverändert. Kein Merge-Commit, kein Rebase, kein --force,
    kein Push."""
    schmutzig = stand(repo)
    if schmutzig:
        raise WorktreeFehler("Ziel-Repo nicht sauber: " + ", ".join(z.split("\t")[1] for z in schmutzig[:5]))
    jetzt = zweig(repo)
    if jetzt != zweig_beim_start:
        raise WorktreeFehler(f"anderer Zweig ausgecheckt: {jetzt or '(kein Zweig)'} statt {zweig_beim_start}")
    kopf_jetzt = kopf(repo)
    if kopf_jetzt != basis:
        raise WorktreeFehler(f"Hauptzweig ist weitergelaufen (HEAD {kopf_jetzt[:7]} statt Basis {basis[:7]})")
    ziel = _git(repo, "rev-parse", "--verify", f"refs/heads/{branch}").stdout.strip()
    if erwartet and ziel != erwartet:
        raise WorktreeFehler(f"Lauf-Branch hat sich seit der Prüfung geändert ({ziel[:7]} statt {erwartet[:7]})")
    _git(repo, "merge", "--ff-only", "-q", ziel)
    return kopf(repo)


def branch_loeschen(repo: Path, branch: str) -> None:
    """git branch -d (nie -D): git verweigert das Löschen, wenn der Branch nicht gemergt ist."""
    _git(repo, "branch", "-d", branch)


def name_status(worktree: Path, basis: str) -> str:
    """git diff --name-status basis..HEAD (für die Tür-Bewertung, Stufe 7)."""
    return _git(worktree, "diff", "--name-status", basis, "HEAD").stdout


def diffstat(worktree: Path, basis: str) -> str:
    return _git(worktree, "diff", "--stat", basis, "HEAD").stdout
