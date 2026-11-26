"""Tests for the `jjh` CLI entry point."""

import subprocess
import sys
from importlib.metadata import version

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
