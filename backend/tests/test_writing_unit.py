"""Rubric maths, AI-output validation and AI provider settings (no database)."""

from decimal import Decimal

import pytest

from app.ai.contracts import CorrectionResult, CriterionScore, WritingEvaluation
from app.ai.contracts import WritingEvaluationRequest as Request
from app.ai.engine import AIError
from app.core.config import Settings
from app.modules.writing import rubric
from app.modules.writing.service import validate_evaluation

TEXT = "Yesterday i go home."


@pytest.mark.parametrize(
    ("scores", "band"),
    [
        ([6, 6, 6, 6], "6.0"),
        ([6, 6, 6, 7], "6.5"),  # 6.25 rounds up to 6.5
        ([6, 7, 7, 7], "7.0"),  # 6.75 rounds up to 7
        ([6, 6, 6, 6.5], "6.0"),  # 6.125 rounds down
        ([5.5, 6, 6, 6], "6.0"),  # 5.875 rounds up to 6
        ([0, 0, 0, 0], "0.0"),
        ([9, 9, 9, 9], "9.0"),
    ],
)
def test_overall_band_uses_ielts_rounding(scores, band) -> None:
    assert rubric.overall_band(scores) == Decimal(band)


def test_snapshot_marks_every_criterion_required() -> None:
    snapshot = rubric.snapshot()
    assert snapshot["version"] == rubric.RUBRIC_VERSION
    assert [c["code"] for c in snapshot["criteria"]] == rubric.CODES
    assert all(c["required"] for c in snapshot["criteria"])
    assert "not an official IELTS score" in snapshot["disclaimer"]


def request(text=TEXT) -> Request:
    return Request(
        title="t",
        instructions="i",
        cefr_level="B1",
        target_word_count=None,
        response_text=text,
        criteria=rubric.CRITERIA,
        score_min=0,
        score_max=9,
        score_step=0.5,
    )


def result(scores=None, corrections=(), codes=None, corrected="Yesterday I went home."):
    codes = codes or rubric.CODES
    scores = scores or [6.0] * len(codes)
    return WritingEvaluation(
        summary="s",
        corrected_text=corrected,
        criteria=[
            CriterionScore(code=c, score=s, feedback="f")
            for c, s in zip(codes, scores, strict=True)
        ],
        corrections=list(corrections),
    )


def fix(start, end, original, replacement="X") -> CorrectionResult:
    return CorrectionResult(
        start=start,
        end=end,
        original=original,
        replacement=replacement,
        category="grammar",
        title="t",
        explanation="e",
        example="",
    )


def test_valid_output_passes() -> None:
    validate_evaluation(
        request(), result(corrections=[fix(10, 11, "i", "I"), fix(12, 14, "go", "went")])
    )
    validate_evaluation(request(), result(corrections=[fix(14, 14, "", " quickly")]))  # insertion


@pytest.mark.parametrize(
    "bad",
    [
        result(codes=rubric.CODES[:3]),  # missing a criterion
        result(codes=[*rubric.CODES[:3], "task_response"]),  # duplicate criterion
        result(scores=[6.0, 6.0, 6.0, 9.5]),  # out of range
        result(scores=[6.0, 6.0, 6.0, 6.3]),  # not a half band
        result(corrections=[fix(0, 3, "xyz")]),  # span does not match the text
        result(corrections=[fix(18, 30, "me.")]),  # out of bounds
        result(corrections=[fix(12, 14, "go"), fix(10, 11, "i")]),  # unordered
        result(corrections=[fix(10, 14, "i go"), fix(12, 14, "go")]),  # overlapping
        result(corrections=[fix(12, 14, "go", "go")]),  # no-op correction
        result(corrected="   "),
    ],
)
def test_invalid_output_is_rejected(bad) -> None:
    with pytest.raises(AIError) as error:
        validate_evaluation(request(), bad)
    assert error.value.code == "AI_OUTPUT_INVALID" and error.value.retryable


def test_ai_provider_defaults_and_production_guard() -> None:
    base = {"_env_file": None, "postgres_password": "p", "jwt_secret": "j" * 32}
    assert Settings(**base).ai_provider == "fake"
    assert Settings(**base, app_env="production").ai_provider == "none"
    with pytest.raises(ValueError):
        Settings(**base, app_env="production", ai_provider="fake")
