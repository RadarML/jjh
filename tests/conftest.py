"""Fixtures: a real jj repository with a bare git remote, and a fake GitHub."""

import os
import shutil
import subprocess
from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest

from jjh.context import Context
from jjh.github import PullRequest, RepoInfo
from jjh.jj import JJ
from jjh.run import Runner

requires_jj = pytest.mark.skipif(shutil.which("jj") is None, reason="jj is not installed")

URL = "https://github.com/RadarML/xwr"


def link(n: int, head: str) -> str:
    return f'<a href="{URL}/pull/{n}">#{n} {head}</a>'


GOLDEN_94 = f"""\
@  {link(94, "dev/demo-config")}: Select demo config and rsp from --device
├─╮
│ ○  {link(90, "fix/real-only-range")}: Fix XWRConfig.max_range for real-only radars
○ │  {link(93, "dev/awrl6888-docs")}: Document AWRL6888EVM setup
○ │  {link(92, "dev/awrl6888-rsp")}: Add AWRL6888EVM signal processing and demo config
○ │  {link(91, "dev/awrl6888")}: Add AWRL6888 radar interface
├─╯
○  {link(96, "ci/all-pr-bases")}: Run CI on pull requests against any base
◆  main"""


@dataclass
class FakeGitHub:
    """In-memory stand-in for [`GhCli`][jjh.github.GhCli]."""

    info: RepoInfo = field(default_factory=lambda: RepoInfo(URL, "main", "me"))
    prs: dict[int, PullRequest] = field(default_factory=dict)
    calls: list[tuple] = field(default_factory=list)
    next_number: int = 1

    def repo(self) -> RepoInfo:
        return self.info

    def pull_requests(self) -> list[PullRequest]:
        return sorted(self.prs.values(), key=lambda p: p.number)

    def add(self, number: int, head: str, base: str, title: str = "", body: str = "",
            author: str = "me", draft: bool | None = None) -> PullRequest:
        pr = PullRequest(
            number, head, base, title, body, author,
            is_draft=base != "main" if draft is None else draft)
        self.prs[number] = pr
        self.next_number = max(self.next_number, number + 1)
        return pr

    def create(self, head, base, title, body, draft, reviewers=()) -> int:
        n = self.next_number
        self.add(n, head, base, title, body, draft=draft)
        self.calls.append(("create", n, base, draft))
        return n

    def edit(self, number, *, title=None, body=None, base=None) -> None:
        changes = {k: v for k, v in [("title", title), ("body", body), ("base", base)]
                   if v is not None}
        self.prs[number] = replace(self.prs[number], **changes)
        self.calls.append(("edit", number, tuple(sorted(changes))))

    def ready(self, number) -> None:
        self.prs[number] = replace(self.prs[number], is_draft=False)
        self.calls.append(("ready", number))

    def merge(self, number: int) -> None:
        self.prs[number] = replace(self.prs[number], state="MERGED")

    def edits(self) -> list[tuple]:
        return [c for c in self.calls if c[0] == "edit"]


@dataclass
class Repo:
    """A colocated jj repository cloned from a bare git remote."""

    root: Path
    path: Path
    env: dict[str, str]
    gh: FakeGitHub

    def jj(self, *args: str) -> str:
        return subprocess.run(
            ["jj", "--no-pager", "--color=never", *args], cwd=self.path, env=self.env,
            check=True, capture_output=True, text=True).stdout

    def git_remote(self, *args: str) -> str:
        """Run git in a scratch clone of the remote (to act as GitHub)."""
        scratch = self.root / "github"
        if not scratch.exists():
            subprocess.run(
                ["git", "clone", "-q", str(self.root / "remote.git"), str(scratch)],
                check=True, capture_output=True)
        return subprocess.run(
            ["git", "-c", "user.name=GitHub", "-c", "user.email=gh@example.com", *args],
            cwd=scratch, check=True, capture_output=True, text=True).stdout

    def ctx(self) -> Context:
        runner = Runner(cwd=self.path, echo=False, env=self.env)
        return Context(jj=JJ(run=runner), gh=self.gh)

    def commit(self, *parents: str, message: str, bookmark: str | None = None,
               file: str | None = None) -> None:
        """Create a commit on `parents` that adds one file."""
        self.jj("new", *parents, "-m", message)
        name = file or (bookmark or message).replace("/", "_").replace(" ", "_")
        (self.path / name).write_text(message + "\n")
        if bookmark:
            self.jj("bookmark", "create", bookmark, "-r", "@")

    def clone(self, name: str) -> "Repo":
        """Another clone of the same remote, sharing the fake GitHub."""
        path = self.root / name
        subprocess.run(
            ["jj", "git", "clone", "--colocate", str(self.root / "remote.git"), str(path)],
            env=self.env, check=True, capture_output=True)
        return Repo(self.root, path, self.env, self.gh)

    def target(self, bookmark: str) -> str:
        return self.jj("log", "--no-graph", "-r", f'bookmarks(exact:"{bookmark}")',
                       "-T", "commit_id").strip()


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    config = tmp_path / "jjconfig.toml"
    config.write_text(
        'user.name = "Me"\nuser.email = "me@example.com"\n'
        '[ui]\ncolor = "never"\npaginate = "never"\n')
    env = {
        "JJ_CONFIG": str(config), "HOME": str(tmp_path), "PATH": _path(),
        "GIT_CONFIG_GLOBAL": "/dev/null"}
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(tmp_path / "remote.git")],
                   check=True)
    subprocess.run(["jj", "git", "clone", "--colocate", str(tmp_path / "remote.git"),
                    str(tmp_path / "work")], env=env, check=True, capture_output=True)
    r = Repo(tmp_path, tmp_path / "work", env, FakeGitHub())
    (r.path / "README").write_text("hi\n")
    r.jj("describe", "-m", "init")
    r.jj("bookmark", "create", "main", "-r", "@")
    r.jj("git", "push", "-b", "main")
    r.jj("new")
    return r


def _path() -> str:
    return os.environ.get("PATH", "")


def remote_branches(repo) -> set[str]:
    out = repo.git_remote("ls-remote", "--heads", "origin")
    return {line.split("refs/heads/", 1)[1] for line in out.splitlines()}


def parents(repo, rev: str) -> list[str]:
    out = repo.jj("log", "--no-graph", "-r", f"parents({rev})", "-T",
                  'local_bookmarks.map(|b| b.name()).join(",") ++ "\\n"')
    return sorted(out.split())


def squash_merge(repo, number: int, retarget: dict[int, str] | None = None) -> None:
    """Squash-merge a PR on the fake GitHub and delete its branch."""
    head = repo.gh.prs[number].head
    repo.git_remote("fetch", "-q", "--prune", "origin")
    repo.git_remote("checkout", "-q", "-B", "main", "origin/main")
    repo.git_remote("merge", "-q", "--squash", f"origin/{head}")
    repo.git_remote("commit", "-q", "-m", f"{repo.gh.prs[number].title} (#{number})")
    repo.git_remote("push", "-q", "origin", "main")
    repo.git_remote("push", "-q", "origin", "--delete", head)
    repo.gh.merge(number)
    for n, base in (retarget or {}).items():
        repo.gh.edit(n, base=base)


XWR_TITLES = {
    96: ("ci/all-pr-bases", "Run CI on pull requests against any base"),
    91: ("dev/awrl6888", "Add AWRL6888 radar interface"),
    92: ("dev/awrl6888-rsp", "Add AWRL6888EVM signal processing and demo config"),
    93: ("dev/awrl6888-docs", "Document AWRL6888EVM setup"),
    90: ("fix/real-only-range", "Fix XWRConfig.max_range for real-only radars"),
    94: ("dev/demo-config", "Select demo config and rsp from --device"),
}


@pytest.fixture
def xwr(repo: Repo) -> Repo:
    """The AWRL6888 PRs from the guide: #94 is a merge of #93's stack and #90."""
    t = XWR_TITLES
    repo.commit("main", message=t[96][1], bookmark=t[96][0])
    repo.commit(t[96][0], message=t[91][1], bookmark=t[91][0])
    repo.commit(t[91][0], message=t[92][1], bookmark=t[92][0])
    repo.commit(t[92][0], message=t[93][1], bookmark=t[93][0])
    repo.commit(t[96][0], message=t[90][1] + "\n\nOnly real-only radars.", bookmark=t[90][0])
    repo.jj("new", t[93][0], t[90][0], "-m", "JJ_MERGE_DIFFBASE: dev/demo-config")
    repo.jj("bookmark", "create", "jj-diffbase/dev/demo-config", "-r", "@")
    repo.commit("jj-diffbase/dev/demo-config", message=t[94][1], bookmark=t[94][0])
    repo.jj("new")
    repo.jj("git", "push", "--all")
    bases = {96: "main", 91: t[96][0], 92: t[91][0], 93: t[92][0], 90: t[96][0],
             94: "jj-diffbase/dev/demo-config"}
    for n, (head, title) in t.items():
        repo.gh.add(n, head, bases[n], title=title, body="old body")
    repo.gh.next_number = 97
    return repo
