import json
import subprocess
from pathlib import Path

import pytest

from entwicklung import agenten, pruefer

BEFUND = {"id": "F1", "severity": "major", "kind": "security", "path": "a.py", "line": 2, "claim": "x",
          "quote": "return 1", "check": "gelesen", "status": "read-only"}
BERICHT = {"verdict": "FAIL", "findings": [BEFUND], "not_checkable": []}


class FakeRunner:
    def __init__(self, stdout="", rc=0, ausnahme=None, datei=None):
        self.stdout, self.rc, self.ausnahme, self.datei = stdout, rc, ausnahme, datei
        self.aufrufe = []

    def __call__(self, cmd, **kwargs):
        self.aufrufe.append((cmd, kwargs))
        if self.ausnahme:
            raise self.ausnahme
        if self.datei is not None:  # codex schreibt sein Ergebnis in die -o-Datei
            Path(cmd[cmd.index("-o") + 1]).write_text(self.datei, encoding="utf-8")
        return subprocess.CompletedProcess(cmd, self.rc, stdout=self.stdout, stderr="")


def _claude_json(**felder):
    basis = {"type": "result", "subtype": "success", "is_error": False, "result": "…",
             "structured_output": BERICHT}
    basis.update(felder)
    return json.dumps(basis)


def _wert(cmd, flag):
    return cmd[cmd.index(flag) + 1]


def test_claude_pruefer_flags(tmp_path):
    runner = FakeRunner(_claude_json())
    erg = pruefer.claude_pruefer("security", "prüfe", tmp_path, modell="sonnet", runner=runner)
    cmd, kw = runner.aufrufe[0]
    assert "--restricted" in cmd and "--strict-mcp-config" in cmd
    assert _wert(cmd, "--tools") == "Read,Glob,Grep"
    assert _wert(cmd, "--permission-prompts") == "none"
    assert json.loads(_wert(cmd, "--json-schema")) == json.loads(pruefer.SCHEMA_PFAD.read_text(encoding="utf-8"))
    assert "--allowedTools" not in cmd and "bypassPermissions" not in cmd
    assert kw["cwd"] == tmp_path and kw["input"] == "prüfe"
    assert erg == {"pruefer": "security", "ok": True, "bericht": BERICHT, "fehler": None,
                   "dauer_s": erg["dauer_s"]}


@pytest.mark.parametrize("runner,teil", [
    (FakeRunner(_claude_json(structured_output=None)), "Schema"),
    (FakeRunner(_claude_json(structured_output={"verdict": "PASS"})), "Schema"),
    (FakeRunner(""), "keine Ausgabe"),
    (FakeRunner("kein json"), "JSON"),
    (FakeRunner(_claude_json(), rc=1), "rc=1"),
    (FakeRunner(_claude_json(is_error=True, subtype="error_max_turns")), "error_max_turns"),
    (FakeRunner(ausnahme=subprocess.TimeoutExpired(["claude"], 600)), "Timeout"),
], ids=["ohne-schema", "schema-unvollstaendig", "leer", "kein-json", "rc", "is-error", "timeout"])
def test_claude_pruefer_nicht_verwertbar(tmp_path, runner, teil):
    erg = pruefer.claude_pruefer("clean_code", "x", tmp_path, runner=runner)
    assert erg["ok"] is False and erg["bericht"] is None
    assert teil in erg["fehler"]


@pytest.mark.parametrize("bericht", [
    {"verdict": "PASS", "findings": [], "not_checkable": [{}]},
    {"verdict": "PASS", "findings": [], "not_checkable": ["text"]},
    {"verdict": "PASS", "findings": ["text"], "not_checkable": []},
])
def test_schema_ok_streng(bericht):
    assert pruefer.schema_ok(bericht) is False


def test_codex_pruefer_flags(tmp_path):
    runner = FakeRunner(datei=json.dumps(BERICHT))
    erg = pruefer.codex_pruefer("prüfe", tmp_path, runner=runner)
    cmd, kw = runner.aufrufe[0]
    assert cmd[1] == "exec" and _wert(cmd, "-s") == "read-only"
    assert "approval_policy=never" in cmd and 'model_reasoning_effort="high"' in cmd
    assert Path(_wert(cmd, "--output-schema")) == pruefer.SCHEMA_PFAD
    assert cmd[-1] == "-" and kw["input"] == "prüfe" and kw["cwd"] == tmp_path
    assert not Path(_wert(cmd, "-o")).exists()  # Temp-Datei wieder weg
    assert erg["ok"] is True and erg["bericht"] == BERICHT and erg["pruefer"] == "codex"


@pytest.mark.parametrize("runner,teil", [
    (FakeRunner(), "keine Ergebnisdatei"),
    (FakeRunner(datei="{kaputt"), "JSON"),
    (FakeRunner(datei=json.dumps({"findings": []})), "Schema"),
    (FakeRunner(datei=json.dumps(BERICHT), rc=1), "rc=1"),
    (FakeRunner(ausnahme=OSError("weg")), "weg"),
], ids=["ohne-datei", "kaputt", "schema", "rc", "oserror"])
def test_codex_pruefer_nicht_verwertbar(tmp_path, runner, teil):
    erg = pruefer.codex_pruefer("x", tmp_path, runner=runner)
    assert erg["ok"] is False and teil in erg["fehler"]


def test_testsperre(tmp_path):
    with pytest.raises(agenten.EchterAgentImTest):
        pruefer.claude_pruefer("security", "x", tmp_path)
    with pytest.raises(agenten.EchterAgentImTest):
        pruefer.codex_pruefer("x", tmp_path)


def test_prompt_inhalt():
    p = pruefer.pruefer_prompt("security", "# A2\nAbgleich bauen.", "+def f(): pass\n", {"a.py": "def f(): pass\n"})
    assert "# A2\nAbgleich bauen." in p and "+def f(): pass" in p
    assert "### a.py" in p and pruefer.ROLLEN["security"] in p
    assert "quote" in p and "wörtlich" in p


def test_prompt_kuerzung():
    gross = {"gross.py": "x = 1\n" * 20000, "klein.py": "y = 2\n"}
    p = pruefer.pruefer_prompt("codex", "A", "+x\n", gross)
    assert len(p) < pruefer.MAX_ZEICHEN + 5000
    assert "gekürzt" in p


def test_unbekannte_rolle():
    with pytest.raises(KeyError):
        pruefer.pruefer_prompt("raten", "A", "", {})


GRUEN = {"gesammelt": 5, "bestanden": 5, "fehlgeschlagen": 0, "fehler": 0, "uebersprungen": 0,
         "akzeptanz": {"gesammelt": 3, "bestanden": 3, "erwartet": 3}, "rc": {"eigene": 0, "akzeptanz": 0},
         "gruen": True, "auszug": ""}


def test_funktion_gruen():
    erg = pruefer.funktion_bericht(GRUEN)
    assert erg["ok"] is True and erg["pruefer"] == "funktion"
    assert erg["bericht"] == {"verdict": "PASS", "findings": [], "not_checkable": []}


def test_funktion_rote_akzeptanz():
    t = {**GRUEN, "bestanden": 4, "fehlgeschlagen": 1, "gruen": False,
         "akzeptanz": {"gesammelt": 3, "bestanden": 2, "erwartet": 3}, "rc": {"eigene": 0, "akzeptanz": 1}}
    b = pruefer.funktion_bericht(t)["bericht"]
    assert b["verdict"] == "FAIL"
    assert all(f["severity"] == "blocker" and f["status"] == "executed" for f in b["findings"])
    assert any("2/3" in f["claim"] for f in b["findings"])
    assert pruefer.schema_ok(b)


def test_funktion_fehlende_akzeptanz():
    t = {**GRUEN, "gruen": False, "akzeptanz": {"gesammelt": 2, "bestanden": 2, "erwartet": 3}}
    b = pruefer.funktion_bericht(t)["bericht"]
    assert b["verdict"] == "FAIL" and any("erwartet 3" in f["claim"] for f in b["findings"])


def test_funktion_rc_und_keine_eigenen_tests():
    t = {**GRUEN, "gesammelt": 3, "bestanden": 3, "gruen": False, "rc": {"eigene": 5, "akzeptanz": 0}}
    claims = " ".join(f["claim"] for f in pruefer.funktion_bericht(t)["bericht"]["findings"])
    assert "Exit-Code" in claims and "keine eigenen Tests" in claims


def test_funktion_nicht_gruen_ohne_erkennbaren_grund_meldet_trotzdem():
    b = pruefer.funktion_bericht({**GRUEN, "gruen": False})["bericht"]
    assert b["verdict"] == "FAIL" and len(b["findings"]) == 1


def test_funktion_nennt_uebersprungene():
    t = {**GRUEN, "gruen": False, "uebersprungen": 1,
         "akzeptanz": {"gesammelt": 3, "bestanden": 2, "erwartet": 3, "uebersprungen": 1}}
    claims = [f["claim"] for f in pruefer.funktion_bericht(t)["bericht"]["findings"]]
    assert any("1 übersprungen" in c for c in claims)



def test_pruefer_effort_im_befehl(tmp_path):
    runner = FakeRunner(_claude_json())
    pruefer.claude_pruefer("security", "prüfe", tmp_path, modell="opus", effort="xhigh", timeout=1200, runner=runner)
    cmd, kw = runner.aufrufe[0]
    assert _wert(cmd, "--effort") == "xhigh" and _wert(cmd, "--model") == "opus" and kw["timeout"] == 1200


def test_schema_ok_prueft_feldtypen():
    """Codex-Review Export SEC-005: falsche Typen (path als Liste, line als Text) sind nicht verwertbar."""
    gut = {"id": "F1", "severity": "major", "kind": "bug", "path": "a.py", "line": 2, "claim": "c", "quote": "q",
           "check": "k", "status": "read-only"}
    def bericht(**kw):
        return {"verdict": "FAIL", "findings": [{**gut, **kw}], "not_checkable": []}
    assert pruefer.schema_ok(bericht())
    assert not pruefer.schema_ok(bericht(path=[]))
    assert not pruefer.schema_ok(bericht(line="2"))
    assert not pruefer.schema_ok(bericht(line=True))
    assert not pruefer.schema_ok(bericht(quote=None))
    assert not pruefer.schema_ok({"verdict": "PASS", "findings": [], "not_checkable": [{"what": 1, "why": "", "need": ""}]})
