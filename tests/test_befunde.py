import shutil
import subprocess

import pytest

from entwicklung import befunde, pruefer

GIT = shutil.which("git")


def _git(cwd, *args):
    return subprocess.run([GIT, *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", check=True).stdout


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "wt"
    r.mkdir()
    _git(r, "init", "-q")
    (r / "a.py").write_text("def lies(name):\n    return open('/daten/' + name).read()\n", encoding="utf-8")
    (r / "b.py").write_text("X = 1\n", encoding="utf-8")
    _git(r, "-c", "user.name=t", "-c", "user.email=t@t", "add", "a.py", "b.py")
    _git(r, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "init")
    return r, _git(r, "rev-parse", "HEAD").strip()


def _befund(**kw):
    b = {"id": "F1", "severity": "major", "kind": "security", "path": "a.py", "line": 2,
         "claim": "Pfad wird ungeprüft verkettet", "quote": "return open('/daten/' + name).read()",
         "check": "gelesen", "status": "read-only"}
    b.update(kw)
    return b


def _pruefer(name, *funde, ok=True, fehler=None):
    bericht = {"verdict": "FAIL" if funde else "PASS", "findings": list(funde), "not_checkable": []}
    return {"pruefer": name, "ok": ok, "bericht": bericht if ok else None, "fehler": fehler, "dauer_s": 1.0}


GRUEN = {"gesammelt": 5, "bestanden": 5, "fehlgeschlagen": 0, "fehler": 0, "uebersprungen": 0,
         "akzeptanz": {"gesammelt": 3, "bestanden": 3, "erwartet": 3}, "rc": {"eigene": 0, "akzeptanz": 0},
         "gruen": True, "auszug": ""}


def test_filtere_zitat_gefunden(repo):
    wt, rev = repo
    toepfe = befunde.filtere({"verdict": "FAIL", "findings": [_befund()], "not_checkable": []}, wt, rev, ["a.py"])
    assert [f["id"] for f in toepfe["candidates"]] == ["F1"]


def test_filtere_kaputter_bericht(repo):
    wt, rev = repo
    with pytest.raises(ValueError):
        befunde.filtere({"irgendwas": 1}, wt, rev, ["a.py"])


def test_zitat_mit_einrueckung_wird_gefunden(repo):
    wt, rev = repo
    erg = befunde.sammle([_pruefer("codex", _befund(quote="    return open('/daten/' + name).read()"))],
                         wt, rev, ["a.py"])
    assert erg["befunde"][0]["topf"] == "candidates" and erg["fix_noetig"] is True


def test_erfundenes_zitat_loest_nichts_aus(repo):
    wt, rev = repo
    erg = befunde.sammle([_pruefer("security", _befund(quote="os.system(eingabe)"))], wt, rev, ["a.py"])
    assert erg["befunde"][0]["topf"] == "quote_missing"
    assert erg["befunde"][0]["ausloesend"] is False
    assert erg["fix_noetig"] is False


def test_minor_ist_nebenbefund(repo):
    wt, rev = repo
    erg = befunde.sammle([_pruefer("clean_code", _befund(severity="minor"))], wt, rev, ["a.py"])
    assert erg["befunde"][0]["topf"] == "side" and erg["fix_noetig"] is False


def test_ausserhalb_des_diffs(repo):
    wt, rev = repo
    erg = befunde.sammle([_pruefer("security", _befund(path="b.py", quote="X = 1"))], wt, rev, ["a.py"])
    assert erg["befunde"][0]["topf"] == "out_of_scope" and erg["fix_noetig"] is False


def test_nicht_verwertbar(repo):
    wt, rev = repo
    erg = befunde.sammle([_pruefer("codex", ok=False, fehler="Timeout nach 900 s")], wt, rev, ["a.py"])
    assert erg["nicht_verwertbar"] == [{"pruefer": "codex", "fehler": "Timeout nach 900 s"}]
    assert erg["befunde"] == []


def test_filter_timeout_ist_nicht_verwertbar(repo, monkeypatch):
    wt, rev = repo

    def haengt(*a, **k):
        raise subprocess.TimeoutExpired(["fusion_harness"], 120)

    monkeypatch.setattr(befunde.subprocess, "run", haengt)
    erg = befunde.sammle([_pruefer("security", _befund())], wt, rev, ["a.py"])
    assert erg["nicht_verwertbar"][0]["pruefer"] == "security"
    assert "Timeout" in erg["nicht_verwertbar"][0]["fehler"]


def test_nicht_pruefbar_wird_gesammelt(repo):
    wt, rev = repo
    p = _pruefer("codex")
    p["bericht"]["not_checkable"] = [{"what": "Laufzeit", "why": "keine Prozesse", "need": "Sandbox"}]
    erg = befunde.sammle([p], wt, rev, ["a.py"])
    assert erg["nicht_pruefbar"] == [{"pruefer": "codex", "was": "Laufzeit", "warum": "keine Prozesse"}]


def test_dublette_ueber_pruefer(repo):
    wt, rev = repo
    erg = befunde.sammle([_pruefer("security", _befund()), _pruefer("codex", _befund(id="SEC-1"))],
                         wt, rev, ["a.py"])
    assert len(erg["befunde"]) == 1
    assert erg["befunde"][0]["pruefer"] == ["codex", "security"]


def test_funktion_rot_loest_aus_ohne_filter(repo):
    wt, rev = repo
    rot = {**GRUEN, "gruen": False, "fehlgeschlagen": 1, "bestanden": 4,
           "akzeptanz": {"gesammelt": 3, "bestanden": 2, "erwartet": 3}, "rc": {"eigene": 0, "akzeptanz": 1}}
    erg = befunde.sammle([pruefer.funktion_bericht(rot)], wt, rev, ["a.py"])
    assert erg["fix_noetig"] is True
    assert {b["topf"] for b in erg["befunde"]} == {"deterministisch"}
    assert all(b["pruefer"] == ["funktion"] for b in erg["befunde"])


def test_funktion_gruen_ohne_befunde(repo):
    wt, rev = repo
    erg = befunde.sammle([pruefer.funktion_bericht(GRUEN)], wt, rev, ["a.py"])
    erg.pop("befund_filter")  # welcher Filter lief, steht seit der öffentlichen Fassung mit im Ergebnis
    assert erg == {"befunde": [], "nicht_verwertbar": [], "nicht_pruefbar": [], "fix_noetig": False}


def test_ausloesende_zuerst(repo):
    wt, rev = repo
    erg = befunde.sammle([_pruefer("clean_code", _befund(severity="minor", claim="Name unklar")),
                          _pruefer("security", _befund())], wt, rev, ["a.py"])
    assert [b["ausloesend"] for b in erg["befunde"]] == [True, False]


# Fix-Regel seit dem Gate von Stufe 3 (20.10.): Ein major von Clean Code allein löst nicht aus (Schwere-Inflation,
# Lauf 20261019-225712). Es braucht eine zweite Stimme an derselben Stelle.

def _clean_major(**kw):
    return _befund(kind="bug", claim="main() ist schwer wartbar", **kw)


def test_clean_code_major_allein_loest_nicht_aus(repo):
    wt, rev = repo
    erg = befunde.sammle([_pruefer("clean_code", _clean_major())], wt, rev, ["a.py"])
    (b,) = erg["befunde"]
    assert b["topf"] == "candidates" and b["ausloesend"] is False and b["gebremst"] is True
    assert erg["fix_noetig"] is False


def test_clean_code_major_mit_zweiter_stimme_loest_aus(repo):
    wt, rev = repo
    erg = befunde.sammle([_pruefer("clean_code", _clean_major()),
                          _pruefer("codex", _befund(id="C1", severity="minor", line=1, claim="anderer Wortlaut",
                                                    quote="def lies(name):"))], wt, rev, ["a.py"])
    clean = next(b for b in erg["befunde"] if b["pruefer"] == ["clean_code"])
    assert clean["ausloesend"] is True and clean["gebremst"] is False and erg["fix_noetig"] is True


def test_zweite_stimme_in_anderer_datei_zaehlt_nicht(repo):
    wt, rev = repo
    erg = befunde.sammle([_pruefer("clean_code", _clean_major()),
                          _pruefer("codex", _befund(id="C1", severity="minor", path="b.py", line=1, quote="X = 1"))],
                         wt, rev, ["a.py", "b.py"])
    assert erg["fix_noetig"] is False


def test_clean_code_blocker_loest_allein_aus(repo):
    wt, rev = repo
    erg = befunde.sammle([_pruefer("clean_code", _clean_major(severity="blocker"))], wt, rev, ["a.py"])
    assert erg["fix_noetig"] is True and erg["befunde"][0]["gebremst"] is False


def test_security_major_allein_loest_aus(repo):
    wt, rev = repo
    erg = befunde.sammle([_pruefer("security", _befund())], wt, rev, ["a.py"])
    assert erg["fix_noetig"] is True


def test_bericht_zeigt_gebremst(repo):
    from entwicklung.bericht import befund_zeile
    wt, rev = repo
    (b,) = befunde.sammle([_pruefer("clean_code", _clean_major())], wt, rev, ["a.py"])["befunde"]
    assert "⚑" not in befund_zeile(b) and "nur Clean Code" in befund_zeile(b)


def test_dublette_ohne_belegtes_zitat_ist_keine_zweite_stimme(repo):
    """Codex F1: Security meldet denselben Wortlaut, aber ihr Zitat steht nicht im Code (quote_missing)."""
    wt, rev = repo
    erg = befunde.sammle([_pruefer("clean_code", _clean_major()),
                          _pruefer("security", _clean_major(id="S1", quote="gibt es nicht"))], wt, rev, ["a.py"])
    (b,) = erg["befunde"]
    assert b["pruefer"] == ["clean_code", "security"] and b["topf"] == "candidates"
    assert b["gebremst"] is True and erg["fix_noetig"] is False


def test_ungueltige_zeilen_bestaetigen_nicht_und_stuerzen_nicht(repo):
    """Codex F2: Zeile None darf keinen TypeError werfen, Zeile 0 ist keine Stelle."""
    wt, rev = repo
    ohne_zeile = {**_befund(id="T1", severity="blocker", kind="bug", claim="Tests rot"), "line": None}
    erg = befunde.sammle([_pruefer("funktion", ohne_zeile), _pruefer("security", _befund())], wt, rev, ["a.py"])
    assert erg["fix_noetig"] is True
    erg = befunde.sammle([_pruefer("clean_code", _clean_major(line=0)),
                          _pruefer("codex", _befund(id="C1", severity="minor", line=0, claim="anderer Wortlaut"))],
                         wt, rev, ["a.py"])
    assert all(not b["ausloesend"] for b in erg["befunde"])


def test_zweite_stimme_bleibt_trotz_dublette_mit_funktion(repo):
    """Codex F3: Die Codex-Stimme zählt, auch wenn ihr Befund mit einem Funktionsbefund zusammengeführt wird."""
    wt, rev = repo
    gleich = {"severity": "minor", "line": 1, "claim": "gleicher Wortlaut", "quote": "def lies(name):"}
    erg = befunde.sammle([_pruefer("clean_code", _clean_major()),
                          _pruefer("codex", _befund(id="C1", **gleich)),
                          _pruefer("funktion", _befund(id="T1", **gleich))], wt, rev, ["a.py"])
    clean = next(b for b in erg["befunde"] if b["pruefer"] == ["clean_code"])
    assert clean["gebremst"] is False and clean["ausloesend"] is True
