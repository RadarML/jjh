"""Integration tests for `jjh check`."""

from conftest import requires_jj

from jjh.commands.check import Kind, check, find_problems
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


def test_check_merge_without_diffbase(repo):
    repo.commit("main", message="Add a", bookmark="dev/a")
    repo.commit("main", message="Fix c", bookmark="fix/c")
    repo.commit("dev/a", "fix/c", message="Merge both", bookmark="dev/m")
    repo.jj("git", "push", "--all")
    for n, head in enumerate(["dev/a", "fix/c", "dev/m"], 1):
        repo.gh.add(n, head, "main" if n < 3 else "dev/a")
    [p] = [p for p in find_problems(repo.ctx().snapshot()) if p.kind == Kind.NO_BASE]
    assert "jjh diffbase add dev/m" in p.message
