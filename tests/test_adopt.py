"""Integration tests for `jjh adopt` and `jjh release`."""

import pytest
from conftest import requires_jj

from jjh.commands.adopt import adopt, release
from jjh.run import JJHError

pytestmark = requires_jj


def test_adopt_and_release(example):
    other = example.clone("other")
    new = adopt(other.ctx(), "#93")
    assert set(new) == {
        "ci/test-all-prs", "dev/parser", "dev/parser-cli", "docs/parser",
        "fix/empty-input", "jj-diffbase/dev/examples", "dev/examples"}
    assert adopt(other.ctx(), "dev/examples") == []

    other.jj("describe", "-r", "dev/parser", "-m", "Local edit")
    with pytest.raises(JJHError, match="Unpushed"):
        release(other.ctx(), "94")
    other.jj("undo")
    assert len(release(other.ctx(), "94")) == 7
    assert "dev/parser" not in other.jj("bookmark", "list")
