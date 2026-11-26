"""Integration tests for `jjh adopt` and `jjh release`."""

import pytest
from conftest import requires_jj

from jjh.commands.adopt import adopt, release
from jjh.run import JJHError

pytestmark = requires_jj


def test_adopt_and_release(xwr):
    other = xwr.clone("other")
    new = adopt(other.ctx(), "#93")
    assert set(new) == {
        "ci/all-pr-bases", "dev/awrl6888", "dev/awrl6888-rsp", "dev/awrl6888-docs",
        "fix/real-only-range", "jj-diffbase/dev/demo-config", "dev/demo-config"}
    assert adopt(other.ctx(), "dev/demo-config") == []

    other.jj("describe", "-r", "dev/awrl6888", "-m", "Local edit")
    with pytest.raises(JJHError, match="Unpushed"):
        release(other.ctx(), "94")
    other.jj("undo")
    assert len(release(other.ctx(), "94")) == 7
    assert "dev/awrl6888" not in other.jj("bookmark", "list")
