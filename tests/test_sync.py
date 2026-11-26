"""Integration tests for `jjh sync` against a real jj repository."""

from conftest import GOLDEN_94, link, requires_jj

from jjh import description as desc
from jjh.commands.sync import sync

pytestmark = requires_jj


def graph_of(body: str) -> str:
    return body.split("<pre>\n", 1)[1].split("\n</pre>", 1)[0]


def test_graph_section_matches_guide(xwr):
    sync(xwr.ctx(), fetch=False)
    assert graph_of(xwr.gh.prs[94].body) == GOLDEN_94
    # Every PR in the graph gets the section, with itself as `@`.
    g93 = graph_of(xwr.gh.prs[93].body)
    assert g93.splitlines()[0].startswith("○  ")
    assert g93.splitlines()[3].startswith(f"@ │  {link(93, 'dev/awrl6888-docs')}")


def test_first_sync_pushes_commit_text(xwr):
    result = sync(xwr.ctx(), fetch=False)
    assert sorted(result.pushed) == [90, 91, 92, 93, 94, 96]
    pr = xwr.gh.prs[90]
    assert pr.title == "Fix XWRConfig.max_range for real-only radars"
    text, synced = desc.strip_section(pr.body)
    assert text == "Only real-only radars."
    assert synced == desc.text_hash(pr.title, text)
    assert pr.body.startswith("Only real-only radars.\n\n<!-- jj-graph synced=")


def test_sync_is_idempotent(xwr):
    sync(xwr.ctx(), fetch=False)
    xwr.gh.calls.clear()
    result = sync(xwr.ctx(), fetch=False)
    assert xwr.gh.calls == []
    assert result.updated == []


def test_commit_change_pushes(xwr):
    sync(xwr.ctx(), fetch=False)
    xwr.jj("describe", "-r", "fix/real-only-range", "-m", "Fix max_range\n\nNew body.")
    xwr.gh.calls.clear()
    result = sync(xwr.ctx(), fetch=False)
    assert result.pushed == [90]
    assert xwr.gh.prs[90].title == "Fix max_range"
    assert desc.strip_section(xwr.gh.prs[90].body)[0] == "New body."
    # The new title shows in every graph that contains #90.
    assert "Fix max_range" in xwr.gh.prs[94].body
    assert set(c[1] for c in xwr.gh.edits()) >= {90, 94}


def test_pr_edit_is_reported_then_pulled(xwr):
    ctx = xwr.ctx()
    sync(ctx, fetch=False)
    pr = xwr.gh.prs[90]
    xwr.gh.edit(90, body=pr.body.replace("Only real-only radars.", "Edited\r\non GitHub.  "))

    result = sync(ctx, fetch=False)
    assert result.edited == [90]
    assert "Only real-only radars." in xwr.jj("log", "-r", "fix/real-only-range", "-T",
                                               "description")

    result = sync(ctx, fetch=False, pull=True)
    assert result.pulled == [90]
    description = xwr.jj("log", "--no-graph", "-r", "fix/real-only-range", "-T", "description")
    assert description == "Fix XWRConfig.max_range for real-only radars\n\nEdited\non GitHub.\n"
    xwr.gh.calls.clear()
    assert sync(ctx, fetch=False).updated == []


def test_conflict_leaves_pr_alone(xwr):
    ctx = xwr.ctx()
    sync(ctx, fetch=False)
    before = xwr.gh.prs[90]
    xwr.gh.edit(90, title="Edited on GitHub")
    xwr.jj("describe", "-r", "fix/real-only-range", "-m", "Edited locally")
    xwr.gh.calls.clear()
    result = sync(ctx, fetch=False)
    assert result.conflicts == [90]
    assert 90 not in [c[1] for c in xwr.gh.edits()]
    assert xwr.gh.prs[90].body == before.body


def test_other_peoples_prs_only_get_the_graph(xwr):
    xwr.gh.add(90, "fix/real-only-range", "ci/all-pr-bases", title="Their title",
               body="Their text.\n\n<!-- jj-graph -->\nold\n<!-- /jj-graph -->\n\nFooter.",
               author="someone", draft=True)
    sync(xwr.ctx(), fetch=False)
    pr = xwr.gh.prs[90]
    assert pr.title == "Their title"
    assert pr.body.startswith("Their text.\n\n<!-- jj-graph -->\n***")
    assert pr.body.endswith("<!-- /jj-graph -->\n\nFooter.")


def test_unadopted_prs_are_ignored(xwr):
    xwr.gh.add(200, "dev/not-here", "main", title="x", body="untouched")
    sync(xwr.ctx(), fetch=False)
    assert xwr.gh.prs[200].body == "untouched"
