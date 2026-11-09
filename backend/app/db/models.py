"""Central model registry: importing this module registers all Alembic metadata."""

from app.modules.assessment.models import CriterionResult, Evaluation
from app.modules.auth.models import AuthSession, PasswordResetToken
from app.modules.catalog.models import AIPersona, Topic
from app.modules.exercises.models import Exercise
from app.modules.jobs.models import AIJob, APIIdempotencyKey
from app.modules.listening.models import ListeningAttempt, ListeningExercise
from app.modules.media.models import MediaAsset
from app.modules.practice.models import Attempt
from app.modules.quiz.models import Answer, Question, QuestionOption
from app.modules.reading.models import ExerciseVocabulary, ReadingAttempt, ReadingExercise
from app.modules.speaking.models import ConversationMessage, ConversationSession, SpeakingExercise
from app.modules.users.models import User
from app.modules.writing.models import WritingAttempt, WritingExercise

__all__ = [
    "User",
    "AuthSession",
    "PasswordResetToken",
    "Topic",
    "AIPersona",
    "MediaAsset",
    "Exercise",
    "WritingExercise",
    "ReadingExercise",
    "ListeningExercise",
    "SpeakingExercise",
    "Attempt",
    "WritingAttempt",
    "ReadingAttempt",
    "ListeningAttempt",
    "Question",
    "QuestionOption",
    "Answer",
    "Evaluation",
    "CriterionResult",
    "ExerciseVocabulary",
    "ConversationSession",
    "ConversationMessage",
    "AIJob",
    "APIIdempotencyKey",
]
