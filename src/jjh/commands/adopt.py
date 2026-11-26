"""`jjh adopt` / `jjh release`: start or stop working on a PR graph."""

from jjh.context import Context
from jjh.jj import Commit
from jjh.run import JJHError, info
from jjh.stack import Snapshot


def _head(snap: Snapshot, target: str) -> tuple[str, Commit]:
    """Resolve a PR number (`94`, `#94`) or bookmark to its head bookmark and commit."""
    name = target
    number = target.removeprefix("#")
    if number.isdigit():
        pr = next((p for p in snap.prs if p.number == int(number)), None)
        if pr is None:
            raise JJHError(f"No open or recently merged PR #{number}")
        name = pr.head
    commit = snap.remote_commit(name) or snap.local_commit(name)
    if commit is None:
        raise JJHError(f"{name} is not a bookmark above trunk, here or on GitHub")
    return name, commit


def adopt(ctx: Context, target: str) -> list[str]:
    """Track every bookmark in the PR graph containing `target`.

    Args:
        ctx: repository context.
        target: a PR number or bookmark in the graph.

    Returns:
        The bookmarks that were newly tracked.
    """
    ctx.jj.fetch()
    snap = ctx.snapshot()
    name, commit = _head(snap, target)
    names = snap.graph_bookmarks(commit.commit_id)
    new = [
        n for n in names
        if snap.bookmarks[n].remote and not snap.bookmarks[n].tracked]
    if new:
        ctx.jj.track(*new)
        info(f"Tracking {len(new)} bookmark(s): {', '.join(new)}")
    else:
        info(f"Already tracking every bookmark in {name}'s graph.")
    info(f"Start working with `jj new {name}`.")
    return new


def release(ctx: Context, target: str, *, force: bool = False) -> list[str]:
    """Forget the local bookmarks of a PR graph and untrack them.

    Nothing is deleted on GitHub; the branches remain as untracked remote
    bookmarks, so they drop out of `jj log`.

    Args:
        ctx: repository context.
        target: a PR number or bookmark in the graph.
        force: release even if some bookmarks have unpushed changes.

    Returns:
        The bookmarks that were released.
    """
    snap = ctx.snapshot()
    name, commit = _head(snap, target)
    bookmarks = [snap.bookmarks[n] for n in snap.graph_bookmarks(commit.commit_id)]
    unpushed = [b.name for b in bookmarks if b.unpushed or (b.local and not b.remote)]
    if unpushed and not force:
        raise JJHError(
            f"Unpushed changes on {', '.join(unpushed)}; push them first "
            "(`jj git push --tracked`) or pass --force")
    names = [b.name for b in bookmarks if b.local or b.tracked]
    if names:
        ctx.jj.bookmark_forget(*names)
        info(f"Released {len(names)} bookmark(s): {', '.join(names)}")
    else:
        info(f"Nothing in {name}'s graph is adopted here.")
    return names
