"""Integration tests for `jjh pr`."""

import pytest
from conftest import parents, remote_branches, requires_jj

from jjh import description as desc
from jjh.commands.pr import open_pr
from jjh.run import JJHError

pytestmark = requires_jj


def test_pr_on_main(repo):
    repo.commit("main", message="Add a\n\nBody of a.")
    n = open_pr(repo.ctx(), "dev/a")
    pr = repo.gh.prs[n]
    assert (pr.base, pr.is_draft, pr.title) == ("main", False, "Add a")
    assert desc.strip_section(pr.body)[0] == "Body of a."
    assert "<!-- jj-graph synced=" in pr.body
    assert "dev/a" in remote_branches(repo)


def test_pr_stacked_is_draft(repo):
    repo.commit("main", message="Add a")
    open_pr(repo.ctx(), "dev/a")
    repo.commit("dev/a", message="Add b")
    n = open_pr(repo.ctx(), "dev/b")
    assert (repo.gh.prs[n].base, repo.gh.prs[n].is_draft) == ("dev/a", True)
    # Both PRs show both commits.
    for pr in repo.gh.prs.values():
        assert "dev/a" in pr.body and "dev/b" in pr.body


def test_pr_checks_name_and_base(repo):
    repo.commit("main", message="Add a")
    with pytest.raises(JJHError, match="reserved for diffbases"):
        open_pr(repo.ctx(), "jj-diffbase/a")
    repo.jj("bookmark", "create", "dev/a", "-r", "@")
    repo.commit("dev/a", message="Add b")
    with pytest.raises(JJHError, match="isn't on GitHub"):
        open_pr(repo.ctx(), "dev/b")
    with pytest.raises(JJHError, match="no description"):
        repo.jj("new")
        open_pr(repo.ctx(), "dev/c")


def test_pr_merge_commit_gets_diffbase(repo):
    repo.commit("main", message="Add a")
    open_pr(repo.ctx(), "dev/a")
    repo.commit("main", message="Fix c")
    open_pr(repo.ctx(), "fix/c")
    repo.commit("dev/a", "fix/c", message="Merge both")
    n = open_pr(repo.ctx(), "dev/m")
    assert repo.gh.prs[n].base == "jj-diffbase/dev/m"
    assert {"jj-diffbase/dev/m", "dev/m"} <= remote_branches(repo)
    assert parents(repo, "dev/m") == ["jj-diffbase/dev/m"]
    assert parents(repo, "jj-diffbase/dev/m") == ["dev/a", "fix/c"]
    # The diffbase is left out of the graph; #m is drawn as the merge.
    body = repo.gh.prs[n].body
    assert "jj-diffbase" not in body and "├─╮" in body
