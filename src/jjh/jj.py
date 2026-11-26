"""Wrapper around the `jj` command line."""

import json
import re
from dataclasses import dataclass, field

from .run import JJHError, Runner

DIFFBASE_PREFIX = "jj-diffbase/"
"""Bookmark prefix for diffbase commits."""

DIFFBASE_MARKER = "JJ_MERGE_DIFFBASE:"
"""First word of a diffbase commit's description."""

NOT_DIFFBASE = f'~ description(glob:"{DIFFBASE_MARKER}*")'
"""Revset suffix that removes diffbase commits."""

MIN_VERSION = (0, 47, 0)
"""Oldest jj release `jjh` has been tested with."""


def quote(name: str) -> str:
    """Quote a string for use in a revset."""
    return json.dumps(name)


def bookmark_rev(name: str) -> str:
    """Revset for the local bookmark `name`."""
    return f"bookmarks(exact:{quote(name)})"


@dataclass(frozen=True)
class Commit:
    """A jj commit.

    Attributes:
        change_id: jj change id.
        commit_id: git commit id.
        parents: parent commit ids.
        description: commit description.
        empty: whether the commit changes no files.
        on_trunk: whether the commit is an ancestor of `trunk()`.
        bookmarks: local bookmarks pointing at this commit.
    """

    change_id: str
    commit_id: str
    parents: tuple[str, ...]
    description: str
    empty: bool = False
    on_trunk: bool = False
    bookmarks: tuple[str, ...] = ()

    @property
    def is_diffbase(self) -> bool:
        """Whether this is a diffbase commit."""
        return self.description.startswith(DIFFBASE_MARKER)

    @property
    def is_merge(self) -> bool:
        """Whether this commit has more than one parent."""
        return len(self.parents) > 1


@dataclass(frozen=True)
class Bookmark:
    """A bookmark, as seen locally and on one remote.

    Attributes:
        name: bookmark name.
        local: local targets: none if there is no local bookmark, several if
            it is conflicted.
        remote: targets on the remote: none if the remote doesn't have it.
        tracked: whether the remote bookmark is tracked.
    """

    name: str
    local: tuple[str, ...] = ()
    remote: tuple[str, ...] = ()
    tracked: bool = False

    @property
    def target(self) -> str | None:
        """The local target, if there is exactly one."""
        return self.local[0] if len(self.local) == 1 else None

    @property
    def remote_target(self) -> str | None:
        """The remote target, if there is exactly one."""
        return self.remote[0] if len(self.remote) == 1 else None

    @property
    def adopted(self) -> bool:
        """Local or tracked: part of a graph you work on here."""
        return bool(self.local) or self.tracked

    @property
    def conflicted(self) -> bool:
        """`name??`: several targets, locally or on the remote."""
        return len(self.local) > 1 or len(self.remote) > 1

    @property
    def unpushed(self) -> bool:
        """`name*`: the local bookmark differs from the tracked remote bookmark."""
        return self.tracked and bool(self.local) and self.local != self.remote

    @property
    def deleted(self) -> bool:
        """Deleted locally but not on the remote."""
        return self.tracked and not self.local and bool(self.remote)


_COMMIT_TEMPLATE = (
    'json({"change_id" => change_id, "commit_id" => commit_id, '
    '"parents" => parents.map(|p| p.commit_id()), "description" => description, '
    '"empty" => empty, "on_trunk" => self.contained_in("::trunk()"), '
    '"bookmarks" => local_bookmarks.map(|b| b.name())})')


def _parse_commit(data: dict) -> Commit:
    return Commit(
        change_id=data["change_id"], commit_id=data["commit_id"],
        parents=tuple(data["parents"]), description=data["description"],
        empty=data["empty"], on_trunk=data["on_trunk"],
        bookmarks=tuple(data["bookmarks"]))


@dataclass(frozen=True)
class GraphNode:
    """One commit in a rendered `jj log` graph.

    Attributes:
        prefix: graph characters drawn before the commit.
        commit_id: git commit id.
        title: first line of the description.
        on_trunk: whether the commit is an ancestor of `trunk()`.
        bookmarks: local bookmarks, then untracked remote bookmarks.
    """

    prefix: str
    commit_id: str
    title: str
    on_trunk: bool
    bookmarks: tuple[str, ...]


GraphLine = GraphNode | str
"""A graph line: a commit, or a line of edges only."""

_SENTINEL = "@@JJH@@"


@dataclass
class JJ:
    """Runs jj commands in a repository.

    Attributes:
        run: command runner.
        remote: git remote that holds the PR branches.
    """

    run: Runner = field(default_factory=Runner)
    remote: str = "origin"

    def _run(self, *args: str, mutates: bool = True) -> str:
        return self.run(["jj", "--no-pager", "--color=never", *args], mutates=mutates)

    def _read(self, *args: str) -> str:
        return self._run(*args, mutates=False)

    def version(self) -> tuple[int, ...]:
        """The installed jj version."""
        out = self._read("--version")
        m = re.search(r"(\d+)\.(\d+)\.(\d+)", out)
        if not m:
            raise JJHError(f"Could not parse jj version from {out!r}")
        return tuple(int(x) for x in m.groups())

    def root(self) -> str:
        """The workspace root."""
        return self._read("root").strip()

    def log(self, revset: str) -> list[Commit]:
        """Commits in `revset`, newest first."""
        out = self._read("log", "--no-graph", "-r", revset, "-T", _COMMIT_TEMPLATE + ' ++ "\\n"')
        return [_parse_commit(json.loads(line)) for line in out.splitlines() if line.strip()]

    def commit(self, rev: str) -> Commit:
        """The single commit `rev` resolves to."""
        commits = self.log(rev)
        if len(commits) != 1:
            raise JJHError(f"`{rev}` resolves to {len(commits)} commits, expected 1")
        return commits[0]

    def bookmarks(self) -> dict[str, Bookmark]:
        """Every local bookmark and every bookmark on `self.remote`."""
        out = self._read("bookmark", "list", "--all-remotes", "-T", 'json(self) ++ "\\n"')
        local: dict[str, tuple[str, ...]] = {}
        remote: dict[str, tuple[str, ...]] = {}
        tracked: set[str] = set()
        for line in out.splitlines():
            if not line.strip():
                continue
            data = json.loads(line)
            targets = tuple(t for t in data.get("target") or () if t)
            if "remote" not in data:
                local[data["name"]] = targets
            elif data["remote"] == self.remote:
                remote[data["name"]] = targets
                if "tracking_target" in data:
                    tracked.add(data["name"])
        return {
            name: Bookmark(
                name, local=local.get(name, ()), remote=remote.get(name, ()),
                tracked=name in tracked)
            for name in sorted(set(local) | set(remote))}

    def graph(self, revset: str, current: str | None) -> list[GraphLine]:
        """Render `revset` with jj's graph renderer.

        Trunk commits are drawn as `◆`, and other commits as `○`.

        Args:
            revset: commits to draw.
            current: id of the commit to draw as `@`.
        """
        cur = f'self.contained_in("{current}")' if current else "false"
        node = f'if(self, if(self.contained_in("::trunk()"), "◆", if({cur}, "@", "○")), "~")'
        template = (
            f'"{_SENTINEL}" ++ json({{"commit_id" => commit_id, '
            '"title" => description.first_line(), '
            '"on_trunk" => self.contained_in("::trunk()"), '
            '"bookmarks" => local_bookmarks.map(|b| b.name()), '
            f'"remote" => remote_bookmarks.filter(|b| b.remote() == {quote(self.remote)} '
            '&& !b.tracked()).map(|b| b.name())}) ++ "\\n"')
        out = self._read(
            "log", "-r", revset, "-T", template,
            "--config", 'ui.graph.style="curved"',
            "--config", "ui.log-synthetic-elided-nodes=false",
            "--config", f"templates.log_node={json.dumps(node)}")
        lines: list[GraphLine] = []
        for line in out.splitlines():
            if _SENTINEL in line:
                prefix, payload = line.split(_SENTINEL, 1)
                data = json.loads(payload)
                lines.append(GraphNode(
                    prefix=prefix, commit_id=data["commit_id"], title=data["title"],
                    on_trunk=data["on_trunk"],
                    bookmarks=tuple(data["bookmarks"]) + tuple(data["remote"])))
            else:
                lines.append(line)
        return lines

    def fetch(self) -> None:
        """Fetch from the remote."""
        self._run("git", "fetch", "--remote", self.remote)

    def push(
        self, *bookmarks: str, tracked: bool = False, deleted: bool = False,
    ) -> None:
        """Push the given bookmarks, all tracked bookmarks, or deletions."""
        args = ["git", "push", "--remote", self.remote]
        for b in bookmarks:
            args += ["-b", f"exact:{b}"]
        if tracked:
            args.append("--tracked")
        if deleted:
            args.append("--deleted")
        self._run(*args)

    def bookmark_create(self, name: str, rev: str) -> None:
        """Create a local bookmark."""
        self._run("bookmark", "create", name, "-r", rev)

    def bookmark_forget(self, *names: str) -> None:
        """Forget local bookmarks and untrack their remote bookmarks."""
        self._run("bookmark", "forget", *(f"exact:{n}" for n in names))

    def track(self, *names: str) -> None:
        """Track remote bookmarks."""
        self._run("bookmark", "track", *(f"exact:{n}" for n in names), f"--remote={self.remote}")

    def new_insert_before(self, rev: str, message: str) -> None:
        """Insert an empty commit below `rev` without moving `@`."""
        self._run("new", "--insert-before", rev, "--no-edit", "-m", message)

    def rebase(self, source: str, dest: str, skip_emptied: bool = False) -> None:
        """Rebase `source` and its descendants onto `dest`."""
        args = ["rebase", "-s", source, "-d", dest]
        if skip_emptied:
            args.append("--skip-emptied")
        self._run(*args)

    def abandon(self, rev: str) -> None:
        """Abandon a commit."""
        self._run("abandon", rev)

    def describe(self, rev: str, message: str) -> None:
        """Set a commit's description."""
        self._run("describe", rev, "-m", message)
