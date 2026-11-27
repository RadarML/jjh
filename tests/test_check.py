"""Integration tests for `jjh check`."""

from conftest import parents, remote_branches, requires_jj

from jjh.commands.check import DIFFBASE_KINDS, Kind, check, find_problems
from jjh.commands.diffbase import diffbase_add
from jjh.commands.sync import sync

pytestmark = requires_jj


def test_check_clean(example):
    sync(example.ctx(), fetch=False)
    assert find_problems(example.ctx().snapshot()) == []


def test_check_base_mismatch_fix(example):
    example.gh.edit(92, base="main")
    problems = check(example.ctx())
    assert [(p.kind, p.pr, p.base) for p in problems if p.kind == Kind.BASE] == [
        (Kind.BASE, 92, "dev/parser")]
    assert check(example.ctx(), fix=True) == [p for p in problems if p.kind not in {Kind.BASE}]
    assert example.gh.prs[92].base == "dev/parser"


def test_check_unpushed_and_stale(example):
    example.jj("describe", "-r", "dev/parser", "-m", "Reworded")
    kinds = {(p.kind, p.subject) for p in find_problems(example.ctx().snapshot())}
    assert (Kind.UNPUSHED, "dev/parser*") in kinds
    assert (Kind.UNPUSHED, "dev/examples*") in kinds

    example.jj("git", "push", "-b", "dev/parser")
    kinds = {(p.kind, p.pr) for p in find_problems(example.ctx().snapshot())}
    assert (Kind.STALE, 92) in kinds

    check(example.ctx(), fix=True)
    assert find_problems(example.ctx().snapshot()) == []


def _merge_pr(repo):
    """dev/m (#3) merges dev/a (#1) and fix/c (#2), with no diffbase yet."""
    repo.commit("main", message="Add a", bookmark="dev/a")
    repo.commit("main", message="Fix c", bookmark="fix/c")
    repo.commit("dev/a", "fix/c", message="Merge both", bookmark="dev/m")
    repo.jj("git", "push", "--all")
    for n, head in enumerate(["dev/a", "fix/c", "dev/m"], 1):
        repo.gh.add(n, head, "main" if n < 3 else "dev/a")


def _diffbase_problems(repo):
    return [(p.kind, p.subject) for p in find_problems(repo.ctx().snapshot())
            if p.kind in DIFFBASE_KINDS]


def test_check_merge_without_diffbase(repo):
    _merge_pr(repo)
    [p] = [p for p in find_problems(repo.ctx().snapshot()) if p.kind == Kind.NO_DIFFBASE]
    assert "jjh diffbase add dev/m" in p.message

    check(repo.ctx(), fix=True)
    assert _diffbase_problems(repo) == []
    assert repo.gh.prs[3].base == "jj-diffbase/dev/m"
    assert "jj-diffbase/dev/m" in remote_branches(repo)


def test_check_removes_spent_diffbase(repo):
    _merge_pr(repo)
    diffbase_add(repo.ctx(), "dev/m")
    # The diffbase loses its fix/c parent without anything landing.
    repo.jj("rebase", "-s", "jj-diffbase/dev/m", "-d", "dev/a")
    assert _diffbase_problems(repo) == [(Kind.SPENT_DIFFBASE, "jj-diffbase/dev/m")]

    check(repo.ctx(), fix=True)
    assert _diffbase_problems(repo) == []
    assert parents(repo, "dev/m") == ["dev/a"]
    assert repo.gh.prs[3].base == "dev/a"
    assert "jj-diffbase/dev/m" not in remote_branches(repo)


def test_check_abandons_orphan_diffbase(repo):
    _merge_pr(repo)
    diffbase_add(repo.ctx(), "dev/m")
    # The PR's commit moves off its diffbase onto one parent.
    repo.jj("rebase", "-s", "dev/m", "-d", "dev/a")
    assert _diffbase_problems(repo) == [(Kind.ORPHAN_DIFFBASE, "jj-diffbase/dev/m")]

    check(repo.ctx(), fix=True)
    assert _diffbase_problems(repo) == []
    assert repo.gh.prs[3].base == "dev/a"
    assert "jj-diffbase/dev/m" not in remote_branches(repo)
    assert not repo.jj("log", "--no-graph", "-r", 'description(glob:"JJ_MERGE_DIFFBASE:*")',
                       "-T", "change_id")


def test_merged_elsewhere_only_into_adopted_branches(example):
    # A teammate's branch, never adopted here, with a sub-PR merged into it on purpose.
    example.git_remote("push", "-q", "origin", "main:refs/heads/dev/theirs")
    example.jj("git", "fetch")
    example.gh.add(200, "dev/their-part", "dev/theirs")
    example.gh.merge(200)
    # A PR merged into one of the branches in our own graph by mistake.
    example.gh.add(201, "dev/oops", "dev/parser")
    example.gh.merge(201)
    problems = find_problems(example.ctx().snapshot())
    assert [p.pr for p in problems if p.kind == Kind.MERGED_ELSEWHERE] == [201]
