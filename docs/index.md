# `jjh`: Tooling for using a jj workflow on github

[![Version](https://img.shields.io/github/v/release/RadarML/jjh)](https://github.com/RadarML/jjh/releases)
![Python Version](https://img.shields.io/badge/python-3.14-blue)
![License - MIT](https://img.shields.io/badge/license-MIT-green)
[![CI](https://github.com/RadarML/jjh/actions/workflows/ci.yml/badge.svg)](https://github.com/RadarML/jjh/actions/workflows/ci.yml)
![GitHub issues](https://img.shields.io/github/issues/RadarML/jjh)

`jjh` is a tool and workflow for using [jj](https://github.com/jj-vcs/jj) on GitHub.

- Each PR is a single commit with a bookmark, and the bookmark is the PR's head branch.
- A PR's base is the bookmark directly below it. A commit with two parents gets a [diffbase](workflow.md#merge-commits) commit so that GitHub shows a clean diff.
- The PR title and body are automatically set from the `jj` commit description, with two-way sync via `jjh sync`.

## Install

`jjh` is a CLI tool only (not a library), and should be installed with [`uv`](https://docs.astral.sh/uv/getting-started/installation/). It requires [jj](https://jj-vcs.github.io/jj/latest/install-and-setup/) and an authenticated [`gh`](https://cli.github.com/).

```sh
uv tool install git+ssh://git@github.com/RadarML/jjh.git
jjh --help
```

Or run it without installing:
```sh
uvx --from git+ssh://git@github.com/RadarML/jjh.git jjh --help
```

To upgrade:
```sh
uv tool upgrade jjh
```

## Agent Skill

`jjh` includes an [agent skill](https://agentskills.io) that teaches coding agents this workflow. Install it with [`gh skill`](https://cli.github.com/manual/gh_skill):

```sh
gh skill install RadarML/jjh jjh --agent claude-code --scope user
```

- `--agent` defaults to GitHub Copilot when run non-interactively; see `gh skill install --help` for other agents.
- `--scope project` installs the skill into the current repository instead, so it can be committed and every contributor's agent gets it.
- `gh skill update jjh` updates it to the latest release.

Agents only load a skill when they judge that its description matches the task. To make sure they do, add this to the `CLAUDE.md` or `AGENTS.md` of each repository that uses `jjh`:

```md
This repository uses the jjh workflow (https://radarml.github.io/jjh). Load the `jjh` skill before describing commits, pushing, or opening or updating PRs. Don't use gh-stack here.
```

## Commands

For more details, see the [CLI reference](cli.md).

| Command | Description | Workflow |
| --- | --- | --- |
| `jjh pr <bookmark> [-r <rev>]` | Bookmark a commit, push it, and open a PR against the bookmark below it (adding a diffbase if it has two parents) | [GitHub PRs](workflow.md#github-prs) |
| `jjh sync [--no-pull]` | Sync PR titles and bodies with commit messages in both directions; regenerate each PR's graph | [Descriptions](workflow.md#descriptions) |
| `jjh check [--fix]` | Report (and fix) wrong bases, unpushed or conflicted bookmarks, and stale PRs | [Push Changes](workflow.md#push-changes) |
| `jjh adopt <pr>` / `jjh release <pr>` | Start or stop co-owning a PR graph by tracking every bookmark in it | [Collaborative Coding](workflow.md#collaborative-coding) |
| `jjh land` | After merging on GitHub: rebase the rest onto main, remove diffbases, retarget, and mark ready | [Landing](workflow.md#landing-dependent-prs) |
| `jjh diffbase add\|rm <bookmark>` | Add or remove a merge commit's diffbase by hand | [Merge Commits](workflow.md#merge-commits) |

## Example

```sh
jj new main -m "Add a config parser"                      # write a change
jjh pr dev/parser                                         # open its PR
jj new dev/parser -m "Add a command line for the parser"  # add a change on top of it
jjh pr dev/parser-cli                                     # open a PR based on dev/parser

jj new dev/parser                                         # address review comments in a new commit
jj squash                                                 # fold them into dev/parser
jj git push --tracked                                     # push every rewritten bookmark
jjh check --fix                                           # retarget PRs and sync descriptions

# merge dev/parser on GitHub
jjh land                                                  # rebase dev/parser-cli onto main and retarget it
```
