"""IELTS-style Writing rubric used for practice scoring.

Scores are practice band estimates for learning, not official IELTS results. The four
criteria follow the public IELTS Writing assessment criteria. Each is scored 0-9 in
half-band steps and all are required. The overall band is their mean rounded the way
IELTS reports it: to the nearest half band, with .25 rounding up to .5 and .75 up to the
next whole band.

A snapshot of this rubric is stored on every exercise and evaluation, so changing it
later (with a new RUBRIC_VERSION) never changes how past results were scored.
"""

import math
from decimal import Decimal

from app.ai.contracts import RubricCriterion

RUBRIC_VERSION = "writing-ielts-practice-v1"
SCORE_MIN, SCORE_MAX, SCORE_STEP = 0.0, 9.0, 0.5
DISCLAIMER = "Practice band estimate for learning only; not an official IELTS score."

CRITERIA = [
    RubricCriterion(
        code="task_response",
        name="Task Response",
        descriptor=(
            "Answers every part of the task, presents a clear position or purpose, and "
            "supports main ideas with relevant, extended examples."
        ),
    ),
    RubricCriterion(
        code="coherence_cohesion",
        name="Coherence and Cohesion",
        descriptor=(
            "Organises ideas logically into paragraphs, progresses clearly, and uses "
            "linking words and referencing accurately without overuse."
        ),
    ),
    RubricCriterion(
        code="lexical_resource",
        name="Lexical Resource",
        descriptor=(
            "Uses a range of vocabulary precisely and naturally, with accurate spelling "
            "and word formation."
        ),
    ),
    RubricCriterion(
        code="grammatical_range_accuracy",
        name="Grammatical Range and Accuracy",
        descriptor=(
            "Uses a variety of sentence structures with accurate grammar and punctuation; "
            "errors do not reduce communication."
        ),
    ),
]
CODES = [criterion.code for criterion in CRITERIA]


def snapshot() -> dict:
    """Stored as rubric_snapshot. The database reads criteria[].code/required."""
    return {
        "version": RUBRIC_VERSION,
        "scale": {"min": SCORE_MIN, "max": SCORE_MAX, "step": SCORE_STEP},
        "overall": "mean of criteria, rounded to nearest half band (.25 and .75 round up)",
        "disclaimer": DISCLAIMER,
        "criteria": [
            {"code": c.code, "name": c.name, "descriptor": c.descriptor, "required": True}
            for c in CRITERIA
        ],
    }


def is_valid_band(score: float) -> bool:
    return SCORE_MIN <= score <= SCORE_MAX and (score / SCORE_STEP).is_integer()


def overall_band(scores: list[float]) -> Decimal:
    mean = sum(scores) / len(scores)
    # Nearest half band with ties rounding up: 6.25 -> 6.5, 6.75 -> 7.0, 6.125 -> 6.0.
    return Decimal(str(math.floor(mean * 2 + 0.5) / 2))
