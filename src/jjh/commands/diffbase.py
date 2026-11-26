"""`jjh diffbase add|rm`: manage the diffbase below a merge-commit PR."""

from dataclasses import replace

from jjh.context import Context
from jjh.jj import DIFFBASE_MARKER, bookmark_rev
from jjh.run import JJHError, info
from jjh.stack import diffbase_name


def diffbase_add(ctx: Context, bookmark: str, *, push: bool = True) -> str:
    """Insert a diffbase below a merge commit and point its PR at it.

    Args:
        ctx: repository context.
        bookmark: the PR's bookmark; its commit must have two or more parents.
        push: push the diffbase and the PR's bookmark, and retarget its PR.

    Returns:
        The diffbase bookmark's name.
    """
    commit = ctx.jj.commit(bookmark_rev(bookmark))
    if not commit.is_merge:
        raise JJHError(f"{bookmark} has one parent; it doesn't need a diffbase")
    name = diffbase_name(bookmark)
    ctx.jj.new_insert_before(commit.change_id, f"{DIFFBASE_MARKER} {bookmark}")
    ctx.jj.bookmark_create(name, f"{commit.change_id}-")
    info(f"Added diffbase {name} below {bookmark}")
    if push:
        ctx.jj.push(name, bookmark)
        pr = next((p for p in ctx.gh.pull_requests()
                   if p.head == bookmark and p.state == "OPEN"), None)
        if pr is not None:
            ctx.gh.edit(pr.number, base=name)
    return name


def diffbase_rm(ctx: Context, bookmark: str, *, push: bool = True) -> str:
    """Remove a PR's diffbase once all but one of its parents have landed.

    Rebases the PR's commit onto the remaining parent (or trunk), abandons
    the diffbase, retargets the PR, and only then pushes the deletion, since
    GitHub closes a PR whose base branch is deleted.

    The PR got the landed parents' changes through the diffbase, so the
    remaining parent's stack is first moved onto trunk if it isn't on it.

    Args:
        ctx: repository context.
        bookmark: the PR's bookmark.
        push: push the rewritten bookmarks and the deletion.

    Returns:
        The PR's new base.
    """
    snap = ctx.snapshot()
    commit = snap.local_commit(bookmark)
    if commit is None:
        raise JJHError(f"{bookmark} is not a local bookmark above trunk")
    diffbase = snap.commits.get(commit.parents[0])
    if diffbase is None or not diffbase.is_diffbase:
        raise JJHError(f"{bookmark} is not on a diffbase")
    remaining = [p for p in diffbase.parents if p in snap.commits]
    if len(remaining) > 1:
        raise JJHError(
            f"{bookmark}'s diffbase still has {len(remaining)} unlanded parents; "
            "land all but one first")

    base = snap.expected_base(
        replace(commit, parents=tuple(remaining) or diffbase.parents[:1]))
    if base.name is None:
        raise JJHError(f"Can't tell what {bookmark} should be based on: {base.problem}")

    dest = snap.commits[remaining[0]].change_id if remaining else "trunk()"
    if remaining and not ctx.jj.log(f"trunk() & ::{dest}"):
        ctx.jj.rebase(f"roots(trunk()..{dest})", "trunk()")
    ctx.jj.rebase(commit.change_id, dest)
    ctx.jj.abandon(diffbase.change_id)
    pr = snap.open_prs.get(bookmark)
    if pr is not None and pr.base != base.name:
        ctx.gh.edit(pr.number, base=base.name)
    if push:
        ctx.jj.push(tracked=True)
        ctx.jj.push(deleted=True)
    info(f"Removed {diffbase_name(bookmark)}; {bookmark} is now based on {base.name}")
    return base.name
