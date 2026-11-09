"""add_domain_schema

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-09 14:19:25.050154
"""

from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_personas",
        sa.Column(
            "persona_id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("role_description", sa.Text(), nullable=False),
        sa.Column("behavior_instructions", sa.Text(), nullable=False),
        sa.Column("voice_key", sa.String(length=100), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.CheckConstraint(
            "length(btrim(behavior_instructions)) > 0",
            name=op.f("ck_ai_personas_behavior_instructions_not_blank"),
        ),
        sa.CheckConstraint("length(btrim(name)) > 0", name=op.f("ck_ai_personas_name_not_blank")),
        sa.CheckConstraint(
            "length(btrim(role_description)) > 0",
            name=op.f("ck_ai_personas_role_description_not_blank"),
        ),
        sa.CheckConstraint(
            "length(btrim(voice_key)) > 0", name=op.f("ck_ai_personas_voice_key_not_blank")
        ),
        sa.PrimaryKeyConstraint("persona_id", name=op.f("pk_ai_personas")),
    )
    op.create_table(
        "topics",
        sa.Column(
            "topic_id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.CheckConstraint("length(btrim(name)) > 0", name=op.f("ck_topics_name_not_blank")),
        sa.PrimaryKeyConstraint("topic_id", name=op.f("pk_topics")),
        sa.UniqueConstraint("name", name=op.f("uq_topics_name")),
    )
    op.create_table(
        "users",
        sa.Column(
            "user_id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column(
            "user_role", sa.String(length=16), server_default=sa.text("'student'"), nullable=False
        ),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "user_role IN ('student', 'teacher')", name=op.f("ck_users_user_role_values")
        ),
        sa.CheckConstraint(
            "email = lower(btrim(email)) AND length(email) > 0",
            name=op.f("ck_users_normalized_email"),
        ),
        sa.CheckConstraint(
            "length(btrim(display_name)) > 0", name=op.f("ck_users_display_name_not_blank")
        ),
        sa.CheckConstraint(
            "length(btrim(password_hash)) > 0", name=op.f("ck_users_password_hash_not_blank")
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_table(
        "api_idempotency_keys",
        sa.Column(
            "idempotency_record_id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.Uuid(), nullable=False),
        sa.Column("operation", sa.String(length=160), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default=sa.text("'pending'"), nullable=False
        ),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column(
            "result_refs",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            (
                "(status = 'pending' AND response_status IS NULL) OR (status = "
                "'completed' AND response_status BETWEEN 200 AND 299)"
            ),
            name=op.f("ck_api_idempotency_keys_response_state"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(result_refs) = 'object'",
            name=op.f("ck_api_idempotency_keys_result_refs_shape"),
        ),
        sa.CheckConstraint(
            "request_hash ~ '^[0-9a-f]{64}$'", name=op.f("ck_api_idempotency_keys_hash_format")
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'completed')", name=op.f("ck_api_idempotency_keys_status_values")
        ),
        sa.CheckConstraint(
            "expires_at > created_at", name=op.f("ck_api_idempotency_keys_valid_expiry")
        ),
        sa.CheckConstraint(
            "length(btrim(operation)) > 0", name=op.f("ck_api_idempotency_keys_operation_not_blank")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.user_id"],
            name=op.f("fk_api_idempotency_keys_user_id_users"),
            ondelete="RESTRICT",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.PrimaryKeyConstraint("idempotency_record_id", name=op.f("pk_api_idempotency_keys")),
        sa.UniqueConstraint(
            "user_id",
            "idempotency_key",
            name=op.f("uq_api_idempotency_keys_user_id_idempotency_key"),
        ),
    )
    op.create_table(
        "auth_sessions",
        sa.Column(
            "session_id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("refresh_token_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "expires_at > created_at AND (revoked_at IS NULL OR revoked_at >= created_at)",
            name=op.f("ck_auth_sessions_valid_times"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.user_id"],
            name=op.f("fk_auth_sessions_user_id_users"),
            ondelete="RESTRICT",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.PrimaryKeyConstraint("session_id", name=op.f("pk_auth_sessions")),
        sa.UniqueConstraint("refresh_token_hash", name=op.f("uq_auth_sessions_refresh_token_hash")),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"], unique=False)
    op.create_table(
        "exercises",
        sa.Column(
            "exercise_id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("topic_selection", sa.String(length=16), nullable=False),
        sa.Column("topic_id", sa.Uuid(), nullable=True),
        sa.Column("custom_topic", sa.String(length=200), nullable=True),
        sa.Column("skill", sa.String(length=16), nullable=False),
        sa.Column("difficulty", sa.String(length=16), nullable=False),
        sa.Column("content_cefr_level", sa.String(length=2), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column(
            "content_source", sa.String(length=16), server_default=sa.text("'ai'"), nullable=False
        ),
        sa.Column(
            "generation_status",
            sa.String(length=16),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column(
            "generation_config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("generator_version", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            (
                "(difficulty = 'beginner' AND content_cefr_level = 'A2') OR (difficulty"
                " = 'intermediate' AND content_cefr_level = 'B1') OR (difficulty = "
                "'advanced' AND content_cefr_level = 'B2')"
            ),
            name=op.f("ck_exercises_level_mapping"),
        ),
        sa.CheckConstraint(
            (
                "(topic_selection = 'catalog' AND topic_id IS NOT NULL AND custom_topic"
                " IS NULL) OR (topic_selection = 'custom' AND topic_id IS NULL AND "
                "custom_topic IS NOT NULL AND length(btrim(custom_topic)) > 0) OR "
                "(topic_selection = 'random' AND custom_topic IS NULL AND "
                "(generation_status <> 'ready' OR topic_id IS NOT NULL))"
            ),
            name=op.f("ck_exercises_topic_choice"),
        ),
        sa.CheckConstraint(
            "content_cefr_level IN ('A2', 'B1', 'B2')",
            name=op.f("ck_exercises_content_cefr_level_values"),
        ),
        sa.CheckConstraint(
            "content_source IN ('ai', 'prepared')", name=op.f("ck_exercises_content_source_values")
        ),
        sa.CheckConstraint(
            "difficulty IN ('beginner', 'intermediate', 'advanced')",
            name=op.f("ck_exercises_difficulty_values"),
        ),
        sa.CheckConstraint(
            (
                "generation_status <> 'ready' OR (title IS NOT NULL AND "
                "length(btrim(title)) > 0 AND instructions IS NOT NULL AND "
                "length(btrim(instructions)) > 0)"
            ),
            name=op.f("ck_exercises_ready_content"),
        ),
        sa.CheckConstraint(
            "generation_status IN ('pending', 'generating', 'ready', 'failed', 'cancelled')",
            name=op.f("ck_exercises_generation_status_values"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(generation_config) = 'object'",
            name=op.f("ck_exercises_generation_config_shape"),
        ),
        sa.CheckConstraint(
            "skill IN ('writing', 'reading', 'listening', 'speaking')",
            name=op.f("ck_exercises_skill_values"),
        ),
        sa.CheckConstraint(
            "topic_selection IN ('catalog', 'custom', 'random')",
            name=op.f("ck_exercises_topic_selection_values"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.user_id"],
            name=op.f("fk_exercises_created_by_users"),
            ondelete="RESTRICT",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.ForeignKeyConstraint(
            ["topic_id"],
            ["topics.topic_id"],
            name=op.f("fk_exercises_topic_id_topics"),
            ondelete="RESTRICT",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.PrimaryKeyConstraint("exercise_id", name=op.f("pk_exercises")),
    )
    op.create_index(
        "ix_exercises_created_by_skill_created_at",
        "exercises",
        ["created_by", "skill", "created_at"],
        unique=False,
    )
    op.create_index("ix_exercises_topic_id", "exercises", ["topic_id"], unique=False)
    op.create_table(
        "media_assets",
        sa.Column(
            "media_id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column(
            "status", sa.String(length=16), server_default=sa.text("'pending'"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "purpose IN ('listening_audio', 'speaking_user_audio', 'speaking_ai_audio')",
            name=op.f("ck_media_assets_purpose_values"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'ready', 'failed', 'deleted')",
            name=op.f("ck_media_assets_status_values"),
        ),
        sa.CheckConstraint(
            "expires_at IS NULL OR expires_at > created_at",
            name=op.f("ck_media_assets_valid_expiry"),
        ),
        sa.CheckConstraint(
            "length(btrim(mime_type)) > 0", name=op.f("ck_media_assets_mime_type_not_blank")
        ),
        sa.CheckConstraint(
            "length(btrim(storage_key)) > 0", name=op.f("ck_media_assets_storage_key_not_blank")
        ),
        sa.CheckConstraint(
            "size_bytes >= 0 AND (duration_ms IS NULL OR duration_ms >= 0)",
            name=op.f("ck_media_assets_size_nonnegative"),
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.user_id"],
            name=op.f("fk_media_assets_owner_user_id_users"),
            ondelete="RESTRICT",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.PrimaryKeyConstraint("media_id", name=op.f("pk_media_assets")),
        sa.UniqueConstraint("storage_key", name=op.f("uq_media_assets_storage_key")),
    )
    op.create_index(
        "ix_media_assets_owner_user_id_created_at",
        "media_assets",
        ["owner_user_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "password_reset_tokens",
        sa.Column(
            "reset_id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "expires_at > created_at AND (used_at IS NULL OR used_at >= created_at)",
            name=op.f("ck_password_reset_tokens_valid_times"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.user_id"],
            name=op.f("fk_password_reset_tokens_user_id_users"),
            ondelete="RESTRICT",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.PrimaryKeyConstraint("reset_id", name=op.f("pk_password_reset_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_password_reset_tokens_token_hash")),
    )
    op.create_index(
        "ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"], unique=False
    )
    op.create_table(
        "attempts",
        sa.Column(
            "attempt_id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("exercise_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("source_attempt_id", sa.Uuid(), nullable=True),
        sa.Column(
            "status", sa.String(length=24), server_default=sa.text("'in_progress'"), nullable=False
        ),
        sa.Column("current_stage", sa.String(length=24), nullable=False),
        sa.Column("revision", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("last_saved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "last_activity_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(status = 'completed') = (completed_at IS NOT NULL)",
            name=op.f("ck_attempts_completed_time"),
        ),
        sa.CheckConstraint(
            (
                "current_stage IN ('writing', 'reading', 'quiz', 'listening', "
                "'conversation', 'evaluation', 'results')"
            ),
            name=op.f("ck_attempts_current_stage_values"),
        ),
        sa.CheckConstraint(
            (
                "status IN ('in_progress', 'submitted', 'evaluating', 'completed', "
                "'failed', 'cancelled')"
            ),
            name=op.f("ck_attempts_status_values"),
        ),
        sa.CheckConstraint(
            (
                "status NOT IN ('submitted','evaluating','completed','failed') OR "
                "submitted_at IS NOT NULL"
            ),
            name=op.f("ck_attempts_submitted_states"),
        ),
        sa.CheckConstraint("attempt_number > 0", name=op.f("ck_attempts_attempt_number_positive")),
        sa.CheckConstraint(
            (
                "last_activity_at >= started_at AND (last_saved_at IS NULL OR "
                "last_saved_at >= started_at) AND (submitted_at IS NULL OR submitted_at"
                " >= started_at) AND (completed_at IS NULL OR (submitted_at IS NOT NULL"
                " AND completed_at >= submitted_at))"
            ),
            name=op.f("ck_attempts_valid_times"),
        ),
        sa.CheckConstraint("revision > 0", name=op.f("ck_attempts_revision_positive")),
        sa.CheckConstraint(
            "source_attempt_id IS NULL OR source_attempt_id <> attempt_id",
            name=op.f("ck_attempts_source_not_self"),
        ),
        sa.ForeignKeyConstraint(
            ["exercise_id"],
            ["exercises.exercise_id"],
            name=op.f("fk_attempts_exercise_id_exercises"),
            ondelete="RESTRICT",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.ForeignKeyConstraint(
            ["source_attempt_id"],
            ["attempts.attempt_id"],
            name=op.f("fk_attempts_source_attempt_id_attempts"),
            ondelete="RESTRICT",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.user_id"],
            name=op.f("fk_attempts_user_id_users"),
            ondelete="RESTRICT",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.PrimaryKeyConstraint("attempt_id", name=op.f("pk_attempts")),
        sa.UniqueConstraint(
            "user_id",
            "exercise_id",
            "attempt_number",
            name=op.f("uq_attempts_user_id_exercise_id_attempt_number"),
        ),
    )
    op.create_index("ix_attempts_exercise_id", "attempts", ["exercise_id"], unique=False)
    op.create_index(
        "ix_attempts_source_attempt_id", "attempts", ["source_attempt_id"], unique=False
    )
    op.create_index(
        "ix_attempts_user_id_last_activity_at",
        "attempts",
        ["user_id", "last_activity_at"],
        unique=False,
    )
    op.create_table(
        "exercise_vocabulary",
        sa.Column(
            "vocabulary_item_id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("exercise_id", sa.Uuid(), nullable=False),
        sa.Column("word_or_phrase", sa.String(length=200), nullable=False),
        sa.Column("meaning", sa.Text(), nullable=False),
        sa.Column("example_sentence", sa.Text(), nullable=False),
        sa.Column("example_from_passage", sa.Text(), nullable=False),
        sa.Column(
            "occurrences",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "jsonb_typeof(occurrences) = 'array'",
            name=op.f("ck_exercise_vocabulary_occurrences_shape"),
        ),
        sa.CheckConstraint(
            "length(btrim(example_from_passage)) > 0",
            name=op.f("ck_exercise_vocabulary_example_from_passage_not_blank"),
        ),
        sa.CheckConstraint(
            "length(btrim(example_sentence)) > 0",
            name=op.f("ck_exercise_vocabulary_example_sentence_not_blank"),
        ),
        sa.CheckConstraint(
            "length(btrim(meaning)) > 0", name=op.f("ck_exercise_vocabulary_meaning_not_blank")
        ),
        sa.CheckConstraint(
            "length(btrim(word_or_phrase)) > 0",
            name=op.f("ck_exercise_vocabulary_word_or_phrase_not_blank"),
        ),
        sa.CheckConstraint("position > 0", name=op.f("ck_exercise_vocabulary_position_positive")),
        sa.ForeignKeyConstraint(
            ["exercise_id"],
            ["exercises.exercise_id"],
            name=op.f("fk_exercise_vocabulary_exercise_id_exercises"),
            ondelete="RESTRICT",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.PrimaryKeyConstraint("vocabulary_item_id", name=op.f("pk_exercise_vocabulary")),
        sa.UniqueConstraint(
            "exercise_id", "position", name=op.f("uq_exercise_vocabulary_exercise_id_position")
        ),
    )
    op.create_table(
        "listening_exercises",
        sa.Column("exercise_id", sa.Uuid(), nullable=False),
        sa.Column("audio_media_id", sa.Uuid(), nullable=True),
        sa.Column("transcript", sa.Text(), nullable=False),
        sa.Column(
            "transcript_policy",
            sa.String(length=24),
            server_default=sa.text("'after_submission'"),
            nullable=False,
        ),
        sa.Column("question_count", sa.Integer(), nullable=False),
        sa.Column(
            "feedback_mode",
            sa.String(length=24),
            server_default=sa.text("'after_submission'"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "feedback_mode IN ('after_submission')",
            name=op.f("ck_listening_exercises_feedback_mode_values"),
        ),
        sa.CheckConstraint(
            "transcript_policy IN ('after_submission')",
            name=op.f("ck_listening_exercises_transcript_policy_values"),
        ),
        sa.CheckConstraint(
            "length(btrim(transcript)) > 0",
            name=op.f("ck_listening_exercises_transcript_not_blank"),
        ),
        sa.CheckConstraint(
            "question_count > 0", name=op.f("ck_listening_exercises_question_count_positive")
        ),
        sa.ForeignKeyConstraint(
            ["audio_media_id"],
            ["media_assets.media_id"],
            name=op.f("fk_listening_exercises_audio_media_id_media_assets"),
            ondelete="RESTRICT",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.ForeignKeyConstraint(
            ["exercise_id"],
            ["exercises.exercise_id"],
            name=op.f("fk_listening_exercises_exercise_id_exercises"),
            ondelete="RESTRICT",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.PrimaryKeyConstraint("exercise_id", name=op.f("pk_listening_exercises")),
    )
    op.create_index(
        "ix_listening_exercises_audio_media_id",
        "listening_exercises",
        ["audio_media_id"],
        unique=False,
    )
    op.create_table(
        "questions",
        sa.Column(
            "question_id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("exercise_id", sa.Uuid(), nullable=False),
        sa.Column("question_type", sa.String(length=24), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("reference_answer", sa.Text(), nullable=True),
        sa.Column("reference_explanation", sa.Text(), nullable=False),
        sa.Column(
            "evidence_spans",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("grading_method", sa.String(length=16), nullable=False),
        sa.Column("rubric_version", sa.String(length=64), nullable=True),
        sa.Column("rubric_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("max_points", sa.Numeric(precision=6, scale=2), nullable=False),
        sa.CheckConstraint(
            (
                "(question_type = 'multiple_choice' AND grading_method = 'answer_key' "
                "AND reference_answer IS NULL AND rubric_version IS NULL AND "
                "rubric_snapshot IS NULL) OR (question_type = 'short_answer' AND "
                "grading_method = 'rubric' AND reference_answer IS NOT NULL AND "
                "length(btrim(reference_answer)) > 0 AND rubric_version IS NOT NULL AND"
                " length(btrim(rubric_version)) > 0 AND rubric_snapshot IS NOT NULL)"
            ),
            name=op.f("ck_questions_grading_configuration"),
        ),
        sa.CheckConstraint(
            "grading_method IN ('answer_key', 'rubric')",
            name=op.f("ck_questions_grading_method_values"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(evidence_spans) = 'array'", name=op.f("ck_questions_evidence_spans_shape")
        ),
        sa.CheckConstraint(
            "question_type IN ('multiple_choice', 'short_answer')",
            name=op.f("ck_questions_question_type_values"),
        ),
        sa.CheckConstraint(
            "rubric_snapshot IS NULL OR jsonb_typeof(rubric_snapshot) = 'object'",
            name=op.f("ck_questions_rubric_snapshot_shape"),
        ),
        sa.CheckConstraint(
            "length(btrim(question_text)) > 0", name=op.f("ck_questions_question_text_not_blank")
        ),
        sa.CheckConstraint(
            "length(btrim(reference_explanation)) > 0",
            name=op.f("ck_questions_reference_explanation_not_blank"),
        ),
        sa.CheckConstraint("max_points > 0", name=op.f("ck_questions_max_points_positive")),
        sa.CheckConstraint("position > 0", name=op.f("ck_questions_position_positive")),
        sa.ForeignKeyConstraint(
            ["exercise_id"],
            ["exercises.exercise_id"],
            name=op.f("fk_questions_exercise_id_exercises"),
            ondelete="RESTRICT",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.PrimaryKeyConstraint("question_id", name=op.f("pk_questions")),
        sa.UniqueConstraint(
            "exercise_id", "position", name=op.f("uq_questions_exercise_id_position")
        ),
    )
    op.create_table(
        "reading_exercises",
        sa.Column("exercise_id", sa.Uuid(), nullable=False),
        sa.Column("passage", sa.Text(), nullable=False),
        sa.Column("requested_word_count", sa.Integer(), nullable=True),
        sa.Column("question_count", sa.Integer(), nullable=False),
        sa.Column(
            "feedback_mode",
            sa.String(length=24),
            server_default=sa.text("'per_question'"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "feedback_mode IN ('per_question')",
            name=op.f("ck_reading_exercises_feedback_mode_values"),
        ),
        sa.CheckConstraint(
            "length(btrim(passage)) > 0", name=op.f("ck_reading_exercises_passage_not_blank")
        ),
        sa.CheckConstraint(
            "question_count > 0", name=op.f("ck_reading_exercises_question_count_positive")
        ),
        sa.CheckConstraint(
            "requested_word_count IS NULL OR requested_word_count > 0",
            name=op.f("ck_reading_exercises_requested_word_count_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["exercise_id"],
            ["exercises.exercise_id"],
            name=op.f("fk_reading_exercises_exercise_id_exercises"),
            ondelete="RESTRICT",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.PrimaryKeyConstraint("exercise_id", name=op.f("pk_reading_exercises")),
    )
    op.create_table(
        "speaking_exercises",
        sa.Column("exercise_id", sa.Uuid(), nullable=False),
        sa.Column("persona_id", sa.Uuid(), nullable=False),
        sa.Column("persona_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("rubric_version", sa.String(length=64), nullable=False),
        sa.Column("rubric_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "jsonb_typeof(persona_snapshot) = 'object'",
            name=op.f("ck_speaking_exercises_persona_snapshot_shape"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(rubric_snapshot) = 'object'",
            name=op.f("ck_speaking_exercises_rubric_snapshot_shape"),
        ),
        sa.CheckConstraint(
            "length(btrim(rubric_version)) > 0",
            name=op.f("ck_speaking_exercises_rubric_version_not_blank"),
        ),
        sa.ForeignKeyConstraint(
            ["exercise_id"],
            ["exercises.exercise_id"],
            name=op.f("fk_speaking_exercises_exercise_id_exercises"),
            ondelete="RESTRICT",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.ForeignKeyConstraint(
            ["persona_id"],
            ["ai_personas.persona_id"],
            name=op.f("fk_speaking_exercises_persona_id_ai_personas"),
            ondelete="RESTRICT",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.PrimaryKeyConstraint("exercise_id", name=op.f("pk_speaking_exercises")),
    )
    op.create_index(
        "ix_speaking_exercises_persona_id", "speaking_exercises", ["persona_id"], unique=False
    )
    op.create_table(
        "writing_exercises",
        sa.Column("exercise_id", sa.Uuid(), nullable=False),
        sa.Column("target_word_count", sa.Integer(), nullable=True),
        sa.Column("rubric_version", sa.String(length=64), nullable=False),
        sa.Column("rubric_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "jsonb_typeof(rubric_snapshot) = 'object'",
            name=op.f("ck_writing_exercises_rubric_snapshot_shape"),
        ),
        sa.CheckConstraint(
            "length(btrim(rubric_version)) > 0",
            name=op.f("ck_writing_exercises_rubric_version_not_blank"),
        ),
        sa.CheckConstraint(
            "target_word_count IS NULL OR target_word_count > 0",
            name=op.f("ck_writing_exercises_target_word_count_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["exercise_id"],
            ["exercises.exercise_id"],
            name=op.f("fk_writing_exercises_exercise_id_exercises"),
            ondelete="RESTRICT",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.PrimaryKeyConstraint("exercise_id", name=op.f("pk_writing_exercises")),
    )
    op.create_table(
        "conversation_sessions",
        sa.Column(
            "conversation_session_id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default=sa.text("'active'"), nullable=False
        ),
        sa.Column("provider_session_ref", sa.Text(), nullable=True),
        sa.Column("context_summary", sa.Text(), nullable=True),
        sa.Column("next_position", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "last_activity_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(status = 'ended') = (ended_at IS NOT NULL)",
            name=op.f("ck_conversation_sessions_ended_time"),
        ),
        sa.CheckConstraint(
            "status IN ('active', 'paused', 'ended')",
            name=op.f("ck_conversation_sessions_status_values"),
        ),
        sa.CheckConstraint(
            "next_position > 0", name=op.f("ck_conversation_sessions_next_position_positive")
        ),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["attempts.attempt_id"],
            name=op.f("fk_conversation_sessions_attempt_id_attempts"),
            ondelete="RESTRICT",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.PrimaryKeyConstraint("conversation_session_id", name=op.f("pk_conversation_sessions")),
        sa.UniqueConstraint("attempt_id", name=op.f("uq_conversation_sessions_attempt_id")),
    )
    op.create_table(
        "evaluations",
        sa.Column(
            "evaluation_id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default=sa.text("'pending'"), nullable=False
        ),
        sa.Column("overall_score", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("max_score", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("rubric_version", sa.String(length=64), nullable=False),
        sa.Column("rubric_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("corrected_text", sa.Text(), nullable=True),
        sa.Column(
            "feedback_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text(
                '\'{"schema_version": 1,"corrections":[],"limitations":[]}\'::jsonb'
            ),
            nullable=False,
        ),
        sa.Column("model_version", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(status = 'completed') = (completed_at IS NOT NULL)",
            name=op.f("ck_evaluations_completed_time"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(feedback_payload) = 'object'",
            name=op.f("ck_evaluations_feedback_payload_shape"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(rubric_snapshot) = 'object'",
            name=op.f("ck_evaluations_rubric_snapshot_shape"),
        ),
        sa.CheckConstraint(
            "status = 'completed' OR overall_score IS NULL",
            name=op.f("ck_evaluations_score_requires_completion"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed', 'cancelled')",
            name=op.f("ck_evaluations_status_values"),
        ),
        sa.CheckConstraint(
            (
                "(overall_score IS NULL AND max_score IS NULL) OR (overall_score IS NOT"
                " NULL AND max_score IS NOT NULL AND max_score > 0 AND overall_score >="
                " 0 AND overall_score <= max_score)"
            ),
            name=op.f("ck_evaluations_score_pair"),
        ),
        sa.CheckConstraint(
            "length(btrim(rubric_version)) > 0",
            name=op.f("ck_evaluations_rubric_version_not_blank"),
        ),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["attempts.attempt_id"],
            name=op.f("fk_evaluations_attempt_id_attempts"),
            ondelete="RESTRICT",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.PrimaryKeyConstraint("evaluation_id", name=op.f("pk_evaluations")),
        sa.UniqueConstraint("attempt_id", name=op.f("uq_evaluations_attempt_id")),
    )
    op.create_table(
        "listening_attempts",
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column(
            "playback_position_ms", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("current_question_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "playback_position_ms >= 0", name=op.f("ck_listening_attempts_position_nonnegative")
        ),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["attempts.attempt_id"],
            name=op.f("fk_listening_attempts_attempt_id_attempts"),
            ondelete="RESTRICT",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.ForeignKeyConstraint(
            ["current_question_id"],
            ["questions.question_id"],
            name=op.f("fk_listening_attempts_current_question_id_questions"),
            ondelete="RESTRICT",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.PrimaryKeyConstraint("attempt_id", name=op.f("pk_listening_attempts")),
    )
    op.create_index(
        "ix_listening_attempts_current_question_id",
        "listening_attempts",
        ["current_question_id"],
        unique=False,
    )
    op.create_table(
        "question_options",
        sa.Column(
            "option_id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("option_text", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "length(btrim(option_text)) > 0", name=op.f("ck_question_options_option_text_not_blank")
        ),
        sa.CheckConstraint("position > 0", name=op.f("ck_question_options_position_positive")),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.question_id"],
            name=op.f("fk_question_options_question_id_questions"),
            ondelete="RESTRICT",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.PrimaryKeyConstraint("option_id", name=op.f("pk_question_options")),
        sa.UniqueConstraint(
            "question_id", "position", name=op.f("uq_question_options_question_id_position")
        ),
    )
    op.create_table(
        "reading_attempts",
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("paragraph_index", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("offset_in_paragraph", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("current_question_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "offset_in_paragraph >= 0",
            name=op.f("ck_reading_attempts_offset_in_paragraph_nonnegative"),
        ),
        sa.CheckConstraint(
            "paragraph_index >= 0", name=op.f("ck_reading_attempts_paragraph_index_nonnegative")
        ),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["attempts.attempt_id"],
            name=op.f("fk_reading_attempts_attempt_id_attempts"),
            ondelete="RESTRICT",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.ForeignKeyConstraint(
            ["current_question_id"],
            ["questions.question_id"],
            name=op.f("fk_reading_attempts_current_question_id_questions"),
            ondelete="RESTRICT",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.PrimaryKeyConstraint("attempt_id", name=op.f("pk_reading_attempts")),
    )
    op.create_index(
        "ix_reading_attempts_current_question_id",
        "reading_attempts",
        ["current_question_id"],
        unique=False,
    )
    op.create_table(
        "writing_attempts",
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("response_text", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["attempts.attempt_id"],
            name=op.f("fk_writing_attempts_attempt_id_attempts"),
            ondelete="RESTRICT",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.PrimaryKeyConstraint("attempt_id", name=op.f("pk_writing_attempts")),
    )
    op.create_table(
        "answers",
        sa.Column(
            "answer_id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("selected_option_id", sa.Uuid(), nullable=True),
        sa.Column("response_text", sa.Text(), nullable=True),
        sa.Column("revision", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "grading_status",
            sa.String(length=16),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("awarded_points", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.Column("grading_model_version", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            (
                "(grading_status = 'graded' AND submitted_at IS NOT NULL AND "
                "awarded_points IS NOT NULL AND awarded_points >= 0) OR (grading_status"
                " <> 'graded' AND awarded_points IS NULL)"
            ),
            name=op.f("ck_answers_grade_consistency"),
        ),
        sa.CheckConstraint(
            "grading_status = 'pending' OR submitted_at IS NOT NULL",
            name=op.f("ck_answers_grading_requires_submission"),
        ),
        sa.CheckConstraint(
            "grading_status IN ('pending', 'processing', 'graded', 'failed', 'cancelled')",
            name=op.f("ck_answers_grading_status_values"),
        ),
        sa.CheckConstraint("revision > 0", name=op.f("ck_answers_revision_positive")),
        sa.CheckConstraint(
            "selected_option_id IS NULL OR response_text IS NULL",
            name=op.f("ck_answers_one_answer_format"),
        ),
        sa.CheckConstraint(
            (
                "submitted_at IS NULL OR selected_option_id IS NOT NULL OR "
                "(response_text IS NOT NULL AND length(btrim(response_text)) > 0)"
            ),
            name=op.f("ck_answers_submitted_not_empty"),
        ),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["attempts.attempt_id"],
            name=op.f("fk_answers_attempt_id_attempts"),
            ondelete="RESTRICT",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.question_id"],
            name=op.f("fk_answers_question_id_questions"),
            ondelete="RESTRICT",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.ForeignKeyConstraint(
            ["selected_option_id"],
            ["question_options.option_id"],
            name=op.f("fk_answers_selected_option_id_question_options"),
            ondelete="RESTRICT",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.PrimaryKeyConstraint("answer_id", name=op.f("pk_answers")),
        sa.UniqueConstraint(
            "attempt_id", "question_id", name=op.f("uq_answers_attempt_id_question_id")
        ),
    )
    op.create_index("ix_answers_question_id", "answers", ["question_id"], unique=False)
    op.create_index(
        "ix_answers_selected_option_id", "answers", ["selected_option_id"], unique=False
    )
    op.create_table(
        "conversation_messages",
        sa.Column(
            "message_id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("conversation_session_id", sa.Uuid(), nullable=False),
        sa.Column("client_message_key", sa.Uuid(), nullable=False),
        sa.Column("reply_to_message_id", sa.Uuid(), nullable=True),
        sa.Column("sender", sa.String(length=16), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("transcript", sa.Text(), nullable=True),
        sa.Column("audio_media_id", sa.Uuid(), nullable=True),
        sa.Column("transcription_status", sa.String(length=20), nullable=False),
        sa.Column(
            "delivery_status",
            sa.String(length=16),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "delivery_status IN ('pending', 'processing', 'ready', 'failed', 'cancelled')",
            name=op.f("ck_conversation_messages_delivery_status_values"),
        ),
        sa.CheckConstraint(
            (
                "reply_to_message_id IS NULL OR (sender = 'assistant' AND "
                "reply_to_message_id <> message_id)"
            ),
            name=op.f("ck_conversation_messages_reply_sender"),
        ),
        sa.CheckConstraint(
            "sender <> 'assistant' OR transcription_status = 'not_applicable'",
            name=op.f("ck_conversation_messages_assistant_transcription"),
        ),
        sa.CheckConstraint(
            "sender IN ('user', 'assistant')", name=op.f("ck_conversation_messages_sender_values")
        ),
        sa.CheckConstraint(
            (
                "transcription_status <> 'completed' OR (transcript IS NOT NULL AND "
                "length(btrim(transcript)) > 0)"
            ),
            name=op.f("ck_conversation_messages_completed_transcript"),
        ),
        sa.CheckConstraint(
            "transcription_status IN ('pending', 'completed', 'failed', 'not_applicable')",
            name=op.f("ck_conversation_messages_transcription_status_values"),
        ),
        sa.CheckConstraint("position > 0", name=op.f("ck_conversation_messages_position_positive")),
        sa.ForeignKeyConstraint(
            ["audio_media_id"],
            ["media_assets.media_id"],
            name=op.f("fk_conversation_messages_audio_media_id_media_assets"),
            ondelete="RESTRICT",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.ForeignKeyConstraint(
            ["conversation_session_id"],
            ["conversation_sessions.conversation_session_id"],
            name=op.f("fk_conversation_messages_conversation_session_id_conversation_sessions"),
            ondelete="RESTRICT",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.ForeignKeyConstraint(
            ["reply_to_message_id"],
            ["conversation_messages.message_id"],
            name=op.f("fk_conversation_messages_reply_to_message_id_conversation_messages"),
            ondelete="RESTRICT",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.PrimaryKeyConstraint("message_id", name=op.f("pk_conversation_messages")),
        sa.UniqueConstraint(
            "conversation_session_id",
            "client_message_key",
            name=op.f("uq_conversation_messages_conversation_session_id_client_message_key"),
        ),
        sa.UniqueConstraint(
            "conversation_session_id",
            "position",
            name=op.f("uq_conversation_messages_conversation_session_id_position"),
        ),
        sa.UniqueConstraint(
            "reply_to_message_id", name=op.f("uq_conversation_messages_reply_to_message_id")
        ),
    )
    op.create_index(
        "ix_conversation_messages_audio_media_id",
        "conversation_messages",
        ["audio_media_id"],
        unique=False,
    )
    op.create_index(
        "uq_conversation_messages_greeting",
        "conversation_messages",
        ["conversation_session_id"],
        unique=True,
        postgresql_where=sa.text("sender = 'assistant' AND reply_to_message_id IS NULL"),
    )
    op.create_table(
        "criterion_results",
        sa.Column(
            "criterion_result_id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("evaluation_id", sa.Uuid(), nullable=False),
        sa.Column("criterion_code", sa.String(length=40), nullable=False),
        sa.Column("assessment_status", sa.String(length=20), nullable=False),
        sa.Column("score", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("max_score", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("feedback", sa.Text(), nullable=False),
        sa.CheckConstraint(
            (
                "(assessment_status = 'not_assessed' AND score IS NULL AND max_score IS"
                " NULL) OR (assessment_status = 'assessed' AND score IS NOT NULL AND "
                "max_score IS NOT NULL AND max_score > 0 AND score >= 0 AND score <= "
                "max_score)"
            ),
            name=op.f("ck_criterion_results_assessment_score"),
        ),
        sa.CheckConstraint(
            "assessment_status IN ('assessed', 'not_assessed')",
            name=op.f("ck_criterion_results_assessment_status_values"),
        ),
        sa.CheckConstraint(
            "length(btrim(criterion_code)) > 0",
            name=op.f("ck_criterion_results_criterion_code_not_blank"),
        ),
        sa.CheckConstraint(
            "length(btrim(feedback)) > 0", name=op.f("ck_criterion_results_feedback_not_blank")
        ),
        sa.ForeignKeyConstraint(
            ["evaluation_id"],
            ["evaluations.evaluation_id"],
            name=op.f("fk_criterion_results_evaluation_id_evaluations"),
            ondelete="RESTRICT",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.PrimaryKeyConstraint("criterion_result_id", name=op.f("pk_criterion_results")),
        sa.UniqueConstraint(
            "evaluation_id",
            "criterion_code",
            name=op.f("uq_criterion_results_evaluation_id_criterion_code"),
        ),
    )
    op.create_table(
        "ai_jobs",
        sa.Column("job_id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("exercise_id", sa.Uuid(), nullable=True),
        sa.Column("attempt_id", sa.Uuid(), nullable=True),
        sa.Column("answer_id", sa.Uuid(), nullable=True),
        sa.Column("message_id", sa.Uuid(), nullable=True),
        sa.Column("job_type", sa.String(length=32), nullable=False),
        sa.Column(
            "status", sa.String(length=24), server_default=sa.text("'queued'"), nullable=False
        ),
        sa.Column("attempt_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("execution_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "result_refs",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            (
                "(job_type = 'generate_exercise' AND exercise_id IS NOT NULL) OR "
                "(job_type IN ('evaluate_attempt','start_conversation') AND attempt_id "
                "IS NOT NULL) OR (job_type = 'grade_answer' AND answer_id IS NOT NULL) "
                "OR (job_type = 'process_voice_turn' AND message_id IS NOT NULL)"
            ),
            name=op.f("ck_ai_jobs_target_type"),
        ),
        sa.CheckConstraint(
            "(status IN ('succeeded','failed','cancelled')) = (finished_at IS NOT NULL)",
            name=op.f("ck_ai_jobs_finished_time"),
        ),
        sa.CheckConstraint(
            (
                "job_type IN ('generate_exercise', 'evaluate_attempt', 'grade_answer', "
                "'start_conversation', 'process_voice_turn')"
            ),
            name=op.f("ck_ai_jobs_job_type_values"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(result_refs) = 'object'", name=op.f("ck_ai_jobs_result_refs_shape")
        ),
        sa.CheckConstraint(
            "status <> 'cancel_requested' OR cancel_requested_at IS NOT NULL",
            name=op.f("ck_ai_jobs_cancel_timestamp"),
        ),
        sa.CheckConstraint(
            "status <> 'running' OR (lease_expires_at IS NOT NULL AND started_at IS NOT NULL)",
            name=op.f("ck_ai_jobs_running_lease"),
        ),
        sa.CheckConstraint(
            (
                "status IN ('queued', 'running', 'cancel_requested', 'succeeded', "
                "'failed', 'cancelled')"
            ),
            name=op.f("ck_ai_jobs_status_values"),
        ),
        sa.CheckConstraint(
            "attempt_count >= 0 AND attempt_count <= max_attempts",
            name=op.f("ck_ai_jobs_attempt_bounds"),
        ),
        sa.CheckConstraint(
            "execution_version > 0", name=op.f("ck_ai_jobs_execution_version_positive")
        ),
        sa.CheckConstraint("max_attempts > 0", name=op.f("ck_ai_jobs_max_attempts_positive")),
        sa.CheckConstraint(
            "num_nonnulls(exercise_id, attempt_id, answer_id, message_id) = 1",
            name=op.f("ck_ai_jobs_one_target"),
        ),
        sa.ForeignKeyConstraint(
            ["answer_id"],
            ["answers.answer_id"],
            name=op.f("fk_ai_jobs_answer_id_answers"),
            ondelete="RESTRICT",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["attempts.attempt_id"],
            name=op.f("fk_ai_jobs_attempt_id_attempts"),
            ondelete="RESTRICT",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.ForeignKeyConstraint(
            ["exercise_id"],
            ["exercises.exercise_id"],
            name=op.f("fk_ai_jobs_exercise_id_exercises"),
            ondelete="RESTRICT",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["conversation_messages.message_id"],
            name=op.f("fk_ai_jobs_message_id_conversation_messages"),
            ondelete="RESTRICT",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"],
            ["users.user_id"],
            name=op.f("fk_ai_jobs_requested_by_users"),
            ondelete="RESTRICT",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.PrimaryKeyConstraint("job_id", name=op.f("pk_ai_jobs")),
    )
    op.create_index("ix_ai_jobs_answer_id", "ai_jobs", ["answer_id"], unique=False)
    op.create_index("ix_ai_jobs_attempt_id", "ai_jobs", ["attempt_id"], unique=False)
    op.create_index("ix_ai_jobs_exercise_id", "ai_jobs", ["exercise_id"], unique=False)
    op.create_index("ix_ai_jobs_message_id", "ai_jobs", ["message_id"], unique=False)
    op.create_index(
        "ix_ai_jobs_queued",
        "ai_jobs",
        ["next_retry_at", "created_at"],
        unique=False,
        postgresql_where=sa.text("status = 'queued'"),
    )
    op.create_index(
        "ix_ai_jobs_requested_by_created_at",
        "ai_jobs",
        ["requested_by", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_ai_jobs_status_next_retry_at_created_at",
        "ai_jobs",
        ["status", "next_retry_at", "created_at"],
        unique=False,
    )
    op.create_index(
        "uq_ai_jobs_active_answer_id",
        "ai_jobs",
        ["answer_id"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('queued', 'running', 'cancel_requested') AND answer_id IS NOT NULL"
        ),
    )
    op.create_index(
        "uq_ai_jobs_active_attempt_type",
        "ai_jobs",
        ["attempt_id", "job_type"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('queued', 'running', 'cancel_requested') AND attempt_id IS NOT NULL"
        ),
    )
    op.create_index(
        "uq_ai_jobs_active_exercise_id",
        "ai_jobs",
        ["exercise_id"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('queued', 'running', 'cancel_requested') AND exercise_id IS NOT NULL"
        ),
    )
    op.create_index(
        "uq_ai_jobs_active_message_id",
        "ai_jobs",
        ["message_id"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('queued', 'running', 'cancel_requested') AND message_id IS NOT NULL"
        ),
    )
    op.execute((Path(__file__).resolve().parents[1] / "sql/0002_integrity.sql").read_text())


def downgrade() -> None:
    # Drop triggers/functions before the tables referenced by their row types.
    op.execute("DROP FUNCTION ep_check_write() CASCADE")
    op.execute("DROP FUNCTION ep_guard_write() CASCADE")
    op.execute("DROP FUNCTION ep_validate_exercise(uuid)")
    op.execute("DROP FUNCTION ep_exercise_ids(text, jsonb)")
    op.execute("DROP FUNCTION ep_validate_spans(text, jsonb)")
    op.execute("DROP FUNCTION ep_assert(boolean, text)")

    op.drop_index(
        "uq_ai_jobs_active_message_id",
        table_name="ai_jobs",
        postgresql_where=sa.text(
            "status IN ('queued', 'running', 'cancel_requested') AND message_id IS NOT NULL"
        ),
    )
    op.drop_index(
        "uq_ai_jobs_active_exercise_id",
        table_name="ai_jobs",
        postgresql_where=sa.text(
            "status IN ('queued', 'running', 'cancel_requested') AND exercise_id IS NOT NULL"
        ),
    )
    op.drop_index(
        "uq_ai_jobs_active_attempt_type",
        table_name="ai_jobs",
        postgresql_where=sa.text(
            "status IN ('queued', 'running', 'cancel_requested') AND attempt_id IS NOT NULL"
        ),
    )
    op.drop_index(
        "uq_ai_jobs_active_answer_id",
        table_name="ai_jobs",
        postgresql_where=sa.text(
            "status IN ('queued', 'running', 'cancel_requested') AND answer_id IS NOT NULL"
        ),
    )
    op.drop_index("ix_ai_jobs_status_next_retry_at_created_at", table_name="ai_jobs")
    op.drop_index("ix_ai_jobs_requested_by_created_at", table_name="ai_jobs")
    op.drop_index(
        "ix_ai_jobs_queued", table_name="ai_jobs", postgresql_where=sa.text("status = 'queued'")
    )
    op.drop_index("ix_ai_jobs_message_id", table_name="ai_jobs")
    op.drop_index("ix_ai_jobs_exercise_id", table_name="ai_jobs")
    op.drop_index("ix_ai_jobs_attempt_id", table_name="ai_jobs")
    op.drop_index("ix_ai_jobs_answer_id", table_name="ai_jobs")
    op.drop_table("ai_jobs")
    op.drop_table("criterion_results")
    op.drop_index(
        "uq_conversation_messages_greeting",
        table_name="conversation_messages",
        postgresql_where=sa.text("sender = 'assistant' AND reply_to_message_id IS NULL"),
    )
    op.drop_index("ix_conversation_messages_audio_media_id", table_name="conversation_messages")
    op.drop_table("conversation_messages")
    op.drop_index("ix_answers_selected_option_id", table_name="answers")
    op.drop_index("ix_answers_question_id", table_name="answers")
    op.drop_table("answers")
    op.drop_table("writing_attempts")
    op.drop_index("ix_reading_attempts_current_question_id", table_name="reading_attempts")
    op.drop_table("reading_attempts")
    op.drop_table("question_options")
    op.drop_index("ix_listening_attempts_current_question_id", table_name="listening_attempts")
    op.drop_table("listening_attempts")
    op.drop_table("evaluations")
    op.drop_table("conversation_sessions")
    op.drop_table("writing_exercises")
    op.drop_index("ix_speaking_exercises_persona_id", table_name="speaking_exercises")
    op.drop_table("speaking_exercises")
    op.drop_table("reading_exercises")
    op.drop_table("questions")
    op.drop_index("ix_listening_exercises_audio_media_id", table_name="listening_exercises")
    op.drop_table("listening_exercises")
    op.drop_table("exercise_vocabulary")
    op.drop_index("ix_attempts_user_id_last_activity_at", table_name="attempts")
    op.drop_index("ix_attempts_source_attempt_id", table_name="attempts")
    op.drop_index("ix_attempts_exercise_id", table_name="attempts")
    op.drop_table("attempts")
    op.drop_index("ix_password_reset_tokens_user_id", table_name="password_reset_tokens")
    op.drop_table("password_reset_tokens")
    op.drop_index("ix_media_assets_owner_user_id_created_at", table_name="media_assets")
    op.drop_table("media_assets")
    op.drop_index("ix_exercises_topic_id", table_name="exercises")
    op.drop_index("ix_exercises_created_by_skill_created_at", table_name="exercises")
    op.drop_table("exercises")
    op.drop_index("ix_auth_sessions_user_id", table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_table("api_idempotency_keys")
    op.drop_table("users")
    op.drop_table("topics")
    op.drop_table("ai_personas")
