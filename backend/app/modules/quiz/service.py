"""Questions, answers and grading shared by Reading and Listening.

Answer keys (is_correct, reference_answer, explanation, evidence) never leave the
backend until that answer's feedback is unlocked:
- Reading: the answer is submitted and graded.
- Listening: the whole attempt is submitted and the answer graded (added with Listening).
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.contracts import GeneratedQuestion, ShortAnswerGrade, ShortAnswerGradeRequest
from app.ai.engine import AIEngine, AIError
from app.core.errors import ApiError, validation_error
from app.modules.assessment.models import Evaluation
from app.modules.jobs import service as jobs
from app.modules.jobs.models import AIJob
from app.modules.practice.models import Attempt
from app.modules.quiz import rubric
from app.modules.quiz.models import Answer, Question, QuestionOption
from app.modules.quiz.schemas import (
    AnswerFeedbackOut,
    AnswerOut,
    DraftAnswer,
    OptionOut,
    QuestionOut,
    QuizSummary,
    Span,
)


async def questions(db: AsyncSession, exercise_id: UUID) -> list[Question]:
    return list(
        await db.scalars(
            select(Question).where(Question.exercise_id == exercise_id).order_by(Question.position)
        )
    )


async def options_by_question(db: AsyncSession, question_ids: list[UUID]) -> dict:
    rows = await db.scalars(
        select(QuestionOption)
        .where(QuestionOption.question_id.in_(question_ids))
        .order_by(QuestionOption.question_id, QuestionOption.position)
    )
    grouped: dict[UUID, list[QuestionOption]] = {}
    for option in rows:
        grouped.setdefault(option.question_id, []).append(option)
    return grouped


async def questions_out(db: AsyncSession, exercise_id: UUID) -> list[QuestionOut]:
    items = await questions(db, exercise_id)
    options = await options_by_question(db, [q.question_id for q in items])
    return [
        QuestionOut(
            question_id=q.question_id,
            position=q.position,
            question_type=q.question_type,
            question_text=q.question_text,
            max_points=float(q.max_points),
            options=[
                OptionOut(option_id=o.option_id, option_text=o.option_text, position=o.position)
                for o in options.get(q.question_id, [])
            ],
        )
        for q in items
    ]


async def answers_for_attempt(db: AsyncSession, attempt_id: UUID) -> list[Answer]:
    return list(
        await db.scalars(
            select(Answer)
            .join(Question, Question.question_id == Answer.question_id)
            .where(Answer.attempt_id == attempt_id)
            .order_by(Question.position)
        )
    )


def feedback_unlocked(skill: str, attempt: Attempt, answer: Answer) -> bool:
    if answer.grading_status != "graded" or answer.submitted_at is None:
        return False
    if skill == "listening":
        return attempt.submitted_at is not None
    return True


def answer_out(answer: Answer, feedback_available: bool) -> AnswerOut:
    return AnswerOut(
        answer_id=answer.answer_id,
        question_id=answer.question_id,
        selected_option_id=answer.selected_option_id,
        response_text=answer.response_text,
        revision=answer.revision,
        submitted_at=answer.submitted_at,
        grading_status=answer.grading_status,
        feedback_available=feedback_available,
    )


async def feedback_out(db: AsyncSession, answer: Answer) -> AnswerFeedbackOut:
    question = await db.get(Question, answer.question_id)
    correct_option_id = None
    is_correct = None
    if question.question_type == "multiple_choice":
        correct_option_id = await db.scalar(
            select(QuestionOption.option_id).where(
                QuestionOption.question_id == question.question_id, QuestionOption.is_correct
            )
        )
        is_correct = answer.selected_option_id == correct_option_id
    explanation = question.reference_explanation
    if answer.feedback:
        explanation = f"{answer.feedback}\n\n{explanation}"
    return AnswerFeedbackOut(
        answer_id=answer.answer_id,
        question_id=question.question_id,
        grading_status=answer.grading_status,
        awarded_points=None if answer.awarded_points is None else float(answer.awarded_points),
        max_points=float(question.max_points),
        is_correct=is_correct,
        correct_option_id=correct_option_id,
        reference_answer=question.reference_answer,
        explanation=explanation,
        evidence_spans=[Span(**span) for span in question.evidence_spans],
    )


def locked_feedback_error(answer: Answer) -> ApiError:
    if answer.submitted_at is not None and answer.grading_status in ("pending", "processing"):
        return ApiError(
            409, "GRADING_PENDING", "This answer is still being checked.", retryable=True
        )
    if answer.grading_status in ("failed", "cancelled"):
        return ApiError(409, "GRADING_FAILED", "This answer could not be checked. Retry the job.")
    return ApiError(409, "FEEDBACK_LOCKED", "Feedback is not available yet.")


async def apply_draft_answers(
    db: AsyncSession, attempt_id: UUID, exercise_id: UUID, drafts: list[DraftAnswer]
) -> None:
    """Update listed answers only; omitted answers keep their values."""
    if len({d.question_id for d in drafts}) != len(drafts):
        raise validation_error("draft.answers", "Each question may appear only once.")
    for draft in drafts:
        answer, question = await _answer_and_question(
            db, attempt_id, exercise_id, draft.question_id
        )
        if answer.submitted_at is not None:
            raise ApiError(409, "STATE_CONFLICT", "Submitted answers cannot be changed.")
        await _check_format(db, question, draft.selected_option_id, draft.response_text, False)
        if (answer.selected_option_id, answer.response_text) != (
            draft.selected_option_id,
            draft.response_text,
        ):
            answer.selected_option_id = draft.selected_option_id
            answer.response_text = draft.response_text
            answer.revision = answer.revision + 1


async def _answer_and_question(db, attempt_id, exercise_id, question_id):
    question = await db.scalar(
        select(Question).where(
            Question.question_id == question_id, Question.exercise_id == exercise_id
        )
    )
    if question is None:
        raise validation_error("question_id", "Question does not belong to this exercise.")
    answer = await db.scalar(
        select(Answer)
        .where(Answer.attempt_id == attempt_id, Answer.question_id == question_id)
        .with_for_update()
    )
    return answer, question


async def _check_format(db, question, option_id, text, required: bool) -> None:
    if question.question_type == "multiple_choice":
        if text is not None:
            raise validation_error("response_text", "This question needs a selected option.")
        if option_id is None:
            if required:
                raise validation_error("selected_option_id", "Choose an option.")
            return
        belongs = await db.scalar(
            select(QuestionOption.option_id).where(
                QuestionOption.option_id == option_id,
                QuestionOption.question_id == question.question_id,
            )
        )
        if belongs is None:
            raise validation_error("selected_option_id", "Option does not belong to this question.")
    else:
        if option_id is not None:
            raise validation_error("selected_option_id", "This question needs a written answer.")
        if required and (text is None or not text.strip()):
            raise validation_error("response_text", "Write an answer.")


async def lock_answer_for_submission(
    db: AsyncSession,
    attempt_id: UUID,
    exercise_id: UUID,
    question_id: UUID,
    option_id: UUID | None,
    text: str | None,
) -> tuple[Answer, Question]:
    answer, question = await _answer_and_question(db, attempt_id, exercise_id, question_id)
    if answer.submitted_at is not None:
        raise ApiError(409, "STATE_CONFLICT", "This answer was already submitted.")
    await _check_format(db, question, option_id, text, True)
    answer.selected_option_id = option_id
    answer.response_text = text
    answer.submitted_at = func.now()
    answer.revision = answer.revision + 1
    return answer, question


async def grade_choice(db: AsyncSession, answer: Answer, question: Question) -> None:
    correct = await db.scalar(
        select(QuestionOption.is_correct).where(
            QuestionOption.option_id == answer.selected_option_id
        )
    )
    answer.grading_status = "graded"
    answer.awarded_points = question.max_points if correct else Decimal("0")


async def quiz_summary(db: AsyncSession, attempt_id: UUID) -> QuizSummary | None:
    """Only once every question is graded. correct_count only for all-MCQ quizzes."""
    rows = (
        await db.execute(
            select(Question, Answer)
            .join(Answer, Answer.question_id == Question.question_id)
            .where(Answer.attempt_id == attempt_id)
        )
    ).all()
    if not rows or any(answer.grading_status != "graded" for _, answer in rows):
        return None
    all_choice = all(q.question_type == "multiple_choice" for q, _ in rows)
    return QuizSummary(
        question_count=len(rows),
        graded_count=len(rows),
        correct_count=sum(a.awarded_points == q.max_points for q, a in rows)
        if all_choice
        else None,
        awarded_points=float(sum(a.awarded_points for _, a in rows)),
        max_points=float(sum(q.max_points for q, _ in rows)),
    )


def score(summary: QuizSummary) -> tuple[Decimal, str]:
    """Percentage (max 100) and a short result line for a fully graded quiz."""
    percent = Decimal(str(summary.awarded_points)) / Decimal(str(summary.max_points)) * 100
    percent = percent.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if summary.correct_count is not None:
        text = f"{summary.correct_count} of {summary.question_count} answers correct."
    else:
        text = f"{summary.awarded_points:g} of {summary.max_points:g} points."
    return percent, text


def complete(attempt: Attempt, evaluation: Evaluation, summary: QuizSummary) -> None:
    """Store the aggregate result and close a submitted attempt (caller holds the locks)."""
    percent, text = score(summary)
    evaluation.status = "completed"
    evaluation.overall_score = percent
    evaluation.max_score = Decimal("100")
    evaluation.summary = text
    evaluation.completed_at = func.now()
    attempt.status = "completed"
    attempt.current_stage = "results"
    attempt.completed_at = func.now()
    attempt.last_activity_at = func.now()


# --- Generated content (untrusted model output) ------------------------------------------


def invalid_output() -> AIError:
    return AIError("AI_OUTPUT_INVALID", retryable=True)


def locate(source: str, quote: str) -> dict:
    """Code-point span of an exact quote; the model never supplies offsets."""
    start = source.find(quote) if quote.strip() else -1
    if start < 0:
        raise invalid_output()
    return {"start": start, "end": start + len(quote), "original": quote}


def check_question(question: GeneratedQuestion, source: str) -> list[dict]:
    """Validates one generated question and returns its evidence spans."""
    if question.question_type == "multiple_choice":
        options = [o.strip() for o in question.options]
        if not 2 <= len(options) <= 6 or not all(options):
            raise invalid_output()
        if len({o.lower() for o in options}) != len(options):
            raise invalid_output()
        if question.correct_option is None or not 0 <= question.correct_option < len(options):
            raise invalid_output()
        if question.reference_answer is not None:
            raise invalid_output()
    else:
        if question.options or question.correct_option is not None:
            raise invalid_output()
        if not (question.reference_answer or "").strip():
            raise invalid_output()
    return [locate(source, quote) for quote in question.evidence_quotes]


async def add_questions(
    db: AsyncSession,
    exercise_id: UUID,
    generated: list[GeneratedQuestion],
    evidence: list[list[dict]],
) -> None:
    for position, (question, spans) in enumerate(zip(generated, evidence, strict=True), start=1):
        choice = question.question_type == "multiple_choice"
        row = Question(
            exercise_id=exercise_id,
            question_type=question.question_type,
            question_text=question.question_text.strip(),
            reference_answer=None if choice else question.reference_answer.strip(),
            reference_explanation=question.explanation.strip(),
            evidence_spans=spans,
            grading_method="answer_key" if choice else "rubric",
            # Omitted for multiple choice: a Python None in a JSONB column would be stored
            # as JSON null, not SQL NULL, and break the grading-configuration check.
            **(
                {}
                if choice
                else {"rubric_version": rubric.RUBRIC_VERSION, "rubric_snapshot": rubric.snapshot()}
            ),
            position=position,
            max_points=Decimal("1"),
        )
        db.add(row)
        await db.flush()
        for index, text in enumerate(question.options):
            db.add(
                QuestionOption(
                    question_id=row.question_id,
                    option_text=text.strip(),
                    position=index + 1,
                    is_correct=index == question.correct_option,
                )
            )


# --- grade_answer job handler -----------------------------------------------------------


@dataclass(frozen=True)
class GradeInput:
    answer_id: UUID
    request: ShortAnswerGradeRequest


async def prepare_grade(db: AsyncSession, job: AIJob) -> GradeInput:
    answer = await db.get(Answer, job.answer_id)
    question = await db.get(Question, answer.question_id)
    answer.grading_status = "processing"
    snapshot = question.rubric_snapshot
    return GradeInput(
        answer_id=answer.answer_id,
        request=ShortAnswerGradeRequest(
            question_text=question.question_text,
            reference_answer=question.reference_answer,
            evidence=[span["original"] for span in question.evidence_spans],
            response_text=answer.response_text,
            max_points=float(question.max_points),
            point_step=snapshot["point_step"],
            rubric=snapshot["rubric"],
        ),
    )


async def execute_grade(engine: AIEngine, data: GradeInput) -> ShortAnswerGrade:
    grade = await engine.grade_short_answer(data.request)
    if not rubric.is_valid_points(
        grade.awarded_points, data.request.max_points, data.request.point_step
    ):
        raise AIError("AI_OUTPUT_INVALID", retryable=True)
    return grade


async def publish_grade(
    db: AsyncSession, engine: AIEngine, data: GradeInput, grade: ShortAnswerGrade
) -> dict:
    answer = await db.get(Answer, data.answer_id)
    answer.grading_status = "graded"
    answer.awarded_points = Decimal(str(grade.awarded_points))
    answer.feedback = grade.feedback.strip()
    answer.grading_model_version = engine.name
    await jobs.wake_coordinator(db, answer.attempt_id)
    return {"answer_id": data.answer_id, "attempt_id": answer.attempt_id}
