# ruff: noqa: E501 - prompt text is easier to maintain unwrapped
"""Real AI engine: 9router (OpenAI-compatible gateway) for text, STT and evaluation;
Microsoft Edge TTS for speech.

Every result is still untrusted: the domain services re-validate it. This engine only
does the repair work a model reliably gets wrong (character offsets, exact quotes,
voice keys, score steps) so that fewer jobs fail validation, and it retries a call when
the model returns broken JSON or an unusable package.
"""

import asyncio
import base64
import io
import json
import logging
import re
import shutil
import wave
from typing import Any

import httpx

from app.ai.contracts import (
    ConversationReply,
    ConversationRequest,
    CorrectionResult,
    CriterionScore,
    GeneratedQuestion,
    GeneratedVocabulary,
    ListeningPackage,
    ListeningRequest,
    ReadingPackage,
    ReadingRequest,
    ScriptLine,
    ShortAnswerGrade,
    ShortAnswerGradeRequest,
    SpeakingCriterionResult,
    SpeakingEvaluation,
    SpeakingEvaluationRequest,
    SpeakingPrompt,
    SpeakingPromptRequest,
    SpeechAudio,
    SpeechRequest,
    Transcription,
    TranscriptionRequest,
    WritingEvaluation,
    WritingEvaluationRequest,
    WritingPrompt,
    WritingPromptRequest,
)
from app.ai.engine import AIError
from app.core.config import Settings

logger = logging.getLogger(__name__)

TEACHER = (
    "You are an experienced English teacher and IELTS examiner who writes clear, natural, "
    "level-appropriate practice material for Indonesian learners and grades strictly but "
    "kindly using public IELTS-style band descriptors. Never inflate scores."
)
CEFR_GUIDE = {
    "A2": "A2 (elementary): short simple sentences, very common everyday words, present and past simple.",
    "B1": "B1 (intermediate): clear connected sentences, common topics, some linking words and tenses.",
    "B2": "B2 (upper-intermediate): varied sentence structures, some less common vocabulary, opinions and reasons.",
}
CATEGORY_MAP = {
    "grammar": "grammar",
    "punctuation": "grammar",
    "tense": "grammar",
    "agreement": "grammar",
    "spelling": "spelling",
    "capitalization": "spelling",
    "capitalisation": "spelling",
    "vocabulary": "vocabulary",
    "word choice": "vocabulary",
    "collocation": "vocabulary",
    "style": "style",
    "cohesion": "style",
    "coherence": "style",
    "register": "style",
}
NO_SPEECH = "<<NO_SPEECH>>"
SAMPLE_RATE = 24_000
LINE_GAP_MS = 350


def _clip(text: Any, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip() if limit <= 200 else str(text or "").strip()
    return text[:limit]


def _on_step(value: Any, low: float, high: float, step: float) -> float:
    try:
        number = float(value)
    except TypeError, ValueError:
        raise AIError("AI_OUTPUT_INVALID", retryable=True) from None
    stepped = round(number / step) * step
    return max(low, min(high, round(stepped, 4)))


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def repair_quote(source: str, quote: str) -> str | None:
    """Exact substring of source for a model quote: as-is, else case/space-insensitive."""
    quote = (quote or "").strip().strip('"“”')
    if not quote:
        return None
    if quote in source:
        return quote
    words = [re.escape(w) for w in quote.split()]
    if not words:
        return None
    match = re.search(r"\s+".join(words), source, re.IGNORECASE)
    if match:
        return match.group(0)
    # Long paraphrase: fall back to its longest sentence-like fragment that does occur.
    for part in sorted(re.split(r"(?<=[.!?;,])\s+", quote), key=len, reverse=True):
        if len(part.split()) >= 4:
            found = repair_quote(source, part) if part != quote else None
            if found:
                return found
    return None


def sentence_containing(source: str, needle: str) -> str | None:
    """A whole sentence (or transcript line) of source that contains needle."""
    if not needle.strip():
        return None
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", source):
        if needle.lower() in sentence.lower() and sentence.strip():
            return sentence.strip()
    return None


def locate_corrections(text: str, items: list[dict]) -> list[CorrectionResult]:
    """Model gives exact original fragments; the engine computes offsets, in order,
    without overlaps. Fragments it cannot find exactly are dropped, never guessed."""
    located = []
    for item in items:
        original = str(item.get("original") or "")
        replacement = str(item.get("replacement") if item.get("replacement") is not None else "")
        if not original or original == replacement:
            continue
        located.append((original, replacement, item))
    results: list[CorrectionResult] = []
    cursor = 0
    used: list[tuple[int, int]] = []
    for original, replacement, item in located:
        start = text.find(original, cursor)
        if start < 0:  # model listed it out of order: search from the beginning
            start = text.find(original)
        if start < 0:
            continue
        end = start + len(original)
        if any(start < u_end and end > u_start for u_start, u_end in used):
            continue
        used.append((start, end))
        cursor = end
        category = CATEGORY_MAP.get(str(item.get("category", "")).lower().strip(), "style")
        try:
            results.append(
                CorrectionResult(
                    start=start,
                    end=end,
                    original=original,
                    replacement=replacement,
                    category=category,
                    title=_clip(item.get("title") or category.title(), 200) or category.title(),
                    explanation=_clip(
                        item.get("explanation") or "See the corrected version.", 2_000
                    ),
                    example=_clip(item.get("example") or "", 1_000),
                )
            )
        except Exception:  # noqa: BLE001 - a single malformed item is dropped
            continue
    results.sort(key=lambda c: c.start)
    return results


def apply_corrections(text: str, corrections: list[CorrectionResult]) -> str:
    for c in sorted(corrections, key=lambda c: c.start, reverse=True):
        text = text[: c.start] + c.replacement + text[c.end :]
    return text


def _extract_json(text: str) -> Any:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        return json.loads(text[start : end + 1])
    raise ValueError("no JSON object in model output")


class _Throttled(Exception):
    """Provider said slow down (429) or is overloaded (503/52x): worth waiting and retrying."""

    def __init__(self, code: str, wait: float | None) -> None:
        super().__init__(code)
        self.code, self.wait = code, wait


def _throttle_of(status: int, body: str, headers) -> _Throttled | None:
    text = body.lower()
    quota = status == 429 or "429" in text or "quota" in text or "rate limit" in text
    if not quota and status not in (502, 503, 504, 520, 522, 524):
        return None
    wait = None
    header = headers.get("retry-after") if headers else None
    if header and header.replace(".", "", 1).isdigit():
        wait = float(header) + 1
    else:
        hint = re.search(
            r"(?:reset after|retry in|retry after|try again in)\s*(\d+(?:\.\d+)?)\s*s", text
        )
        if hint:
            wait = float(hint.group(1)) + 1
    return _Throttled("AI_RATE_LIMITED" if quota else "AI_UNAVAILABLE", wait)


class _Retry(Exception):
    """Model output parsed but unusable; the message is fed back to the model."""


class RouterAIEngine:
    is_fake = False

    def __init__(self, settings: Settings) -> None:
        if settings.router_api_key is None:
            raise ValueError("ROUTER_API_KEY is required when AI_PROVIDER=router.")
        self.settings = settings
        self.m_generate = settings.router_model_generate
        self.m_grade = settings.router_model_grade or settings.router_model_generate
        self.m_chat = settings.router_model_chat or settings.router_model_generate
        self.m_stt = settings.router_model_stt or settings.router_model_generate
        self.assesses_audio = settings.router_assess_audio
        self.name = f"9router (gen={self.m_generate}, grade={self.m_grade}, stt={self.m_stt})"
        self._client = httpx.AsyncClient(
            base_url=settings.router_base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {settings.router_api_key.get_secret_value()}"},
            timeout=httpx.Timeout(settings.ai_request_timeout_seconds, connect=15),
        )
        self._json_mode: dict[str, bool] = {}
        self._audio_style: str | None = None
        self._tts_slots = asyncio.Semaphore(4)
        self._slots = asyncio.Semaphore(settings.router_max_concurrency)

    # ------------------------------------------------------------------ transport
    async def _complete(
        self, model: str, messages: list[dict], *, temperature: float, json_mode: bool = False
    ) -> str:
        """One model call: at most router_max_concurrency at once per process, and on a
        provider rate limit / overload it waits (using the provider's hint) and tries again
        instead of failing the job straight away."""
        retries = self.settings.router_rate_limit_retries
        for attempt in range(1, retries + 2):
            try:
                async with self._slots:
                    return await self._complete_once(
                        model, messages, temperature=temperature, json_mode=json_mode
                    )
            except _Throttled as throttled:
                if attempt > retries:
                    raise AIError(throttled.code, retryable=True) from None
                wait = min(throttled.wait or 5 * 2 ** (attempt - 1), 60)
                logger.info(
                    "router %s for %s; retry %s/%s in %.0fs",
                    throttled.code,
                    model,
                    attempt,
                    retries,
                    wait,
                )
                await asyncio.sleep(wait)
        raise AIError("AI_UNAVAILABLE", retryable=True)

    async def _complete_once(
        self, model: str, messages: list[dict], *, temperature: float, json_mode: bool = False
    ) -> str:
        """Streams the reply so gateways behind Cloudflare never see an idle connection."""
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        if json_mode and self._json_mode.get(model, True):
            payload["response_format"] = {"type": "json_object"}
        try:
            async with self._client.stream("POST", "/chat/completions", json=payload) as res:
                if res.status_code >= 400:
                    body = (await res.aread()).decode(errors="replace")[:300]
                    if "response_format" in payload and res.status_code in (400, 422):
                        self._json_mode[model] = False  # provider has no JSON mode
                        return await self._complete_once(model, messages, temperature=temperature)
                    throttled = _throttle_of(res.status_code, body, res.headers)
                    if throttled:
                        raise throttled
                    raise self._http_error(res.status_code, body)
                parts: list[str] = []
                async for line in res.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    if chunk.get("error"):
                        text = str(chunk["error"])[:300]
                        logger.warning("router stream error: %s", text)
                        raise _throttle_of(503, text, {}) or AIError(
                            "AI_UNAVAILABLE", retryable=True
                        )
                    for choice in chunk.get("choices") or []:
                        piece = (choice.get("delta") or {}).get("content")
                        if piece:
                            parts.append(piece)
                return "".join(parts)
        except httpx.TimeoutException:
            raise AIError("AI_TIMEOUT", retryable=True) from None
        except httpx.TransportError:
            raise AIError("AI_UNAVAILABLE", retryable=True) from None

    @staticmethod
    def _http_error(status: int, body: str) -> AIError:
        logger.warning("router HTTP %s: %s", status, body)
        if status in (401, 403):
            return AIError("AI_AUTH_FAILED", retryable=False)
        if status == 429:
            return AIError("AI_RATE_LIMITED", retryable=True)
        if status >= 500:  # includes Cloudflare 52x
            return AIError("AI_UNAVAILABLE", retryable=True)
        return AIError("AI_REQUEST_REJECTED", retryable=False)

    async def _json(
        self, model: str, prompt: str, build, *, temperature: float = 0.7, attempts: int = 3
    ):
        """Ask for JSON, then build/validate it. Feeds problems back to the model."""
        messages = [
            {"role": "system", "content": TEACHER + "\nRespond with ONLY one valid JSON object."},
            {"role": "user", "content": prompt},
        ]
        for attempt in range(1, attempts + 1):
            text = await self._complete(model, messages, temperature=temperature, json_mode=True)
            try:
                return build(_extract_json(text))
            except (ValueError, KeyError, TypeError, _Retry) as problem:
                logger.info("model output rejected (attempt %s): %s", attempt, problem)
                messages += [
                    {"role": "assistant", "content": text[:6_000]},
                    {
                        "role": "user",
                        "content": f"That output cannot be used: {problem}. "
                        "Return the corrected, complete JSON object only.",
                    },
                ]
            except AIError:
                raise
            except Exception as problem:  # noqa: BLE001 - pydantic and friends
                logger.info("model output invalid (attempt %s): %s", attempt, problem)
                messages += [
                    {"role": "assistant", "content": text[:6_000]},
                    {
                        "role": "user",
                        "content": "That JSON does not match the required "
                        f"fields: {str(problem)[:500]}. Return the corrected JSON object only.",
                    },
                ]
        raise AIError("AI_OUTPUT_INVALID", retryable=True)

    # ------------------------------------------------------------------ writing
    async def generate_writing_prompt(self, request: WritingPromptRequest) -> WritingPrompt:
        length = (
            f"about {request.target_word_count} words"
            if request.target_word_count
            else "a length that suits the level"
        )
        prompt = f"""Write ONE writing task for a learner.
Topic: {request.topic}
Level: {CEFR_GUIDE[request.cefr_level]} Difficulty: {request.difficulty}.
Expected answer length: {length}.
The task should be like an IELTS Writing Task 2 question simplified to the level: a clear
question or situation, what to include (2-3 points), and the expected length.
JSON: {{"title": "short title (max 12 words)", "instructions": "the full task text for the student"}}"""

        def build(d):
            return WritingPrompt(
                title=_clip(d["title"], 200), instructions=_clip(d["instructions"], 4_000)
            )

        return await self._json(self.m_generate, prompt, build, temperature=0.9)

    async def evaluate_writing(self, request: WritingEvaluationRequest) -> WritingEvaluation:
        criteria = "\n".join(f"- {c.code}: {c.name}. {c.descriptor}" for c in request.criteria)
        prompt = f"""Grade this student's writing.

TASK TITLE: {request.title}
TASK: {request.instructions}
STUDENT LEVEL: {request.cefr_level}. Target length: {request.target_word_count or "not set"} words.

STUDENT TEXT (between the markers, exactly as written):
<<<TEXT
{request.response_text}
TEXT>>>

CRITERIA (score each from {request.score_min} to {request.score_max} in steps of {request.score_step}):
{criteria}

Rules:
- Use every criterion code exactly once.
- "corrections": the most useful 3-15 fixes, in the order they appear. "original" MUST be copied
  character-for-character from the student text (a short fragment, a few words), "replacement" is the fix.
  category is one of: grammar, spelling, vocabulary, style.
- "corrected_text": the whole student text with all your corrections applied, keeping their ideas.
- Feedback is specific, encouraging and quotes the student's words. Write feedback in simple English.

JSON:
{{"summary": "2-4 sentences overall",
  "criteria": [{{"code": "...", "score": 6.0, "feedback": "..."}}],
  "corrections": [{{"original": "...", "replacement": "...", "category": "grammar",
                   "title": "short rule name", "explanation": "why", "example": "a correct example sentence"}}],
  "corrected_text": "..."}}"""
        codes = {c.code for c in request.criteria}

        def build(d):
            scores = {}
            for item in d.get("criteria") or []:
                code = str(item.get("code", "")).strip()
                if code in codes and code not in scores:
                    scores[code] = CriterionScore(
                        code=code,
                        score=_on_step(
                            item.get("score"),
                            request.score_min,
                            request.score_max,
                            request.score_step,
                        ),
                        feedback=_clip(item.get("feedback") or "No feedback.", 2_000),
                    )
            missing = codes - scores.keys()
            if missing:
                raise _Retry(f"missing criteria codes {sorted(missing)}")
            corrections = locate_corrections(request.response_text, d.get("corrections") or [])
            corrected = str(d.get("corrected_text") or "").strip()
            if not corrected:
                corrected = apply_corrections(request.response_text, corrections)
            return WritingEvaluation(
                summary=_clip(d.get("summary") or "Evaluation complete.", 4_000),
                corrected_text=corrected or request.response_text,
                criteria=[scores[c.code] for c in request.criteria],
                corrections=corrections,
            )

        return await self._json(self.m_grade, prompt, build, temperature=0.2)

    # ------------------------------------------------------------------ reading / quiz
    def _question_spec(self, kinds: list[str]) -> str:
        return "\n".join(
            f"  Q{i}: {k}"
            + (
                " (4 options, correct_option = 0-based index)"
                if k == "multiple_choice"
                else " (reference_answer = a short model answer)"
            )
            for i, k in enumerate(kinds, 1)
        )

    def _build_questions(
        self, raw: list[dict], kinds: list[str], source: str
    ) -> list[GeneratedQuestion]:
        if len(raw) != len(kinds):
            raise _Retry(f"expected exactly {len(kinds)} questions, got {len(raw)}")
        out = []
        for index, (item, kind) in enumerate(zip(raw, kinds, strict=True), 1):
            options: list[str] = []
            correct = None
            reference = None
            if kind == "multiple_choice":
                options = [
                    re.sub(r"^\s*[A-Fa-f][.)]\s+", "", _clip(o, 300))
                    for o in item.get("options") or []
                ]
                options = [o for o in options if o][:6]
                if len(options) < 2 or len({o.lower() for o in options}) != len(options):
                    raise _Retry(f"Q{index} needs 4 distinct options")
                correct = item.get("correct_option")
                if isinstance(correct, str):
                    correct = correct.strip()
                    correct = (
                        "ABCDEF".index(correct.upper())
                        if len(correct) == 1 and correct.upper() in "ABCDEF"
                        else int(correct)
                        if correct.isdigit()
                        else None
                    )
                if not isinstance(correct, int) or not 0 <= correct < len(options):
                    raise _Retry(f"Q{index} correct_option must be an index 0-{len(options) - 1}")
                answer_text = options[correct]
            else:
                reference = _clip(item.get("reference_answer") or "", 1_000)
                if not reference:
                    raise _Retry(f"Q{index} needs a reference_answer")
                answer_text = reference
            quotes = []
            for q in item.get("evidence_quotes") or []:
                fixed = repair_quote(source, str(q))
                if fixed and fixed not in quotes:
                    quotes.append(fixed)
            if not quotes:
                fallback = sentence_containing(source, answer_text)
                if fallback and fallback in source:
                    quotes = [fallback]
            if not quotes:
                raise _Retry(f"Q{index} evidence_quotes must be copied exactly from the text")
            out.append(
                GeneratedQuestion(
                    question_type=kind,
                    question_text=_clip(item.get("question_text") or item.get("question"), 1_000),
                    options=options,
                    correct_option=correct,
                    reference_answer=reference,
                    explanation=_clip(
                        item.get("explanation") or "See the evidence in the text.", 2_000
                    ),
                    evidence_quotes=quotes[:5],
                )
            )
        return out

    async def generate_reading(self, request: ReadingRequest) -> ReadingPackage:
        target, tol = request.target_word_count, self.settings.reading_word_count_tolerance
        low, high = int(target * (1 - tol * 0.7)), int(target * (1 + tol * 0.7))
        extra_vocab = request.vocabulary_count + 3
        prompt = f"""Create a reading practice package.
Topic: {request.topic}
Level: {CEFR_GUIDE[request.cefr_level]} Difficulty: {request.difficulty}.
Passage length: about {target} words (must be between {low} and {high} words), in 3-6 paragraphs
separated by a blank line. Make it interesting and factual-sounding, like an IELTS reading text
adapted to the level.

Questions, exactly in this order:
{self._question_spec(request.question_types)}
Each question needs "evidence_quotes": 1-2 sentences copied EXACTLY (character for character) from the passage.
Multiple-choice: plausible distractors, one clearly correct answer. Short answer: answerable in a few words.

Vocabulary: {extra_vocab} useful words or phrases that appear EXACTLY in the passage, with a simple meaning
and a new example sentence.

JSON:
{{"title": "...", "instructions": "one sentence telling the student what to do",
  "passage": "paragraph 1\\n\\nparagraph 2 ...",
  "questions": [{{"question_type": "multiple_choice", "question_text": "...", "options": ["...","...","...","..."],
                 "correct_option": 0, "explanation": "...", "evidence_quotes": ["..."]}},
                {{"question_type": "short_answer", "question_text": "...", "reference_answer": "...",
                 "explanation": "...", "evidence_quotes": ["..."]}}],
  "vocabulary": [{{"word_or_phrase": "...", "meaning": "...", "example_sentence": "..."}}]}}"""

        def build(d):
            passage = str(d.get("passage") or "").strip()
            words = len(passage.split())
            if abs(words - target) > tol * target:
                raise _Retry(
                    f"the passage has {words} words; it must be about {target} ({low}-{high})"
                )
            questions = self._build_questions(
                d.get("questions") or [], request.question_types, passage
            )
            vocab, seen = [], set()
            for v in d.get("vocabulary") or []:
                word = _clip(v.get("word_or_phrase"), 200)
                key = word.lower()
                if not word or key in seen:
                    continue
                if not re.search(rf"(?<!\w){re.escape(word)}(?!\w)", passage, re.IGNORECASE):
                    continue
                seen.add(key)
                vocab.append(
                    GeneratedVocabulary(
                        word_or_phrase=word,
                        meaning=_clip(v.get("meaning") or "-", 500),
                        example_sentence=_clip(v.get("example_sentence") or word, 500),
                    )
                )
            if len(vocab) < request.vocabulary_count:
                raise _Retry(
                    f"only {len(vocab)} vocabulary items appear exactly in the passage; "
                    f"need {request.vocabulary_count}"
                )
            return ReadingPackage(
                title=_clip(d.get("title") or request.topic, 200),
                instructions=_clip(
                    d.get("instructions") or "Read the text and answer the questions.", 2_000
                ),
                passage=passage,
                questions=questions,
                vocabulary=vocab[: request.vocabulary_count],
            )

        return await self._json(self.m_generate, prompt, build, temperature=0.8)

    async def grade_short_answer(self, request: ShortAnswerGradeRequest) -> ShortAnswerGrade:
        evidence = "\n".join(f"- {e}" for e in request.evidence)
        prompt = f"""Grade one short answer.
QUESTION: {request.question_text}
REFERENCE ANSWER: {request.reference_answer}
EVIDENCE FROM THE TEXT:
{evidence}
STUDENT ANSWER: {request.response_text}
RUBRIC: {request.rubric}
Points: 0 to {request.max_points} in steps of {request.point_step}.
JSON: {{"awarded_points": 1.0, "feedback": "1-2 sentences for the student"}}"""

        def build(d):
            return ShortAnswerGrade(
                awarded_points=_on_step(
                    d.get("awarded_points"), 0, request.max_points, request.point_step
                ),
                feedback=_clip(d.get("feedback") or "Graded.", 2_000),
            )

        return await self._json(self.m_grade, prompt, build, temperature=0.1)

    # ------------------------------------------------------------------ listening
    async def generate_listening(self, request: ListeningRequest) -> ListeningPackage:
        target, tol = request.target_word_count, self.settings.listening_word_count_tolerance
        low, high = int(target * (1 - tol * 0.7)), int(target * (1 + tol * 0.7))
        prompt = f"""Create a listening practice script (it will be read aloud by text-to-speech).
Topic: {request.topic}
Level: {CEFR_GUIDE[request.cefr_level]} Difficulty: {request.difficulty}.
A natural conversation between 2 speakers (or a short monologue with an announcer), like IELTS
Listening Part 1 or 3 adapted to the level. Total spoken words: about {target} (between {low} and {high}).
Each line is one turn: first names only as "speaker" (no colons), plain spoken text, no stage directions,
no line breaks inside a line. Include one or two natural distractors (a speaker corrects themselves).

Questions, exactly in this order:
{self._question_spec(request.question_types)}
Each question needs "evidence_quotes": words copied EXACTLY from one line's text.

JSON:
{{"title": "...", "instructions": "one sentence for the student",
  "lines": [{{"speaker": "Anna", "text": "..."}}],
  "questions": [{{"question_type": "...", "question_text": "...", "options": [...], "correct_option": 0,
                 "reference_answer": null, "explanation": "...", "evidence_quotes": ["..."]}}]}}"""

        def build(d):
            raw_lines = d.get("lines") or []
            voice_of: dict[str, str] = {}
            lines: list[ScriptLine] = []
            for item in raw_lines:
                speaker = (
                    re.sub(r"[:\n]", "", _clip(item.get("speaker") or "Speaker", 40)).strip()
                    or "Speaker"
                )
                text = re.sub(r"\s+", " ", str(item.get("text") or "")).strip()
                if not text:
                    continue
                if speaker not in voice_of:
                    if len(voice_of) >= 4:
                        raise _Retry("use at most 4 speakers")
                    voice_of[speaker] = request.voices[len(voice_of) % len(request.voices)]
                lines.append(
                    ScriptLine(speaker=speaker, voice=voice_of[speaker], text=text[:2_000])
                )
            if not lines:
                raise _Retry("no script lines")
            if len(lines) > 80:
                raise _Retry("use at most 80 lines")
            words = sum(len(line.text.split()) for line in lines)
            if abs(words - target) > tol * target:
                raise _Retry(
                    f"the script has {words} spoken words; it must be about {target} ({low}-{high})"
                )
            transcript = "\n".join(f"{line.speaker}: {line.text}" for line in lines)
            questions = self._build_questions(
                d.get("questions") or [], request.question_types, transcript
            )
            return ListeningPackage(
                title=_clip(d.get("title") or request.topic, 200),
                instructions=_clip(
                    d.get("instructions") or "Listen and answer the questions.", 2_000
                ),
                lines=lines,
                questions=questions,
            )

        return await self._json(self.m_generate, prompt, build, temperature=0.8)

    # ------------------------------------------------------------------ speech (TTS)
    def _edge_voice(self, key: str) -> str:
        mapping = self.settings.tts_voice_map
        if key in mapping:
            return mapping[key]
        pool = [v for k, v in mapping.items() if k.split("_")[0] == key.split("_")[0]] or list(
            mapping.values()
        )
        return pool[sum(map(ord, key)) % len(pool)]

    async def _tts_pcm(self, text: str, voice: str) -> bytes:
        import edge_tts

        async with self._tts_slots:
            mp3 = bytearray()
            try:
                async for chunk in edge_tts.Communicate(
                    text, voice, rate=self.settings.tts_rate
                ).stream():
                    if chunk["type"] == "audio":
                        mp3.extend(chunk["data"])
            except Exception as error:  # noqa: BLE001 - network / service errors
                logger.warning("edge-tts failed: %s", error)
                raise AIError("TTS_UNAVAILABLE", retryable=True) from None
        if not mp3:
            raise AIError("TTS_OUTPUT_INVALID", retryable=True)
        return await asyncio.to_thread(_mp3_to_pcm, bytes(mp3))

    async def synthesize_speech(self, request: SpeechRequest) -> SpeechAudio:
        if shutil.which("ffmpeg") is None:
            logger.error("ffmpeg is not installed; it is needed to produce WAV audio")
            raise AIError("TTS_UNAVAILABLE", retryable=False)
        pcm_parts = await asyncio.gather(
            *(self._tts_pcm(s.text, self._edge_voice(s.voice)) for s in request.segments)
        )
        gap = b"\x00\x00" * (SAMPLE_RATE * LINE_GAP_MS // 1000)
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(SAMPLE_RATE)
            for index, pcm in enumerate(pcm_parts):
                if index:
                    out.writeframes(gap)
                out.writeframes(pcm)
        return SpeechAudio(audio=buffer.getvalue())

    # ------------------------------------------------------------------ speech (STT)
    @staticmethod
    def _audio_part(style: str, b64: str, fmt: str, mime: str) -> dict:
        if style == "input_audio":
            return {"type": "input_audio", "input_audio": {"data": b64, "format": fmt}}
        if style == "file":
            return {
                "type": "file",
                "file": {"file_data": f"data:{mime};base64,{b64}", "filename": f"audio.{fmt}"},
            }
        return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}

    async def _with_audio(
        self,
        model: str,
        text: str,
        clips: list[bytes],
        *,
        temperature: float,
        json_mode: bool = False,
    ) -> str:
        """Sends WAV clips with a prompt, trying the content formats gateways accept."""
        styles = ["input_audio", "file", "image_url"]
        if self._audio_style:
            styles.remove(self._audio_style)
            styles.insert(0, self._audio_style)
        encoded = [base64.b64encode(c).decode() for c in clips]
        last: AIError | None = None
        for style in styles:
            content = [{"type": "text", "text": text}] + [
                self._audio_part(style, b64, "wav", "audio/wav") for b64 in encoded
            ]
            try:
                reply = await self._complete(
                    model,
                    [{"role": "user", "content": content}],
                    temperature=temperature,
                    json_mode=json_mode,
                )
            except AIError as error:
                if error.code != "AI_REQUEST_REJECTED":
                    raise
                last = error
                continue
            if re.search(
                r"(no|not|cannot|can't|unable)\b.{0,30}\b(audio|hear|listen|file|attachment)",
                reply[:200],
                re.IGNORECASE,
            ):
                logger.info("audio style %s did not reach the model", style)
                last = AIError("STT_UNAVAILABLE", retryable=True)
                continue
            self._audio_style = style
            return reply
        raise last or AIError("STT_UNAVAILABLE", retryable=True)

    async def transcribe(self, request: TranscriptionRequest) -> Transcription:
        prompt = (
            "Transcribe this English speech VERBATIM, exactly as spoken by a language learner. "
            "Keep fillers (um, uh), repetitions and grammar mistakes; do NOT correct anything. "
            f"If there is no intelligible speech, output exactly {NO_SPEECH}. "
            "Output ONLY the transcript text."
        )
        text = (await self._with_audio(self.m_stt, prompt, [request.audio], temperature=0)).strip()
        text = text.strip('"').strip()
        if not text or NO_SPEECH in text:
            return Transcription(text="")
        return Transcription(text=text[:20_000])

    # ------------------------------------------------------------------ speaking
    async def generate_speaking_prompt(self, request: SpeakingPromptRequest) -> SpeakingPrompt:
        prompt = f"""Create a speaking practice task: a conversation with {request.persona_name}
({request.persona_role}) about "{request.topic}".
Level: {CEFR_GUIDE[request.cefr_level]} Difficulty: {request.difficulty}.
Like IELTS Speaking Part 1/3 adapted to the level: tell the student what the conversation is about,
2-3 things they should talk about, and to answer with full sentences and examples.
JSON: {{"title": "short title", "instructions": "instructions for the student (2-4 sentences)"}}"""

        def build(d):
            return SpeakingPrompt(
                title=_clip(d["title"], 200), instructions=_clip(d["instructions"], 2_000)
            )

        return await self._json(self.m_generate, prompt, build, temperature=0.9)

    async def converse(self, request: ConversationRequest) -> ConversationReply:
        system = (
            f"You are {request.persona_name}, {request.persona_role}. {request.behavior_instructions}\n"
            f"You are having a spoken English practice conversation with a learner.\n"
            f"Activity: {request.title}. {request.instructions}\nTopic: {request.topic}.\n"
            f"Learner level: {CEFR_GUIDE[request.cefr_level]} Speak at that level.\n"
            "Your reply is read aloud: plain spoken text only, no emojis, lists, markdown or stage "
            "directions. Keep every reply to 1-3 short sentences and usually end with one question "
            "that keeps the learner talking. Do not correct the learner's grammar during the chat."
        )
        messages = [{"role": "system", "content": system}]
        for turn in request.history:
            messages.append(
                {"role": "user" if turn.sender == "user" else "assistant", "content": turn.text}
            )
        if not request.history:
            messages.append(
                {
                    "role": "user",
                    "content": "(The learner has joined. Greet them and ask your first question.)",
                }
            )
        text = (await self._complete(self.m_chat, messages, temperature=0.8)).strip()
        text = re.sub(r"[*_#`]+", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        limit = min(4_000, self.settings.speaking_max_reply_chars) - 10
        if len(text) > limit:
            cut = max(text.rfind(m, 0, limit) for m in (". ", "? ", "! "))
            text = text[: cut + 1] if cut > 0 else text[:limit]
        if not text:
            raise AIError("AI_OUTPUT_INVALID", retryable=True)
        return ConversationReply(text=text)

    async def evaluate_speaking(self, request: SpeakingEvaluationRequest) -> SpeakingEvaluation:
        listen = self.assesses_audio and bool(request.recordings)
        criteria = "\n".join(
            f"- {c.code}: {c.name}. {c.descriptor}"
            + (
                ""
                if listen or not c.requires_audio
                else "  [NEEDS AUDIO: set assessed=false, score=null]"
            )
            for c in request.criteria
        )
        dialogue = "\n".join(
            f"{'STUDENT' if t.sender == 'user' else 'PARTNER'}: {t.text}" for t in request.turns
        )
        prompt = f"""Evaluate the STUDENT's speaking in this practice conversation.
ACTIVITY: {request.title}. {request.instructions}
STUDENT LEVEL: {request.cefr_level}

TRANSCRIPT (speech-to-text):
{dialogue}

{"The student's original recordings are attached in order; use them for fluency and pronunciation." if listen else ""}
CRITERIA (score {request.score_min}-{request.score_max} in steps of {request.score_step}):
{criteria}
Use every criterion code exactly once. Feedback quotes the student's words and gives one concrete tip.
JSON: {{"summary": "2-4 sentences",
        "criteria": [{{"code": "...", "assessed": true, "score": 6.0, "feedback": "..."}}]}}"""
        by_code = {c.code: c for c in request.criteria}

        def build(d):
            results: dict[str, SpeakingCriterionResult] = {}
            for item in d.get("criteria") or []:
                code = str(item.get("code", "")).strip()
                if code not in by_code or code in results:
                    continue
                criterion = by_code[code]
                assessed = bool(item.get("assessed", True)) and (
                    listen or not criterion.requires_audio
                )
                feedback = _clip(item.get("feedback") or "Not assessed.", 2_000) or "Not assessed."
                if assessed:
                    score = _on_step(
                        item.get("score"), request.score_min, request.score_max, request.score_step
                    )
                    results[code] = SpeakingCriterionResult(
                        code=code, assessed=True, score=score, feedback=feedback
                    )
                else:
                    results[code] = SpeakingCriterionResult(
                        code=code, assessed=False, feedback=feedback
                    )
            missing = set(by_code) - results.keys()
            if missing:
                raise _Retry(f"missing criteria codes {sorted(missing)}")
            return SpeakingEvaluation(
                summary=_clip(d.get("summary") or "Evaluation complete.", 4_000),
                criteria=[results[c.code] for c in request.criteria],
            )

        if not listen:
            return await self._json(self.m_grade, prompt, build, temperature=0.2)
        clips = _limit_clips(request.recordings, self.settings.router_audio_eval_max_bytes)
        for attempt in range(1, 3):
            text = await self._with_audio(
                self.m_grade,
                TEACHER + "\nRespond with ONLY one valid JSON object.\n\n" + prompt,
                clips,
                temperature=0.2,
                json_mode=True,
            )
            try:
                return build(_extract_json(text))
            except Exception as problem:  # noqa: BLE001
                logger.info("speaking evaluation rejected (attempt %s): %s", attempt, problem)
        raise AIError("AI_OUTPUT_INVALID", retryable=True)

    async def aclose(self) -> None:
        await self._client.aclose()


def _limit_clips(clips: list[bytes], max_bytes: int) -> list[bytes]:
    """Most recent recordings first until the byte budget is used, then back in order."""
    kept, total = [], 0
    for clip in reversed(clips):
        if total + len(clip) > max_bytes:
            break
        kept.append(clip)
        total += len(clip)
    return list(reversed(kept))


def _mp3_to_pcm(mp3: bytes) -> bytes:
    import subprocess

    process = subprocess.run(
        [
            "ffmpeg",
            "-loglevel",
            "error",
            "-i",
            "pipe:0",
            "-f",
            "s16le",
            "-acodec",
            "pcm_s16le",
            "-ac",
            "1",
            "-ar",
            str(SAMPLE_RATE),
            "pipe:1",
        ],
        input=mp3,
        capture_output=True,
        check=False,
    )
    if process.returncode != 0 or not process.stdout:
        logger.warning("ffmpeg decode failed: %s", process.stderr[:300])
        raise AIError("TTS_OUTPUT_INVALID", retryable=True)
    return process.stdout
