"""`jjh` command line entry point."""

from collections.abc import Callable
from importlib.metadata import version as _pkg_version

import tyro


def cli_version() -> None:
    """Print the installed `jjh` version."""
    print(_pkg_version("jjh"))


COMMANDS: dict[str, Callable[..., object]] = {
    "version": cli_version,
}


def main() -> None:
    """Run the `jjh` CLI."""
    tyro.extras.subcommand_cli_from_dict(
        COMMANDS, prog="jjh", description="Tooling for using a jj workflow on github.")
