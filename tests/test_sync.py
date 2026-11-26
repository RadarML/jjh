"""Integration tests for `jjh sync` against a real jj repository."""

from conftest import EXAMPLE_GRAPH, link, requires_jj

from jjh import description as desc
from jjh.commands.sync import sync

pytestmark = requires_jj


def graph_of(body: str) -> str:
    return body.split("<pre>\n", 1)[1].split("\n</pre>", 1)[0]


def test_graph_section_matches_guide(example):
    sync(example.ctx(), fetch=False)
    assert graph_of(example.gh.prs[94].body) == EXAMPLE_GRAPH
    # Every PR in the graph gets the section, with itself as `@`.
    g93 = graph_of(example.gh.prs[93].body)
    assert g93.splitlines()[0].startswith("○  ")
    assert g93.splitlines()[3].startswith(f"@ │  {link(93, 'docs/parser')}")


def test_first_sync_pushes_commit_text(example):
    result = sync(example.ctx(), fetch=False)
    assert sorted(result.pushed) == [90, 91, 92, 93, 94, 96]
    pr = example.gh.prs[90]
    assert pr.title == "Handle empty input files"
    text, synced = desc.strip_section(pr.body)
    assert text == "Empty files used to crash."
    assert synced == desc.text_hash(pr.title, text)
    assert pr.body.startswith("Empty files used to crash.\n\n<!-- jj-graph synced=")


def test_sync_is_idempotent(example):
    sync(example.ctx(), fetch=False)
    example.gh.calls.clear()
    result = sync(example.ctx(), fetch=False)
    assert example.gh.calls == []
    assert result.updated == []


def test_commit_change_pushes(example):
    sync(example.ctx(), fetch=False)
    example.jj("describe", "-r", "fix/empty-input", "-m", "Handle empty input\n\nNew body.")
    example.gh.calls.clear()
    result = sync(example.ctx(), fetch=False)
    assert result.pushed == [90]
    assert example.gh.prs[90].title == "Handle empty input"
    assert desc.strip_section(example.gh.prs[90].body)[0] == "New body."
    # The new title shows in every graph that contains #90.
    assert "Handle empty input" in example.gh.prs[94].body
    assert set(c[1] for c in example.gh.edits()) >= {90, 94}


def test_pr_edit_is_reported_then_pulled(example):
    ctx = example.ctx()
    sync(ctx, fetch=False)
    pr = example.gh.prs[90]
    edited = pr.body.replace("Empty files used to crash.", "Edited\r\non GitHub.  ")
    example.gh.edit(90, body=edited)

    result = sync(ctx, fetch=False)
    assert result.edited == [90]
    assert "Empty files used to crash." in example.jj("log", "-r", "fix/empty-input", "-T",
                                               "description")

    result = sync(ctx, fetch=False, pull=True)
    assert result.pulled == [90]
    description = example.jj("log", "--no-graph", "-r", "fix/empty-input", "-T", "description")
    assert description == "Handle empty input files\n\nEdited\non GitHub.\n"
    example.gh.calls.clear()
    assert sync(ctx, fetch=False).updated == []


def test_conflict_leaves_pr_alone(example):
    ctx = example.ctx()
    sync(ctx, fetch=False)
    before = example.gh.prs[90]
    example.gh.edit(90, title="Edited on GitHub")
    example.jj("describe", "-r", "fix/empty-input", "-m", "Edited locally")
    example.gh.calls.clear()
    result = sync(ctx, fetch=False)
    assert result.conflicts == [90]
    assert 90 not in [c[1] for c in example.gh.edits()]
    assert example.gh.prs[90].body == before.body


def test_other_peoples_prs_only_get_the_graph(example):
    example.gh.add(90, "fix/empty-input", "ci/test-all-prs", title="Their title",
               body="Their text.\n\n<!-- jj-graph -->\nold\n<!-- /jj-graph -->\n\nFooter.",
               author="someone", draft=True)
    sync(example.ctx(), fetch=False)
    pr = example.gh.prs[90]
    assert pr.title == "Their title"
    assert pr.body.startswith("Their text.\n\n<!-- jj-graph -->\n***")
    assert pr.body.endswith("<!-- /jj-graph -->\n\nFooter.")


def test_unadopted_prs_are_ignored(example):
    example.gh.add(200, "dev/not-here", "main", title="x", body="untouched")
    sync(example.ctx(), fetch=False)
    assert example.gh.prs[200].body == "untouched"
