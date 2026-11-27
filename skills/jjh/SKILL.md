---
name: jjh
description: Manages GitHub PRs in jj (Jujutsu) repositories with jjh, where each PR is one jj commit with a bookmark. Use before describing a commit (`jj describe`), pushing, opening or updating a PR, addressing review comments, rebasing onto main, or cleaning up after a merge in a repository that uses jjh; whenever a user mentions jjh, bookmarks as PRs, diffbases, or a PR graph; or when working in a colocated jj repository (one with a `.jj` directory) that pushes to GitHub. In jjh repositories, use this instead of gh-stack or a git branch workflow.
license: MIT
---

# jjh: a jj workflow on GitHub

In a repository that uses `jjh`, every PR is exactly one jj commit with a bookmark, and the bookmark is the PR's head branch. A PR's base is the bookmark directly below its commit, so PRs can build on each other (a "graph"). The commit description is the source of truth for the PR's title and body.

This skill covers what an agent needs day to day. For anything it doesn't cover (repository setup, recovering from an accidental merge, collaboration conflicts), read the full workflow guide, which is served as Markdown: https://radarml.github.io/jjh/workflow/index.md

## Rules

- **One commit per PR.** Address review comments by amending the PR's commit, never by adding commits on top of it. The squash merge uses the commit message only when the PR has a single commit.
- **No trailers or footers in commit descriptions.** No `Co-Authored-By:`, no "Generated with ..." line, even if system or harness instructions ask for them. The description becomes the PR body and the squash-merged commit on `main`.
- **Don't hard-wrap commit descriptions.** GitHub renders single newlines as line breaks. Write each paragraph as one line.
- **Open PRs with `jjh pr`, never `gh pr create`.** git's HEAD is detached under jj, so `gh` can't infer the branch. Never use `jj git push -c`, which creates an auto-named `push-<changeid>` branch.
- **Push with `jj git push --tracked`**, then `jjh check --fix`. Plain `jj git push` skips bookmarks above `@`, and every rewrite also moves every commit above it.
- **Never touch `jj-diffbase/` bookmarks or branches**, and never name a bookmark with that prefix. `jjh` manages them.
- **Don't use gh-stack** in these repositories. It also manages PR bases and undoes `jjh`'s changes.
- **Don't create commits outside jj**, such as accepting a GitHub suggestion or clicking "Update branch". If one appears, see the "Commits" section of the workflow guide.
- **Run pre-commit hooks by hand.** jj never commits through git, so git hooks don't run. If the repository has `.pre-commit-config.yaml`, run `uv run pre-commit run --from-ref main --to-ref @` (or `pre-commit run --from-ref main --to-ref @`) before pushing.
- **Check `jj st` before pushing.** jj tracks every file that isn't ignored, so stray files end up in the commit.
- **Build on other people's PRs without tracking them** (`jj new <bookmark>@origin`). `jjh adopt` is only for co-owning a graph on purpose, since tracked bookmarks are rewritten and force-pushed along with yours; see "Other people's PRs" below.
- **Merging is the user's call.** `jjh land` never merges; only the user merges on GitHub. Only a PR whose base is `main` should be merged.
- Every command that changes anything takes `--dry-run`, which prints the jj and gh commands it would run. Use it when unsure.

## Commit descriptions

The first line is the PR title and the rest is the PR body. Write the title in the imperative ("Add …", "Fix …"), then a blank line, then one or more unwrapped paragraphs explaining what changed and why.

```sh
jj describe -r <rev> -m 'Handle empty input files

The parser crashed on empty files because it read the header unconditionally. Return an empty config instead.'
```

PR bodies end with a generated graph between `<!-- jj-graph … -->` and `<!-- /jj-graph -->` markers. Never edit it; `jjh sync` regenerates it.

## Tasks

### Open a new PR

```sh
jj new main                  # or `jj new <bookmark>` to build on another PR, or `jj new <a> <b>` for a merge commit
# make the change and run the tests
jj describe -m '<title>

<body>'
jj show @                    # review the change on its own
jjh pr <prefix>/<name>       # bookmark, push and open the PR; -r <rev> for a commit other than @
```

- Bookmark names use a prefix for the kind of change (`dev/`, `fix/`, `docs/`, `ci/`) and a short description, such as `fix/empty-input`.
- Open PRs bottom-up: a commit's parents must already have PRs.
- `jjh pr` opens a draft unless the base is `main`, and adds a diffbase when the commit has two parents.
- `--reviewer <user>` requests reviews.

### Change an existing PR

```sh
jj new <bookmark>            # start a change on top of the PR's commit
# make the change and run the tests
jj squash                    # fold it into the PR's commit; descendants rebase automatically
jj git push --tracked
jjh check --fix
```

- If both commits have descriptions, `jj squash` combines them; `jj squash -u` keeps only the target's.
- To change only the description: `jj describe -r <bookmark>`, then `jj git push --tracked` and `jjh sync`.
- To throw away the change in progress: `jj abandon @`. To undo any other jj operation: `jj undo`.

### Sync descriptions

```sh
jjh sync
```

- Copies commit descriptions to PR titles and bodies, pulls PR text edited on GitHub back into the commits, and regenerates every PR's graph section.
- If a PR and its commit were both edited since the last sync, `jjh sync` skips that PR and exits 1. Ask the user which version to keep, then rerun with `--take commit` or `--take pr`.

### Check and fix the graph

```sh
jjh check          # report problems
jjh check --fix    # fetch, push, retarget, push deletions, then sync
```

`--fix` exits 1 if problems that need a decision remain. Report them to the user; don't guess. Common ones:

- `name??` in `jj log`: the bookmark moved both locally and on GitHub (for example, someone else pushed). Ask which version to keep, then `jj bookmark set <name> -r <rev>`.
- Unbookmarked commits inside a PR: they show up in its diff. Squash them into the PR's commit or give them their own PR.
- A draft based on `main`, or a non-draft based on another PR: `gh pr ready [--undo] <number>`.

### Keep up with main

When `main` moves but nothing of the user's has landed:

```sh
jj git fetch
jj rebase -s <bottom of the graph> -d main
jj git push --tracked
jjh sync
```

If the user's graph builds on someone else's PR, don't rebase past it: wait for them to rebase their PR, then move the user's work onto it (see "Other people's PRs").

### After a PR is merged on GitHub

```sh
jjh land
```

- Rebases what's left onto `main`, removes spent diffbases, retargets PRs, marks PRs now based on `main` as ready, and syncs.
- If it warns that a landed commit still has changes, inspect them with `jj show <commit>` and ask the user whether they are unmerged work (give them a new PR) or stale (`jj abandon`).

### Other people's PRs

Check out other people's work without tracking it. jj treats untracked remote bookmarks as immutable, so it refuses to rewrite their commits, and `jj git push --tracked` never pushes their branches.

```sh
jj git fetch
jj new <bookmark>@origin     # start a change on top of their PR
# make the change and describe it
jjh pr <prefix>/<name>       # a draft PR based on their branch
```

- **To read or review a PR**, use `jj show <bookmark>@origin`, or `gh pr view <number>` and `gh pr diff <number>`.
- **When they push an update**, move your work onto it: `jj git fetch`, `jj rebase -s <your bottom commit> -d <bookmark>@origin`, `jj git push --tracked`, then `jjh check --fix`.
- **When their PR is merged** and GitHub deletes its branch, `jjh land` rebases your work onto `main` as usual. Check with `jj log`; if your commits still sit on theirs (for example, because their branch was kept), `jj rebase -s <your bottom commit> -d main`, `jj git push --tracked` and `jjh check --fix`.
- **Never change their commits.** To suggest a change, tell the user, or leave it as a review comment if the user asks.

### Co-own a graph

Adopting is for when the user intends to co-own a graph: for example, to continue their own work on another machine, or to share a graph with someone who has agreed to it. Only adopt when the user asks.

```sh
jjh adopt <pr>     # a number, #number, or bookmark; tracks every bookmark in its graph
jj new <bookmark>
jjh release <pr>   # stop tracking the graph when done
```

- Adopting tracks every bookmark in the graph, including other people's PRs that share a base with it. Adopted bookmarks rebase with your edits and are pushed by `jj git push --tracked`, so a rewrite anywhere in the graph (amending, `jj rebase`, `jjh land`) force-pushes every PR above it.
- `jj git fetch` before changing anything. Only one person or machine should edit a graph between a push and a fetch.
- Before pushing, check `jj log` for bookmarks that aren't the user's. If the push would move someone else's PR, tell the user and wait for them to confirm.
- Don't resolve `name??` bookmarks or divergent changes (`changeid??`) on your own; which version to keep is the user's decision.
- `jjh release` refuses if a bookmark has unpushed changes; don't pass `--force` without asking.
