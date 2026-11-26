"""Unit tests for commit/PR text handling."""

import pytest

from jjh import description as desc
from jjh.description import Action


def test_split_and_join():
    assert desc.split("Title\n\nPara one.\n\n- item\n") == ("Title", "Para one.\n\n- item")
    assert desc.split("Title only\n") == ("Title only", "")
    assert desc.split("") == ("", "")
    assert desc.join("Title", "Body\r\n") == "Title\n\nBody\n"
    assert desc.join("Title", "") == "Title\n"


def test_hash_ignores_crlf_and_trailing_space():
    assert desc.text_hash("T", "a\nb") == desc.text_hash("T ", "a  \r\nb\r\n")
    assert desc.text_hash("T", "a") != desc.text_hash("T", "b")


SECTION = desc.render_section("◆  main", "abc123")


def test_render_section():
    assert SECTION == (
        "<!-- jj-graph synced=abc123 -->\n***\n**JJ Commit Graph**\n\n<pre>\n◆  main\n"
        "</pre>\n<!-- /jj-graph -->")
    assert desc.render_section("x", None).startswith("<!-- jj-graph -->\n")


def test_strip_section():
    assert desc.strip_section(f"Body.\r\n\r\n{SECTION}\n") == ("Body.", "abc123")
    assert desc.strip_section("<!-- jj-graph -->\nx\n<!-- /jj-graph -->") == ("", None)
    assert desc.strip_section("No section") == ("No section", None)


def test_set_section_keeps_text_outside_markers():
    body = "Before.\n<!-- jj-graph -->\nold\n<!-- /jj-graph -->\nAfter."
    assert desc.set_section(body, "NEW") == "Before.\nNEW\nAfter."
    assert desc.set_section("Text.  \n", "NEW") == "Text.\n\nNEW\n"
    assert desc.set_section("", "NEW") == "NEW\n"
    once = desc.set_section("Text.", SECTION)
    assert desc.set_section(once, SECTION) == once


def test_pr_body():
    assert desc.pr_body("Body.\n", "S") == "Body.\n\nS\n"
    assert desc.pr_body("", "S") == "S\n"


def test_escape():
    assert desc.escape('a & <b> "c"') == 'a &amp; &lt;b&gt; "c"'


@pytest.mark.parametrize(("commit", "pr", "synced", "action"), [
    ("a", "a", "a", Action.NOTHING),
    ("b", "a", "a", Action.PUSH),
    ("a", "b", "a", Action.PULL),
    ("b", "c", "a", Action.CONFLICT),
    ("b", "b", "a", Action.NOTHING),   # both made the same edit
    ("a", "b", None, Action.PUSH),     # never synced: the commit wins
    ("a", "a", None, Action.NOTHING),
])
def test_decide(commit, pr, synced, action):
    assert desc.decide(commit, pr, synced) == action
