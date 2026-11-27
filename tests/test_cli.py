"""Tests for the `jjh` CLI entry point."""

import subprocess
import sys
from importlib.metadata import version
from types import SimpleNamespace

import pytest

from jjh import cli


def test_version(capsys):
    cli.cli_version()
    assert capsys.readouterr().out.strip() == version("jjh")


def test_main_dispatch(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["jjh", "version"])
    cli.main()
    assert capsys.readouterr().out.strip() == version("jjh")


def test_main_help(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["jjh", "--help"])
    with pytest.raises(SystemExit) as e:
        cli.main()
    assert e.value.code == 0
    assert "version" in capsys.readouterr().out


def test_module_entrypoint():
    out = subprocess.run(
        [sys.executable, "-m", "jjh", "version"],
        capture_output=True, text=True, check=True)
    assert out.stdout.strip() == version("jjh")


@pytest.mark.parametrize(("args", "pull"), [([], True), (["--no-pull"], False)])
def test_sync_pulls_by_default(monkeypatch, args, pull):
    seen = {}

    def fake_sync(ctx, *, pull, fetch, take):
        seen["pull"] = pull
        return SimpleNamespace(conflicts=[])

    monkeypatch.setattr(cli, "sync", fake_sync)
    monkeypatch.setattr(cli.Context, "create", staticmethod(lambda **_: None))
    monkeypatch.setattr(sys, "argv", ["jjh", "sync", *args])
    cli.main()
    assert seen["pull"] is pull
