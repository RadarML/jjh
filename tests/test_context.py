"""Integration tests for reading the repository into a snapshot."""

from conftest import GOLDEN_94, requires_jj

pytestmark = requires_jj


def test_snapshot(xwr):
    snap = xwr.ctx().snapshot()
    assert set(snap.open_prs) == {
        "ci/all-pr-bases", "dev/awrl6888", "dev/awrl6888-rsp", "dev/awrl6888-docs",
        "fix/real-only-range", "dev/demo-config"}
    head = snap.local_commit("dev/demo-config")
    assert head is not None
    assert snap.expected_base(head).name == "jj-diffbase/dev/demo-config"
    assert not any(b.unpushed or b.conflicted for b in snap.bookmarks.values())


def test_graph_text_matches_guide(xwr):
    ctx = xwr.ctx()
    snap = ctx.snapshot()
    assert ctx.graph_text(snap, xwr.target("dev/demo-config")) == GOLDEN_94
