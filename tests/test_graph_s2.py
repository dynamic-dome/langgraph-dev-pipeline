import dataclasses
from pathlib import Path

import pytest

from entwicklung import cli
from entwicklung.graph import baue_graph_s2
from tests.test_graph_s1 import _abh, _fake, _git, umgebung  # noqa: F401  (umgebung ist eine Fixture)

PASS = {"verdict": "PASS", "findings": [], "not_checkable": []}


def _ok(name, bericht=PASS):
    return {"pruefer": name, "ok": True, "bericht": bericht, "fehler": None, "dauer_s": 0.1}


def _pruefer(berichte=None, prompts=None, extra=None):
    """Fake für claude_pruefer: je Rolle ein fester Bericht."""
    berichte = berichte or {}

    def pruefer(rolle, prompt, wt, modell="sonnet", timeout=600, effort=None, runner=None):
        if prompts is not None:
            prompts[rolle] = prompt
        if extra:
            extra(rolle, wt)
        return _ok(rolle, berichte.get(rolle, PASS))
    return pruefer


def _codex(bericht=PASS, fehler=None):
    def codex(prompt, wt, timeout=900, effort=None, runner=None):
        if fehler:
            raise RuntimeError(fehler)
        return _ok("codex", bericht)
    return codex


def _abh2(aufgaben, **kw):
    kw.setdefault("pruefer", _pruefer())
    kw.setdefault("codex", _codex())
    return _abh(aufgaben, **kw)


def _lauf(repo, abh):
    return baue_graph_s2(abh).invoke({"repo": str(repo), "aufgabe_id": "M1"})


def test_vier_pruefer_laufen(umgebung):
    repo, aufgaben = umgebung
    erg = _lauf(repo, _abh2(aufgaben))
    assert erg["status"] == "gruen"
    assert sorted(p["pruefer"] for p in erg["pruefberichte"]) == ["clean_code", "codex", "funktion", "security"]
    assert erg["befunde"] == [] and erg["fix_noetig"] is False
    text = Path(erg["bericht_pfad"]).read_text(encoding="utf-8")
    assert "## Prüfer" in text and "Fix-Runde nötig: nein" in text


def test_prompt_enthaelt_diff_und_dateien(umgebung):
    repo, aufgaben = umgebung
    prompts = {}
    _lauf(repo, _abh2(aufgaben, pruefer=_pruefer(prompts=prompts)))
    assert set(prompts) == {"security", "clean_code"}
    assert "+def plus(a, b):" in prompts["security"] and "### mathe.py" in prompts["security"]
    assert "# M1: plus" in prompts["clean_code"]


def test_befund_mit_zitat_loest_fix_aus(umgebung):
    repo, aufgaben = umgebung
    befund = {"id": "S1", "severity": "major", "kind": "bug", "path": "mathe.py", "line": 2,
              "claim": "Keine Typprüfung", "quote": "return a + b", "check": "gelesen", "status": "read-only"}
    abh = _abh2(aufgaben, pruefer=_pruefer({"security": {"verdict": "FAIL", "findings": [befund],
                                                          "not_checkable": []}}))
    erg = _lauf(repo, abh)
    assert erg["status"] == "gruen" and erg["fix_noetig"] is True
    assert erg["befunde"][0]["topf"] == "candidates" and erg["befunde"][0]["pruefer"] == ["security"]
    assert "Fix-Runde nötig: ja" in Path(erg["bericht_pfad"]).read_text(encoding="utf-8")


def test_pruefer_schreibt_ist_grenzverletzung(umgebung):
    repo, aufgaben = umgebung

    def schreiben(rolle, wt):
        if rolle == "clean_code":
            (wt / "notiz.txt").write_text("x", encoding="utf-8")

    erg = _lauf(repo, _abh2(aufgaben, pruefer=_pruefer(extra=schreiben)))
    assert erg["status"] == "grenzverletzung"
    assert any("Prüfer" in v and "notiz.txt" in v for v in erg["grenzverletzungen"])


def test_testcode_schreibt_ins_hauptrepo(umgebung):
    repo, aufgaben = umgebung

    def boeser_test(wt):
        (wt / "tests" / "test_spur.py").write_text(
            f"from pathlib import Path\n\n\ndef test_spur():\n    Path(r'{repo / 'spur.txt'}').write_text('x')\n",
            encoding="utf-8")

    erg = _lauf(repo, _abh2(aufgaben, implementierer=_fake(extra=boeser_test)))
    assert erg["status"] == "grenzverletzung"
    assert any("Testlauf" in v and "spur.txt" in v for v in erg["grenzverletzungen"])
    assert erg.get("pruefberichte", []) == []


def test_testcode_veraendert_worktree(umgebung):
    repo, aufgaben = umgebung

    def umschreibender_test(wt):
        (wt / "tests" / "test_um.py").write_text(
            "from pathlib import Path\n\n\ndef test_um():\n"
            "    p = Path(__file__).resolve().parents[1] / 'mathe.py'\n"
            "    p.write_text(p.read_text() + '# nachträglich\\n')\n", encoding="utf-8")

    erg = _lauf(repo, _abh2(aufgaben, implementierer=_fake(extra=umschreibender_test)))
    assert erg["status"] == "grenzverletzung"
    assert any("Testlauf" in v and "mathe.py" in v for v in erg["grenzverletzungen"])
    assert erg.get("pruefberichte", []) == []


def test_vom_filter_verworfener_bericht_ist_nicht_pass(umgebung):
    repo, aufgaben = umgebung
    kaputt = {"verdict": "PASS", "findings": [], "not_checkable": [{}]}
    erg = _lauf(repo, _abh2(aufgaben, pruefer=_pruefer({"security": kaputt})))
    assert [n["pruefer"] for n in erg["nicht_verwertbar"]] == ["security"]
    text = Path(erg["bericht_pfad"]).read_text(encoding="utf-8")
    assert "security: nicht verwertbar" in text and "security: PASS" not in text


def test_pruefer_kaputt_nicht_verwertbar(umgebung):
    repo, aufgaben = umgebung

    def pruefer(rolle, prompt, wt, modell="sonnet", timeout=600, effort=None, runner=None):
        if rolle == "clean_code":
            return {"pruefer": rolle, "ok": False, "bericht": None, "fehler": "Bericht entspricht nicht dem Schema",
                    "dauer_s": 1.0}
        return _ok(rolle)

    erg = _lauf(repo, _abh2(aufgaben, pruefer=pruefer, codex=_codex(fehler="codex weg")))
    assert sorted(n["pruefer"] for n in erg["nicht_verwertbar"]) == ["clean_code", "codex"]
    assert "codex weg" in str(erg["nicht_verwertbar"])
    assert "nicht verwertbar" in Path(erg["bericht_pfad"]).read_text(encoding="utf-8")


def test_grenzverletzung_ueberspringt_pruefer(umgebung):
    repo, aufgaben = umgebung
    boese = _fake(extra=lambda wt: (repo / "boese.py").write_text("x\n", encoding="utf-8"))
    erg = _lauf(repo, _abh2(aufgaben, implementierer=boese))
    assert erg["status"] == "grenzverletzung"
    assert erg.get("pruefberichte", []) == []


def test_roter_testlauf_wird_trotzdem_geprueft(umgebung):
    repo, aufgaben = umgebung
    erg = _lauf(repo, _abh2(aufgaben, implementierer=_fake(code="def plus(a, b):\n    return 0\n")))
    assert erg["status"] == "rot" and len(erg["pruefberichte"]) == 4
    assert erg["fix_noetig"] is True
    assert any(b["topf"] == "deterministisch" for b in erg["befunde"])


def test_cli_stufe_1_weiter_lauffaehig(umgebung):
    repo, aufgaben = umgebung
    rc = cli.main(["lauf", "--repo", str(repo), "--aufgabe", "M1", "--stufe", "1"], abh=_abh(aufgaben))
    assert rc == 0


def test_cli_exit_bei_fix_noetig(umgebung, capsys):
    repo, aufgaben = umgebung
    befund = {"id": "C1", "severity": "blocker", "kind": "bug", "path": "mathe.py", "line": 2, "claim": "falsch",
              "quote": "return a + b", "check": "gelesen", "status": "read-only"}
    abh = _abh2(aufgaben, codex=_codex({"verdict": "FAIL", "findings": [befund], "not_checkable": []}))
    assert cli.main(["lauf", "--repo", str(repo), "--aufgabe", "M1", "--stufe", "2"], abh=abh) == 1
    aus = capsys.readouterr().out
    assert "Fix-Runde nötig: ja" in aus and "falsch" in aus


def test_cli_live_zeigt_pruefer(umgebung, capsys):
    repo, aufgaben = umgebung
    assert cli.main(["lauf", "--repo", str(repo), "--aufgabe", "M1", "--live", "--stufe", "2"], abh=_abh2(aufgaben)) == 0
    aus = capsys.readouterr().out
    for knoten in ("pruefen_funktion", "pruefen_security", "pruefen_clean_code", "pruefen_codex", "befunde_sammeln"):
        assert knoten in aus
