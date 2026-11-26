"""Integration tests for `jjh diffbase`."""

import pytest
from conftest import parents, remote_branches, requires_jj

from jjh.commands.diffbase import diffbase_add, diffbase_rm
from jjh.run import JJHError

pytestmark = requires_jj


def test_diffbase_add_and_rm(repo):
    repo.commit("main", message="Add a", bookmark="dev/a")
    repo.commit("main", message="Fix c", bookmark="fix/c")
    repo.commit("dev/a", "fix/c", message="Merge both", bookmark="dev/m")
    repo.jj("git", "push", "--all")
    repo.gh.add(1, "dev/a", "main")
    repo.gh.add(2, "fix/c", "main")
    repo.gh.add(3, "dev/m", "dev/a")
    ctx = repo.ctx()
    assert diffbase_add(ctx, "dev/m") == "jj-diffbase/dev/m"
    assert repo.gh.prs[3].base == "jj-diffbase/dev/m"

    with pytest.raises(JJHError, match="2 unlanded parents"):
        diffbase_rm(ctx, "dev/m")
    # Land fix/c by moving main onto it.
    repo.jj("bookmark", "set", "main", "-r", "fix/c")
    repo.jj("git", "push", "-b", "main")
    assert diffbase_rm(ctx, "dev/m") == "dev/a"
    assert repo.gh.prs[3].base == "dev/a"
    assert parents(repo, "dev/m") == ["dev/a"]
    # dev/m still has fix/c's change, which it got through the diffbase.
    assert "fix_c" in repo.jj("file", "list", "-r", "dev/m")
    assert "jj-diffbase/dev/m" not in remote_branches(repo)
