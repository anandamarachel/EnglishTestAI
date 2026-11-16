"""IELTS-style Speaking rubric used for practice feedback.

Scores are practice band estimates for learning, not official IELTS results. The four
criteria follow the public IELTS Speaking assessment criteria, each 0-9 in half bands,
all required. Fluency and Pronunciation depend on how the student sounds (pace,
hesitation, sounds, stress, intonation), so they need an audio assessor: an engine that
only reads transcripts marks them not_assessed, and the overall band then stays empty
(a missing criterion is never treated as zero).

A snapshot of this rubric is stored on every exercise and evaluation.
"""

import math
from decimal import Decimal

from app.ai.contracts import SpeakingCriterion

RUBRIC_VERSION = "speaking-ielts-practice-v1"
SCORE_MIN, SCORE_MAX, SCORE_STEP = 0.0, 9.0, 0.5
DISCLAIMER = "Practice band estimate for learning only; not an official IELTS score."
NOT_ASSESSED = (
    "Not assessed: this needs an audio assessor, which is not available yet. "
    "It is never judged from the transcript."
)
OVERALL_MISSING = (
    "No overall band: every criterion must be assessed first, and fluency and "
    "pronunciation need an audio assessor."
)

CRITERIA = [
    SpeakingCriterion(
        code="fluency_coherence",
        name="Fluency and Coherence",
        descriptor=(
            "Speaks at length without noticeable effort or long hesitation, and links "
            "ideas clearly and logically."
        ),
        requires_audio=True,
    ),
    SpeakingCriterion(
        code="lexical_resource",
        name="Lexical Resource",
        descriptor="Uses a range of vocabulary flexibly and precisely to discuss the topic.",
        requires_audio=False,
    ),
    SpeakingCriterion(
        code="grammatical_range_accuracy",
        name="Grammatical Range and Accuracy",
        descriptor="Uses a variety of sentence structures with accurate grammar.",
        requires_audio=False,
    ),
    SpeakingCriterion(
        code="pronunciation",
        name="Pronunciation",
        descriptor=(
            "Is easy to understand, with clear individual sounds, word stress, rhythm and "
            "intonation."
        ),
        requires_audio=True,
    ),
]
CODES = [criterion.code for criterion in CRITERIA]


def snapshot() -> dict:
    """Stored as rubric_snapshot. The database reads criteria[].code/required."""
    return {
        "version": RUBRIC_VERSION,
        "scale": {"min": SCORE_MIN, "max": SCORE_MAX, "step": SCORE_STEP},
        "overall": "mean of all criteria rounded to the nearest half band; null if any is "
        "not assessed",
        "disclaimer": DISCLAIMER,
        "criteria": [
            {
                "code": c.code,
                "name": c.name,
                "descriptor": c.descriptor,
                "requires_audio": c.requires_audio,
                "required": True,
            }
            for c in CRITERIA
        ],
    }


def is_valid_band(score: float) -> bool:
    return SCORE_MIN <= score <= SCORE_MAX and (score / SCORE_STEP).is_integer()


def overall_band(scores: list[float]) -> Decimal:
    mean = sum(scores) / len(scores)
    return Decimal(str(math.floor(mean * 2 + 0.5) / 2))
