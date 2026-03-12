"""Tests voor kill switch CLI gedrag."""

from typer.testing import CliRunner

from henk.cli import app


runner = CliRunner()


def test_stop_sets_hard_stop_true(tmp_path, monkeypatch):
    data_dir = tmp_path / "henk"
    (data_dir / "control").mkdir(parents=True)
    monkeypatch.setattr("henk.cli._get_data_dir", lambda: data_dir)

    result = runner.invoke(app, ["stop"])
    assert result.exit_code == 0
    assert (data_dir / "control" / "hard_stop").read_text(encoding="utf-8") == "true"


def test_pause_sets_graceful_true(tmp_path, monkeypatch):
    data_dir = tmp_path / "henk"
    (data_dir / "control").mkdir(parents=True)
    monkeypatch.setattr("henk.cli._get_data_dir", lambda: data_dir)

    result = runner.invoke(app, ["pause"])
    assert result.exit_code == 0
    assert (data_dir / "control" / "graceful_stop").read_text(encoding="utf-8") == "true"


def test_resume_sets_graceful_false(tmp_path, monkeypatch):
    data_dir = tmp_path / "henk"
    (data_dir / "control").mkdir(parents=True)
    (data_dir / "control" / "graceful_stop").write_text("true", encoding="utf-8")
    monkeypatch.setattr("henk.cli._get_data_dir", lambda: data_dir)

    result = runner.invoke(app, ["resume"])
    assert result.exit_code == 0
    assert (data_dir / "control" / "graceful_stop").read_text(encoding="utf-8") == "false"


def test_chat_refuses_when_hard_stop_active(tmp_path, monkeypatch):
    data_dir = tmp_path / "henk"
    (data_dir / "control").mkdir(parents=True)
    (data_dir / "control" / "hard_stop").write_text("true", encoding="utf-8")
    monkeypatch.setattr("henk.cli._get_data_dir", lambda: data_dir)

    result = runner.invoke(app, ["chat"])
    assert result.exit_code == 1


def test_gateway_blocks_tool_calls_when_graceful_active(config, mock_brain):
    from henk.gateway import LoopDecision
    from henk.transcript import TranscriptWriter
    from henk.gateway import Gateway

    (config.control_dir / "graceful_stop").write_text("true", encoding="utf-8")
    gw = Gateway(config, mock_brain, TranscriptWriter(config.logs_dir))
    decision = gw.check_tool_call("web_search", {"query": "x"})
    assert decision.decision == LoopDecision.DENY_KILL_SWITCH
