"""Unit tests for the PR graph model and graph rendering."""

from jjh.github import PullRequest, RepoInfo
from jjh.jj import Bookmark, Commit, GraphNode
from jjh.stack import Snapshot, render_graph

REPO = RepoInfo("https://github.com/o/r", "main", "me")
TRUNK = "t0"


def make(commits: dict[str, tuple[tuple[str, ...], str, tuple[str, ...]]], prs=()) -> Snapshot:
    """Build a snapshot from {id: (parents, description, bookmarks)}."""
    cs = {
        cid: Commit(change_id=f"ch{cid}", commit_id=cid, parents=p, description=d, bookmarks=b)
        for cid, (p, d, b) in commits.items()}
    bms = {
        b: Bookmark(b, local=(cid,), remote=(cid,), tracked=True)
        for cid, c in cs.items() for b in c.bookmarks}
    return Snapshot(REPO, cs, bms, list(prs))


def pr(n: int, head: str, base: str = "main") -> PullRequest:
    return PullRequest(n, head, base, "t", "", "me")


SNAP = make({
    "a": ((TRUNK,), "A", ("dev/a",)),
    "b": (("a",), "B", ()),                      # unbookmarked
    "c": (("b",), "C", ("dev/c",)),
    "x": ((TRUNK,), "X", ("fix/x",)),
    "d": (("c", "x"), "JJ_MERGE_DIFFBASE: dev/m", ("jj-diffbase/dev/m",)),
    "m": (("d",), "M", ("dev/m",)),
    "n": (("c", "x"), "Merge without diffbase", ("dev/n",)),
    "z": ((TRUNK,), "Unrelated", ("dev/z",)),
}, prs=[pr(1, "dev/a"), pr(2, "dev/c", "dev/a"), pr(3, "fix/x")])


def test_expected_base():
    c = SNAP.commits
    assert SNAP.expected_base(c["a"]).name == "main"
    base = SNAP.expected_base(c["c"])
    assert (base.name, base.skipped) == ("dev/a", ("b",))
    assert SNAP.expected_base(c["m"]).name == "jj-diffbase/dev/m"
    n = SNAP.expected_base(c["n"])
    assert n.name is None and "more than one parent" in (n.problem or "")


def test_graph_membership():
    # The merges above dev/a also pull in their other parent, fix/x.
    connected = ["dev/a", "dev/c", "dev/m", "dev/n", "fix/x", "jj-diffbase/dev/m"]
    assert SNAP.graph_bookmarks("a") == connected
    assert SNAP.graph_bookmarks("x") == connected
    assert SNAP.graph_bookmarks("z") == ["dev/z"]
    assert SNAP.is_ancestor("a", "m") and not SNAP.is_ancestor("m", "a")
    assert SNAP.is_ancestor(TRUNK, "a")


def test_remote_only_bookmarks_count():
    snap = make({"a": ((TRUNK,), "A", ()), "b": (("a",), "B", ())})
    snap.bookmarks["dev/a"] = Bookmark("dev/a", remote=("a",))
    assert snap.expected_base(snap.commits["b"]).name == "dev/a"
    assert snap.graph_bookmarks("b") == ["dev/a"]


def test_render_graph():
    lines = [
        GraphNode("○    ", "m", "M & co", False, ("dev/m",)),
        "├─╮",
        "╷ ╷",
        GraphNode("╷ ○  ", "x", "X", False, ("fix/x",)),
        "╷ │",
        GraphNode("○ │  ", "c", "C", False, ("dev/c",)),
        "├─╯",
        GraphNode("◆  ", TRUNK, "init", True, ("main",)),
        "│",
        "~",
    ]
    prs = {"dev/m": pr(9, "dev/m"), "fix/x": pr(3, "fix/x")}
    assert render_graph(lines, prs, REPO).splitlines() == [
        '○  <a href="https://github.com/o/r/pull/9">#9 dev/m</a>: M &amp; co',
        "├─╮",
        '│ ○  <a href="https://github.com/o/r/pull/3">#3 fix/x</a>: X',
        "○ │  dev/c: C",
        "├─╯",
        "◆  main",
    ]



def test_render_graph_keeps_lines_after_trunk():
    """A trunk commit in a side column doesn't cut off the rest of the graph."""
    lines = [
        GraphNode("○    ", "m", "Merge", False, ("dev/m",)),
        "├─╮",
        "╷ ╷",
        GraphNode("╷ ◆  ", "t", "init", True, ("main",)),
        "╷ │",
        "╷ ~",
        GraphNode("○  ", "a", "A", False, ("dev/a",)),
        "│",
        "~",
    ]
    assert render_graph(lines, {}, REPO).splitlines() == [
        "○  dev/m: Merge", "├─╮", "│ ◆  main", "○  dev/a: A"]
