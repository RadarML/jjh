"""The repositories a `jjh` command works on."""

from dataclasses import dataclass
from pathlib import Path

from .github import GhCli, GitHub, PullRequest, RepoInfo
from .jj import JJ, MIN_VERSION, NOT_DIFFBASE, Commit, quote
from .run import JJHError, Runner
from .stack import Snapshot, render_graph


@dataclass
class Context:
    """The jj and GitHub repositories a command works on.

    Attributes:
        jj: jj command wrapper.
        gh: GitHub access.
        dry_run: print mutating commands instead of running them.
    """

    jj: JJ
    gh: GitHub
    dry_run: bool = False

    @classmethod
    def create(
        cls, *, dry_run: bool = False, remote: str = "origin", cwd: Path | None = None,
    ) -> "Context":
        """Set up a context for the repository containing `cwd`."""
        runner = Runner(cwd=cwd, dry_run=dry_run)
        jj = JJ(run=runner, remote=remote)
        version = jj.version()
        if version < MIN_VERSION:
            raise JJHError(
                f"jj {'.'.join(map(str, version))} is too old; jjh needs "
                f"{'.'.join(map(str, MIN_VERSION))} or newer")
        root = Path(jj.root())
        if not (root / ".git").exists():
            raise JJHError(
                f"{root} is not a colocated jj repository; run `jj git init --colocate`")
        return cls(jj=jj, gh=GhCli(run=Runner(cwd=root, dry_run=dry_run)), dry_run=dry_run)

    @property
    def repo(self) -> RepoInfo:
        """The GitHub repository."""
        return self.gh.repo()

    def _snapshot_commits(self, extra: str | None = None) -> dict[str, Commit]:
        """Every commit between trunk and a bookmark, local or remote, or `extra`."""
        remote = quote(self.jj.remote)
        heads = f"bookmarks() | remote_bookmarks(remote=exact:{remote})"
        if extra:
            heads += f" | ({extra})"
        return {c.commit_id: c for c in self.jj.log(f"trunk()..({heads})")}

    def snapshot(
        self, prs: list[PullRequest] | None = None, extra: str | None = None,
    ) -> Snapshot:
        """Read the current commits, bookmarks and PRs.

        Args:
            prs: reuse an earlier PR listing instead of querying GitHub.
            extra: revset of more commits to include, with their ancestors.
        """
        return Snapshot(
            repo=self.repo, bookmarks=self.jj.bookmarks(),
            commits=self._snapshot_commits(extra),
            prs=self.gh.pull_requests() if prs is None else prs)

    def graph_text(self, snap: Snapshot, head: str) -> str:
        """Render the graph for the PR whose head commit is `head`.

        Shows the PR graph's bookmarked commits, without diffbases, and main
        once at the bottom. After a landing, part of a graph can sit on a newer
        main than the rest. Only the oldest main commit is drawn, and jj
        connects the other edges to it.
        """
        remote = quote(self.jj.remote)
        graph = f"trunk()..(roots(trunk()..{head})::)"
        shown = (
            f"(({graph}) & (bookmarks() | untracked_remote_bookmarks(remote=exact:{remote}))"
            f" {NOT_DIFFBASE}) | roots(parents({graph}) & ::trunk())")
        return render_graph(self.jj.graph(shown, current=head), snap.open_prs, snap.repo)
