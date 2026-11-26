"""Tests for the `gh` wrapper, with a canned command runner."""

import json

from jjh.github import GhCli
from jjh.run import Runner

NODE = {
    "number": 94, "headRefName": "dev/demo-config", "baseRefName": "jj-diffbase/dev/demo-config",
    "title": "Select demo config", "body": None, "isDraft": True, "state": "OPEN",
    "headRefOid": "abc", "author": {"login": "me"}}


class FakeRunner(Runner):
    def __init__(self, dry_run: bool = False):
        super().__init__(dry_run=dry_run, echo=False)
        self.calls: list[tuple[list[str], str | None]] = []

    def __call__(self, args, *, mutates=False, input=None):
        self.calls.append((args, input))
        if args[1:3] == ["repo", "view"]:
            return json.dumps({
                "nameWithOwner": "RadarML/xwr", "url": "https://github.com/RadarML/xwr",
                "defaultBranchRef": {"name": "main"}})
        if args[1:3] == ["api", "user"]:
            return "me\n"
        if args[1:3] == ["api", "graphql"]:
            page2 = any(a.startswith("cursor=") for a in args)
            return json.dumps({"data": {"repository": {
                "open": {"pageInfo": {"hasNextPage": not page2, "endCursor": "c1"},
                         "nodes": [{**NODE, "number": 95 if page2 else 94}]},
                "merged": {"nodes": [{**NODE, "number": 80, "state": "MERGED"}]}}}})
        if args[1:3] == ["pr", "create"]:
            return "https://github.com/RadarML/xwr/pull/97\n"
        return ""


def test_repo_and_prs():
    gh = GhCli(run=FakeRunner())
    assert gh.repo().pr_url(3) == "https://github.com/RadarML/xwr/pull/3"
    assert gh.repo().viewer == "me"
    prs = gh.pull_requests()
    assert [(p.number, p.state) for p in prs] == [(80, "MERGED"), (94, "OPEN"), (95, "OPEN")]
    assert prs[1].body == "" and prs[1].is_draft and prs[1].author == "me"


def test_create_and_edit():
    runner = FakeRunner()
    gh = GhCli(run=runner)
    assert gh.create("dev/x", "dev/w", "Title", "Body", draft=True, reviewers=("bob",)) == 97
    args, body = runner.calls[-1]
    assert args[:3] == ["gh", "pr", "create"] and "--draft" in args and body == "Body"
    assert args[args.index("--reviewer") + 1] == "bob"

    gh.edit(97, title="T", body="B", base="main")
    args, body = runner.calls[-1]
    assert args == ["gh", "pr", "edit", "97", "--title", "T", "--body-file", "-", "--base", "main"]
    assert body == "B"
    gh.edit(97, base="dev/w")
    assert runner.calls[-1] == (["gh", "pr", "edit", "97", "--base", "dev/w"], None)
    gh.ready(97)
    assert runner.calls[-1][0] == ["gh", "pr", "ready", "97"]


def test_create_dry_run():
    assert GhCli(run=FakeRunner(dry_run=True)).create("a", "b", "t", "", False) == 0
