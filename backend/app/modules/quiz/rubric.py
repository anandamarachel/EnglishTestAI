"""Short-answer rubric, snapshotted on every short-answer question."""

RUBRIC_VERSION = "short-answer-v1"
MAX_POINTS = 1.0
POINT_STEP = 0.5
TEXT = (
    "Award 1 point if the answer states the key idea of the reference answer, in any "
    "wording. Award 0.5 if it is partly correct or incomplete. Award 0 if it is wrong, "
    "unrelated, or not supported by the passage. Ignore spelling and grammar unless they "
    "change the meaning."
)


def snapshot() -> dict:
    return {
        "version": RUBRIC_VERSION,
        "max_points": MAX_POINTS,
        "point_step": POINT_STEP,
        "rubric": TEXT,
    }


def is_valid_points(points: float, max_points: float, step: float) -> bool:
    return 0 <= points <= max_points and (points / step).is_integer()
