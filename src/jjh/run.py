"""Subprocess helpers shared by the jj and GitHub wrappers."""

import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


class JJHError(Exception):
    """An error to show the user without a traceback."""


def info(msg: str) -> None:
    """Print a progress or result message."""
    print(msg, flush=True)


def warn(msg: str) -> None:
    """Print a warning to stderr."""
    print(f"warning: {msg}", file=sys.stderr, flush=True)


@dataclass
class Runner:
    """Runs external commands.

    Attributes:
        cwd: working directory for every command.
        dry_run: print mutating commands instead of running them.
        echo: print mutating commands to stderr before running them.
        env: extra environment variables (used by tests).
    """

    cwd: Path | None = None
    dry_run: bool = False
    echo: bool = True
    env: dict[str, str] | None = None

    def __call__(
        self, args: list[str], *, mutates: bool = False, input: str | None = None,
    ) -> str:
        """Run a command and return its stdout.

        Mutating commands are printed to stderr before they run. In dry-run
        mode they are only printed, and return an empty string.
        """
        if mutates and (self.echo or self.dry_run):
            prefix = "(dry run) " if self.dry_run else ""
            print(f"{prefix}$ {shlex.join(args)}", file=sys.stderr, flush=True)
        if mutates and self.dry_run:
            return ""

        env = None
        if self.env is not None:
            env = {**os.environ, **self.env}
        try:
            proc = subprocess.run(
                args, cwd=self.cwd, input=input, capture_output=True, text=True, env=env)
        except FileNotFoundError as e:
            raise JJHError(f"`{args[0]}` is not installed or not on PATH") from e
        if proc.returncode != 0:
            raise JJHError(
                f"`{shlex.join(args)}` failed (exit {proc.returncode}):\n"
                f"{proc.stderr.strip() or proc.stdout.strip()}")
        return proc.stdout
