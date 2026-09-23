# tests/test_http.py
from fitness_app import http


def test_http_error_message_names_status_and_path():
    err = http.HttpError(500, "/v2/recovery", body="boom")
    assert str(err) == "HTTP 500 on /v2/recovery"
    assert err.status == 500
    assert err.body == "boom"


def test_network_error_message():
    err = http.HttpError(0, "/v2/recovery", body="network error: timed out")
    assert str(err) == "Network error on /v2/recovery: network error: timed out"


def test_log_path_strips_query_string():
    # Query strings carry pagination tokens and, on the auth redirect, a code.
    # Nothing after '?' may ever reach a log line.
    assert http._log_path("https://x.test/v2/recovery?nextToken=abc&limit=25") == "/v2/recovery"
