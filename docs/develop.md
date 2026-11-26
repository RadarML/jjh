# Development Environment

!!! info "`jjh` uses `uv`"

    While `pyproject.toml` reflects known limitations on dependency versions, we use `uv` to manage a lock file used for development.

    On a fresh linux install, you will need to [install `uv`](https://docs.astral.sh/uv/getting-started/installation/):
    ```sh
    curl -LsSf https://astral.sh/uv/install.sh | sh
    source ~/.bashrc
    ```

## Setup

```sh
git clone git@github.com:RadarML/jjh.git
cd jjh
uv sync --extra dev --frozen
uv run pre-commit install
```

Run the development copy of the CLI:
```sh
uv run jjh --help
```

Or install the development copy as an editable tool:
```sh
uv tool install --editable .
```

## Adding Commands

Each subcommand is a plain function whose arguments are parsed by [tyro](https://brentyi.github.io/tyro/); register it in `COMMANDS` in `src/jjh/cli.py`. The first paragraph of the function's docstring is shown in `jjh --help`, and the arguments' docstrings are shown in `jjh <command> --help`. Add a corresponding section to `docs/cli.md`.

## Tests

Run tests:
```sh
uv run --extra dev pytest -ra --cov --cov-report=html --cov-report=term -- tests
```

!!! tip

    HTML-format code coverage is saved to `./htmlcov`; view these with `cd htmlcov; python -m http.server 8001`.

!!! info

    The tests are also run by our [pre-commit](https://pre-commit.com/) hooks, which you can manually trigger with `uv run pre-commit run`; these hooks (`ruff + pyright + pytest`) mirror the CI.

## Docs

Build docs for development:
```sh
uv run --extra docs zensical serve
```

!!! info

    The [documentation site](https://radarml.github.io/jjh) is automatically built and deployed via GitHub Actions when a PR is merged.
