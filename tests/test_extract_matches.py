import json
import logging
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests
import responses

from src import extract_matches

API_URL = f"{extract_matches.API_BASE_URL}/competitions/BSA/matches"
VALID_PAYLOAD = {"matches": [{"id": 1001}]}


@pytest.fixture(autouse=True)
def configure_test_logging() -> None:
    extract_matches.configure_logging()


def test_build_http_session_retries_expected_status_codes() -> None:
    session = extract_matches.build_http_session()
    retries = session.get_adapter("https://").max_retries

    assert retries.total == 4
    assert retries.backoff_factor == 1
    assert set(retries.status_forcelist) == {429, 500, 502, 503, 504}
    assert retries.respect_retry_after_header is True
    session.close()


@responses.activate
def test_load_matches_from_api_returns_valid_payload(
    capsys: pytest.CaptureFixture[str],
) -> None:
    responses.get(
        API_URL,
        json=VALID_PAYLOAD,
        status=200,
        headers={"X-RequestsAvailable": "9"},
    )

    result = extract_matches.load_matches_from_api("BSA", 2025, "secret")

    assert result == VALID_PAYLOAD
    assert responses.calls[0].request.params == {"season": "2025"}
    assert responses.calls[0].request.headers["X-Auth-Token"] == "secret"
    assert "secret" not in capsys.readouterr().err


@responses.activate
def test_load_matches_from_api_retries_rate_limit_response() -> None:
    responses.get(API_URL, status=429, headers={"Retry-After": "0"})
    responses.get(API_URL, json=VALID_PAYLOAD, status=200)

    result = extract_matches.load_matches_from_api("BSA", 2025, "secret")

    assert result == VALID_PAYLOAD
    assert len(responses.calls) == 2


def test_load_matches_from_api_reports_timeout() -> None:
    session = Mock(spec=requests.Session)
    session.get.side_effect = requests.Timeout("slow response")

    with pytest.raises(extract_matches.ApiRequestError, match="timed out"):
        extract_matches.load_matches_from_api(
            "BSA",
            2025,
            "secret",
            session=session,
        )


def test_invalid_rate_limit_header_is_logged_without_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = Mock(spec=requests.Response)
    response.headers = {
        "X-RequestsAvailable": "0",
        "X-RequestCounter-Reset": "invalid",
    }
    warning = Mock()
    monkeypatch.setattr(extract_matches.LOGGER, "warning", warning)

    extract_matches.handle_rate_limit_headers(response)

    assert warning.call_args.kwargs["extra"]["event"] == "invalid_rate_limit_header"


@responses.activate
def test_load_matches_from_api_rejects_invalid_json() -> None:
    responses.get(
        API_URL,
        body="not-json",
        status=200,
        content_type="application/json",
    )

    with pytest.raises(
        extract_matches.PayloadValidationError,
        match="invalid JSON",
    ):
        extract_matches.load_matches_from_api("BSA", 2025, "secret")


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ([], "JSON object"),
        ({}, "missing the 'matches' field"),
        ({"matches": {}}, "must be a list"),
        ({"matches": ["invalid"]}, "must be an object"),
        ({"matches": [{"id": None}]}, "invalid positive integer"),
        ({"matches": [{"id": -1}]}, "invalid positive integer"),
    ],
)
def test_validate_matches_payload_rejects_invalid_shape(
    payload: object,
    message: str,
) -> None:
    with pytest.raises(extract_matches.PayloadValidationError, match=message):
        extract_matches.validate_matches_payload(payload)


def test_load_matches_from_sample_rejects_missing_file(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.json"

    with pytest.raises(extract_matches.PipelineError, match="not found"):
        extract_matches.load_matches_from_sample(missing_path)


def test_upsert_empty_payload_does_not_connect(monkeypatch: pytest.MonkeyPatch) -> None:
    connect = Mock(side_effect=AssertionError("database should not be used"))
    monkeypatch.setattr(extract_matches, "connect_to_postgres", connect)

    assert extract_matches.upsert_raw_matches({"matches": []}, "BSA", 2025) == 0
    connect.assert_not_called()


def test_upsert_builds_rows_and_commits(monkeypatch: pytest.MonkeyPatch) -> None:
    cursor = Mock()
    cursor.__enter__ = Mock(return_value=cursor)
    cursor.__exit__ = Mock(return_value=False)

    connection = Mock()
    connection.__enter__ = Mock(return_value=connection)
    connection.__exit__ = Mock(return_value=False)
    connection.cursor.return_value = cursor
    monkeypatch.setattr(
        extract_matches,
        "connect_to_postgres",
        Mock(return_value=connection),
    )

    result = extract_matches.upsert_raw_matches(
        VALID_PAYLOAD,
        competition_code="BSA",
        season=2025,
        source="sample",
    )

    assert result == 1
    rows = cursor.executemany.call_args.args[1]
    assert rows[0][0:4] == ("sample", "BSA", 2025, 1001)
    connection.commit.assert_called_once_with()


def test_main_runs_sample_without_api_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    upsert = Mock(return_value=1)
    monkeypatch.setattr(extract_matches, "load_dotenv", Mock())
    monkeypatch.setattr(
        extract_matches,
        "load_matches_from_sample",
        Mock(return_value=VALID_PAYLOAD),
    )
    monkeypatch.setattr(extract_matches, "upsert_raw_matches", upsert)
    monkeypatch.delenv("FOOTBALL_DATA_API_TOKEN", raising=False)

    result = extract_matches.main(["--sample"])

    assert result == 0
    assert upsert.call_args.kwargs["source"] == "sample"


def test_main_returns_failure_without_api_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(extract_matches, "load_dotenv", Mock())
    monkeypatch.delenv("FOOTBALL_DATA_API_TOKEN", raising=False)

    assert extract_matches.main([]) == 1


def test_json_log_formatter_emits_machine_readable_context() -> None:
    record = logging.LogRecord(
        name="football_pipeline",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="Completed",
        args=(),
        exc_info=None,
    )
    record.event = "pipeline_completed"
    record.match_count = 4

    output = json.loads(extract_matches.JsonLogFormatter().format(record))

    assert output["level"] == "INFO"
    assert output["event"] == "pipeline_completed"
    assert output["match_count"] == 4
