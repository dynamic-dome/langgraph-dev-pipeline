"""Stufe 7, Task 1: Werkzeuge für den Abschluss (Fast-Forward-Merge, Übernahme der Akzeptanztests, Tür, Einwände)."""
import shutil
import subprocess
import sys

import pytest

from entwicklung import abschluss, testlauf, worktree

GIT = shutil.which("git")


def _git(cwd, *args):
    return subprocess.run([GIT, *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", check=True).stdout


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "zielrepo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    _git(r, "config", "user.email", "test@lab2")
    _git(r, "config", "user.name", "test")
    (r / "README.md").write_text("hallo\n", encoding="utf-8")
    _git(r, "add", "README.md")
    _git(r, "commit", "-q", "-m", "init")
    return r


@pytest.fixture
def lauf(repo):
    """Worktree mit einem gesicherten Commit auf lauf/x; gibt (worktree, basis, kopf) zurück."""
    wt = worktree.anlegen(repo, "x")
    basis = worktree.kopf(wt)
    (wt / "neu.py").write_text("x = 1\n", encoding="utf-8")
    kopf = worktree.sichern(wt, "lauf x")
    return wt, basis, kopf


def _kopf(repo):
    return _git(repo, "rev-parse", "HEAD").strip()


# ------------------------------------------------------------------------------------------ worktree.merge_ff


def test_zweig(repo):
    assert worktree.zweig(repo) == "main"


def test_merge_ff_fast_forward(repo, lauf):
    wt, basis, kopf = lauf
    assert worktree.merge_ff(repo, "lauf/x", basis, "main") == kopf
    assert _kopf(repo) == kopf
    assert (repo / "neu.py").read_text(encoding="utf-8") == "x = 1\n"
    assert worktree.stand(repo) == []


def test_merge_abgelehnt_bei_schmutzigem_repo(repo, lauf):
    wt, basis, _ = lauf
    (repo / "README.md").write_text("geändert\n", encoding="utf-8")
    vorher = worktree.stand(repo)
    with pytest.raises(worktree.WorktreeFehler, match="Ziel-Repo nicht sauber"):
        worktree.merge_ff(repo, "lauf/x", basis, "main")
    assert _kopf(repo) == basis and worktree.stand(repo) == vorher


def test_merge_abgelehnt_bei_anderem_zweig(repo, lauf):
    wt, basis, _ = lauf
    _git(repo, "switch", "-q", "-c", "nebenzweig")
    with pytest.raises(worktree.WorktreeFehler, match="anderer Zweig ausgecheckt: nebenzweig statt main"):
        worktree.merge_ff(repo, "lauf/x", basis, "main")
    assert _kopf(repo) == basis and worktree.stand(repo) == []


def test_merge_abgelehnt_wenn_main_weiter(repo, lauf):
    wt, basis, _ = lauf
    (repo / "anders.txt").write_text("weiter\n", encoding="utf-8")
    _git(repo, "add", "anders.txt")
    _git(repo, "commit", "-q", "-m", "main läuft weiter")
    weiter = _kopf(repo)
    with pytest.raises(worktree.WorktreeFehler, match="Hauptzweig ist weitergelaufen"):
        worktree.merge_ff(repo, "lauf/x", basis, "main")
    assert _kopf(repo) == weiter and worktree.stand(repo) == []


def test_branch_loeschen_nach_merge(repo, lauf):
    wt, basis, _ = lauf
    worktree.merge_ff(repo, "lauf/x", basis, "main")
    worktree.entfernen(repo, wt)
    worktree.branch_loeschen(repo, "lauf/x")
    assert _git(repo, "branch", "--list", "lauf/x").strip() == ""


def test_branch_loeschen_ungemergt_scheitert(repo, lauf):
    wt, _, _ = lauf
    worktree.entfernen(repo, wt)
    with pytest.raises(worktree.WorktreeFehler):
        worktree.branch_loeschen(repo, "lauf/x")  # -d, nie -D: ungemergte Arbeit bleibt
    assert _git(repo, "branch", "--list", "lauf/x").strip() != ""


# ------------------------------------------------------------------------------------------ Übernahme


def test_uebernahme_kopiert_nur_py(tmp_path):
    quelle = tmp_path / "berichte" / "akzeptanz" / "M2"
    quelle.mkdir(parents=True)
    (quelle / "test_akzeptanz_m2.py").write_text("def test_x(): pass\n", encoding="utf-8")
    (quelle / "notiz.txt").write_text("nein\n", encoding="utf-8")
    (quelle / "__pycache__").mkdir()
    ziel = tmp_path / "aufgaben" / "mini" / "M2"
    kopiert = abschluss.uebernimm_tests(quelle, ziel)
    assert kopiert == [ziel / "test_akzeptanz_m2.py"]
    assert sorted(p.name for p in ziel.iterdir()) == ["test_akzeptanz_m2.py"]


def test_uebernahme_ueberschreibt_nicht(tmp_path):
    quelle = tmp_path / "q"
    quelle.mkdir()
    (quelle / "test_a.py").write_text("neu\n", encoding="utf-8")
    ziel = tmp_path / "ziel"
    ziel.mkdir()
    (ziel / "test_a.py").write_text("alt\n", encoding="utf-8")
    with pytest.raises(FileExistsError):
        abschluss.uebernimm_tests(quelle, ziel)
    assert (ziel / "test_a.py").read_text(encoding="utf-8") == "alt\n"


# ------------------------------------------------------------------------------------------ Gesamtreview


def _gesamt(verdict="PASS", restpunkte=(), tuer=None):
    return {"verdict": verdict, "zusammenfassung": "ok", "spec_erfuellt": verdict == "PASS",
            "restpunkte": list(restpunkte),
            "tuer": tuer or {"urteil": "zweiseitig", "radius": "Datei", "begruendung": "nur Code", "faelle": [],
                             "selbstbewertung_stimmt": True}}


def test_gesamt_schema_streng():
    s = abschluss.GESAMT_SCHEMA
    assert s["additionalProperties"] is False
    assert set(s["required"]) == {"verdict", "zusammenfassung", "spec_erfuellt", "restpunkte", "tuer"}
    tuer = s["properties"]["tuer"]
    assert tuer["additionalProperties"] is False
    assert set(tuer["required"]) == {"urteil", "radius", "begruendung", "faelle", "selbstbewertung_stimmt"}
    assert tuer["properties"]["urteil"]["enum"] == ["einseitig", "zweiseitig"]
    punkt = s["properties"]["restpunkte"]["items"]
    assert punkt["properties"]["schwere"]["enum"] == ["major", "minor"]


def test_gesamt_schema_tuer_streng():
    """Codex verlangt mit --output-schema: jedes Objekt streng (alle Felder Pflicht, keine zusätzlichen)."""
    def objekte(schema):
        if schema.get("type") == "object":
            yield schema
            for wert in schema["properties"].values():
                yield from objekte(wert)
        if schema.get("type") == "array":
            yield from objekte(schema["items"])
    for o in objekte(abschluss.GESAMT_SCHEMA):
        assert o["additionalProperties"] is False and set(o["required"]) == set(o["properties"])


def _state(**mehr):
    return {"spec": "SPEC-TEXT", "plan": "PLAN-TEXT", "befunde": [], "testergebnis": None, **mehr}


def test_gesamt_prompt_enthaelt_spec_plan_diff_und_selbstbewertung():
    selbst = {"urteil": "zweiseitig", "radius": "Datei", "faelle": []}
    prompt = abschluss.gesamt_prompt(_state(), "DIFF-TEXT", selbst)
    assert "SPEC-TEXT" in prompt and "PLAN-TEXT" in prompt and "DIFF-TEXT" in prompt
    assert "zweiseitig" in prompt and "widerleg" in prompt.lower()


def test_gesamt_prompt_kuerzt():
    prompt = abschluss.gesamt_prompt(_state(), "x" * (abschluss.GESAMT_GRENZE * 2),
                                     {"urteil": "zweiseitig", "radius": "Datei", "faelle": []})
    assert len(prompt) <= abschluss.GESAMT_GRENZE
    assert "gekürzt" in prompt


# ------------------------------------------------------------------------------------------ Tür


DIFF_CODE = "diff --git a/neu.py b/neu.py\n+++ b/neu.py\n+def plus(a, b):\n+    return a + b\n"


@pytest.mark.parametrize("diff,name_status,fall", [
    ("+++ b/m.sql\n+ALTER TABLE ports ADD x;\n", "A\tmigrations/001.sql", "Schema-Migration"),
    ("+++ b/a.py\n+    shutil.rmtree(ziel)\n", "M\ta.py", "Löschen"),
    ("", "D\talt.py", "Löschen"),
    ("+++ b/a.py\n+subprocess.run(['git', 'push'])\n", "M\ta.py", "Veröffentlichen"),
    ("", "A\t.github/workflows/ci.yml", "Veröffentlichen"),
    ("+++ b/a.py\n+con = sqlite3.connect('daten.db')\n", "M\ta.py", "Produktions-DB"),
    ("+++ b/a.py\n+os.system('icacls x /grant y')\n", "M\ta.py", "Rechte"),
    ("", "A\t.env", "Rechte"),
])
def test_tuer_selbst_erkennt_migration_loeschen_push_db_secret(diff, name_status, fall):
    tuer = abschluss.tuer_selbst(diff, name_status)
    assert tuer["urteil"] == "einseitig"
    assert any(f.startswith(fall) for f in tuer["faelle"]), tuer["faelle"]


def test_tuer_selbst_zweiseitig_bei_reinem_code():
    assert abschluss.tuer_selbst(DIFF_CODE, "A\tneu.py") == {"urteil": "zweiseitig", "radius": "Datei", "faelle": []}


def test_tuer_selbst_radius():
    assert abschluss.tuer_selbst("", "M\tpaket/a.py\nM\tpaket/b.py")["radius"] == "Modul"
    assert abschluss.tuer_selbst("", "M\tpaket/a.py\nM\ttests/test_a.py")["radius"] == "Repo"
    assert abschluss.tuer_selbst("+x = subprocess.run(['git', 'push'])\n", "M\ta.py")["radius"] == "System"


def test_tuer_selbst_entfernte_zeilen_zaehlen_nicht():
    assert abschluss.tuer_selbst("--- a/a.py\n-    shutil.rmtree(ziel)\n", "M\ta.py")["urteil"] == "zweiseitig"


def test_tuer_strengeres_urteil_gewinnt():
    selbst = {"urteil": "zweiseitig", "radius": "Datei", "faelle": []}
    codex = _gesamt(tuer={"urteil": "einseitig", "radius": "System", "begruendung": "löscht Daten",
                          "faelle": ["Löschen von Daten"], "selbstbewertung_stimmt": False})
    t = abschluss.tuer_endgueltig(selbst, codex)
    assert t["urteil"] == "einseitig" and t["radius"] == "System"
    assert t["faelle"] == ["Löschen von Daten"]
    assert t["selbst"] == selbst and t["codex"]["urteil"] == "einseitig"
    # umgekehrt: die Selbstbewertung ist strenger
    t2 = abschluss.tuer_endgueltig({"urteil": "einseitig", "radius": "Repo", "faelle": ["Löschen: x"]}, _gesamt())
    assert t2["urteil"] == "einseitig" and t2["faelle"] == ["Löschen: x"]


def test_tuer_codex_fehlt_selbstbewertung_gilt():
    selbst = {"urteil": "zweiseitig", "radius": "Modul", "faelle": []}
    t = abschluss.tuer_endgueltig(selbst, None)
    assert (t["urteil"], t["radius"], t["codex"]) == ("zweiseitig", "Modul", None)


# ------------------------------------------------------------------------------------------ Einwände


def test_einwaende_major_und_fehlend():
    gesamt = _gesamt("FAIL", [{"schwere": "major", "aussage": "Spec-Punkt 3 fehlt"},
                              {"schwere": "minor", "aussage": "Name"}])
    assert abschluss.einwaende({"ok": True, "daten": gesamt, "fehler": None}) == [
        "Gesamtreview (Codex) meldet major: Spec-Punkt 3 fehlt"]
    assert abschluss.einwaende({"ok": False, "daten": None, "fehler": "Timeout"}) == ["Gesamtreview fehlt: Timeout"]
    assert abschluss.einwaende(None) == ["Gesamtreview fehlt: nicht gelaufen"]
    assert abschluss.einwaende({"ok": True, "daten": _gesamt(), "fehler": None}) == []


def _testergebnis(uebersprungen=0, gruende=None):
    t = {"gesammelt": 3, "bestanden": 3 - uebersprungen, "fehlgeschlagen": 0, "fehler": 0,
         "uebersprungen": uebersprungen,
         "akzeptanz": {"gesammelt": 2, "bestanden": 2, "erwartet": 2, "uebersprungen": 0, "fehler": 0}}
    if gruende is not None:
        t["skip_gruende"] = gruende
    return t


def test_einwand_einseitig_und_skips():
    ok = {"ok": True, "daten": _gesamt(), "fehler": None}
    tuer = {"urteil": "einseitig", "radius": "Repo", "faelle": ["Löschen: rmtree"]}
    assert abschluss.einwaende(ok, tuer=tuer) == ["Tür einseitig: Löschen: rmtree"]
    assert abschluss.einwaende(ok, testergebnis=_testergebnis(1, ["hier nicht möglich"])) == [
        "Tests übersprungen: 1 ohne Plattform-Begründung (unerwartete Skips sind eine Lücke, kein Bestehen)"]
    # ältere Läufe ohne Gründe: jeder Skip zählt
    assert abschluss.einwaende(ok, testergebnis=_testergebnis(2)) == [
        "Tests übersprungen: 2 ohne Plattform-Begründung (unerwartete Skips sind eine Lücke, kein Bestehen)"]


def test_plattform_skip_ist_kein_einwand():
    ok = {"ok": True, "daten": _gesamt(), "fehler": None}
    assert abschluss.einwaende(ok, testergebnis=_testergebnis(1, ["plattform: nur Linux"])) == []
    assert abschluss.skips_undokumentiert(_testergebnis(2, ["plattform: nur Linux", "kaputt"])) == 1


# ------------------------------------------------------------------------------------------ Skip-Gründe im Testlauf


def test_testlauf_sammelt_skip_gruende(tmp_path):
    wt = tmp_path / "wt"
    (wt / "tests").mkdir(parents=True)
    (wt / "tests" / "test_x.py").write_text(
        "import pytest\n\n\ndef test_ok():\n    assert True\n\n\n"
        "@pytest.mark.skipif(True, reason='plattform: nur anderswo')\ndef test_p():\n    pass\n\n\n"
        "def test_s():\n    pytest.skip('fixture fehlt')\n", encoding="utf-8")
    e = testlauf.fuehre_tests_aus(wt, {"python": sys.executable, "testbefehl": ["-m", "pytest", "-q"]}, [])
    assert e["uebersprungen"] == 2
    assert sorted(e["skip_gruende"]) == ["fixture fehlt", "plattform: nur anderswo"]


def test_merge_ff_nur_der_gepruefte_commit(repo, lauf):
    """Codex-Verifier S7-01: Kommt nach der Prüfung ein Commit auf den Lauf-Branch, wird nicht gemergt."""
    wt, basis, kopf = lauf
    (wt / "spaet.py").write_text("y = 2\n", encoding="utf-8")
    worktree.sichern(wt, "nach der Prüfung")
    with pytest.raises(worktree.WorktreeFehler, match="Lauf-Branch hat sich seit der Prüfung geändert"):
        worktree.merge_ff(repo, "lauf/x", basis, "main", erwartet=kopf)
    assert _kopf(repo) == basis
