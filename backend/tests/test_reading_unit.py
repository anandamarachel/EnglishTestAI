"""Reading planning, span location and generated-package validation (no database)."""

import asyncio

import pytest

from app.ai.contracts import ReadingRequest
from app.ai.engine import AIError
from app.ai.fake import FakeAIEngine
from app.core.config import Settings
from app.core.errors import ApiError
from app.modules.quiz.service import locate
from app.modules.reading.schemas import CreateReadingExerciseRequest
from app.modules.reading.service import (
    GenerationInput,
    occurrences,
    plan,
    sentence_at,
    validate_package,
)

SETTINGS = Settings(_env_file=None, postgres_password="p", jwt_secret="j" * 32)


def request(**changes) -> ReadingRequest:
    values = {
        "topic": "Budaya",
        "difficulty": "intermediate",
        "cefr_level": "B1",
        "target_word_count": 150,
        "question_types": ["multiple_choice", "short_answer"],
        "vocabulary_count": 3,
        **changes,
    }
    return ReadingRequest(**values)


def generation(req: ReadingRequest) -> GenerationInput:
    return GenerationInput(
        exercise_id=None, topic_id=None, requested_word_count=None, tolerance=0.4, request=req
    )


def package(req: ReadingRequest):
    return asyncio.run(FakeAIEngine().generate_reading(req))


def test_plan_cycles_types_and_defaults_length() -> None:
    data = CreateReadingExerciseRequest(
        difficulty="beginner", question_count=5, question_types=["multiple_choice", "short_answer"]
    )
    types, target = plan(SETTINGS, data)
    assert types == ["multiple_choice", "short_answer"] * 2 + ["multiple_choice"]
    assert target == 150
    many = CreateReadingExerciseRequest(difficulty="beginner", question_count=10)
    assert plan(SETTINGS, many)[1] == 200  # room for 10 questions beats the default


@pytest.mark.parametrize(
    ("changes", "status"),
    [
        ({"question_count": 16}, 413),
        ({"requested_word_count": 1201}, 413),
        ({"question_count": 5, "requested_word_count": 99}, 422),
    ],
)
def test_plan_rejects_instead_of_shrinking(changes, status) -> None:
    with pytest.raises(ApiError) as error:
        plan(SETTINGS, CreateReadingExerciseRequest(difficulty="beginner", **changes))
    assert error.value.status_code == status


def test_spans_use_code_points() -> None:
    passage = "🌍 Rina met a curious cat. The Curious one ran.\n\nNext day."
    assert locate(passage, "Rina met a curious cat.") == {
        "start": 2,
        "end": 25,
        "original": "Rina met a curious cat.",
    }
    found = occurrences(passage, "curious")
    assert [passage[s["start"] : s["end"]] for s in found] == ["curious", "Curious"]
    assert occurrences(passage, "cur") == []  # whole words only
    assert sentence_at(passage, found[1]["start"]) == "The Curious one ran."
    with pytest.raises(AIError):
        locate(passage, "not in the passage")


def test_fake_package_is_valid() -> None:
    req = request()
    validated = validate_package(generation(req), package(req))
    assert len(validated.evidence) == 2 and len(validated.vocabulary) == 3


def _broken(req, **update):
    return package(req).model_copy(update=update)


def _question(req, index, **update):
    original = package(req)
    questions = list(original.questions)
    questions[index] = questions[index].model_copy(update=update)
    return original.model_copy(update={"questions": questions})


@pytest.mark.parametrize(
    "make",
    [
        lambda r: _broken(r, questions=package(r).questions[:1]),  # wrong count
        lambda r: _broken(r, questions=list(reversed(package(r).questions))),  # wrong types order
        lambda r: _broken(r, passage="Too short."),  # length outside tolerance
        lambda r: _broken(r, vocabulary=package(r).vocabulary[:2]),  # vocabulary count
        lambda r: _question(r, 0, correct_option=9),  # key out of range
        lambda r: _question(r, 0, options=["Same", "same"]),  # duplicate options
        lambda r: _question(r, 0, options=["Only one"], correct_option=0),
        lambda r: _question(r, 0, reference_answer="key leak"),  # MCQ with free-text key
        lambda r: _question(r, 1, reference_answer=None),  # short answer without key
        lambda r: _question(r, 1, options=["A", "B"]),  # short answer with options
        lambda r: _question(r, 0, evidence_quotes=["Not in the story."]),
    ],
)
def test_invalid_packages_are_rejected(make) -> None:
    req = request()
    with pytest.raises(AIError) as error:
        validate_package(generation(req), make(req))
    assert error.value.code == "AI_OUTPUT_INVALID"
