"""Validate the shared match contract before any database writes."""

from datetime import date, datetime

STATUSES = {
    "SCHEDULED",
    "TIMED",
    "IN_PLAY",
    "PAUSED",
    "FINISHED",
    "SUSPENDED",
    "POSTPONED",
    "CANCELLED",
    "AWARDED",
}


def validate(data, competition=None, season=None, error=ValueError):
    def fail(message):
        raise error(message)

    def integer(value, name, maximum=2**63 - 1, minimum=1):
        if type(value) is not int or not minimum <= value <= maximum:
            fail(f"{name}: invalid positive integer or out of range.")

    def obj(value):
        if not isinstance(value, dict):
            fail("Expected an object.")
        return value

    def text(value, name):
        if not isinstance(value, str) or not value.strip():
            fail(f"{name}: required text.")

    def timestamp(value, name):
        text(value, name)
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            fail(f"{name}: invalid timestamp.")
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            fail(f"{name}: timezone required.")

    if not isinstance(data, dict):
        fail("Payload must be a JSON object.")
    if "matches" not in data:
        fail("Payload is missing the 'matches' field.")
    matches = data["matches"]
    if not isinstance(matches, list):
        fail("matches must be a list.")
    if not matches:
        fail("Payload contains no matches.")
    seen = set()
    for m in matches:
        if not isinstance(m, dict):
            fail("Each match must be an object.")
        integer(m.get("id"), "id")
        if m["id"] in seen:
            fail("Duplicate match ID.")
        seen.add(m["id"])
        code = obj(m.get("competition")).get("code")
        text(code, "competition.code")
        if code != obj(data.get("competition")).get("code"):
            fail("Match competition differs from payload.")
        if competition is not None and code != competition:
            fail("Unexpected competition.")
        try:
            year = date.fromisoformat(obj(m.get("season"))["startDate"]).year
        except (KeyError, TypeError, ValueError):
            fail("Invalid season startDate.")
        if season is None:
            season = year
        if year != season:
            fail("Unexpected season.")
        timestamp(m.get("utcDate"), "utcDate")
        timestamp(m.get("lastUpdated"), "lastUpdated")
        if m.get("status") not in STATUSES:
            fail("Unsupported status.")
        integer(m.get("matchday"), "matchday", 38 if code == "BSA" else 1000)
        if code == "BSA" and m.get("stage") != "REGULAR_SEASON":
            fail("Unexpected BSA stage.")
        teams = [obj(m.get(side)) for side in ("homeTeam", "awayTeam")]
        for team in teams:
            integer(team.get("id"), "team.id")
            text(team.get("name"), "team.name")
        if teams[0]["id"] == teams[1]["id"]:
            fail("Teams must differ.")
        full_time = obj(obj(m.get("score", {})).get("fullTime", {}))
        for side in ("home", "away"):
            value = full_time.get(side)
            if value is None:
                if m["status"] == "FINISHED":
                    fail("FINISHED requires both scores.")
            else:
                integer(value, "score", 2**31 - 1, 0)
    return data
