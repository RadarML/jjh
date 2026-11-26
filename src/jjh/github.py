"""GitHub access through the `gh` command line."""

import json
import re
from dataclasses import dataclass, field
from typing import Protocol

from .run import JJHError, Runner


@dataclass(frozen=True)
class RepoInfo:
    """A GitHub repository.

    Attributes:
        url: repository URL, e.g. `https://github.com/example/repo`.
        default_branch: the branch PRs land in, usually `main`.
        viewer: login of the authenticated user.
    """

    url: str
    default_branch: str
    viewer: str

    def pr_url(self, number: int) -> str:
        """URL of a pull request."""
        return f"{self.url}/pull/{number}"


@dataclass(frozen=True)
class PullRequest:
    """A pull request.

    Attributes:
        number: PR number.
        head: head branch name (the bookmark).
        base: base branch name.
        title: PR title.
        body: PR description.
        author: login of the PR's author.
        is_draft: whether the PR is a draft.
        state: `OPEN`, `MERGED` or `CLOSED`.
        head_oid: commit id of the PR's head.
    """

    number: int
    head: str
    base: str
    title: str
    body: str
    author: str
    is_draft: bool = False
    state: str = "OPEN"
    head_oid: str = ""


class GitHub(Protocol):
    """The GitHub operations `jjh` needs."""

    def repo(self) -> RepoInfo:
        """Repository and viewer information."""
        ...

    def pull_requests(self) -> list[PullRequest]:
        """Every open PR, plus recently merged ones."""
        ...

    def create(
        self, head: str, base: str, title: str, body: str, draft: bool,
        reviewers: tuple[str, ...] = (),
    ) -> int:
        """Open a PR and return its number."""
        ...

    def edit(
        self, number: int, *, title: str | None = None, body: str | None = None,
        base: str | None = None,
    ) -> None:
        """Edit a PR's title, body or base."""
        ...

    def ready(self, number: int) -> None:
        """Mark a draft PR as ready for review."""
        ...


_PR_FIELDS = """
  number headRefName baseRefName title body isDraft state headRefOid
  author { login }
"""

_QUERY = """
query($owner: String!, $name: String!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    open: pullRequests(first: 100, after: $cursor, states: [OPEN]) {
      pageInfo { hasNextPage endCursor }
      nodes { %s }
    }
    merged: pullRequests(last: 50, states: [MERGED]) {
      nodes { %s }
    }
  }
}
""" % (_PR_FIELDS, _PR_FIELDS)


def _parse_pr(node: dict) -> PullRequest:
    return PullRequest(
        number=node["number"], head=node["headRefName"], base=node["baseRefName"],
        title=node["title"], body=node["body"] or "",
        author=(node.get("author") or {}).get("login", ""),
        is_draft=node["isDraft"], state=node["state"], head_oid=node["headRefOid"] or "")


@dataclass
class GhCli:
    """[`GitHub`][^.] implemented with the `gh` command line.

    Attributes:
        run: command runner.
    """

    run: Runner = field(default_factory=Runner)
    _repo: RepoInfo | None = None
    _owner_name: tuple[str, str] | None = None

    def _gh(self, *args: str, mutates: bool = False, input: str | None = None) -> str:
        return self.run(["gh", *args], mutates=mutates, input=input)

    def repo(self) -> RepoInfo:
        if self._repo is None:
            data = json.loads(self._gh(
                "repo", "view", "--json", "nameWithOwner,url,defaultBranchRef"))
            viewer = self._gh("api", "user", "--jq", ".login").strip()
            owner, name = data["nameWithOwner"].split("/", 1)
            self._owner_name = (owner, name)
            self._repo = RepoInfo(
                url=data["url"], default_branch=data["defaultBranchRef"]["name"],
                viewer=viewer)
        return self._repo

    def pull_requests(self) -> list[PullRequest]:
        self.repo()
        assert self._owner_name is not None
        owner, name = self._owner_name
        prs: dict[int, PullRequest] = {}
        cursor: str | None = None
        while True:
            args = [
                "api", "graphql", "-f", f"query={_QUERY}",
                "-f", f"owner={owner}", "-f", f"name={name}"]
            if cursor:
                args += ["-f", f"cursor={cursor}"]
            repo = json.loads(self._gh(*args))["data"]["repository"]
            for node in repo["open"]["nodes"] + repo["merged"]["nodes"]:
                prs[node["number"]] = _parse_pr(node)
            page = repo["open"]["pageInfo"]
            if not page["hasNextPage"]:
                break
            cursor = page["endCursor"]
        return sorted(prs.values(), key=lambda p: p.number)

    def create(
        self, head: str, base: str, title: str, body: str, draft: bool,
        reviewers: tuple[str, ...] = (),
    ) -> int:
        args = [
            "pr", "create", "--head", head, "--base", base, "--title", title,
            "--body-file", "-"]
        if draft:
            args.append("--draft")
        for r in reviewers:
            args += ["--reviewer", r]
        out = self._gh(*args, mutates=True, input=body)
        if self.run.dry_run:
            return 0
        m = re.search(r"/pull/(\d+)", out)
        if not m:
            raise JJHError(f"Could not find the new PR's number in {out!r}")
        return int(m.group(1))

    def edit(
        self, number: int, *, title: str | None = None, body: str | None = None,
        base: str | None = None,
    ) -> None:
        args = ["pr", "edit", str(number)]
        if title is not None:
            args += ["--title", title]
        if body is not None:
            args += ["--body-file", "-"]
        if base is not None:
            args += ["--base", base]
        self._gh(*args, mutates=True, input=body)

    def ready(self, number: int) -> None:
        self._gh("pr", "ready", str(number), mutates=True)

