import json
import sys

from app.cli import main


def test_cli_dry_run_prints_report(capsys, monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "detector",
            "--base", "https://x.example",
            "--key", "sk-test",
            "--model", "claude-opus-4-7",
            "--rounds", "11",
            "--budget", "0.5",
            "--dry-run",
            "--json",
        ],
    )
    rc = main()
    assert rc == 0
    out = capsys.readouterr().out
    body = json.loads(out)
    assert body["verdict"] == "authentic"
    assert body["score"] >= 90


def test_cli_unknown_model_returns_2(capsys, monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "detector",
            "--base", "https://x",
            "--key", "sk-test",
            "--model", "no-such",
            "--dry-run",
        ],
    )
    rc = main()
    assert rc == 2
    err = capsys.readouterr().err
    assert "unknown model" in err.lower()


def test_cli_pretty_output_human_readable(capsys, monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "detector",
            "--base", "https://x",
            "--key", "sk-test",
            "--model", "claude-opus-4-7",
            "--dry-run",
        ],
    )
    rc = main()
    assert rc == 0
    out = capsys.readouterr().out
    assert "verdict" in out.lower()
    assert "score" in out.lower()
