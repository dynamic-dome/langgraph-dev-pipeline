import json
import subprocess
from pathlib import Path

import pytest

from entwicklung import agenten, strukturiert
from tests.test_pruefer import FakeRunner, _wert

SCHEMA = {"type": "object", "required": ["klar", "fragen"],
          "properties": {"klar": {"type": "boolean"}, "fragen": {"type": "array", "items": {"type": "string"}}}}
DATEN = {"klar": False, "fragen": ["Welche Dateiarten?"]}


def _claude_json(**felder):
    basis = {"type": "result", "subtype": "success", "is_error": False, "result": "…", "structured_output": DATEN}
    basis.update(felder)
    return json.dumps(basis)


def test_claude_strukturiert_liefert_daten(tmp_path):
    runner = FakeRunner(_claude_json())
    erg = strukturiert.claude_strukturiert("klaeren", "frage", tmp_path, SCHEMA, modell="haiku", runner=runner)
    cmd, kw = runner.aufrufe[0]
    assert "--restricted" in cmd and "--strict-mcp-config" in cmd
    assert _wert(cmd, "--tools") == "Read,Glob,Grep" and _wert(cmd, "--model") == "haiku"
    assert _wert(cmd, "--permission-prompts") == "none"
    assert json.loads(_wert(cmd, "--json-schema")) == SCHEMA
    assert "--allowedTools" not in cmd
    assert kw["cwd"] == tmp_path and kw["input"] == "frage"
    assert erg == {"name": "klaeren", "ok": True, "daten": DATEN, "fehler": None, "dauer_s": erg["dauer_s"]}


@pytest.mark.parametrize("runner,teil", [
    (FakeRunner(_claude_json(structured_output=None)), "Schema"),
    (FakeRunner(_claude_json(structured_output={"klar": True})), "Schema"),
    (FakeRunner(_claude_json(structured_output={"klar": "ja", "fragen": []})), "Schema"),
    (FakeRunner(""), "keine Ausgabe"),
    (FakeRunner("kein json"), "JSON"),
    (FakeRunner(_claude_json(), rc=1), "rc=1"),
    (FakeRunner(_claude_json(is_error=True, subtype="error_max_turns")), "error_max_turns"),
    (FakeRunner(ausnahme=subprocess.TimeoutExpired(["claude"], 600)), "Timeout"),
], ids=["ohne", "pflichtfeld", "typ", "leer", "kein-json", "rc", "is-error", "timeout"])
def test_claude_strukturiert_fehlerfaelle(tmp_path, runner, teil):
    erg = strukturiert.claude_strukturiert("spec", "x", tmp_path, SCHEMA, runner=runner)
    assert erg["ok"] is False and erg["daten"] is None and teil in erg["fehler"]


def test_codex_strukturiert_liest_ausgabedatei(tmp_path):
    runner = FakeRunner(datei=json.dumps(DATEN))
    erg = strukturiert.codex_strukturiert("spec_codex", "prüfe", tmp_path, SCHEMA, runner=runner)
    cmd, kw = runner.aufrufe[0]
    assert cmd[1] == "exec" and _wert(cmd, "-s") == "read-only"
    assert "approval_policy=never" in cmd and 'model_reasoning_effort="high"' in cmd
    schema_datei = Path(_wert(cmd, "--output-schema"))
    assert not schema_datei.exists() and not Path(_wert(cmd, "-o")).exists()  # Temp-Dateien wieder weg
    assert cmd[-1] == "-" and kw["input"] == "prüfe" and kw["cwd"] == tmp_path
    assert erg["ok"] is True and erg["daten"] == DATEN and erg["name"] == "spec_codex"


def test_codex_strukturiert_schema_an_codex(tmp_path):
    gesehen = {}

    def runner(cmd, **kw):
        gesehen["schema"] = json.loads(Path(cmd[cmd.index("--output-schema") + 1]).read_text(encoding="utf-8"))
        Path(cmd[cmd.index("-o") + 1]).write_text(json.dumps(DATEN), encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    strukturiert.codex_strukturiert("x", "p", tmp_path, SCHEMA, runner=runner)
    assert gesehen["schema"] == SCHEMA


@pytest.mark.parametrize("runner,teil", [
    (FakeRunner(), "keine Ergebnisdatei"),
    (FakeRunner(datei="{kaputt"), "JSON"),
    (FakeRunner(datei=json.dumps({"klar": True})), "Schema"),
    (FakeRunner(datei=json.dumps(DATEN), rc=1), "rc=1"),
    (FakeRunner(ausnahme=OSError("weg")), "weg"),
], ids=["ohne-datei", "kaputt", "schema", "rc", "oserror"])
def test_codex_strukturiert_fehlerfaelle(tmp_path, runner, teil):
    erg = strukturiert.codex_strukturiert("x", "p", tmp_path, SCHEMA, runner=runner)
    assert erg["ok"] is False and teil in erg["fehler"]


def test_testsperre_gilt(tmp_path):
    with pytest.raises(agenten.EchterAgentImTest):
        strukturiert.claude_strukturiert("x", "p", tmp_path, SCHEMA)
    with pytest.raises(agenten.EchterAgentImTest):
        strukturiert.codex_strukturiert("x", "p", tmp_path, SCHEMA)



def test_claude_effort_im_befehl(tmp_path):
    runner = FakeRunner(_claude_json())
    strukturiert.claude_strukturiert("x", "p", tmp_path, SCHEMA, effort="high", runner=runner)
    strukturiert.claude_strukturiert("x", "p", tmp_path, SCHEMA, runner=runner)
    assert _wert(runner.aufrufe[0][0], "--effort") == "high" and "--effort" not in runner.aufrufe[1][0]


def test_codex_effort_im_befehl(tmp_path):
    runner = FakeRunner(datei=json.dumps(DATEN))
    strukturiert.codex_strukturiert("x", "p", tmp_path, SCHEMA, effort="medium", runner=runner)
    assert 'model_reasoning_effort="medium"' in runner.aufrufe[0][0]
