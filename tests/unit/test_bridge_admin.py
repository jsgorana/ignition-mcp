"""_zip_with_secret must only rewrite the BRIDGE_SECRET assignment, not the
gateway-side "is this configured?" guard that shares the same placeholder
token. A blind text-wide replace corrupts that guard into an always-true
comparison, so bridge_install would report "not configured" forever even on
a correctly configured install.
"""

from __future__ import annotations

import zipfile
from io import BytesIO

from ignition_mcp.tools.bridge_admin import LIB_ARCNAME, SECRET_PLACEHOLDER, _zip_with_secret


def test_zip_with_secret_leaves_the_guard_placeholder_intact():
    secret = "some-real-secret-value"
    payload = _zip_with_secret(secret)

    with zipfile.ZipFile(BytesIO(payload)) as zf:
        text = zf.read(LIB_ARCNAME).decode("utf-8")

    assert f"BRIDGE_SECRET = {secret!r}" in text
    assert f"BRIDGE_SECRET == '{SECRET_PLACEHOLDER}'" in text
    assert text.count(secret) == 1, "secret must only appear in the assignment line"
