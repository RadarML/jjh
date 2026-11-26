"""Integration tests for `jjh land`."""

from dataclasses import replace

from conftest import parents, remote_branches, requires_jj, squash_merge

from jjh.commands.check import find_problems
from jjh.commands.diffbase import diffbase_add
from jjh.commands.land import land
from jjh.commands.sync import sync

pytestmark = requires_jj


def test_land_bottom_up(example):
    ctx = example.ctx()
    sync(ctx, fetch=False)

    # GitHub retargets #91 itself; land must retarget #90.
    squash_merge(example, 96, retarget={91: "main"})
    result = land(ctx)
    assert result.landed == [96]
    assert parents(example, "dev/parser") == ["main"]
    assert parents(example, "fix/empty-input") == ["main"]
    assert example.gh.prs[90].base == "main"
    assert {90, 91} <= set(result.readied)
    assert not example.gh.prs[90].is_draft and not example.gh.prs[91].is_draft
    assert "#96" not in example.gh.prs[94].body
    assert find_problems(ctx.snapshot()) == []

    # Landing #90 leaves the diffbase with one unlanded parent: remove it.
    squash_merge(example, 90)
    result = land(ctx)
    assert result.landed == [90]
    assert result.diffbases == ["dev/examples"]
    assert parents(example, "dev/examples") == ["docs/parser"]
    # #94 still has #90's change, which it got through the diffbase.
    assert "fix_empty-input" in example.jj("file", "list", "-r", "dev/examples")
    assert example.gh.prs[94].base == "docs/parser"
    assert "jj-diffbase/dev/examples" not in remote_branches(example)
    assert find_problems(ctx.snapshot()) == []


def test_land_twice(example):
    """A landed commit is hidden after the first land; the second must not touch it."""
    ctx = example.ctx()
    sync(ctx, fetch=False)
    # GitHub reports the merged PR's head commit, which jj keeps as a hidden commit.
    example.gh.prs[96] = replace(example.gh.prs[96], head_oid=example.target("ci/test-all-prs"))
    squash_merge(example, 96, retarget={91: "main", 90: "main"})
    assert land(ctx).landed == [96]
    assert land(ctx).landed == []
    assert find_problems(ctx.snapshot()) == []


def test_graph_ends_in_one_main_after_partial_land(repo):
    """Landing one parent of a three-way merge moves the merge onto the new main but
    not its other parents; the graph still ends in a single `◆  main`."""
    ctx = repo.ctx()
    repo.commit("main", message="Add a", bookmark="dev/a")
    repo.commit("main", message="Add b", bookmark="dev/b")
    repo.commit("main", message="Fix c", bookmark="fix/c")
    repo.commit("dev/a", "dev/b", "fix/c", message="Merge all", bookmark="dev/m")
    repo.jj("git", "push", "--all")
    for n, head in enumerate(["dev/a", "dev/b", "fix/c"], 1):
        repo.gh.add(n, head, "main")
    repo.gh.add(4, "dev/m", "dev/a")
    diffbase_add(ctx, "dev/m")
    sync(ctx, fetch=False)

    squash_merge(repo, 3)
    assert land(ctx).diffbases == []  # two parents still unlanded
    for n in (1, 2, 4):
        graph = repo.gh.prs[n].body.split("<pre>\n", 1)[1].split("\n</pre>", 1)[0]
        assert [line for line in graph.splitlines() if "◆" in line] == ["◆  main"]
        assert graph.endswith("◆  main")
