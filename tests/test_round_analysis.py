"""Manual expectations for late results, corrections and partial tie breakers."""

import json
import os
from copy import deepcopy
from decimal import Decimal
from uuid import uuid4

from src import extract_matches as extract
from src.history import ingest


def calendar(games):
    # (round, home suffix, away suffix, home goals, away goals, status)
    data = json.loads(extract.DEFAULT_SAMPLE_PATH.read_text(encoding="utf-8"))
    template = deepcopy(data["matches"][0])
    data["filters"]["season"] = "2026"
    data["matches"] = []
    for index, (round_number, home, away, hg, ag, status) in enumerate(games):
        m = deepcopy(template)
        m.update(id=700001 + index, matchday=round_number, status=status)
        m["season"]["startDate"] = "2026-01-28"
        m["homeTeam"] = {"id": 100 + home, "name": f"Clube {home} sintético"}
        m["awayTeam"] = {"id": 100 + away, "name": f"Clube {away} sintético"}
        m["score"]["fullTime"] = {"home": hg, "away": ag}
        data["matches"].append(m)
    extract.validate_matches_payload(data, "BSA", 2026)
    return data


def load(data, source, database):
    extract.validate_matches_payload(data, "BSA", 2026)
    ingest(data, "BSA", 2026, source, database)


def test_manual_rounds_delay_correction_and_tie_breakers(database, build_dbt):
    prefix = "rounds-" + uuid4().hex
    source = prefix + "-late"
    data = calendar(
        [
            (1, 1, 2, 2, 0, "FINISHED"),
            (1, 3, 4, 1, 1, "FINISHED"),
            (2, 1, 3, None, None, "POSTPONED"),
            (2, 2, 4, 0, 1, "FINISHED"),
            (3, 1, 4, 0, 0, "FINISHED"),
            (3, 2, 3, None, None, "SCHEDULED"),
        ]
    )
    load(data, source, database)
    points_source = prefix + "-h2h-points"
    load(
        calendar(
            [
                (1, 1, 2, 1, 0, "FINISHED"),
                (2, 2, 1, 0, 1, "FINISHED"),
                (3, 1, 3, 0, 1, "FINISHED"),
                (3, 2, 4, 1, 0, "FINISHED"),
                (4, 1, 4, 0, 1, "FINISHED"),
                (4, 2, 3, 1, 0, "FINISHED"),
            ]
        ),
        points_source,
        database,
    )
    gd_source = prefix + "-h2h-gd"
    load(
        calendar(
            [
                (1, 1, 2, 3, 0, "FINISHED"),
                (2, 2, 1, 2, 0, "FINISHED"),
                (3, 1, 3, 1, 0, "FINISHED"),
                (3, 2, 4, 0, 1, "FINISHED"),
                (4, 1, 4, 0, 2, "FINISHED"),
                (4, 2, 3, 2, 0, "FINISHED"),
            ]
        ),
        gd_source,
        database,
    )
    trio_source = prefix + "-trio"
    load(
        calendar(
            [
                (1, 1, 2, 1, 0, "FINISHED"),
                (2, 2, 3, 1, 0, "FINISHED"),
                (3, 3, 1, 1, 0, "FINISHED"),
            ]
        ),
        trio_source,
        database,
    )
    wins_source = prefix + "-wins"
    load(
        calendar(
            [
                (1, 1, 3, 1, 0, "FINISHED"),
                (2, 4, 1, 10, 0, "FINISHED"),
                (1, 2, 4, 0, 0, "FINISHED"),
                (2, 2, 3, 0, 0, "FINISHED"),
                (3, 3, 2, 0, 0, "FINISHED"),
            ]
        ),
        wins_source,
        database,
    )
    # Real-scope configuration with an intentionally reduced calendar in the test DB.
    load(calendar([(3, 1, 2, 3, 0, "AWARDED")]), "football-data.org", database)
    build_dbt(os.environ["FOOTBALL_TEST_DSN"])

    with database() as conn:
        # (team, games, wins, draws, losses, GF, GA, GD, P) at cutoff 3.
        assert conn.execute(
            "SELECT team_id,matches_played,wins,draws,losses,goals_for,"
            "goals_against,goal_difference,points FROM mart.team_round_performance "
            "WHERE source=%s AND cutoff_round=3 AND venue='total' ORDER BY team_id",
            (source,),
        ).fetchall() == [
            (101, 2, 1, 1, 0, 2, 0, 2, 4),
            (102, 2, 0, 0, 2, 0, 3, -3, 0),
            (103, 1, 0, 1, 0, 1, 1, 0, 1),
            (104, 3, 1, 2, 0, 2, 1, 1, 5),
        ]
        assert conn.execute(
            "SELECT team_id,position,tie_reason FROM mart.standings_by_round "
            "WHERE source=%s AND cutoff_round=1 ORDER BY display_order",
            (source,),
        ).fetchall() == [
            (101, 1, None),
            (103, 2, "head_to_head_incomplete"),
            (104, 2, "head_to_head_incomplete"),
            (102, 4, None),
        ]
        assert conn.execute(
            "SELECT efficiency_pct FROM mart.team_round_performance WHERE source=%s "
            "AND cutoff_round=1 AND team_id=102 AND venue='home'",
            (source,),
        ).fetchone() == (None,)
        efficiency = conn.execute(
            "SELECT efficiency_pct FROM mart.team_round_performance WHERE source=%s "
            "AND cutoff_round=3 AND team_id=104 AND venue='total'",
            (source,),
        ).fetchone()[0]
        assert abs(efficiency - Decimal(500) / 9) < Decimal("0.00000001")
        assert conn.execute(
            "SELECT team_id,head_to_head_points,head_to_head_goal_difference,position "
            "FROM mart.standings_by_round WHERE source=%s AND cutoff_round=4 "
            "AND team_id IN (101,102) ORDER BY team_id",
            (points_source,),
        ).fetchall() == [(101, 6, 2, 1), (102, 0, -2, 2)]
        assert conn.execute(
            "SELECT team_id,head_to_head_points,head_to_head_goal_difference,position "
            "FROM mart.standings_by_round WHERE source=%s AND cutoff_round=4 "
            "AND team_id IN (101,102) ORDER BY team_id",
            (gd_source,),
        ).fetchall() == [(101, 3, 1, 2), (102, 3, -1, 3)]
        assert (
            conn.execute(
                "SELECT position,head_to_head_games,tie_reason "
                "FROM mart.standings_by_round "
                "WHERE source=%s AND cutoff_round=3 ORDER BY team_id",
                (trio_source,),
            ).fetchall()
            == [(1, 0, "cards_and_draw_unavailable")] * 3
        )
        positions = dict(
            conn.execute(
                "SELECT team_id,position FROM mart.standings_by_round "
                "WHERE source=%s AND cutoff_round=3",
                (wins_source,),
            ).fetchall()
        )
        assert positions[101] < positions[102]
        assert conn.execute(
            "SELECT count(*),max(points),max(position),count(efficiency_pct) "
            "FROM mart.standings_by_round WHERE source='football-data.org' "
            "AND season_year=2026"
        ).fetchone() == (76, 0, 1, 0)
        assert conn.execute(
            "SELECT matchday,matches_received,matches_played,"
            "missing_matches,round_status "
            "FROM mart.round_summary WHERE source='football-data.org' "
            "AND season_year=2026 AND matchday IN (1,3,38) ORDER BY matchday"
        ).fetchall() == [
            (1, 0, 0, 10, "incomplete"),
            (3, 1, 0, 9, "incomplete"),
            (38, 0, 0, 10, "incomplete"),
        ]
        assert conn.execute(
            "SELECT observed_team_count,expected_team_count FROM mart.dim_rounds "
            "WHERE source='football-data.org' AND season_year=2026 LIMIT 1"
        ).fetchone() == (2, 20)
        assert conn.execute(
            "SELECT count(*) FROM mart.team_attack_defense "
            "WHERE source='football-data.org' AND season_year=2026"
        ).fetchone() == (0,)
        # Synthetic source stays observed, without assumed ten-game rounds.
        assert conn.execute(
            "SELECT matches_expected,round_status FROM mart.round_summary "
            "WHERE source=%s LIMIT 1",
            (source,),
        ).fetchone() == (None, "unknown")

    data["matches"][2]["status"] = "FINISHED"
    data["matches"][2]["score"]["fullTime"] = {"home": 1, "away": 0}
    load(data, source, database)
    build_dbt(os.environ["FOOTBALL_TEST_DSN"])
    with database() as conn:
        assert conn.execute(
            "SELECT cutoff_round,points FROM mart.team_round_performance "
            "WHERE source=%s AND team_id=101 AND venue='total' ORDER BY cutoff_round",
            (source,),
        ).fetchall() == [(1, 3), (2, 6), (3, 7)]

    data["matches"][2]["score"]["fullTime"] = {"home": 0, "away": 1}
    load(data, source, database)
    build_dbt(os.environ["FOOTBALL_TEST_DSN"])
    with database() as conn:
        assert conn.execute(
            "SELECT team_id,matches_played,wins,draws,losses,goals_for,"
            "goals_against,goal_difference,points FROM mart.team_round_performance "
            "WHERE source=%s AND cutoff_round=3 AND venue='total' ORDER BY team_id",
            (source,),
        ).fetchall() == [
            (101, 3, 1, 1, 1, 2, 1, 1, 4),
            (102, 2, 0, 0, 2, 0, 3, -3, 0),
            (103, 2, 1, 1, 0, 2, 1, 1, 4),
            (104, 3, 1, 2, 0, 2, 1, 1, 5),
        ]
        assert conn.execute(
            "SELECT team_id,position FROM mart.standings_by_round "
            "WHERE source=%s AND cutoff_round=2 ORDER BY display_order",
            (source,),
        ).fetchall() == [(103, 1), (104, 1), (101, 3), (102, 4)]
        assert conn.execute(
            "SELECT position_change FROM mart.standings_by_round "
            "WHERE source=%s AND team_id=104 AND cutoff_round=2",
            (source,),
        ).fetchone() == (1,)
