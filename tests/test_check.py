"""Integration tests for `jjh check`."""

from conftest import requires_jj

from jjh.commands.check import Kind, check, find_problems
from jjh.commands.sync import sync

pytestmark = requires_jj


def test_check_clean(xwr):
    sync(xwr.ctx(), fetch=False)
    assert find_problems(xwr.ctx().snapshot()) == []


def test_check_base_mismatch_fix(xwr):
    xwr.gh.edit(92, base="main")
    problems = check(xwr.ctx())
    assert [(p.kind, p.pr, p.base) for p in problems if p.kind == Kind.BASE] == [
        (Kind.BASE, 92, "dev/awrl6888")]
    assert check(xwr.ctx(), fix=True) == [p for p in problems if p.kind not in {Kind.BASE}]
    assert xwr.gh.prs[92].base == "dev/awrl6888"


def test_check_unpushed_and_stale(xwr):
    xwr.jj("describe", "-r", "dev/awrl6888", "-m", "Reworded")
    kinds = {(p.kind, p.subject) for p in find_problems(xwr.ctx().snapshot())}
    assert (Kind.UNPUSHED, "dev/awrl6888*") in kinds
    assert (Kind.UNPUSHED, "dev/demo-config*") in kinds

    xwr.jj("git", "push", "-b", "dev/awrl6888")
    kinds = {(p.kind, p.pr) for p in find_problems(xwr.ctx().snapshot())}
    assert (Kind.STALE, 92) in kinds

    check(xwr.ctx(), fix=True)
    assert find_problems(xwr.ctx().snapshot()) == []


def test_check_merge_without_diffbase(repo):
    repo.commit("main", message="Add a", bookmark="dev/a")
    repo.commit("main", message="Fix c", bookmark="fix/c")
    repo.commit("dev/a", "fix/c", message="Merge both", bookmark="dev/m")
    repo.jj("git", "push", "--all")
    for n, head in enumerate(["dev/a", "fix/c", "dev/m"], 1):
        repo.gh.add(n, head, "main" if n < 3 else "dev/a")
    [p] = [p for p in find_problems(repo.ctx().snapshot()) if p.kind == Kind.NO_BASE]
    assert "jjh diffbase add dev/m" in p.message
