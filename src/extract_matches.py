import argparse
import json
import logging
import os
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg
import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

if __package__ in (None, ""):
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

API_BASE_URL = "https://api.football-data.org/v4"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SAMPLE_PATH = (
    PROJECT_ROOT / "data" / "sample" / "football_data_bsa_matches_sample.json"
)
REQUEST_TIMEOUT = (5, 30)
RETRYABLE_STATUS_CODES = (429, 500, 502, 503, 504)
LOGGER = logging.getLogger("football_pipeline")


class PipelineError(RuntimeError):
    """Base exception for expected pipeline failures."""


class ApiRequestError(PipelineError):
    """Raised when the football-data.org request fails."""


class PayloadValidationError(PipelineError):
    """Raised when an API or sample payload has an invalid shape."""


class ConfigurationError(PipelineError):
    """Raised when required configuration is missing."""


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in (
            "event",
            "source",
            "competition_code",
            "season",
            "match_count",
            "status_code",
            "requests_available",
            "reset_seconds",
        ):
            if hasattr(record, field):
                payload[field] = getattr(record, field)

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=True)


def configure_logging() -> None:
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())

    LOGGER.handlers.clear()
    LOGGER.addHandler(handler)
    LOGGER.setLevel(level)
    LOGGER.propagate = False


def build_http_session() -> requests.Session:
    retry = Retry(
        total=4,
        connect=4,
        read=4,
        status=4,
        backoff_factor=1,
        status_forcelist=RETRYABLE_STATUS_CODES,
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def handle_rate_limit_headers(response: requests.Response) -> None:
    requests_available = response.headers.get(
        "X-RequestsAvailable",
        response.headers.get("X-Requests-Available"),
    )
    reset_seconds = response.headers.get(
        "X-RequestCounter-Reset",
        response.headers.get("X-Request-Counter-Reset"),
    )

    if requests_available is not None:
        LOGGER.info(
            "API rate limit received",
            extra={
                "event": "api_rate_limit",
                "requests_available": requests_available,
                "reset_seconds": reset_seconds,
            },
        )

    if requests_available == "0" and reset_seconds is not None:
        try:
            parsed_reset = max(0.0, float(reset_seconds))
        except ValueError:
            LOGGER.warning(
                "API returned an invalid rate limit reset value",
                extra={
                    "event": "invalid_rate_limit_header",
                    "reset_seconds": reset_seconds,
                },
            )
        else:
            LOGGER.warning(
                "API request quota is exhausted",
                extra={
                    "event": "api_rate_limit_exhausted",
                    "reset_seconds": parsed_reset,
                },
            )


def validate_matches_payload(
    data: Any, competition_code: str | None = None, season: int | None = None
) -> dict[str, Any]:
    from src.validation import validate

    return validate(data, competition_code, season, PayloadValidationError)


def load_matches_from_api(
    competition_code: str,
    season: int,
    token: str,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    url = f"{API_BASE_URL}/competitions/{competition_code}/matches"
    client = session or build_http_session()
    owns_session = session is None

    LOGGER.info(
        "Requesting matches from API",
        extra={
            "event": "api_request_started",
            "competition_code": competition_code,
            "season": season,
        },
    )

    try:
        response = client.get(
            url,
            headers={"X-Auth-Token": token},
            params={"season": season},
            timeout=REQUEST_TIMEOUT,
        )
        handle_rate_limit_headers(response)
        response.raise_for_status()
    except requests.Timeout as error:
        raise ApiRequestError("football-data.org request timed out.") from error
    except requests.RequestException as error:
        status_code = getattr(error.response, "status_code", None)
        message = "football-data.org request failed"
        if status_code is not None:
            message = f"{message} with HTTP {status_code}"
        raise ApiRequestError(f"{message}.") from error
    finally:
        if owns_session:
            client.close()

    try:
        data = response.json()
    except (requests.JSONDecodeError, ValueError) as error:
        raise PayloadValidationError("API returned invalid JSON.") from error

    validated_data = validate_matches_payload(data, competition_code, season)
    LOGGER.info(
        "API request completed",
        extra={
            "event": "api_request_completed",
            "competition_code": competition_code,
            "season": season,
            "match_count": len(validated_data["matches"]),
            "status_code": response.status_code,
        },
    )
    return validated_data


def load_matches_from_sample(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except FileNotFoundError as error:
        raise PipelineError(f"Sample file not found: {path}") from error
    except OSError as error:
        raise PipelineError(f"Could not read sample file: {path}") from error
    except json.JSONDecodeError as error:
        raise PayloadValidationError(
            f"Sample file contains invalid JSON: {path}"
        ) from error

    return validate_matches_payload(data)


def connect_to_postgres() -> psycopg.Connection:
    return psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5434"),
        dbname=os.getenv("POSTGRES_DB", "futebol_dw"),
        user=os.getenv("POSTGRES_USER", "futebol"),
        password=os.getenv("POSTGRES_PASSWORD", "futebol"),
        connect_timeout=10,
    )


def upsert_raw_matches(
    data: dict[str, Any],
    competition_code: str,
    season: int,
    source: str = "football-data.org",
    observed_at: datetime | None = None,
    run_id=None,
) -> int:
    from src.history import ingest

    validate_matches_payload(data, competition_code, season)
    return ingest(
        data, competition_code, season, source, connect_to_postgres, observed_at, run_id
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract football matches and load raw JSON into PostgreSQL."
    )
    parser.add_argument(
        "--sample",
        action="store_true",
        help="Load local sample data instead of calling the API.",
    )
    parser.add_argument(
        "--sample-path",
        type=Path,
        default=DEFAULT_SAMPLE_PATH,
        help="Path to a football-data.org compatible sample JSON file.",
    )
    parser.add_argument(
        "--competition",
        default=os.getenv("FOOTBALL_COMPETITION_CODE", "BSA"),
        help=(
            "football-data.org competition code. BSA is Campeonato Brasileiro Serie A."
        ),
    )
    parser.add_argument(
        "--season",
        type=int,
        default=os.getenv("FOOTBALL_SEASON", "2026"),
        help="Season start year.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    load_dotenv(PROJECT_ROOT / ".env")
    configure_logging()
    args = parse_args(argv)
    source = "sample" if args.sample else "football-data.org"

    LOGGER.info(
        "Pipeline started",
        extra={
            "event": "pipeline_started",
            "source": source,
            "competition_code": args.competition,
            "season": args.season,
        },
    )

    try:
        if args.sample:
            data = load_matches_from_sample(args.sample_path)
        else:
            token = os.getenv("FOOTBALL_DATA_API_TOKEN")
            if not token:
                raise ConfigurationError(
                    "FOOTBALL_DATA_API_TOKEN is required. "
                    "Use --sample to run without an API token."
                )
            data = load_matches_from_api(args.competition, args.season, token)

        loaded_count = upsert_raw_matches(
            data=data,
            competition_code=args.competition,
            season=args.season,
            source=source,
        )
    except (PipelineError, psycopg.Error):
        LOGGER.exception(
            "Pipeline failed",
            extra={
                "event": "pipeline_failed",
                "source": source,
                "competition_code": args.competition,
                "season": args.season,
            },
        )
        return 1

    LOGGER.info(
        "Pipeline completed",
        extra={
            "event": "pipeline_completed",
            "source": source,
            "competition_code": args.competition,
            "season": args.season,
            "match_count": loaded_count,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
