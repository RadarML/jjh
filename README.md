# `jjh`: Tooling for using a jj workflow on github

[![Version](https://img.shields.io/github/v/release/RadarML/jjh)](https://github.com/RadarML/jjh/releases)
![Python Version](https://img.shields.io/badge/python-3.14-blue)
![License - MIT](https://img.shields.io/badge/license-MIT-green)
[![CI](https://github.com/RadarML/jjh/actions/workflows/ci.yml/badge.svg)](https://github.com/RadarML/jjh/actions/workflows/ci.yml)
![GitHub issues](https://img.shields.io/github/issues/RadarML/jjh)

`jjh` is a command line tool for using a [jj](https://github.com/jj-vcs/jj) workflow on github; see the [documentation](https://radarml.github.io/jjh) for the full workflow.

## Install

`jjh` is a CLI tool only (not a library), and should be installed with [`uv`](https://docs.astral.sh/uv/):

```sh
uv tool install git+ssh://git@github.com/RadarML/jjh.git
jjh --help
```

Or run it without installing:
```sh
uvx --from git+ssh://git@github.com/RadarML/jjh.git jjh --help
```

> [!NOTE]
> `jjh` requires Python 3.14 (`uv` will download it automatically if needed), [jj](https://jj-vcs.github.io/jj/latest/install-and-setup/), and an authenticated [`gh`](https://cli.github.com/).

## Development

See the [development guide](docs/develop.md); in short:
```sh
uv sync --extra dev --frozen
uv run pre-commit install
uv run --extra dev pytest -ra -- tests
```
