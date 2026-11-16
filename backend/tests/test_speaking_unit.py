"""Speaking rules that need no database: evaluation output and recording checks."""

import io
import wave

import pytest

from app.ai.contracts import (
    SpeakingCriterionResult,
    SpeakingEvaluation,
    SpeakingEvaluationRequest,
)
from app.ai.engine import AIError
from app.core.errors import ApiError
from app.modules.speaking import rubric
from app.modules.speaking.service import check_recording, validate_evaluation

REQUEST = SpeakingEvaluationRequest(
    title="t",
    instructions="i",
    cefr_level="B1",
    turns=[],
    recordings=[],
    criteria=rubric.CRITERIA,
    score_min=0,
    score_max=9,
    score_step=0.5,
)


def result(**overrides) -> SpeakingEvaluation:
    items = {
        code: SpeakingCriterionResult(code=code, assessed=True, score=6.0, feedback="ok")
        for code in rubric.CODES
    }
    items.update(overrides)
    return SpeakingEvaluation(summary="Summary.", criteria=list(items.values()))


def test_audio_criteria_are_forced_unassessed_without_audio() -> None:
    verdicts = validate_evaluation(REQUEST, result(), audio_assessed=False).verdicts
    scores = {v.code: v.score for v in verdicts}
    assert scores["pronunciation"] is None and scores["fluency_coherence"] is None
    assert scores["lexical_resource"] == 6.0
    assert all(v.feedback == rubric.NOT_ASSESSED for v in verdicts if v.score is None)


def test_audio_criteria_kept_with_real_audio_assessment() -> None:
    verdicts = validate_evaluation(REQUEST, result(), audio_assessed=True).verdicts
    assert all(v.score == 6.0 for v in verdicts)


@pytest.mark.parametrize(
    "bad",
    [
        SpeakingEvaluation(summary="s", criteria=result().criteria[:3]),  # one missing
        SpeakingEvaluation(summary="s", criteria=[*result().criteria, result().criteria[0]]),
        result(
            lexical_resource=SpeakingCriterionResult(
                code="lexical_resource", assessed=True, score=6.3, feedback="x"
            )
        ),
        result(
            lexical_resource=SpeakingCriterionResult(
                code="lexical_resource", assessed=True, score=None, feedback="x"
            )
        ),
        result(
            made_up=SpeakingCriterionResult(code="made_up", assessed=True, score=5, feedback="x")
        ),
    ],
)
def test_invalid_evaluations_are_rejected(bad) -> None:
    with pytest.raises(AIError):
        validate_evaluation(REQUEST, bad, audio_assessed=True)


def test_overall_band_rounding() -> None:
    assert str(rubric.overall_band([6.0, 6.5, 6.5, 6.0])) == "6.5"  # 6.25 rounds up
    assert str(rubric.overall_band([7.0, 6.5, 6.5, 6.5])) == "6.5"  # 6.625 rounds down


def _wav(seconds: float) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(1)
        writer.setframerate(8_000)
        writer.writeframes(b"\x80" * int(8_000 * seconds))
    return buffer.getvalue()


def test_recording_checks(settings) -> None:
    assert check_recording(settings, _wav(1)).duration_ms == 1000
    with pytest.raises(ApiError) as long:
        check_recording(settings, _wav(settings.max_audio_duration_ms / 1000 + 1))
    assert long.value.status_code == 413
    with pytest.raises(ApiError) as garbage:
        check_recording(settings, b"OggS" + b"\x00" * 200)
    assert garbage.value.status_code == 415
