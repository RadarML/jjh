"""`jjh land`: clean up after PRs have been merged on GitHub."""

from dataclasses import dataclass, field

from jjh.context import Context
from jjh.jj import DIFFBASE_MARKER, bookmark_rev
from jjh.run import info, warn

from .diffbase import diffbase_rm
from .sync import sync


@dataclass
class LandResult:
    """What `land` did.

    Attributes:
        landed: PR numbers whose commits were rebased away.
        diffbases: PRs whose diffbase was removed, by bookmark.
        retargeted: PR numbers whose base was changed.
        readied: PR numbers marked ready for review.
    """

    landed: list[int] = field(default_factory=list)
    diffbases: list[str] = field(default_factory=list)
    retargeted: list[int] = field(default_factory=list)
    readied: list[int] = field(default_factory=list)


def land(ctx: Context) -> LandResult:
    """Rebase what's left onto trunk after PRs were merged on GitHub.

    Args:
        ctx: repository context.
    """
    result = LandResult()
    before = ctx.jj.bookmarks()
    ctx.jj.fetch()
    prs = ctx.gh.pull_requests()
    default = ctx.repo.default_branch

    # Find the local commits of merged PRs.
    candidates: dict[int, list[str]] = {}
    for pr in prs:
        if pr.state != "MERGED":
            continue
        if pr.base != default:
            if pr.base in before and before[pr.base].adopted:
                warn(
                    f"#{pr.number} {pr.head} was merged into {pr.base}, not {default}; "
                    "see 'Recovering from an accidental merge' in the docs")
            continue
        ids = [i for i in (pr.head_oid, before.get(pr.head) and before[pr.head].target) if i]
        if ids:
            candidates[pr.number] = ids
    extra = " | ".join(f"present({i})" for ids in candidates.values() for i in ids)
    # A merged PR's head may already be hidden (landed by an earlier run). Naming a
    # hidden commit by id makes jj treat it as visible in `mutable()` and `all()`,
    # so restrict to ancestors of the visible heads explicitly.
    visible = f"({extra}) & ::visible_heads() & mutable()"
    snap = ctx.snapshot(prs=prs, extra=visible if extra else None)
    landed = {
        next(i for i in ids if i in snap.commits): n
        for n, ids in candidates.items() if any(i in snap.commits for i in ids)}

    # Rebase each landed commit (and everything above it) onto trunk.
    roots = [
        c for c in landed
        if not any(o != c and o in snap.ancestors(c) for o in landed)]
    for c in roots:
        ctx.jj.rebase(snap.commits[c].change_id, "trunk()", skip_emptied=True)
    result.landed = sorted(landed.values())
    if not ctx.dry_run:
        for c, n in landed.items():
            left = ctx.jj.log(f"present({snap.commits[c].change_id}) & mutable()")
            if left:
                cid = left[0].change_id[:8]
                warn(
                    f"#{n}'s commit {cid} still has changes after rebasing onto {default}, so "
                    f"what landed differs from your local version. Check it with `jj show {cid}`: "
                    "keep work that didn't land as a new change, or `jj abandon` it if "
                    f"{default} already has what you want")

    # Remove diffbases that are down to one unlanded parent.
    snap = ctx.snapshot(prs=prs)
    for d in snap.commits.values():
        if d.is_diffbase and sum(p in snap.commits for p in d.parents) <= 1:
            bookmark = d.description.removeprefix(DIFFBASE_MARKER).strip().split("\n")[0]
            if ctx.jj.log(f"present({bookmark_rev(bookmark)})"):
                diffbase_rm(ctx, bookmark, push=False)
                result.diffbases.append(bookmark)

    ctx.jj.push(tracked=True)
    if result.diffbases:
        ctx.jj.push(deleted=True)

    # Retarget PRs GitHub didn't, and mark PRs on trunk as ready.
    snap = ctx.snapshot()
    for pr in sorted(snap.open_prs.values(), key=lambda p: p.number):
        commit = snap.local_commit(pr.head)
        if commit is None:
            continue
        base = snap.expected_base(commit).name
        if base is not None and base != pr.base:
            ctx.gh.edit(pr.number, base=base)
            result.retargeted.append(pr.number)
        if (base or pr.base) == default and pr.is_draft:
            ctx.gh.ready(pr.number)
            result.readied.append(pr.number)

    sync(ctx, fetch=False)
    if result.landed:
        info(f"Landed: {', '.join(f'#{n}' for n in result.landed)}")
    else:
        info("No merged PRs to clean up.")
    return result
