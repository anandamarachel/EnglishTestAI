# Backend design and API field contract — revision 2

Design date: 9 November 2026. Status: database implemented; account, catalog, dashboard,
history, capabilities, Writing, Reading and job APIs implemented (16 November 2026);
Listening and Speaking APIs planned.
SQLAlchemy models and migration `0002` implement the domain schema.
The full column/type/key reference is [database.dbml](database.dbml), containing 25 tables.
The contract below specifies the intended implementation. Its machine-readable version is
[api/openapi.json](api/openapi.json); the generated Postman collection and usage instructions
are in [api/README.md](api/README.md). These describe planned routes as well as implemented
ones; each operation's `x-implementation-status` says which.

## 1. Scope and decisions

The SDD defines product features. Figma defines interaction behavior where compatible.
The user explicitly confirmed:

- Keep all four skills, topic-based exercises, scoring, feedback, drafts/resume, and history.
- Do not impose the Figma 500-character Writing limit. Writing content is PostgreSQL
  `text`, with no 500-character database or API-schema constraint.
- Live transcription is optional. The required Speaking flow is record, upload,
  transcribe, generate a reply, and synthesize its audio. No streaming endpoint is
  required for the first implementation.

Derived implementation choices for this revision:

- Writing retains generated prompts and learning targets. The correction screen is
  used after an exercise response; free-text grammar checking is not silently added
  as a separate mandatory product mode.
- Reading checks each submitted question and shows feedback immediately. Listening
  submits the complete quiz, then exposes results and its transcript.
- Editing submitted Writing creates a new attempt on the same exercise, copying the
  original response and referencing `source_attempt_id`. Existing results stay intact.
  The UI must state that the copied text is the original; copying the corrected
  version can be a future explicit action. "Write again" creates a blank attempt.
- Vocabulary is generated with the Reading passage and is available before the quiz.
- Registration includes a student/teacher profile label. Both roles initially have
  identical self-practice permissions. A self-selected teacher role grants no student access.
- A random topic request resolves to a real active catalog topic before an exercise is ready.
- Initial content labels map `beginner -> Easy/A2`, `intermediate -> Medium/B1`,
  `advanced -> Hard/B2`. These are generation targets, not measured learner levels.
- Five Reading questions and three Listening questions are defaults, not fixed schema limits.
  Reading length remains configurable to preserve the SDD requirement.
- Listening transcripts unlock after successful submission, not merely selecting all options.
- Raw audio and transcripts remain private on the VPS. Optional streaming transcripts
  are ephemeral; only final transcripts are required in persisted messages.

HTTP payload, audio-duration, queue, and model-context capacity protections will be
configured during implementation/benchmarking. They must not silently truncate text,
pretend an oversized request succeeded, or reintroduce an arbitrary 500-character rule.
Return an explicit error and retain the user's draft if processing cannot proceed.

## 2. Changes from the SDD schema

| Change | Reason |
|---|---|
| Add `password_reset_tokens` | Login UI includes password recovery; hashed, expiring, single-use verification. |
| Add `listening_attempts` | Resume saved audio position and quiz progress. |
| Add `api_idempotency_keys` | Retried creation/submission requests must not duplicate resources, including operations that do not create AI jobs. |
| Replace attempt-linked `vocabulary_items` with `exercise_vocabulary` | Vocabulary is available during reading and reused in history. |
| Add `answers.submitted_at`, `revision`, and processing states | Per-question grading must freeze answers before revealing feedback. |
| Add `attempts.source_attempt_id`, `current_stage`, `last_activity_at` | Preserve Writing revisions and provide a resumable dashboard card. |
| Add structured corrections to `evaluations.feedback_payload` | Highlight original spans and open correction explanations. |
| Add `questions.evidence_spans` | Connect explanations to immutable Reading/Listening source text. |
| Add rubric snapshots and versions | Historical scores remain interpretable when rubrics change. |
| Extend AI jobs with answer targets, opening-conversation jobs, cancellation, and worker execution versions | Support individual short-answer grading, AI greetings, cancel/retry, and stale-result rejection. |
| Add `conversation_messages.reply_to_message_id` | Retry a turn without generating multiple final AI replies. |
| Remove redundant `exercises.interaction_mode` from the draft | Current interaction follows skill; optional streaming is a capability, not another exercise type. |

The SDD's 22 tables become 25: three additions and one replacement. No table is
created for a screen, loading animation, permission dialog, open sheet, or play/pause state.

## 3. Relationships and integrity

### Ownership and immutable content

- A user owns exercises, attempts, jobs, and media. Each attempt belongs to its exercise's
  owner in this version. Exercise sharing and teacher dashboards are outside this scope.
- Exactly one matching detail row exists for a ready exercise. Pending generation may
  temporarily have no detail. Detail-table inserts must match the parent's skill.
- A ready exercise has a nonempty title/instructions, a resolved topic, valid complete
  content, and, for Listening, ready audio. Material and questions cannot change once
  any attempt exists; create a new exercise for regeneration.
- Catalog topic and custom topic are exclusive. For `topic_selection=random`, both can
  be null only while generation is incomplete; ready random exercises use `topic_id`.
- `source_attempt_id` is allowed only for Writing, must reference the same user and
  exercise, and must reference an existing submitted attempt. No self-links or cycles.
- Writing text freezes on submit. Quiz answers freeze individually on their `submitted_at`.
  Listening freezes all answers atomically on whole-quiz submission.
- A current question, answer question, and chosen option must belong to the matching
  exercise/question. Media ownership must match every exercise or message referencing it.
- A reply must refer to a user message in the same conversation. Only one assistant
  reply can reference a given user message. There is at most one opening greeting per
  session; enforce a partial unique index on assistant messages with a null reply target.

### Constraints implemented in migrations

DBML declares columns, nullability, keys, and relationships. Notes describing states
and business conditions are requirements, not executable constraints. Do not apply
its SQL export directly as the application migration.

Use `CHECK` for enums and same-row rules, `UNIQUE` for identity/order rules, and FKs
for relationships. PostgreSQL does not support cross-table guarantees in a normal
`CHECK`; use deferred constraint triggers for cross-table rules below, validating
changes on both sides of a relationship. See [PostgreSQL constraints](https://www.postgresql.org/docs/17/ddl-constraints.html).

| Enforcement | Required rules |
|---|---|
| Same-row checks | Positive attempt numbers, question positions, max points, and target lengths; nonnegative progress/durations/sizes; allowed enum values; revision/execution version >= 1. |
| Same-row checks | Scores are both null or valid with `0 <= score <= max_score` and positive max; `not_assessed` requires null scores. Final score presence is independent of evaluation completion. |
| Same-row checks | `topic_selection` is consistent with topic fields; no blank custom topic. Token expiry must follow creation; used/revoked timestamps cannot precede creation. |
| Same-row checks | Exactly one AI-job target; generation targets exercise, grading targets answer, voice-turn targets message, evaluation/opening conversation target attempt. Retry counts obey configured bounds. |
| Deferred triggers | Exercise/detail skill match and readiness completeness; valid topic resolution; valid audio ownership/status; exercise content immutability after first attempt. |
| Deferred triggers | Attempt ownership and skill-detail match; current question belongs to exercise; answer question/option/format consistency; awarded points cannot exceed its question's max. |
| Deferred triggers | Ready MCQ has at least two choices and exactly one correct choice; short-answer uses a versioned rubric and has no choice rows. |
| Deferred triggers | Submitted answer content cannot change; grading fields may update. Submitted Writing content cannot change. Progress changes cannot reopen an ended session/attempt. |
| Deferred triggers | Valid source attempt; Reading-only vocabulary; Speaking-only sessions; same-session user-message reply target; matching job ownership and job target. |
| Partial unique indexes | One active generation job per exercise; one active grading job per answer; one active voice job per user message; one active job of each type per attempt. Active = queued/running/cancel_requested. |
| Concurrency control | Lock the conversation session while accepting a turn; allow only one active turn job per session. Allocate message positions and attempt numbers transactionally. |

FK deletion behavior starts with `RESTRICT`/`NO ACTION`; authorized account/media
deletion removes dependents through an explicit service. Historical learning content
must not vanish because a topic/persona is deactivated. Cleanup may remove expired
reset/idempotency records without deleting their users.

Index frequently queried FKs. Add descending user/activity history indexes and a
partial queue index for queued jobs. Do not duplicate indexes already supplied by
unique constraints. Use UUIDs and UTC `timestamptz` throughout; UUIDs do not replace
authorization checks.

### Structured text spans

All persisted text spans use **zero-based Unicode code point indexes**, start inclusive
and end exclusive, against the exact stored source text. Do not normalize or rewrite
the source after creating spans. Flutter must translate these offsets before applying
them to UTF-16 string indexes. Verify both the range and `original` substring.

`Span = {start: integer, end: integer, original: string}`.
`questions.evidence_spans` is an array of Span objects in the passage (Reading) or
transcript (Listening). `exercise_vocabulary.occurrences` is an array of Span objects
in the passage. Timing alignment is optional future work, not inferred from text offsets.

`evaluations.feedback_payload` has this initial versioned shape:

```json
{
  "schema_version": 1,
  "corrections": [
    {
      "correction_id": "c1",
      "start": 12,
      "end": 14,
      "original": "go",
      "replacement": "went",
      "category": "grammar",
      "title": "Past tense",
      "explanation": "Use past tense for an event that happened yesterday.",
      "example": "Last week, she went to the library."
    }
  ],
  "limitations": []
}
```

This example corresponds to `Yesterday I go to school.`. Corrections must have unique
IDs, valid nonoverlapping original spans, and an allowed category (`grammar`, `spelling`,
`vocabulary`, `style`). Zero-width insertion spans are allowed with empty `original`;
resolve multiple edits at the same position into one correction. The original answer
is never replaced by `corrected_text`. A no-error result has an empty corrections array.
The UI derives correction count; it does not need another table/column for that count.

## 4. State and transaction rules

### Attempts and grading

- Writing: `in_progress -> submitted -> evaluating -> completed`.
- Reading: attempt stays `in_progress` while individual answers are locked/graded;
  final submit requires all questions locked and graded, then stores the aggregate result.
  The UI submits the attempt after its last answer finishes grading.
- Listening: save draft answers, then submit the complete set atomically and grade.
  If open-ended questions require AI, the attempt remains `evaluating` until they finish.
- Speaking: persist a conversation for an in-progress attempt; finish freezes the session
  and schedules its evaluation. A pending turn must settle or be cancelled before finish.
- Evaluation failure sets the attempt to `failed` while preserving the frozen submission.
  Retry continues evaluation of the same attempt. It never reopens editable answers.
- Whole-attempt cancellation is distinct from cancelling a job. It freezes further
  work under `cancelled` and retains history; the user can start a new attempt.
  For Speaking it also ends the conversation and records `ended_at`. Completed attempts
  cannot be cancelled, and a cancelled attempt cannot resume or retry its jobs.

The dashboard chooses the owner's most recently active `in_progress` attempt using
`last_activity_at DESC, attempt_id DESC`. It returns `null` when none exist. Waiting
evaluations appear separately as pending work, not as editable drafts. A paused Speaking
session is resumable; an ended one is not.

MCQ score is determined by the stored answer key. Open short answers use their rubric.
Quiz score is `sum(awarded_points) / sum(max_points) * 100` after every required answer
is graded. Return `correct_count` only for MCQs; for mixed quizzes use points and the
percentage. Writing/Speaking use versioned rubric snapshots. Missing pronunciation
assessment is `not_assessed`, not zero. If a required criterion is unassessed, leave
the overall score null and return the explanation; valid partial feedback can still
be completed. Do not label this an official IELTS score.

### Jobs, cancellation, and retry

Use a short transaction to save a submission and its job together. AI execution
happens outside transactions. The worker claims a job with a lease and execution
version, and may commit only while the job is running with the same version.

- `queued -> running -> succeeded` is normal processing.
- Temporary failure returns to queued with backoff; retry exhaustion becomes failed.
- Cancelling queued work makes it cancelled immediately. Cancelling running work marks
  `cancel_requested` and increments its execution version, invalidating late results.
  The worker cooperatively stops when possible, or discards output and then records
  cancelled. This does not guarantee immediate interruption of GPU inference.
- Completion and cancellation race under a row lock. If completion already committed,
  cancellation returns `409 ALREADY_COMPLETED` and preserves the result.
- Cancelling generation leaves the exercise cancelled. Cancelling evaluation leaves
  its frozen submission and marks the evaluation cancelled and attempt failed, with
  a retry action. Cancelling per-answer grading keeps the answer locked and retryable.
- Cancelling a voice job preserves its user audio/message, marks delivery cancelled,
  and excludes that turn from future AI context until successfully retried. No partial
  assistant reply is presented as complete. Session stays active.
- Explicit retry requeues a failed/cancelled job, resets its per-run attempt counter,
  increments execution version, and preserves its target/result identities. Rate-limit
  user retries. Automated retries are bounded by `max_attempts`.

If the AI PC is unavailable, existing saved content and drafts remain available on
the VPS. The frontend polls job status with backoff; `slow` is a presentation state,
not another database status. Error messages must not expose model prompts or credentials.

### Idempotency and revisions

Require `Idempotency-Key` (UUID) on authenticated POST operations that create resources,
submit work, retry/cancel jobs, or change conversation state. Authentication/password
endpoints are excluded; they have dedicated token/single-use semantics.

Reserve `(user_id, key)` with a hash of method, concrete path, and validated input.
Perform resource creation and mark the reservation completed in the same transaction.
Same key/input returns the existing resource references with their current state and
original success status; same key with different input is `409 IDEMPOTENCY_CONFLICT`.
Do not store response access tokens or raw audio in this table. Upload hashing includes
the audio digest. Cleanup retention is a documented deployment setting; additional
unique turn/answer constraints remain after key expiry.

Draft PATCH requests use optimistic `revision` checks. Reject stale revisions with
`409 REVISION_CONFLICT`, returning the current revision. Increment only on a successful
save, and report saved only after commit. Failed network saves must not be labelled synced.

## 5. API contract conventions

All routes below use `/api/v1`. Only `/health/live` and `/health/ready` currently exist.
All other routes are **planned**. Protected routes require `Authorization: Bearer <access_token>`.
The owner comes from the verified session, never a client-supplied `user_id`.

- `uuid` = UUID string; `datetime` = RFC 3339 UTC string; `integer` = whole number;
  `number` = JSON number; `?` after a property means optional request property.
  `T | null` means the property exists but may be null in the response.
- All listed response properties are required unless explicitly labelled optional.
- Reject unknown request properties. Only expose public response models, not ORM serialization.
- GET lists use `limit?: integer` (default 20, maximum 100) and `cursor?: string`.
  Response is `{items: T[], next_cursor: string | null}`. Cursors are opaque and scoped
  to the user/filter. Full resource getters return a single resource without a data wrapper.
- Standard errors: `{code: string, message: string, request_id: uuid,
  retryable: boolean, details: {field: string, message: string}[]}`. Messages are localized
  by frontend code; error codes remain stable. For revision conflict include
  `current_revision: integer` in an optional error property.
- Common failures: 401 invalid/expired session; 404 missing or unauthorized resource;
  409 state/revision/idempotency conflict; 413 request size capacity; 422 validation;
  429 rate limit; 503 unavailable service. Field validation uses the standard envelope.
- Writes never accept answer keys, awarded scores, job execution counters, ownership,
  rubric snapshots, or internal prompts from the frontend.

### Shared response resources

| Resource | Public fields |
|---|---|
| `User` | `user_id: uuid`, `email: string`, `display_name: string`, `user_role: student|teacher`, `created_at: datetime` |
| `Tokens` | `access_token: string`, `token_type: "bearer"`, `expires_in: integer` (seconds), `refresh_token: string`, `user: User` |
| `Topic` | `topic_id: uuid`, `name: string`, `description: string|null` |
| `Persona` | `persona_id: uuid`, `name: string`, `role_description: string` |
| `Job` | `job_id: uuid`, `job_type: enum from DBML`, `status: enum from DBML`, `target: {type: exercise|attempt|answer|message, id: uuid}`, `created_at: datetime`, `started_at: datetime|null`, `finished_at: datetime|null`, `error: {code: string, retryable: boolean}|null`, `result_refs: {exercise_id?: uuid, attempt_id?: uuid, answer_id?: uuid, evaluation_id?: uuid, message_id?: uuid, assistant_message_id?: uuid}`, `can_cancel: boolean`, `can_retry: boolean` |
| `AttemptSummary` | `attempt_id: uuid`, `exercise_id: uuid`, `skill: enum`, `title: string`, `attempt_number: integer`, `source_attempt_id: uuid|null`, `status: enum`, `current_stage: enum`, `revision: integer`, `last_activity_at: datetime`, `last_saved_at: datetime|null`, `started_at: datetime`, `submitted_at: datetime|null`, `completed_at: datetime|null`, `score: {value: number, max: number}|null` |
| `Question` | `question_id: uuid`, `position: integer`, `question_type: multiple_choice|short_answer`, `question_text: string`, `max_points: number`, `options: {option_id: uuid, option_text: string, position: integer}[]` (empty for short answer) |
| `Answer` | `answer_id: uuid`, `question_id: uuid`, `selected_option_id: uuid|null`, `response_text: string|null`, `revision: integer`, `submitted_at: datetime|null`, `grading_status: enum`, `feedback_available: boolean` |
| `AnswerFeedback` | `answer_id: uuid`, `question_id: uuid`, `grading_status: enum`, `awarded_points: number|null`, `max_points: number`, `is_correct: boolean|null` (null for short answer or not graded), `correct_option_id: uuid|null`, `reference_answer: string|null`, `explanation: string|null`, `evidence_spans: Span[]` |
| `VocabularyItem` | `vocabulary_item_id: uuid`, `word_or_phrase: string`, `meaning: string`, `example_sentence: string`, `example_from_passage: string`, `occurrences: Span[]`, `position: integer` |
| `Media` | `media_id: uuid`, `purpose: enum`, `mime_type: string`, `size_bytes: integer`, `duration_ms: integer|null`, `status: enum`, `available: boolean` |
| `Message` | `message_id: uuid`, `sender: user|assistant`, `position: integer`, `client_message_key: uuid`, `reply_to_message_id: uuid|null`, `transcript: string|null`, `audio: Media|null`, `transcription_status: enum`, `delivery_status: enum`, `created_at: datetime` |
| `Conversation` | `conversation_session_id: uuid`, `attempt_id: uuid`, `status: active|paused|ended`, `last_activity_at: datetime`, `ended_at: datetime|null`, `active_job: Job|null`; messages fetched separately |

`Evaluation` fields: `evaluation_id: uuid`, `attempt_id: uuid`, `status: enum`,
`overall_score: number|null`, `max_score: number|null`, `rubric_version: string`,
`summary: string|null`, `corrected_text: string|null`, `feedback_payload` with the
versioned structure above, `criteria: Criterion[]`, `quiz_summary: QuizSummary|null`,
`created_at: datetime`, `completed_at: datetime|null`.
`Criterion = {criterion_code: string, assessment_status: assessed|not_assessed,
score: number|null, max_score: number|null, feedback: string}`.
`QuizSummary = {question_count: integer, graded_count: integer, correct_count: integer|null,
awarded_points: number, max_points: number}`; it is null until all required grading finishes.
Correction count, word count, display initials, and dashboard labels are derived values.

### Accounts and dashboard

| Method and path | Request fields | Success response |
|---|---|---|
| `POST /auth/register` | `email: string`, `display_name: string`, `password: string`, `password_confirmation: string`, `user_role: student|teacher` | 201 `User`; frontend proceeds to login. Password confirmation is never stored. |
| `POST /auth/login` | `email: string`, `password: string` | 200 `Tokens` |
| `POST /auth/refresh` | `refresh_token: string` | 200 `Tokens`; old token is invalidated atomically |
| `POST /auth/logout` | Bearer token; no body | 204; revoke the current session |
| `POST /auth/password/forgot` | `email: string` | 202 `{message: string}`; identical result for known/unknown email, no token in API response |
| `POST /auth/password/reset` | `token: string`, `new_password: string`, `password_confirmation: string` | 204; consume single-use token and revoke all sessions |
| `POST /auth/password/change` | Bearer token; `current_password: string`, `new_password: string`, `password_confirmation: string` | 204; revoke all sessions and require login |
| `GET /users/me` | No body | 200 `User` |
| `PATCH /users/me` | `display_name: string` | 200 `User`; role/email changes are not allowed here |
| `GET /dashboard` | No body | 200 `{user: User, resume_attempt: AttemptSummary|null, pending_attempts: AttemptSummary[], has_more_pending: boolean}`; pending list capped at 10, full list via `/attempts` |
| `GET /capabilities` | No body | 200 `{speaking: {live_transcription: boolean, pronunciation_assessment: boolean}, limits: {max_audio_bytes: integer, max_audio_duration_ms: integer, max_request_bytes: integer}}` |
| `GET /topics` | Pagination | 200 page of active `Topic` |
| `GET /personas` | Pagination | 200 page of active `Persona` |

Register/login/refresh/forgot/reset are public and rate-limited; the other routes above
require a session. Trim/validate display names and normalize email; never trim passwords.
The password policy is a documented authentication implementation decision, not inferred
from Figma's example error. Validate confirmations only in memory. Store password/token
hashes only. Check revoked session IDs on access-token use, including after password change.

### Exercise creation and retrieval

Use separate skill routes with shared typed fields, not an unvalidated arbitrary skill string.

Common request: `difficulty: beginner|intermediate|advanced` and
`topic: {mode: catalog, topic_id: uuid} | {mode: custom, text: string} | {mode: random}`.
Missing `topic` defaults to random; catalog/custom IDs/text are exclusive. Custom text is
1–200 nonblank characters. Clients do not provide model names or prompts.

| Method and path | Additional request fields | Success response |
|---|---|---|
| `POST /writing/exercises` | `target_word_count?: integer` (>0, learning target only) | 202 `{exercise_id: uuid, job: Job}` |
| `POST /reading/exercises` | `requested_word_count?: integer` (>0), `question_count?: integer` (>0), `question_types?: (multiple_choice|short_answer)[]` (nonempty; default MCQ) | 202 `{exercise_id: uuid, job: Job}` |
| `POST /listening/exercises` | `question_count?: integer` (>0), `question_types?: (multiple_choice|short_answer)[]` (nonempty; default MCQ) | 202 `{exercise_id: uuid, job: Job}` |
| `POST /speaking/exercises` | `persona_id: uuid` | 202 `{exercise_id: uuid, job: Job}` |
| `GET /exercises/{exercise_id}` | UUID path | 200 `Exercise` |
| `GET /exercises/{exercise_id}/vocabulary` | UUID path; Reading only | 200 `{items: VocabularyItem[]}` |

`Exercise = {exercise_id: uuid, skill: enum, difficulty: enum, content_cefr_level: A2|B1|B2,
topic: {mode: catalog|custom|random, topic_id: uuid|null, name: string|null},
title: string|null, instructions: string|null, generation_status: enum, created_at: datetime,
content: SkillContent|null, questions: Question[]}`. Content is null and questions are
empty until ready. Ready content is discriminated by the top-level skill:

- Writing: `{target_word_count: integer|null, rubric_version: string}`.
- Reading: `{passage: string, requested_word_count: integer|null,
  question_count: integer, feedback_mode: "per_question"}`.
- Listening: `{audio: Media, question_count: integer, feedback_mode: "after_submission",
  transcript_policy: "after_submission"}`. The transcript is absent from this object.
- Speaking: `{persona: Persona, rubric_version: string}`. Internal persona instructions
  and full rubric prompts are not returned.

Generation validates the actual number and types of questions and the requested source
content. Unsupported generation sizes get an explicit validation/capacity error; never
silently change a requested value. Final capacity thresholds require benchmarking.

### Attempts, drafts, quiz answers, results, and history

| Method and path | Request fields | Success response |
|---|---|---|
| `POST /exercises/{exercise_id}/attempts` | `source_attempt_id?: uuid` (Writing copy only) | 201 `{attempt: AttemptSummary, conversation: Conversation|null, job: Job|null}`; Speaking creates session and queues initial AI greeting |
| `GET /attempts` | Pagination, `skill?: enum`, `status?: enum` | 200 page of `AttemptSummary`, newest activity first |
| `GET /attempts/{attempt_id}` | UUID path | 200 `AttemptDetail` |
| `PATCH /attempts/{attempt_id}/draft` | `revision: integer` and skill-specific draft below | 200 `{attempt_id: uuid, revision: integer, last_saved_at: datetime, last_activity_at: datetime}` |
| `POST /attempts/{attempt_id}/answers/{question_id}/submit` | Reading only; `revision: integer` (attempt revision), exactly one of `selected_option_id: uuid` or `response_text: string` | 200 `{answer: Answer, feedback: AnswerFeedback, attempt_revision: integer}` for deterministic grading; 202 `{answer: Answer, job: Job, attempt_revision: integer}` for rubric grading |
| `GET /attempts/{attempt_id}/answers/{question_id}/feedback` | UUID paths | 200 `AnswerFeedback` when authorized and graded; 409 while grading is pending or feedback is locked |
| `POST /attempts/{attempt_id}/submit` | `revision: integer`; Writing/Reading/Listening only | 200 `{attempt: AttemptSummary, evaluation: Evaluation}` when fully deterministic; 202 `{attempt: AttemptSummary, job: Job}` when AI is needed |
| `POST /attempts/{attempt_id}/cancel` | No body | 200 `{attempt: AttemptSummary}`; mark related work cancelled/cancel_requested, keep saved material |
| `GET /attempts/{attempt_id}/evaluation` | UUID path | 200 `Evaluation` if record exists, including pending/failed/cancelled states; 404 if not created |
| `GET /attempts/{attempt_id}/transcript` | Listening only; submitted attempt required | 200 `{exercise_id: uuid, transcript: string, evidence: {question_id: uuid, spans: Span[]}[]}`; 409 before submission |

`AttemptDetail = {attempt: AttemptSummary, exercise: Exercise, draft: Draft|null,
answers: Answer[], conversation: Conversation|null, active_jobs: Job[],
evaluation: Evaluation|null}`. Speaking messages are paginated separately. No answer
key is included in `Answer`. Evaluation payloads cannot expose locked quiz feedback.

Draft variants (discriminated by `skill`; both request and persisted GET representation):

- Writing: `{skill: "writing", response_text: string}`. Empty text can be saved;
  whitespace-only submission is rejected. No 500-character limit.
- Reading: `{skill: "reading", paragraph_index: integer, offset_in_paragraph: integer,
  current_question_id: uuid|null, answers: DraftAnswer[]}`.
- Listening: `{skill: "listening", playback_position_ms: integer,
  current_question_id: uuid|null, answers: DraftAnswer[]}`.
- `DraftAnswer = {question_id: uuid, selected_option_id: uuid|null,
  response_text: string|null}`. Both values null means clear an unsubmitted answer;
  otherwise exactly one must match its question type. Locked answers cannot be edited.

PATCH wraps a complete progress snapshot as `{revision, draft}`. It updates the listed
draft answers; omission does not delete an existing answer. All changes occur in one
transaction and update both affected answer revisions and the attempt revision.
Reading per-question submission checks the same attempt revision to avoid races with
autosave, locks the answer, and increments the attempt revision. No guessed answer IDs
are required by the frontend. A current-question update may not skip a required earlier
unsubmitted Reading question; already graded questions remain reviewable.

Whole Reading submission requires all answers graded. Listening requires all answers
nonempty and submits/locks them together. Open-ended Listening grading creates answer
jobs and one aggregate evaluation record in the submission transaction; a coordinating
`evaluate_attempt` job waits for child answer jobs and aggregates their stored scores.
The submit response points to the coordinating job. No model call duplicates grading
already performed for an answer. Failed child grading makes the coordinator retryable;
retry requeues failed child jobs only, preserving completed grades. Cancelling this
coordinator cancels outstanding child grading jobs as well.

Listening transcript text unlocks after submission, but evidence spans/explanations
remain unavailable until that question is graded. A transcript response can therefore
contain an empty evidence array while grading runs. Reading feedback is released only
for a submitted, graded answer; other question keys remain hidden.

### Speaking, media, and jobs

| Method and path | Request fields | Success response |
|---|---|---|
| `GET /speaking/attempts/{attempt_id}/conversation` | UUID path | 200 `Conversation` |
| `GET /speaking/attempts/{attempt_id}/messages` | UUID path; pagination | 200 page of `Message` in ascending position order |
| `POST /speaking/attempts/{attempt_id}/turns` | Multipart `audio: binary`, `client_message_key: uuid`; idempotency header required | 202 `{message: Message, job: Job}` |
| `POST /speaking/attempts/{attempt_id}/pause` | No body | 200 `Conversation`; pause prevents new turns, allows already accepted processing to finish |
| `POST /speaking/attempts/{attempt_id}/resume` | No body | 200 `Conversation`; restore from stored messages/context |
| `POST /speaking/attempts/{attempt_id}/finish` | No body | 202 `{attempt: AttemptSummary, job: Job}`; 409 if a turn is still processing |
| `GET /media/{media_id}` | UUID path | 200 `Media` |
| `GET /media/{media_id}/download` | UUID path; optional HTTP Range | 200 audio stream or 206 partial content; enforce ownership and readiness; 410 for expired/deleted content owned by caller |
| `GET /jobs/{job_id}` | UUID path | 200 `Job` |
| `POST /jobs/{job_id}/cancel` | No body | 200 `Job` if already cancelled or cancelled immediately; 202 `Job` if cancellation is requested |
| `POST /jobs/{job_id}/retry` | No body | 202 `Job`; 409 if not retryable or parent attempt was cancelled |

Validate actual audio type, size, duration, and decodability rather than trusting the
filename. Upload storage and database records need a cleanup strategy for interrupted
uploads. Only ready user audio can enter the AI pipeline. Replay uses the existing
private media resource; it does not rerun TTS. The local audio player enforces one
playback stream at a time. Conversation queries exclude cancelled/failed turns from
model context but retain them in history with their statuses.

The initial greeting is an assistant message with no reply target, created through
`start_conversation`. A completed user turn is followed by a single linked assistant
reply. New turns are rejected while the greeting or another turn is active. Audio
assessment at finish uses the original successful user recordings, never transcript-only
pronunciation guesses. Set `pronunciation_assessment=false` until its assessor is verified.
`live_transcription=false` is the initial capability. A future streaming endpoint can
emit partial text without changing the mandatory persisted message shape.

### Example: saved Writing draft

```http
PATCH /api/v1/attempts/11111111-1111-4111-8111-111111111111/draft
Authorization: Bearer <access_token>
Content-Type: application/json
```

```json
{
  "revision": 2,
  "draft": {
    "skill": "writing",
    "response_text": "Yesterday I go to school."
  }
}
```

```json
{
  "attempt_id": "11111111-1111-4111-8111-111111111111",
  "revision": 3,
  "last_saved_at": "2026-11-09T03:00:00Z",
  "last_activity_at": "2026-11-09T03:00:00Z"
}
```

This short example is illustrative, not a Writing length requirement.

## 6. Implementation status and remaining decisions

The 25 models are organized by feature under `backend/app/modules`, with a central
registry in `backend/app/db/models.py`. Migration `0002` creates their tables and
installs the versioned SQL integrity checks in `backend/alembic/sql/0002_integrity.sql`.
The baseline `0001` is unchanged. Real PostgreSQL tests cover migration roundtrips,
schema drift, four-skill persistence, submission locks, ownership, Unicode text spans,
audio references, cancellation transitions, and competing voice jobs.

Cross-table checks are deferred until commit. Writes lock the affected exercise to
serialize aggregate validation under PostgreSQL's default `READ COMMITTED` isolation.
The initial implementation validates the affected exercise and its attempts; benchmark
large histories before scaling. Services must still implement authentication and
authorization, atomic revision checks, worker execution-version comparisons, scoring,
and response filtering. Database guards do not implement these API behaviors.

The following operational/product choices remain explicit rather than silently invented:

| Choice | Effect |
|---|---|
| Writing/Speaking rubric definitions, weights and scales | Required before releasing meaningful AI scores; versioned snapshots support the decision. |
| Pronunciation/audio assessor | Required to satisfy the full Speaking assessment requirement; until then return unassessed criteria. |
| Password reset delivery/provider and password policy | Required before enabling recovery/registration publicly; the planned token schema is ready. |
| Recording retention, deletion policy, and school consent wording | Required before student pilot; the permission copy must acknowledge storage and assessment uses. |
| Generation sizes, upload limits, timeouts, concurrency and idempotency retention | Configure and publish after hardware/load testing; no arbitrary Writing character restriction is introduced here. |
| Retake UX | Keep previous results accessible; label repeated material as practice rather than treating answer knowledge as a new proficiency measurement. |

The OpenAPI contract and generated Postman collection now cover all 42 operations,
31 of them implemented (health, auth and profile, dashboard, capabilities, topics,
personas, the attempt list, the Writing and Reading flows and job operations).
Offline contract tests validate schemas,
examples, endpoint coverage, public-field boundaries, security declarations and export
consistency. They do not verify unimplemented runtime behavior.

Session decisions: access tokens are HS256 JWTs (default 15 minutes) bound to an
`auth_sessions` row and checked against it on every request, so logout revokes immediately.
Refresh tokens are opaque, stored as SHA-256 hashes and rotated with one conditional UPDATE;
each refresh slides session expiry (default 30 days). Replaying a rotated token returns 401
but does not revoke the session, because there is no token-family history; adding replay
revocation would need a migration. Wrong email, wrong password and inactive accounts return
the same 401 `INVALID_CREDENTIALS`.

Password reset tokens are hashed, expire after 30 minutes, work once, and a new request voids
older ones. Change/reset revoke every session and pending token atomically. A wrong current
password is 422 (field `current_password`), not 401, so the app does not log the user out.
No email provider exists yet: development writes to a local outbox; production answers 503.

The dashboard's pending list means attempts waiting for evaluation (`submitted`,
`evaluating`). Failed evaluations are found by filtering the attempt list with `status=failed`.
Catalog seeds (`make seed`) use the Figma topic names; persona voice keys are neutral
placeholders until a TTS model is chosen. Cursors are bound to the owner and filters.

Writing and jobs (implemented):

- Rubric `writing-ielts-practice-v1`: four IELTS-style criteria, all required, 0–9 in
  half bands; overall = mean rounded to the nearest half band with .25/.75 rounding up.
  Snapshotted on the exercise and evaluation. Labelled as a practice estimate.
- No AI model is chosen. `app/ai/` defines typed requests/results; a deterministic fake
  engine serves development/tests and is refused in production. Every model result is
  validated again (criterion set, half bands, exact code-point spans, ordering) before
  persistence, and the database re-checks spans.
- Worker: claim with lease → execute outside transactions with heartbeat and timeout →
  publish only if the job is still `running` with the claimed execution version. Expired
  leases are reclaimed with a new version, so a returning stale worker is ignored.
  Retryable errors back off exponentially up to `job_max_attempts`.
- Locks: exercise row first, then job/attempt row, matching the triggers.
- Idempotency reservations share the work's transaction; concurrent same-key requests
  wait on the unique index and replay. Records expire after 24 hours.
- Submission text above `writing_max_submission_chars` (default 20,000) returns 413 and
  keeps the draft; drafts have no length limit. At most 3 generations per user may be
  in progress (429).
- Generic exercise/attempt routes serve all four skills; Speaking is submitted with
  `/speaking/attempts/{id}/finish` (the generic submit returns 409 for it).

Reading (implemented):

- Generation asks for question types per position (cycling through `question_types`) and
  validates the exact sequence, option sets (2–6, unique, one key), short-answer keys,
  vocabulary count and passage length (±40% of target). Oversized requests return 413;
  too few words per question returns 422. Nothing is silently shrunk.
- The model returns exact evidence and vocabulary quotes; the backend locates them to
  build code-point spans (vocabulary: case-insensitive whole-word matches).
- Attempts create one answer row per question. Questions must be submitted in order;
  each submit checks and increments the attempt revision and locks the answer.
  Multiple choice grades immediately (200); short answers queue `grade_answer` (202)
  with rubric `short-answer-v1` (0/0.5/1, snapshotted on the question).
- Feedback for an answer unlocks only once it is submitted and graded; other keys never
  appear in exercise, attempt or evaluation views.
- Final submit requires every answer graded and stores evaluation `reading-quiz-v1`:
  `overall_score` is the percentage (max 100), `quiz_summary` gives counts/points, and
  `correct_count` is null for quizzes with short answers.

Listening (implemented):

- One `generate_exercise` job: script + questions from the model, validated (offered
  voice keys only, one voice per speaker, at most 4 speakers, no speaker-label injection,
  length ±40% of target, exact question types), then TTS. Audio bytes are checked
  (RIFF/WAVE signature, PCM header, every frame decodes, size/duration bounds) before
  being written atomically to a generated key under `media_storage_dir`. Publish inserts
  the ready media row, transcript and questions in one transaction; if the result is not
  committed (cancelled, superseded, rejected) the worker deletes the file. Files left by a
  crash are removed by the worker's orphan sweep; referenced files are never touched.
- Defaults: 3 questions, 80/120/180 words by difficulty (at least 20 per question); more
  than 10 questions or more words than fit returns 413.
- Exercise views show audio metadata and questions only; the transcript unlocks after
  submission and evidence only for graded questions.
- Drafts store playback position (≤ audio duration), current question (free navigation)
  and editable answers. Submit locks all answers together; any blank answer returns 409
  with one detail per question and locks nothing.
- All multiple choice: 200 with evaluation `listening-quiz-v1`. With short answers: 202
  with the `evaluate_attempt` coordinator. It is deferred at claim (no attempt used) while
  grades are pending, and every grade outcome wakes it. It aggregates and never re-grades.
  A failed or cancelled grade fails it (`GRADING_FAILED`); retrying it requeues only those
  grades. Listening grade jobs are retried through the coordinator. Cancelling it cancels
  outstanding grades.
- Media: owner-only metadata/download (404 otherwise), 409 `MEDIA_NOT_READY`, 410
  `MEDIA_UNAVAILABLE` for deleted/expired (or missing file), one byte range (206) or 416.
  New attempts need available audio; existing results stay readable when audio is gone.
  Retention/expiry policy is still an open decision (no expiry is set yet).

Speaking (implemented):

- Creation takes an active persona; persona (including private behaviour instructions)
  and rubric `speaking-ielts-practice-v1` are snapshotted. One job writes the prompt.
- Starting an attempt creates one session, the greeting message (position 1) and a
  `start_conversation` job. Each turn is a multipart upload (`audio`, `client_message_key`)
  checked from its bytes (PCM WAV, size/duration limits from `/capabilities`; 415/413) and
  stored privately before the user message and its `process_voice_turn` job are created.
  The job runs STT -> persona reply -> TTS; the reply gets the next position under the
  exercise lock. No speech fails the turn with `NO_SPEECH_DETECTED`.
- One active voice job per session (409 `TURN_IN_PROGRESS`), also enforced at commit.
  Same `client_message_key` + same audio replays the original turn; different audio is
  409 `IDEMPOTENCY_CONFLICT`. Paused sessions refuse turns; accepted work still finishes.
- Context: the most recent `speaking_context_messages` successful messages only; failed
  and cancelled turns stay in history with their recordings.
- Finish needs a successful user turn and no voice work in progress, ends the session and
  queues evaluation. Criteria marked `requires_audio` (fluency_coherence, pronunciation)
  are assessed only by an engine declaring `assesses_audio`, which receives the original
  recordings; otherwise they are forced to not_assessed and the overall band stays null.
- Cancelling the attempt ends the session and cancels voice work. Voice jobs retry only
  while the session is open and nothing else is running.

All 42 contract operations are implemented. Remaining work is the real AI/STT/TTS
adapter (no model chosen), an email provider, retention policy and deployment hardening.
Keep the running server's Swagger UI limited to real implementations.

## Sources

- Team SDD chapters 2–5 and `Requirement.pdf`: feature baseline provided in this chat.
- [Mobile EduTech App Figma](https://www.figma.com/design/xvMeCu21bXwNLJ9wcJOiMz/Mobile-EduTech-App?node-id=0-1): account, dashboard, four-skill state screens reviewed visually on 9 November 2026. Prototype execution required sign-in; transitions inferred from screen states are design choices, not verified prototype links.
- User decisions: SDD remains authoritative; no 500-character Writing limit; live transcription optional.
- [DBML syntax](https://dbml.dbdiagram.io/docs/): blueprint notation.
- [PostgreSQL constraint documentation](https://www.postgresql.org/docs/17/ddl-constraints.html): migration enforcement approach.
