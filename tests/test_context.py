"""Integration tests for reading the repository into a snapshot."""

from conftest import EXAMPLE_GRAPH, requires_jj

pytestmark = requires_jj


def test_snapshot(example):
    snap = example.ctx().snapshot()
    assert set(snap.open_prs) == {
        "ci/test-all-prs", "dev/parser", "dev/parser-cli", "docs/parser",
        "fix/empty-input", "dev/examples"}
    head = snap.local_commit("dev/examples")
    assert head is not None
    assert snap.expected_base(head).name == "jj-diffbase/dev/examples"
    assert not any(b.unpushed or b.conflicted for b in snap.bookmarks.values())


def test_graph_text_matches_guide(example):
    ctx = example.ctx()
    snap = ctx.snapshot()
    assert ctx.graph_text(snap, example.target("dev/examples")) == EXAMPLE_GRAPH
