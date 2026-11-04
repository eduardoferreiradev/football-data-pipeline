import json
from copy import deepcopy

import pytest

from src import extract_matches as extract
from src.run_pipeline import coverage


@pytest.fixture
def data():
    return json.loads(extract.DEFAULT_SAMPLE_PATH.read_text(encoding="utf-8"))


def test_wrong_scope(data):
    for competition, season in [("BSA", 2026), ("PL", 2025)]:
        with pytest.raises(extract.PayloadValidationError):
            extract.validate_matches_payload(data, competition, season)


def test_duplicate(data):
    data["matches"].append(deepcopy(data["matches"][0]))
    with pytest.raises(extract.PayloadValidationError, match="Duplicate"):
        extract.validate_matches_payload(data)


@pytest.mark.parametrize("score", [None, -1, True, 2147483648, "2"])
def test_invalid_finished_score(data, score):
    data["matches"][0]["status"] = "FINISHED"
    data["matches"][0]["score"]["fullTime"]["home"] = score
    with pytest.raises(extract.PayloadValidationError):
        extract.validate_matches_payload(data)


def test_scheduled_without_scores(data):
    data["matches"][0]["status"] = "SCHEDULED"
    data["matches"][0]["score"]["fullTime"] = {"home": None, "away": None}
    assert extract.validate_matches_payload(data) is data


def test_sample_is_not_full_season(data):
    assert coverage(data)["matches"] == 4
