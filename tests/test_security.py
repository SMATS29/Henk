"""Tests voor security modules."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from henk.security.path_validator import validate_read_path, validate_write_path
from henk.security.proxy import SecurityProxy
from henk.security.source_tag import tag_output


def test_proxy_blocks_post_requests():
    proxy = SecurityProxy(["example.com"], ["GET"])
    with pytest.raises(PermissionError):
        proxy.request("POST", "https://example.com")


def test_proxy_blocks_domains_not_allowlisted():
    proxy = SecurityProxy(["example.com"], ["GET"])
    with pytest.raises(PermissionError):
        proxy.request("GET", "https://evil.com")


@patch("henk.security.proxy.http_requests.request")
def test_proxy_allows_get_for_allowlisted_domain(mock_request):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "ok"
    mock_request.return_value = mock_response
    proxy = SecurityProxy(["example.com"], ["GET"])

    result = proxy.request("GET", "https://example.com")

    assert result.status_code == 200
    assert result.text == "ok"
    mock_request.assert_called_once_with("GET", "https://example.com", timeout=10)


def test_proxy_blocks_suspicious_query_parameters():
    proxy = SecurityProxy(["example.com"], ["GET"])
    with pytest.raises(PermissionError):
        proxy.request("GET", "https://example.com?q=1&api_key=secret")


def test_path_validator_blocks_path_traversal(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    blocked = validate_read_path(str(root / ".." / ".." / "etc" / "passwd"), [str(root)])
    assert blocked is None


def test_path_validator_blocks_symlink_outside_root(tmp_path):
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (outside / "secret.txt").write_text("x", encoding="utf-8")
    (root / "link.txt").symlink_to(outside / "secret.txt")

    assert validate_read_path(str(root / "link.txt"), [str(root)]) is None


def test_path_validator_accepts_path_within_roots(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    f = root / "a.txt"
    f.write_text("ok", encoding="utf-8")

    assert validate_read_path(str(f), [str(root)]) == str(f.resolve())


def test_validate_write_path_limited_to_run_workspace(tmp_path):
    ws = tmp_path / "workspace"
    run = "run_1"
    allowed = validate_write_path("a/b.txt", run, str(ws))
    blocked = validate_write_path(str(tmp_path / "x.txt"), run, str(ws))

    assert allowed is not None
    assert blocked is None


def test_source_tag_generates_correct_tags():
    tagged = tag_output("web_search", "result", external=True)
    assert tagged.startswith("[TOOL:web_search — EXTERNAL]")
    assert tagged.endswith("[/TOOL:web_search]")
