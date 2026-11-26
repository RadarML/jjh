"""Commit descriptions, PR text, and the graph section in PR bodies."""

import hashlib
import html
import re
from enum import Enum

_OPEN_MARKER = "<!-- jj-graph"
_CLOSE_MARKER = "<!-- /jj-graph -->"

_SECTION = re.compile(
    r"<!-- jj-graph(?:\s+synced=(?P<synced>[0-9a-f]+))?\s*-->.*?<!-- /jj-graph -->",
    re.DOTALL)


def split(description: str) -> tuple[str, str]:
    """Split a commit description into a title and a body.

    The title is the first line. The body is the rest, without the blank
    line between them.
    """
    text = _normalize(description)
    title, _, body = text.partition("\n")
    return title.strip(), body.strip("\n")


def join(title: str, body: str) -> str:
    """Build a commit description from a title and a body."""
    body = _normalize(body)
    return f"{title.strip()}\n\n{body}\n" if body else f"{title.strip()}\n"


def _normalize(text: str) -> str:
    """Normalize text for comparison.

    Converts CRLF to LF (GitHub's web editor saves CRLF), and strips trailing
    whitespace and leading and trailing blank lines.
    """
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return "\n".join(line.rstrip() for line in lines).strip("\n")


def strip_section(body: str) -> tuple[str, str | None]:
    """Remove the graph section from a PR body.

    Returns:
        The normalized body without the section, and the hash stored in the
        opening marker, if any.
    """
    m = _SECTION.search(body)
    if m is None:
        return _normalize(body), None
    return _normalize(body[:m.start()] + body[m.end():]), m.group("synced")


def text_hash(title: str, body: str) -> str:
    """Hash a normalized title and body."""
    text = f"{_normalize(title)}\n\n{_normalize(body)}"
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def render_section(graph: str, synced: str | None) -> str:
    """Render the graph section.

    Args:
        graph: the graph as HTML, with links and escaped titles.
        synced: hash to store in the opening marker.
    """
    opening = f"{_OPEN_MARKER} synced={synced} -->" if synced else f"{_OPEN_MARKER} -->"
    return (
        f"{opening}\n***\n**JJ Commit Graph**\n\n<pre>\n{graph.rstrip()}\n</pre>\n"
        f"{_CLOSE_MARKER}")


def set_section(body: str, section: str) -> str:
    """Replace the graph section in a PR body, or append one.

    Text outside the markers is not changed.
    """
    m = _SECTION.search(body)
    if m is not None:
        return body[:m.start()] + section + body[m.end():]
    text = body.rstrip()
    return f"{text}\n\n{section}\n" if text else f"{section}\n"


def pr_body(text: str, section: str) -> str:
    """Build a PR body from description text and a graph section."""
    text = _normalize(text)
    return f"{text}\n\n{section}\n" if text else f"{section}\n"


def escape(text: str) -> str:
    """HTML-escape `&`, `<` and `>`."""
    return html.escape(text, quote=False)


class Action(Enum):
    """What `jjh sync` does with a PR's title and body."""

    NOTHING = "nothing"
    """Neither side changed: regenerate the graph section only."""
    PUSH = "push"
    """The commit changed: copy its description to the PR."""
    PULL = "pull"
    """The PR changed: copy its title and body into the commit."""
    CONFLICT = "conflict"
    """Both changed: change nothing and report a conflict."""


def decide(commit: str, pr: str, synced: str | None) -> Action:
    """Decide which way to sync.

    Args:
        commit: [`text_hash`][^.] of the commit description.
        pr: [`text_hash`][^.] of the PR title and body, without the section.
        synced: hash stored at the last sync, if any.
    """
    if commit == pr:
        return Action.NOTHING
    if synced is None:
        # Never synced: the commit wins.
        return Action.PUSH
    commit_changed = commit != synced
    pr_changed = pr != synced
    if commit_changed and pr_changed:
        return Action.CONFLICT
    if pr_changed:
        return Action.PULL
    return Action.PUSH
