"""`jjh check`: find PR graph problems, and optionally fix them."""

from dataclasses import dataclass
from enum import Enum

from jjh.context import Context
from jjh.jj import DIFFBASE_PREFIX
from jjh.run import info
from jjh.stack import Snapshot

from .diffbase import diffbase_add, diffbase_owner, diffbase_rm
from .sync import sync


class Kind(Enum):
    """Kinds of problems `check` reports."""

    CONFLICTED = "conflicted"
    UNPUSHED = "unpushed"
    DELETED = "deleted"
    BASE = "base"
    NO_BASE = "no-base"
    NO_DIFFBASE = "no-diffbase"
    SPENT_DIFFBASE = "spent-diffbase"
    ORPHAN_DIFFBASE = "orphan-diffbase"
    SKIPPED = "skipped"
    STALE = "stale"
    MERGED_ELSEWHERE = "merged-elsewhere"
    DRAFT_ON_MAIN = "draft-on-main"
    READY_ON_BRANCH = "ready-on-branch"


DIFFBASE_KINDS = {Kind.NO_DIFFBASE, Kind.SPENT_DIFFBASE, Kind.ORPHAN_DIFFBASE}
"""Diffbase problems, which `check --fix` fixes before anything else."""

FIXABLE = {Kind.UNPUSHED, Kind.DELETED, Kind.BASE} | DIFFBASE_KINDS
"""Kinds that `check --fix` fixes."""


@dataclass(frozen=True)
class Finding:
    """One problem found by `check`.

    Attributes:
        kind: what kind of problem this is.
        subject: the PR (`#94 dev/examples`) or bookmark it is about.
        message: what is wrong, and how to fix it by hand.
        pr: PR number, if the problem is about a PR.
        base: the base the PR should have, for `Kind.BASE`.
        rev: what a diffbase fix acts on: the PR's bookmark, or for
            `Kind.ORPHAN_DIFFBASE` the diffbase's change id.
    """

    kind: Kind
    subject: str
    message: str
    pr: int | None = None
    base: str | None = None
    rev: str | None = None

    def __str__(self) -> str:
        return f"{self.subject}: {self.message}"


def find_problems(snap: Snapshot) -> list[Finding]:
    """Everything `check` reports, without changing anything."""
    out: list[Finding] = []
    default = snap.repo.default_branch

    for b in snap.bookmarks.values():
        if b.conflicted:
            out.append(Finding(
                Kind.CONFLICTED, f"{b.name}??",
                "local and remote both moved; pick one with `jj bookmark set`"))
        elif b.unpushed:
            out.append(Finding(
                Kind.UNPUSHED, f"{b.name}*",
                "differs from GitHub; push with `jj git push --tracked`"))
        elif b.deleted:
            out.append(Finding(
                Kind.DELETED, b.name,
                "deleted locally but not on GitHub; push with `jj git push --deleted`"))

    for pr in sorted(snap.open_prs.values(), key=lambda p: p.number):
        commit = snap.local_commit(pr.head)
        if commit is None:
            continue
        subject = f"#{pr.number} {pr.head}"
        base = snap.expected_base(commit)
        if base.name is None and commit.is_merge:
            out.append(Finding(
                Kind.NO_DIFFBASE, subject,
                f"{base.problem}; add one with `jjh diffbase add {pr.head}`",
                pr=pr.number, rev=pr.head))
        elif base.name is None:
            out.append(Finding(Kind.NO_BASE, subject, f"{base.problem}", pr=pr.number))
        elif base.name != pr.base:
            out.append(Finding(
                Kind.BASE, subject,
                f"based on {pr.base}, but the bookmark below it is {base.name}; "
                f"`gh pr edit {pr.number} --base {base.name}`",
                pr=pr.number, base=base.name))
        if base.skipped:
            ids = ", ".join(snap.commits[c].change_id[:8] for c in base.skipped)
            out.append(Finding(
                Kind.SKIPPED, subject,
                f"commits without a bookmark below it ({ids}) are part of its diff; "
                "squash them or give them their own PR", pr=pr.number))

        lower = snap.remote_commit(pr.base)
        upper = snap.remote_commit(pr.head)
        if lower is not None and upper is not None and not snap.is_ancestor(
                lower.commit_id, upper.commit_id):
            out.append(Finding(
                Kind.STALE, subject,
                f"its branch on GitHub is not on top of {pr.base}, so its diff shows "
                "old changes; push with `jj git push --tracked`", pr=pr.number))

        if pr.base == default and pr.is_draft:
            out.append(Finding(
                Kind.DRAFT_ON_MAIN, subject,
                f"draft based on {default}; `gh pr ready {pr.number}` when it is ready",
                pr=pr.number))
        elif pr.base != default and not pr.is_draft:
            out.append(Finding(
                Kind.READY_ON_BRANCH, subject,
                f"not a draft, so it can be merged into {pr.base} by accident; "
                f"`gh pr ready --undo {pr.number}`", pr=pr.number))

    for name in sorted(snap.bookmarks):
        d = snap.local_commit(name)
        if not name.startswith(DIFFBASE_PREFIX) or d is None or not d.is_diffbase:
            continue
        owner = diffbase_owner(d)
        above = snap.local_commit(owner)
        if above is None or d.commit_id not in above.parents:
            out.append(Finding(
                Kind.ORPHAN_DIFFBASE, name,
                f"{owner} is no longer on it; `jj abandon {d.change_id[:8]}`, then "
                "`jj git push --deleted`", rev=d.change_id))
        elif sum(p in snap.commits for p in d.parents) <= 1:
            out.append(Finding(
                Kind.SPENT_DIFFBASE, name,
                f"only one parent left, so {owner} doesn't need it; "
                f"`jjh diffbase rm {owner}`", rev=owner))

    for pr in snap.prs:
        base = snap.bookmarks.get(pr.base)
        if pr.state == "MERGED" and pr.base != default and base is not None and base.adopted:
            out.append(Finding(
                Kind.MERGED_ELSEWHERE, f"#{pr.number} {pr.head}",
                f"was merged into {pr.base}, not {default}; see "
                "'Recovering from an accidental merge' in the docs", pr=pr.number))
    return out


def check(ctx: Context, *, fix: bool = False, fetch: bool = True) -> list[Finding]:
    """Report problems; with `fix`, fix what can be fixed mechanically.

    Args:
        ctx: repository context.
        fix: add, remove or abandon diffbases as needed, push unpushed
            bookmarks, retarget PRs, push deletions, then sync.
        fetch: run `jj git fetch` first.

    Returns:
        The problems that remain.
    """
    if fetch and fix:
        ctx.jj.fetch()
    snap = ctx.snapshot()
    problems = find_problems(snap)
    for p in problems:
        info(f"{'fixing' if fix and p.kind in FIXABLE else '-'} {p}")
    if not problems:
        info("No problems found.")
    if not fix:
        return problems

    if any(p.kind in DIFFBASE_KINDS for p in problems):
        for p in problems:
            if p.rev is None:
                continue
            if p.kind == Kind.NO_DIFFBASE:
                diffbase_add(ctx, p.rev)
            elif p.kind == Kind.SPENT_DIFFBASE:
                diffbase_rm(ctx, p.rev)
            elif p.kind == Kind.ORPHAN_DIFFBASE:
                ctx.jj.abandon(p.rev)
        # Those rewrote commits and moved bookmarks; fix what they left behind.
        problems = [
            p for p in find_problems(ctx.snapshot()) if p.kind not in DIFFBASE_KINDS]

    if any(p.kind == Kind.UNPUSHED for p in problems):
        ctx.jj.push(tracked=True)
    for p in problems:
        if p.kind == Kind.BASE:
            assert p.pr is not None and p.base is not None
            ctx.gh.edit(p.pr, base=p.base)
    if any(p.kind == Kind.DELETED for p in problems):
        ctx.jj.push(deleted=True)
    sync(ctx, fetch=False)

    remaining = [p for p in problems if p.kind not in FIXABLE]
    if remaining:
        info(f"{len(remaining)} problem(s) need a decision; see above.")
    return remaining
