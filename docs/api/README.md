# API contract and Postman

This folder defines the API that the frontend and backend will implement. It covers
42 operations and the public request/response fields for accounts, all four practice
skills, history, audio, and AI jobs. The database is implemented; **only the two health
endpoints are currently available over HTTP**.

| File | Use |
|---|---|
| [openapi.json](openapi.json) | Source of truth: OpenAPI 3.1 specification, schemas, examples, security and errors. Import into OpenAPI-compatible tools for design review. |
| [english-practice.postman_collection.json](english-practice.postman_collection.json) | Generated Postman v2.1 collection, grouped by feature, with request variants and saved response examples. |
| [local.postman_environment.json](local.postman_environment.json) | Importable local environment; credentials, tokens and resource IDs start empty. |

Every operation has `x-implementation-status: implemented` or `planned`. Postman request
names use the same labels. The running FastAPI `/docs` and `/openapi.json` continue to
show implemented routes only; this design contract does not add placeholder API routes.

## Import and try the available endpoints

1. In Postman, choose **Import** and select the collection and environment JSON files.
2. Select the **English Practice — Local** environment.
3. Start the backend using the [repository setup](../../README.md#local-development-database-in-docker-api-on-your-machine).
4. Run the **Health** folder. Its requests use no authentication. `base_url` defaults
   to `http://127.0.0.1:8000/api/v1` and should have no trailing slash.
5. Review planned request bodies and saved response examples with your frontend team.
   Sending those requests now returns 404. Their success assertions intentionally
   fail until the endpoint exists.

Do not run the entire collection as a single scenario: it contains alternative topic
modes, draft types, cancellation, logout, and password changes. Examples document
choices; they are not one linear end-to-end test.

## Variables and scripts

After authentication is implemented, fill `email`, `password`, and `display_name` locally.
Login and refresh requests save returned tokens into the selected environment. Protected
requests inherit bearer authentication. Logout/reset/change clear locally stored tokens
on success. The checked-in environment contains no real secrets; keep exported values
with live credentials out of the repository.

Successful responses save `exercise_id`, `attempt_id`, `attempt_revision`, and `job_id`
where returned. Fetching an exercise also selects its first question and option for
convenience; choose the intended question/answer before submitting. It does not choose
the correct answer. Set `topic_id` and `persona_id` from the catalog responses when using
those variants. Set `source_attempt_id` explicitly when copying submitted Writing.

New protected POST operations generate an `Idempotency-Key`. The key is recorded as
`last_idempotency_key`. To retry an uncertain request, copy it into `idempotency_key`
and resend the **same body and original revision**. Clear `idempotency_key` before a
new operation. A reused key with changed input returns `409 IDEMPOTENCY_CONFLICT`.
After a successful save, the returned attempt revision replaces `attempt_revision`;
replaying an earlier operation still requires its original payload.

For a voice turn, select an audio file in **Body → form-data → audio**. Postman supplies
the multipart boundary. The script generates a message key and records it in
`last_client_message_key`. For an exact retry, set `client_message_key` to that value,
reuse the idempotency key and identical recording, then clear both overrides for a new
turn. File inputs intentionally contain no local filesystem path.

## Skill flows once implemented

All flows start with login, exercise creation, polling the returned job until success,
and fetching the ready exercise. Use backoff when polling. Start an attempt on that
exercise; save returned IDs and revisions.

| Skill | Remaining sequence |
|---|---|
| Writing | Save the Writing draft, submit the attempt, poll evaluation work, then fetch the evaluation. Empty drafts are valid; submissions must be nonblank. No 500-character limit. |
| Reading | Read passage/vocabulary, save progress, submit each answer, and fetch feedback after grading. Move to the next question and repeat. Submit the whole attempt after all answers are graded. |
| Listening | Play the private audio, save playback position and draft answers, then submit all answers together. Poll the coordinating job if needed. Transcript unlocks after submission; question evidence unlocks after that answer is graded. |
| Speaking | Starting an attempt returns a conversation and greeting job. Wait for the greeting, upload a recording, poll the voice job, and fetch messages/audio. Repeat one turn at a time. Finish after accepted work settles, then fetch evaluation. Live transcription remains optional. |

For Reading/Listening draft examples, replace the empty `answers` array with entries:

```json
{
  "question_id": "<UUID from the exercise>",
  "selected_option_id": "<UUID from that question>",
  "response_text": null
}
```

For a short answer, use `selected_option_id: null` and a text `response_text`. Both
null clears an unsubmitted draft answer. Omitted entries are preserved. Locked answers
cannot be edited. A stale attempt revision returns `409 REVISION_CONFLICT` with
`current_revision`; fetch the latest attempt before reconciling changes.

For audio download, enable the optional `Range` header to test partial playback.
Unavailable owned audio returns 410; missing or another user's audio returns 404.

## Contract rules and open decisions

The [backend design](../backend-design.md) explains transactional and cross-field rules
that JSON Schema alone cannot express, such as ownership, valid state transitions,
score bounds against a question, and exact Unicode span matching.

- Requests reject unknown properties. The authenticated session supplies ownership.
- No response exercise contains answer keys, internal prompts, or Listening transcript.
- Non-health errors use `{code, message, request_id, retryable, details}`; health keeps its
  existing compact `{status}` response. Planned validation errors use the shared envelope,
  so implementation must add the corresponding exception handlers.
- Null is explicit for unavailable response values; omission is only allowed where the
  schema permits it. Skill-specific exercises/drafts use discriminated variants.
- Capacity figures and token lifetimes in examples are illustrative. Final limits,
  password policy, scoring rubrics, retention, and pronunciation assessment remain the
  open implementation decisions recorded in the backend design.
- Postman response scripts check success statuses and capture variables. They do not
  claim runtime schema validation or implemented business behavior. Automated contract
  tests validate the specification and its examples offline.

## Update and validate

Edit `openapi.json`, then run from `backend/`:

```sh
uv sync --locked
make contract-export
make contract-check
```

The exporter is deterministic. Tests fail if the checked-in collection differs from
its source, if examples violate schemas, if documented routes are missing, if public
schemas expose restricted fields, or if implementation-status labels diverge from
registered routes. These tests also run as part of `make check`; they need no database.
When implementing a route, update its status and verify that its runtime request and
response models match this contract.

Formats follow the [OpenAPI 3.1 specification](https://spec.openapis.org/oas/v3.1.0.html)
and [Postman Collection v2.1 schema](https://schema.postman.com/collection/json/v2.1.0/draft-07/docs/index.html).
The Postman schema is vendored unchanged in `backend/tests/fixtures/postman-collection-v2.1.schema.json`
from [Postman's published schema](https://schema.postman.com/collection/json/v2.1.0/draft-07/collection.json)
so validation does not need network access.
