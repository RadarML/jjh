"""`jjh` command line entry point."""

import sys
from collections.abc import Callable
from importlib.metadata import version as _pkg_version
from typing import Annotated, Any, Literal, Union

import tyro

from .commands.adopt import adopt, release
from .commands.check import check
from .commands.diffbase import diffbase_add, diffbase_rm
from .commands.land import land
from .commands.pr import open_pr
from .commands.sync import sync
from .context import Context
from .run import JJHError

Pos = tyro.conf.Positional
Target = Annotated[str, tyro.conf.arg(metavar="PR|BOOKMARK")]


def cli_version() -> None:
    """Print the installed `jjh` version."""
    print(_pkg_version("jjh"))


def cli_sync(
    pull: bool = True, take: Literal["commit", "pr"] | None = None, fetch: bool = True,
    dry_run: bool = False, remote: str = "origin",
) -> int:
    """Sync PR titles and descriptions with their commits, and regenerate graph sections.

    Works on every open PR whose bookmark exists locally (your PRs, and PRs in
    graphs you have adopted). For each of your own PRs, the commit description
    and the PR text are compared with the hash stored at the last sync:

    - only the commit changed: the PR's title and body are updated;
    - only the PR changed: the commit description is updated (unless `--no-pull`);
    - both changed: nothing is changed on that PR, and it is reported (unless
      `--take` picks a side);
    - neither changed: only the graph section is regenerated.

    On PRs other people opened, only the graph section changes. `gh pr edit`
    is only called on PRs whose title or body actually changes.

    Exits with status 1 if any PR has conflicting edits.

    Args:
        pull: copy PR text edited on GitHub into the commit descriptions. This
            rewrites the commits, so the next push force-pushes them and every
            PR above them. With `--no-pull`, edited PRs are only listed.
        take: for PRs changed both locally and on GitHub since the last sync,
            keep the commit's text (`commit`) or the PR's (`pr`) instead of
            reporting a conflict.
        fetch: run `jj git fetch` first.
        dry_run: print the jj and gh commands that would change anything,
            instead of running them.
        remote: git remote that holds the PR branches.
    """
    ctx = Context.create(dry_run=dry_run, remote=remote)
    return 1 if sync(ctx, pull=pull, fetch=fetch, take=take).conflicts else 0


def cli_pr(
    bookmark: Pos[Annotated[str, tyro.conf.arg(metavar="BOOKMARK")]],
    rev: Annotated[str, tyro.conf.arg(aliases=["-r"])] = "@",
    reviewer: tuple[str, ...] = (), dry_run: bool = False,
    remote: str = "origin",
) -> None:
    """Bookmark a commit, push it and open its PR.

    The PR is based on the bookmark directly below the commit (or the default
    branch), and is a draft unless it is based on the default branch. If the
    commit has two parents, a diffbase is added first and the PR is based on
    it. The PR's title and body come from the commit description; `sync`
    then adds the graph section to every PR in the graph.

    Args:
        bookmark: the bookmark (PR head branch) to create, such as
            `fix/empty-input`.
        rev: the commit to open a PR for.
        reviewer: GitHub users to request reviews from (repeatable).
        dry_run: print the jj and gh commands that would change anything,
            instead of running them.
        remote: git remote that holds the PR branches.
    """
    ctx = Context.create(dry_run=dry_run, remote=remote)
    open_pr(ctx, bookmark, rev=rev, reviewers=reviewer)


def cli_check(
    fix: bool = False, dry_run: bool = False, remote: str = "origin",
) -> int:
    """Report problems with the PR graphs; with `--fix`, fix the mechanical ones.

    Reports:

    - bookmarks that differ from GitHub (`name*`), are conflicted (`name??`),
      or were deleted locally but not on GitHub;
    - PRs whose base doesn't match the bookmark below them in `jj log`;
    - merge commits without a diffbase, diffbases left with one parent, and
      diffbases no longer below their PR's commit;
    - unbookmarked commits inside a PR;
    - upper PRs whose branch on GitHub is not on top of their base;
    - PRs merged into a branch other than the default branch;
    - drafts based on the default branch, and non-drafts based on another PR.

    Without `--fix` this changes nothing (it doesn't even fetch), so agents
    can run it at any time. Exits with status 1 if problems remain.

    Args:
        fix: fetch, add, remove or abandon diffbases as needed, push with
            `--tracked`, retarget mismatched PRs, push deletions with
            `--deleted`, then run `sync`.
        dry_run: print the jj and gh commands that would change anything,
            instead of running them.
        remote: git remote that holds the PR branches.
    """
    ctx = Context.create(dry_run=dry_run, remote=remote)
    return 1 if check(ctx, fix=fix) else 0


def cli_adopt(target: Pos[Target], dry_run: bool = False, remote: str = "origin") -> None:
    """Adopt a PR graph: track every bookmark in it so you can work on it here.

    Fetches, finds the graph from the commits (`trunk()..(roots(trunk()..<head>@origin)::)`),
    and tracks every remote bookmark in it, diffbases included. Adopting is
    idempotent: adopt again to pick up PRs someone added to the graph.

    Adopted bookmarks are co-owned: they rebase with your edits and are
    pushed by `jj git push --tracked`.

    Args:
        target: a PR number (`94` or `#94`) or a bookmark in the graph.
        dry_run: print the jj commands that would change anything, instead of
            running them.
        remote: git remote that holds the PR branches.
    """
    adopt(Context.create(dry_run=dry_run, remote=remote), target)


def cli_release(
    target: Pos[Target], force: bool = False, dry_run: bool = False, remote: str = "origin",
) -> None:
    """Release a PR graph: forget its local bookmarks and untrack them.

    Nothing is deleted on GitHub. Refuses if a bookmark in the graph has
    changes that aren't pushed.

    Args:
        target: a PR number (`94` or `#94`) or a bookmark in the graph.
        force: release even if some bookmarks have unpushed changes.
        dry_run: print the jj commands that would change anything, instead of
            running them.
        remote: git remote that holds the PR branches.
    """
    release(Context.create(dry_run=dry_run, remote=remote), target, force=force)


def cli_land(dry_run: bool = False, remote: str = "origin") -> None:
    """Clean up after PRs were merged on GitHub.

    Fetches; rebases each landed commit and everything above it onto trunk with
    `--skip-emptied` (so the landed commits drop out); removes diffbases that
    are down to one unlanded parent, retargeting their PRs before the
    deletion is pushed; pushes; retargets PRs that GitHub didn't; marks PRs
    now based on the default branch as ready for review; then runs `sync`.

    It does not merge anything: merge on GitHub, bottom-up, then run this.

    Args:
        dry_run: print the jj and gh commands that would change anything,
            instead of running them.
        remote: git remote that holds the PR branches.
    """
    land(Context.create(dry_run=dry_run, remote=remote))


def cli_diffbase(
    action: Pos[Literal["add", "rm"]],
    bookmark: Pos[Annotated[str, tyro.conf.arg(metavar="BOOKMARK")]], dry_run: bool = False,
    remote: str = "origin",
) -> None:
    """Add or remove the diffbase below a merge-commit PR.

    `add` inserts an empty merge commit `jj-diffbase/<bookmark>` below the PR's
    commit, pushes it and retargets the PR onto it, so the PR's diff shows
    only its own change. `rm` removes it once all but one of its parents have
    landed: it rebases the PR onto the remaining parent, abandons the
    diffbase, retargets the PR, and pushes the deletion last (GitHub closes a
    PR whose base branch is deleted). `jjh pr`, `jjh land` and
    `jjh check --fix` run these for you.

    Args:
        action: `add` or `rm`.
        bookmark: the PR's bookmark.
        dry_run: print the jj and gh commands that would change anything,
            instead of running them.
        remote: git remote that holds the PR branches.
    """
    ctx = Context.create(dry_run=dry_run, remote=remote)
    if action == "add":
        diffbase_add(ctx, bookmark)
    else:
        diffbase_rm(ctx, bookmark)
    sync(ctx, fetch=False)


COMMANDS: dict[str, Callable[..., object]] = {
    "sync": cli_sync,
    "pr": cli_pr,
    "check": cli_check,
    "adopt": cli_adopt,
    "release": cli_release,
    "land": cli_land,
    "diffbase": cli_diffbase,
    "version": cli_version,
}


def _summary(f: Callable[..., object]) -> str:
    """First paragraph of a function's docstring, for `jjh --help`."""
    return " ".join((f.__doc__ or "").strip().split("\n\n")[0].split())


def main() -> None:
    """Run the `jjh` CLI."""
    # Like `tyro.extras.subcommand_cli_from_dict`, but `jjh --help` lists only
    # the first paragraph of each command's docstring.
    subcommands = tuple(
        Annotated[Any, tyro.conf.subcommand(name=k, constructor=f, description=_summary(f))]
        for k, f in COMMANDS.items())
    try:
        status = tyro.cli(
            Union[subcommands],  # type: ignore
            prog="jjh", description="Tooling for using a jj workflow on github.")
    except JJHError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
    if isinstance(status, int) and status:
        sys.exit(status)
