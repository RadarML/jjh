"""The PR graph: commits, bookmarks and PRs, and how they should relate.

Instead of querying `jj` or `gh` directly, this module works with a
[`Snapshot`][^.] of the repository, which
[`Context.snapshot`][jjh.context.Context.snapshot] loads.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from functools import cached_property

from .description import escape
from .github import PullRequest, RepoInfo
from .jj import DIFFBASE_PREFIX, Bookmark, Commit, GraphLine, GraphNode

BOOKMARK_PREFIXES = ("dev/", "fix/", "docs/", "ci/")
"""Allowed bookmark prefixes for new PRs."""


def diffbase_name(bookmark: str) -> str:
    """Name of the diffbase bookmark for a PR's bookmark."""
    return f"{DIFFBASE_PREFIX}{bookmark}"


@dataclass(frozen=True)
class Base:
    """The branch a PR should be based on.

    Attributes:
        name: the base branch, or `None` if it can't be determined.
        problem: why the base can't be determined.
        skipped: unbookmarked commits between the PR's commit and its base.
            They end up in the PR's diff.
    """

    name: str | None
    problem: str | None = None
    skipped: tuple[str, ...] = ()


@dataclass
class Snapshot:
    """The repository's commits, bookmarks and PRs at one point in time.

    Attributes:
        repo: GitHub repository information.
        commits: every commit in `trunk()..(bookmarks | remote bookmarks)`,
            by commit id. A parent that isn't in here is on trunk.
        bookmarks: local and remote bookmarks, by name.
        prs: open and recently merged PRs.
    """

    repo: RepoInfo
    commits: dict[str, Commit]
    bookmarks: dict[str, Bookmark]
    prs: list[PullRequest] = field(default_factory=list)

    @cached_property
    def open_prs(self) -> dict[str, PullRequest]:
        """Open PRs by head branch."""
        return {pr.head: pr for pr in self.prs if pr.state == "OPEN"}

    @cached_property
    def _remote_names(self) -> dict[str, tuple[str, ...]]:
        """Remote bookmark names by the commit they point at."""
        out: dict[str, list[str]] = {}
        for b in self.bookmarks.values():
            if b.remote_target is not None:
                out.setdefault(b.remote_target, []).append(b.name)
        return {k: tuple(v) for k, v in out.items()}

    @cached_property
    def _children(self) -> dict[str, list[str]]:
        """Child commit ids by parent commit id."""
        out: dict[str, list[str]] = {}
        for c in self.commits.values():
            for p in c.parents:
                out.setdefault(p, []).append(c.commit_id)
        return out

    def local_commit(self, bookmark: str) -> Commit | None:
        """The commit a local bookmark points at, if it is above trunk."""
        b = self.bookmarks.get(bookmark)
        if b is None or b.target is None:
            return None
        return self.commits.get(b.target)

    def remote_commit(self, bookmark: str) -> Commit | None:
        """The commit a remote bookmark points at, if it is above trunk."""
        b = self.bookmarks.get(bookmark)
        if b is None or b.remote_target is None:
            return None
        return self.commits.get(b.remote_target)

    def _names_on(self, commit_id: str) -> tuple[str, ...]:
        """Bookmarks on a commit: local ones, then remote ones with no local bookmark."""
        local = self.commits[commit_id].bookmarks if commit_id in self.commits else ()
        remote = tuple(n for n in self._remote_names.get(commit_id, ()) if n not in local)
        return local + remote

    def ancestors(self, commit_id: str) -> set[str]:
        """Ancestors of a commit above trunk, including itself."""
        seen: set[str] = set()
        stack = [commit_id]
        while stack:
            c = stack.pop()
            if c in seen or c not in self.commits:
                continue
            seen.add(c)
            stack.extend(self.commits[c].parents)
        return seen

    def _descendants(self, commit_ids: Iterable[str]) -> set[str]:
        """Descendants of commits in the snapshot, including themselves."""
        seen: set[str] = set()
        stack = list(commit_ids)
        while stack:
            c = stack.pop()
            if c in seen:
                continue
            seen.add(c)
            stack.extend(self._children.get(c, ()))
        return seen

    def is_ancestor(self, a: str, b: str) -> bool:
        """Whether `a` is an ancestor of `b`. Trunk commits are ancestors of every commit."""
        if a not in self.commits:
            return True
        return a in self.ancestors(b)

    def _graph(self, commit_id: str) -> set[str]:
        """Commits connected to a commit's stack above trunk.

        This matches the revset `trunk()..(roots(trunk()..<head>)::)`.
        """
        ancestors = self.ancestors(commit_id)
        roots = [
            c for c in ancestors if not any(p in ancestors for p in self.commits[c].parents)]
        return set().union(*(self.ancestors(c) for c in self._descendants(roots)))

    def graph_bookmarks(self, commit_id: str) -> list[str]:
        """Every local or remote bookmark in a commit's PR graph."""
        members = self._graph(commit_id)
        return sorted({n for c in members for n in self._names_on(c)})

    def expected_base(self, commit: Commit) -> Base:
        """The branch a PR for `commit` should be based on.

        This is the nearest bookmark below the commit: a diffbase bookmark if
        the commit is on a diffbase, or the default branch if it is on trunk.
        """
        if commit.is_merge:
            return Base(None, problem="commit has more than one parent and no diffbase")
        skipped: list[str] = []
        parent_id = commit.parents[0]
        while True:
            parent = self.commits.get(parent_id)
            if parent is None:
                return Base(self.repo.default_branch, skipped=tuple(skipped))
            names = self._names_on(parent_id)
            if parent.is_diffbase:
                diffbases = [n for n in names if n.startswith(DIFFBASE_PREFIX)]
                if not diffbases:
                    return Base(None, problem=f"diffbase {parent.change_id[:8]} has no bookmark")
                return Base(diffbases[0], skipped=tuple(skipped))
            names = [n for n in names if not n.startswith(DIFFBASE_PREFIX)]
            if names:
                with_pr = [n for n in names if n in self.open_prs]
                return Base((with_pr or names)[0], skipped=tuple(skipped))
            if parent.is_merge:
                return Base(None, problem=(
                    f"unbookmarked merge commit {parent.change_id[:8]} below the PR"))
            skipped.append(parent_id)
            parent_id = parent.parents[0]


def _node_label(node: GraphNode, prs: dict[str, PullRequest], repo: RepoInfo) -> str:
    """The text after a commit's node in the graph section."""
    if node.on_trunk:
        return repo.default_branch
    names = [n for n in node.bookmarks if not n.startswith(DIFFBASE_PREFIX)]
    title = escape(node.title)
    for name in names:
        if name in prs:
            pr = prs[name]
            return f'<a href="{repo.pr_url(pr.number)}">#{pr.number} {escape(name)}</a>: {title}'
    if names:
        return f"{escape(names[0])}: {title}"
    return title


def render_graph(lines: list[GraphLine], prs: dict[str, PullRequest], repo: RepoInfo) -> str:
    """Turn `jj log` graph output into the contents of the graph section.

    Elided edges (`╷`) are drawn as plain edges. Lines with only vertical
    edges or `~` are dropped: they are padding, or the edges below trunk.
    """
    out: list[str] = []
    for line in lines:
        if isinstance(line, GraphNode):
            prefix = line.prefix.replace("╷", "│").rstrip()
            out.append(f"{prefix}  {_node_label(line, prs, repo)}")
        else:
            edges = line.replace("╷", "│").rstrip()
            if edges and set(edges) - set("│ ~"):
                out.append(edges)
    return "\n".join(out)
