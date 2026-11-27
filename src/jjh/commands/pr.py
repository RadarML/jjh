"""`jjh pr`: open a PR for a commit."""

from jjh import description as desc
from jjh.context import Context
from jjh.jj import DIFFBASE_PREFIX
from jjh.run import JJHError, info, warn

from .diffbase import diffbase_add
from .sync import sync


def open_pr(
    ctx: Context, bookmark: str, *, rev: str = "@", reviewers: tuple[str, ...] = (),
) -> int:
    """Bookmark a commit, push it and open its PR.

    Args:
        ctx: repository context.
        bookmark: name for the bookmark (the PR's head branch).
        rev: the commit to open a PR for.
        reviewers: GitHub users to request reviews from.

    Returns:
        The new PR's number (0 in dry-run mode).
    """
    if bookmark.startswith(DIFFBASE_PREFIX):
        raise JJHError(f"{DIFFBASE_PREFIX} is reserved for diffbases")

    commit = ctx.jj.commit(rev)
    if commit.on_trunk:
        raise JJHError(f"{rev} is already on trunk")
    snap = ctx.snapshot(extra=commit.commit_id)
    if bookmark in snap.open_prs:
        raise JJHError(
            f"{bookmark} already has PR #{snap.open_prs[bookmark].number}; "
            "use `jjh sync` to update it")
    title, body = desc.split(commit.description)
    if not title:
        raise JJHError(f"{rev} has no description; write one with `jj describe`")
    if commit.empty:
        warn(f"{rev} is empty; did you mean `-r @-`?")

    existing = snap.bookmarks.get(bookmark)
    if existing is not None and existing.local and existing.target != commit.commit_id:
        raise JJHError(f"Bookmark {bookmark} already exists on another commit")

    if commit.is_merge:
        base = None
    else:
        expected = snap.expected_base(commit)
        if expected.name is None:
            raise JJHError(f"Can't tell what to base {bookmark} on: {expected.problem}")
        if expected.skipped:
            warn(
                f"{len(expected.skipped)} commit(s) without a bookmark sit between {rev} and "
                f"{expected.name}; they will be part of this PR's diff")
        base = expected.name
        lower = snap.bookmarks.get(base)
        if base != snap.repo.default_branch and (lower is None or not lower.remote):
            raise JJHError(f"The bookmark below, {base}, isn't on GitHub; open its PR first")

    if existing is None or not existing.local:
        ctx.jj.bookmark_create(bookmark, commit.change_id)
    if base is None:
        base = diffbase_add(ctx, bookmark, push=False)
        ctx.jj.push(base, bookmark)
    else:
        ctx.jj.push(bookmark)

    draft = base != snap.repo.default_branch
    number = ctx.gh.create(
        head=bookmark, base=base, title=title, body=body, draft=draft, reviewers=reviewers)
    if number:
        info(f"Opened {'draft ' if draft else ''}PR {snap.repo.pr_url(number)} (base {base})")
    sync(ctx, fetch=False)
    return number
