"""`jjh sync`: two-way sync of commit descriptions and PR text."""

from dataclasses import dataclass, field
from typing import Literal

from jjh import description as desc
from jjh.context import Context
from jjh.github import PullRequest
from jjh.run import info, warn
from jjh.stack import Snapshot

Take = Literal["commit", "pr"]
"""Which side wins when a PR changed both locally and on GitHub."""


@dataclass
class SyncResult:
    """What `sync` did, by PR number.

    Attributes:
        pushed: PRs whose title and body were updated from their commit.
        pulled: PRs whose commit description was updated from the PR.
        edited: PRs edited on GitHub that were left alone (`pull=False`).
        conflicts: PRs changed on both sides; nothing was changed on them.
        updated: PRs that `gh pr edit` was called on.
    """

    pushed: list[int] = field(default_factory=list)
    pulled: list[int] = field(default_factory=list)
    edited: list[int] = field(default_factory=list)
    conflicts: list[int] = field(default_factory=list)
    updated: list[int] = field(default_factory=list)


@dataclass
class _Plan:
    pr: PullRequest
    title: str | None = None
    text: str | None = None
    synced: str | None = None


def _plan(
    ctx: Context, snap: Snapshot, pr: PullRequest, pull: bool, take: Take | None,
    result: SyncResult,
) -> _Plan | None:
    """Decide what to do with one PR; runs `jj describe` when pulling."""
    commit = snap.local_commit(pr.head)
    assert commit is not None
    title, body = desc.split(commit.description)
    text, stored = desc.strip_section(pr.body)

    if pr.author != snap.repo.viewer:
        return _Plan(pr, synced=stored)
    if not title:
        warn(f"#{pr.number} {pr.head}: the commit has no description; updating the graph only")
        return _Plan(pr, synced=stored)

    commit_hash = desc.text_hash(title, body)
    pr_hash = desc.text_hash(pr.title, text)
    action = desc.decide(commit_hash, pr_hash, stored)
    if action is desc.Action.CONFLICT and take is not None:
        action = desc.Action.PUSH if take == "commit" else desc.Action.PULL
        pull = pull or take == "pr"
    match action:
        case desc.Action.NOTHING:
            return _Plan(pr, synced=commit_hash)
        case desc.Action.PUSH:
            result.pushed.append(pr.number)
            return _Plan(pr, title=title, text=body, synced=commit_hash)
        case desc.Action.PULL if pull:
            result.pulled.append(pr.number)
            ctx.jj.describe(commit.change_id, desc.join(pr.title, text))
            return _Plan(pr, synced=pr_hash)
        case desc.Action.PULL:
            result.edited.append(pr.number)
            return _Plan(pr, synced=stored)
        case desc.Action.CONFLICT:
            result.conflicts.append(pr.number)
            return None


def sync(
    ctx: Context, *, pull: bool = False, fetch: bool = True, take: Take | None = None,
) -> SyncResult:
    """Sync every adopted PR's title and body with its commit, and regenerate graphs.

    Args:
        ctx: repository context.
        pull: copy PR text edited on GitHub into the commit descriptions.
        fetch: run `jj git fetch` first.
        take: for PRs changed on both sides, keep this side's text instead of
            reporting a conflict.
    """
    if fetch:
        ctx.jj.fetch()
    snap = ctx.snapshot()
    result = SyncResult()

    prs = [
        pr for pr in sorted(snap.open_prs.values(), key=lambda p: p.number)
        if snap.local_commit(pr.head) is not None]
    for pr in prs:
        if snap.bookmarks[pr.head].unpushed:
            warn(
                f"#{pr.number} {pr.head} has unpushed changes (`{pr.head}*`); the graph "
                "shows your local version. Run `jj git push --tracked`.")

    plans = [p for pr in prs if (p := _plan(ctx, snap, pr, pull, take, result)) is not None]
    if result.pulled and not ctx.dry_run:
        # `jj describe` rewrote commits; reload so the graphs use the new ids.
        snap = ctx.snapshot(prs=snap.prs)

    for plan in plans:
        pr = plan.pr
        head = snap.local_commit(pr.head)
        assert head is not None
        section = desc.render_section(ctx.graph_text(snap, head.commit_id), plan.synced)
        if plan.text is not None:
            body = desc.pr_body(plan.text, section)
        else:
            body = desc.set_section(pr.body, section)
        title = plan.title if plan.title is not None and plan.title != pr.title else None
        if title is not None or body != pr.body:
            ctx.gh.edit(pr.number, title=title, body=body if body != pr.body else None)
            result.updated.append(pr.number)

    _report(result)
    return result


def _report(result: SyncResult) -> None:
    def nums(xs: list[int]) -> str:
        return ", ".join(f"#{n}" for n in xs)

    if result.pushed:
        info(f"Updated PR text from commits: {nums(result.pushed)}")
    if result.pulled:
        info(
            f"Updated commit descriptions from PRs: {nums(result.pulled)}. "
            "Push with `jj git push --tracked` (this force-pushes the PRs above them).")
    if result.edited:
        info(
            f"Edited on GitHub, not pulled: {nums(result.edited)}. "
            "Run `jjh sync` to copy the edits into the commits.")
    if result.conflicts:
        warn(
            f"Changed both locally and on GitHub since the last sync: {nums(result.conflicts)}. "
            "Left untouched; rerun with `--take commit` to keep the commit's text, or "
            "`--take pr` to keep the PR's.")
    if result.updated:
        info(f"Edited PRs: {nums(result.updated)}")
    else:
        info("All PRs up to date.")
