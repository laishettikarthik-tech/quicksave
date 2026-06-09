import io
import json

from quicksave.cli import main


def test_cli_roundtrip(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "note.md").write_text("draft")

    main(["init"])
    main(["save", "-m", "wip"])
    main(["list"])
    out = capsys.readouterr().out
    assert "wip" in out

    (tmp_path / "note.md").unlink()
    main(["restore", "0"])
    assert (tmp_path / "note.md").read_text() == "draft"


def test_cli_status_and_clean(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.txt").write_text("v1")
    main(["init"])
    main(["save", "-m", "base"])

    (tmp_path / "junk.txt").write_text("noise")
    main(["status"])
    assert "junk.txt" in capsys.readouterr().out

    main(["restore", "0", "--clean"])
    assert not (tmp_path / "junk.txt").exists()
    main(["status"])
    assert "clean" in capsys.readouterr().out


def test_hook_saves_before_risky_command(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data.txt").write_text("keep")
    main(["init"])

    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "rm -rf data.txt"}})
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    main(["hook"])

    snaps = list((tmp_path / ".quicksave" / "snapshots").glob("*.json"))
    assert len(snaps) == 1
    assert "pre: rm -rf data.txt" in snaps[0].read_text()


def test_hook_skips_safe_command(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    main(["init"])

    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls -la"}})
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    main(["hook"])

    assert not list((tmp_path / ".quicksave" / "snapshots").glob("*.json"))


def test_hook_noop_outside_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "rm -rf x"}})
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    main(["hook"])  # no quicksave project, must not raise


def test_hook_install_claude(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    main(["init"])
    main(["hook", "install"])

    cfg = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    group = cfg["hooks"]["PreToolUse"][0]
    assert group["matcher"] == "Bash"
    assert group["hooks"][0]["command"] == "quicksave hook"


def test_hook_install_codex_and_idempotent(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    main(["init"])
    main(["hook", "install", "--tool", "codex"])
    main(["hook", "install", "--tool", "codex"])
    assert "already wired" in capsys.readouterr().out

    cfg = json.loads((tmp_path / ".codex" / "hooks.json").read_text())
    pre = cfg["hooks"]["PreToolUse"]
    assert len(pre) == 1 and len(pre[0]["hooks"]) == 1


def test_hook_install_merges_existing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    main(["init"])
    cfg_dir = tmp_path / ".claude"
    cfg_dir.mkdir()
    (cfg_dir / "settings.json").write_text(json.dumps({"model": "opus", "hooks": {}}))
    main(["hook", "install"])

    cfg = json.loads((cfg_dir / "settings.json").read_text())
    assert cfg["model"] == "opus"
    assert cfg["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == "quicksave hook"


def test_save_without_init_exits(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    try:
        main(["save"])
    except SystemExit as e:
        assert e.code == 1
    else:
        raise AssertionError("expected SystemExit")
