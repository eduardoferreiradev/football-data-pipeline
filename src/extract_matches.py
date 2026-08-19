import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import psycopg
import requests
from dotenv import load_dotenv
from psycopg.types.json import Jsonb


API_BASE_URL = "https://api.football-data.org/v4"


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
        print(f"API requests available: {requests_available}")

    if requests_available == "0" and reset_seconds:
        wait_seconds = int(reset_seconds) + 1
        print(f"Rate limit reached. Waiting {wait_seconds} seconds before continuing.")
        time.sleep(wait_seconds)


def load_matches_from_api(competition_code: str, season: int, token: str) -> dict:
    url = f"{API_BASE_URL}/competitions/{competition_code}/matches"
    response = requests.get(
        url,
        headers={"X-Auth-Token": token},
        params={"season": season},
        timeout=30,
    )
    handle_rate_limit_headers(response)
    response.raise_for_status()
    return response.json()


def load_matches_from_sample(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def connect_to_postgres() -> psycopg.Connection:
    return psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5433"),
        dbname=os.getenv("POSTGRES_DB", "futebol_dw"),
        user=os.getenv("POSTGRES_USER", "futebol"),
        password=os.getenv("POSTGRES_PASSWORD", "futebol"),
    )


def upsert_raw_matches(
    data: dict,
    competition_code: str,
    season: int,
    source: str = "football-data.org",
) -> int:
    matches = data.get("matches", [])
    extracted_at = datetime.now(timezone.utc)

    if not matches:
        return 0

    with connect_to_postgres() as conn:
        with conn.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO raw.matches (
                    source,
                    competition_code,
                    season_year,
                    match_id,
                    extracted_at,
                    payload
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (source, match_id)
                DO UPDATE SET
                    competition_code = EXCLUDED.competition_code,
                    season_year = EXCLUDED.season_year,
                    extracted_at = EXCLUDED.extracted_at,
                    payload = EXCLUDED.payload
                """,
                [
                    (
                        source,
                        competition_code,
                        season,
                        match["id"],
                        extracted_at,
                        Jsonb(match),
                    )
                    for match in matches
                ],
            )
        conn.commit()

    return len(matches)


def parse_args() -> argparse.Namespace:
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
        default="data/sample/football_data_bsa_matches_sample.json",
        help="Path to a football-data.org compatible sample JSON file.",
    )
    parser.add_argument(
        "--competition",
        default=os.getenv("FOOTBALL_COMPETITION_CODE", "BSA"),
        help="football-data.org competition code. BSA is Campeonato Brasileiro Serie A.",
    )
    parser.add_argument(
        "--season",
        type=int,
        default=int(os.getenv("FOOTBALL_SEASON", "2025")),
        help="Season start year.",
    )
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()

    if args.sample:
        data = load_matches_from_sample(Path(args.sample_path))
        source = "sample"
    else:
        token = os.getenv("FOOTBALL_DATA_API_TOKEN")
        if not token:
            raise RuntimeError(
                "FOOTBALL_DATA_API_TOKEN is required. "
                "Use --sample to run without an API token."
            )
        data = load_matches_from_api(args.competition, args.season, token)
        source = "football-data.org"

    loaded_count = upsert_raw_matches(
        data=data,
        competition_code=args.competition,
        season=args.season,
        source=source,
    )
    print(f"Loaded {loaded_count} matches into raw.matches.")


if __name__ == "__main__":
    main()
