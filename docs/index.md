# `jjh`: Tooling for using a jj workflow on github

![Python Version](https://img.shields.io/badge/python-3.14-blue)
![License - MIT](https://img.shields.io/badge/license-MIT-green)
[![CI](https://github.com/RadarML/jjh/actions/workflows/ci.yml/badge.svg)](https://github.com/RadarML/jjh/actions/workflows/ci.yml)
![GitHub issues](https://img.shields.io/github/issues/RadarML/jjh)

`jjh` is a command line tool for using a [jj](https://github.com/jj-vcs/jj) workflow on github.

## Install

!!! info "`jjh` is a CLI tool only"

    `jjh` is not a library; install it as a standalone tool with [`uv`](https://docs.astral.sh/uv/getting-started/installation/).

```sh
uv tool install git+ssh://git@github.com/RadarML/jjh.git
jjh --help
```

Or run it without installing:
```sh
uvx --from git+ssh://git@github.com/RadarML/jjh.git jjh --help
```

To upgrade an installed copy:
```sh
uv tool upgrade jjh
```
