import json
import subprocess
from pathlib import Path

import pytest

from entwicklung import agenten

PY = "C:/x/.venv/Scripts/python.exe"


class FakeRunner:
    def __init__(self, stdout="", rc=0, ausnahme=None):
        self.stdout, self.rc, self.ausnahme = stdout, rc, ausnahme
        self.aufrufe = []

    def __call__(self, cmd, **kwargs):
        self.aufrufe.append((cmd, kwargs))
        if self.ausnahme:
            raise self.ausnahme
        return subprocess.CompletedProcess(cmd, self.rc, stdout=self.stdout, stderr="")


def _json(**felder):
    basis = {"type": "result", "subtype": "success", "is_error": False, "result": "Fertig: liste.py gebaut.",
             "num_turns": 7, "permission_denials": []}
    basis.update(felder)
    return "\ufeff" + json.dumps(basis)


def test_befehl_gehaertet(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "geheim")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "geheim")
    runner = FakeRunner(_json(permission_denials=[
        {"tool_name": "Bash", "tool_use_id": "t1", "tool_input": {"command": "git commit -m x"}}]))
    erg = agenten.claude_implementierer("Baue A1.", tmp_path, PY, modell="sonnet", runner=runner)
    cmd, kw = runner.aufrufe[0]
    for paar in (["--model", "sonnet"], ["--permission-prompts", "none"], ["--permission-mode", "acceptEdits"],
                 ["--settings", '{"disableAllHooks": true}'], ["--tools", "Read,Edit,Write,Glob,Grep,Bash"],
                 ["--allowedTools", f"Bash({PY} -m pytest:*)"], ["--output-format", "json"]):
        i = cmd.index(paar[0])
        assert cmd[i + 1] == paar[1]
    assert "--restricted" in cmd and "--strict-mcp-config" in cmd and "-p" in cmd
    assert "bypassPermissions" not in cmd
    assert kw["cwd"] == tmp_path
    assert kw["input"] == "Baue A1."
    assert kw["encoding"] == "utf-8"
    assert "ANTHROPIC_API_KEY" not in kw["env"] and "ANTHROPIC_AUTH_TOKEN" not in kw["env"]
    assert erg["ok"] is True
    assert erg["zusammenfassung"] == "Fertig: liste.py gebaut."
    assert erg["turns"] == 7
    assert erg["verweigerungen"] == ["Bash: git commit -m x"]
    assert erg["fehler"] is None


def test_lange_verweigerung_wird_gekuerzt(tmp_path):
    befehl = "cat > portwart/liste.py <<'E'\n" + "x = 1\n" * 50
    runner = FakeRunner(_json(permission_denials=[{"tool_name": "Bash", "tool_input": {"command": befehl}},
                                                  {"tool_name": "Bash", "tool_input": {"command": "a" * 300}}]))
    erg = agenten.claude_implementierer("x", tmp_path, PY, runner=runner)
    assert erg["verweigerungen"][0] == "Bash: cat > portwart/liste.py <<'E' …"
    assert erg["verweigerungen"][1] == "Bash: " + "a" * 120 + " …"


def test_timeout_ok_false(tmp_path):
    runner = FakeRunner(ausnahme=subprocess.TimeoutExpired(["claude"], 600))
    erg = agenten.claude_implementierer("x", tmp_path, PY, runner=runner)
    assert erg["ok"] is False and "Timeout" in erg["fehler"]


def test_nicht_startbar_ok_false(tmp_path):
    erg = agenten.claude_implementierer("x", tmp_path, PY, runner=FakeRunner(ausnahme=OSError("weg")))
    assert erg["ok"] is False and "weg" in erg["fehler"]


def test_leere_ausgabe_ok_false(tmp_path):
    erg = agenten.claude_implementierer("x", tmp_path, PY, runner=FakeRunner("", rc=1))
    assert erg["ok"] is False and "rc=1" in erg["fehler"]


def test_kein_json_ok_false(tmp_path):
    erg = agenten.claude_implementierer("x", tmp_path, PY, runner=FakeRunner("Hallo"))
    assert erg["ok"] is False and "JSON" in erg["fehler"]


def test_is_error_ok_false(tmp_path):
    runner = FakeRunner(_json(is_error=True, subtype="error_max_turns", result=""))
    erg = agenten.claude_implementierer("x", tmp_path, PY, runner=runner)
    assert erg["ok"] is False and "error_max_turns" in erg["fehler"]


def test_rc_ungleich_null_ok_false(tmp_path):
    erg = agenten.claude_implementierer("x", tmp_path, PY, runner=FakeRunner(_json(), rc=1))
    assert erg["ok"] is False and "rc=1" in erg["fehler"]
    assert erg["zusammenfassung"] == "Fertig: liste.py gebaut."


def test_testsperre(tmp_path):
    with pytest.raises(agenten.EchterAgentImTest):
        agenten.claude_implementierer("x", tmp_path, PY)


FIX_BEFUNDE = [{"pruefer": ["clean_code"], "path": "tests/test_abgleich.py", "line": 44,
                "claim": "lies_netstat nur für fehlende Datei getestet"},
               {"pruefer": ["funktion"], "path": "tests", "line": 0, "claim": "Akzeptanztests 34/35 bestanden"}]


def test_fix_prompt_enthaelt_befunde_und_auszug():
    p = agenten.fix_prompt("# A2\nAbgleich.", 1, FIX_BEFUNDE, "FAILED test_x - assert 1 == 2", f"{PY} -m pytest -q")
    assert "# A2\nAbgleich." in p and "Runde 1" in p
    assert "- [clean_code] tests/test_abgleich.py:44 — lies_netstat nur für fehlende Datei getestet" in p
    assert "- [funktion] tests:0 — Akzeptanztests 34/35 bestanden" in p
    assert "FAILED test_x - assert 1 == 2" in p
    assert f"{PY} -m pytest -q" in p and "kein git" in p and "nicht von vorn" in p


def test_fix_prompt_ohne_auszug():
    p = agenten.fix_prompt("A", 2, FIX_BEFUNDE[:1], None, "pytest")
    assert "Runde 2" in p and "Testausgabe" not in p


def test_prompt():
    p = agenten.implementierer_prompt("# A1\nBaue den Prüfer.", f"{PY} -m pytest -q")
    assert "# A1\nBaue den Prüfer." in p
    assert f"{PY} -m pytest -q" in p
    assert "kein git" in p



def test_implementierer_effort_im_befehl(tmp_path):
    runner = FakeRunner(_json())
    agenten.claude_implementierer("Baue.", tmp_path, PY, modell="opus", effort="high", timeout=900, runner=runner)
    cmd, kw = runner.aufrufe[0]
    assert cmd[cmd.index("--effort") + 1] == "high" and kw["timeout"] == 900
    agenten.claude_implementierer("Baue.", tmp_path, PY, runner=runner)
    assert "--effort" not in runner.aufrufe[1][0]
