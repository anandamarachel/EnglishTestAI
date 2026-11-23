"""RouterAIEngine against a mocked 9router: output must pass the domain validators."""

import asyncio
import io
import json
import uuid
import wave

import httpx
import pytest

from app.ai.contracts import (
    ConversationRequest,
    ConversationTurn,
    ListeningRequest,
    ReadingRequest,
    SpeakingEvaluationRequest,
    SpeechRequest,
    SpeechSegment,
    TranscriptionRequest,
    WritingEvaluationRequest,
)
from app.ai.engine import AIError
from app.ai.factory import build_engine
from app.ai.router import RouterAIEngine, locate_corrections, repair_quote
from app.core.config import Settings
from app.modules.listening import service as listening
from app.modules.media.audio import inspect_wav
from app.modules.reading import service as reading
from app.modules.speaking import rubric as speaking_rubric
from app.modules.speaking import service as speaking
from app.modules.writing import rubric as writing_rubric
from app.modules.writing import service as writing

BASE = dict(postgres_password="x", jwt_secret="x" * 32)


def settings(**extra) -> Settings:
    extra.setdefault("router_rate_limit_retries", 0)
    return Settings(**BASE, ai_provider="router", router_api_key="sk-test", **extra)


def sse(text: str) -> bytes:
    chunks = [text[i : i + 40] for i in range(0, len(text), 40)] or [""]
    body = "".join(
        f"data: {json.dumps({'choices': [{'delta': {'content': c}}]})}\n\n" for c in chunks
    )
    return (body + "data: [DONE]\n\n").encode()


class FakeRouter:
    """Replies with queued texts; records every request payload."""

    def __init__(self, *replies, status: int = 200) -> None:
        self.replies = list(replies)
        self.status = status
        self.requests: list[dict] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        self.requests.append(payload)
        if self.status != 200:
            return httpx.Response(self.status, json={"error": "nope"})
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if callable(reply):
            reply = reply(payload)
        if isinstance(reply, httpx.Response):
            return reply
        text = reply if isinstance(reply, str) else json.dumps(reply)
        return httpx.Response(200, content=sse(text), headers={"content-type": "text/event-stream"})


def engine_with(router: FakeRouter, **extra) -> RouterAIEngine:
    engine = RouterAIEngine(settings(**extra))
    engine._client = httpx.AsyncClient(
        base_url="http://router/v1", transport=httpx.MockTransport(router)
    )
    return engine


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------- config / factory
def test_factory_builds_router_and_requires_key() -> None:
    assert isinstance(build_engine(settings()), RouterAIEngine)
    with pytest.raises(ValueError):
        Settings(**BASE, ai_provider="router")
    assert Settings(**BASE, app_env="production", ai_provider="router", router_api_key="k")


# ---------------------------------------------------------------- helpers
def test_repair_quote_and_corrections() -> None:
    source = "Coffee was first found in Ethiopia.\nIt spread  to Yemen later."
    assert repair_quote(source, "coffee WAS first found") == "Coffee was first found"
    assert repair_quote(source, "It spread to Yemen") == "It spread  to Yemen"
    assert repair_quote(source, "completely invented sentence here") is None
    text = "yesterday i go to market and i buy apple"
    found = locate_corrections(
        text,
        [
            {"original": "i go", "replacement": "I went", "category": "grammar"},
            {
                "original": "i buy apple",
                "replacement": "I bought an apple",
                "category": "Punctuation",
            },
            {"original": "not in text", "replacement": "x"},
            {"original": "go", "replacement": "went"},  # overlaps the first one
        ],
    )
    assert [(c.original, c.category) for c in found] == [
        ("i go", "grammar"),
        ("i buy apple", "grammar"),
    ]
    assert all(text[c.start : c.end] == c.original for c in found)


# ---------------------------------------------------------------- transport
def test_streaming_json_mode_fallback_and_errors() -> None:
    def reply(payload):
        if "response_format" in payload:
            return httpx.Response(400, json={"error": "response_format unsupported"})
        return '```json\n{"title": "Holiday", "instructions": "Write about a holiday."}\n```'

    router = FakeRouter(reply)
    engine = engine_with(router)
    from app.ai.contracts import WritingPromptRequest

    prompt = run(
        engine.generate_writing_prompt(
            WritingPromptRequest(
                topic="holidays", difficulty="beginner", cefr_level="A2", target_word_count=120
            )
        )
    )
    assert prompt.title == "Holiday"
    assert all(p["stream"] for p in router.requests)
    assert engine._json_mode[engine.m_generate] is False

    with pytest.raises(AIError) as error:
        run(
            engine_with(FakeRouter("x", status=401)).generate_writing_prompt(
                WritingPromptRequest(
                    topic="t", difficulty="beginner", cefr_level="A2", target_word_count=None
                )
            )
        )
    assert error.value.code == "AI_AUTH_FAILED" and not error.value.retryable

    with pytest.raises(AIError) as error:
        run(
            engine_with(FakeRouter("x", status=524)).generate_writing_prompt(
                WritingPromptRequest(
                    topic="t", difficulty="beginner", cefr_level="A2", target_word_count=None
                )
            )
        )
    assert error.value.code == "AI_UNAVAILABLE" and error.value.retryable


def test_bad_json_is_retried_then_fails_cleanly() -> None:
    from app.ai.contracts import WritingPromptRequest

    router = FakeRouter("not json at all", '{"title": "Ok", "instructions": "Do it."}')
    result = run(
        engine_with(router).generate_writing_prompt(
            WritingPromptRequest(
                topic="t", difficulty="beginner", cefr_level="B1", target_word_count=None
            )
        )
    )
    assert result.title == "Ok" and len(router.requests) == 2
    with pytest.raises(AIError) as error:
        run(
            engine_with(FakeRouter("still broken")).generate_writing_prompt(
                WritingPromptRequest(
                    topic="t", difficulty="beginner", cefr_level="B1", target_word_count=None
                )
            )
        )
    assert error.value.code == "AI_OUTPUT_INVALID"


# ---------------------------------------------------------------- writing
def test_writing_evaluation_passes_domain_validation() -> None:
    text = "Yesterday i go to the market. We was happy because the the food was cheap."
    reply = {
        "summary": "Good effort with a few tense errors.",
        "criteria": [
            {"code": "task_response", "score": 6.2, "feedback": "Clear."},
            {"code": "coherence_cohesion", "score": "6", "feedback": "Ok."},
            {"code": "lexical_resource", "score": 5.5, "feedback": "Ok."},
            {"code": "grammatical_range_accuracy", "score": 9.9, "feedback": "Ok."},
            {"code": "unknown", "score": 3, "feedback": "ignored"},
        ],
        "corrections": [
            {
                "original": "i go",
                "replacement": "I went",
                "category": "grammar",
                "title": "Past tense",
                "explanation": "Yesterday needs past tense.",
                "example": "I went home.",
            },
            {
                "original": "We was",
                "replacement": "We were",
                "category": "grammar",
                "title": "Agreement",
                "explanation": "we + were",
                "example": "We were late.",
            },
            {
                "original": "the the",
                "replacement": "the",
                "category": "style",
                "title": "Repeat",
                "explanation": "Repeated word.",
                "example": "",
            },
        ],
        "corrected_text": "",
    }
    request = WritingEvaluationRequest(
        title="Market",
        instructions="Write about a trip.",
        cefr_level="A2",
        target_word_count=80,
        response_text=text,
        criteria=writing_rubric.CRITERIA,
        score_min=0,
        score_max=9,
        score_step=0.5,
    )
    result = run(engine_with(FakeRouter(reply)).evaluate_writing(request))
    writing.validate_evaluation(request, result)  # raises if invalid
    assert [c.score for c in result.criteria] == [6.0, 6.0, 5.5, 9.0]
    assert result.corrected_text.startswith(
        "Yesterday I went to the market. We were happy because the food"
    )


def test_writing_missing_criterion_is_retried() -> None:
    partial = {
        "summary": "s",
        "criteria": [{"code": "task_response", "score": 6, "feedback": "f"}],
        "corrections": [],
        "corrected_text": "x",
    }
    full = {
        **partial,
        "criteria": [{"code": c, "score": 6, "feedback": "f"} for c in writing_rubric.CODES],
    }
    router = FakeRouter(partial, full)
    request = WritingEvaluationRequest(
        title="t",
        instructions="i",
        cefr_level="B1",
        target_word_count=None,
        response_text="Some text.",
        criteria=writing_rubric.CRITERIA,
        score_min=0,
        score_max=9,
        score_step=0.5,
    )
    result = run(engine_with(router).evaluate_writing(request))
    assert len(result.criteria) == 4 and len(router.requests) == 2
    assert "missing criteria" in router.requests[1]["messages"][-1]["content"]


# ---------------------------------------------------------------- reading
PASSAGE = (
    "Coffee was first discovered in Ethiopia many centuries ago. A young goat herder noticed "
    "that his goats became lively after eating red berries.\n\n"
    "Later, traders carried the beans to Yemen, where people began to roast and brew them. "
    "Coffee houses soon became popular places to meet friends and share news.\n\n"
    "Today, coffee is grown in more than fifty countries and is one of the most traded products "
    "in the world. Many farmers depend on it for their income."
)


def reading_reply(**overrides):
    reply = {
        "title": "The Story of Coffee",
        "instructions": "Read the text and answer the questions.",
        "passage": PASSAGE,
        "questions": [
            {
                "question_type": "multiple_choice",
                "question_text": "Where was coffee first discovered?",
                "options": ["A. Yemen", "B. Ethiopia", "C. Brazil", "D. Italy"],
                "correct_option": "B",
                "explanation": "Paragraph 1.",
                "evidence_quotes": ["coffee was first discovered in ethiopia"],
            },
            {
                "question_type": "short_answer",
                "question_text": "What did the goats eat?",
                "reference_answer": "red berries",
                "explanation": "Paragraph 1.",
                "evidence_quotes": ["This sentence is not in the passage at all."],
            },
        ],
        "vocabulary": [
            {
                "word_or_phrase": "lively",
                "meaning": "full of energy",
                "example_sentence": "The party was lively.",
            },
            {"word_or_phrase": "invented", "meaning": "not in passage", "example_sentence": "x"},
            {
                "word_or_phrase": "traders",
                "meaning": "people who buy and sell",
                "example_sentence": "Traders came.",
            },
        ],
    }
    reply.update(overrides)
    return reply


def test_reading_package_passes_domain_validation() -> None:
    request = ReadingRequest(
        topic="coffee",
        difficulty="beginner",
        cefr_level="A2",
        target_word_count=80,
        question_types=["multiple_choice", "short_answer"],
        vocabulary_count=2,
    )
    package = run(engine_with(FakeRouter(reading_reply())).generate_reading(request))
    data = reading.GenerationInput(
        exercise_id=uuid.uuid4(),
        topic_id=None,
        requested_word_count=None,
        tolerance=0.4,
        request=request,
    )
    validated = reading.validate_package(data, package)
    assert (
        package.questions[0].options[1] == "Ethiopia" and package.questions[0].correct_option == 1
    )
    assert package.questions[0].evidence_quotes == ["Coffee was first discovered in Ethiopia"]
    assert "red berries" in package.questions[1].evidence_quotes[0]  # fallback sentence
    assert [v.word_or_phrase for v in package.vocabulary] == ["lively", "traders"]
    assert len(validated.evidence) == 2


def test_reading_wrong_length_is_fed_back() -> None:
    request = ReadingRequest(
        topic="coffee",
        difficulty="beginner",
        cefr_level="A2",
        target_word_count=300,
        question_types=["multiple_choice", "short_answer"],
        vocabulary_count=2,
    )
    long_passage = (PASSAGE + "\n\n") * 4
    router = FakeRouter(reading_reply(), reading_reply(passage=long_passage.strip()))
    package = run(engine_with(router).generate_reading(request))
    assert len(package.passage.split()) > 200
    assert "words" in router.requests[1]["messages"][-1]["content"]


# ---------------------------------------------------------------- listening
def test_listening_package_passes_domain_validation() -> None:
    lines = [
        {"speaker": "Anna:", "text": "Hi, I'd like to book a table for four people on Friday."},
        {"speaker": "Waiter", "text": "Of course. Is seven o'clock okay,\nor later?"},
        {
            "speaker": "Anna",
            "text": "Actually, make it eight o'clock, please. My name is Anna Lee.",
        },
        {"speaker": "Waiter", "text": "Great, a table for four at eight on Friday for Anna Lee."},
    ]
    reply = {
        "title": "Booking",
        "instructions": "Listen and answer.",
        "lines": lines * 2,
        "questions": [
            {
                "question_type": "multiple_choice",
                "question_text": "What time is the booking?",
                "options": ["Seven", "Eight", "Nine"],
                "correct_option": 1,
                "explanation": "Anna corrects it.",
                "evidence_quotes": ["make it eight o'clock"],
            },
            {
                "question_type": "short_answer",
                "question_text": "How many people?",
                "reference_answer": "four",
                "explanation": "She says four.",
                "evidence_quotes": ["a table for four people"],
            },
        ],
    }
    request = ListeningRequest(
        topic="restaurant",
        difficulty="beginner",
        cefr_level="A2",
        target_word_count=110,
        question_types=["multiple_choice", "short_answer"],
        voices=["female_1", "male_1"],
    )
    package = run(engine_with(FakeRouter(reply)).generate_listening(request))
    data = listening.GenerationInput(
        exercise_id=uuid.uuid4(),
        owner_id=uuid.uuid4(),
        topic_id=None,
        tolerance=0.4,
        max_audio_bytes=1,
        max_audio_duration_ms=1,
        request=request,
    )
    transcript, evidence = listening.validate_package(data, package)
    assert {line.speaker: line.voice for line in package.lines} == {
        "Anna": "female_1",
        "Waiter": "male_1",
    }
    assert len(evidence) == 2 and "\n" not in package.lines[1].text


# ---------------------------------------------------------------- speech
def test_synthesize_speech_makes_valid_wav(monkeypatch) -> None:
    engine = engine_with(FakeRouter("x"))
    voices = []

    async def fake_pcm(text, voice):
        voices.append(voice)
        return b"\x01\x00" * 2_400  # 0.1 s at 24 kHz

    monkeypatch.setattr(engine, "_tts_pcm", fake_pcm)
    # TTS is mocked above, so ffmpeg is never run; only its presence check is.
    monkeypatch.setattr("app.ai.router.shutil.which", lambda name: f"/usr/bin/{name}")
    audio = run(
        engine.synthesize_speech(
            SpeechRequest(
                segments=[
                    SpeechSegment(voice="female_1", text="Hello"),
                    SpeechSegment(voice="male_1", text="Hi"),
                    SpeechSegment(voice="female_9", text="Bye"),
                ]
            )
        )
    )
    info = inspect_wav(audio.audio, max_bytes=10**7, max_duration_ms=10**6)
    assert info.duration_ms >= 300 and voices[:2] == ["en-GB-SoniaNeural", "en-GB-RyanNeural"]
    assert voices[2] in {
        "en-GB-SoniaNeural",
        "en-AU-NatashaNeural",
    }  # unknown key -> same gender pool


def tiny_wav() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        (
            w.setnchannels(1),
            w.setsampwidth(2),
            w.setframerate(16_000),
            w.writeframes(b"\x00\x00" * 16_000),
        )
    return buffer.getvalue()


def test_transcribe_tries_audio_formats_and_remembers() -> None:
    def reply(payload):
        part = payload["messages"][0]["content"][1]
        if part["type"] == "input_audio":
            return httpx.Response(400, json={"error": "unsupported content"})
        if part["type"] == "file":
            return "I'm sorry, I cannot hear any audio in this message."
        return '"Um, I live in Bandung."'

    router = FakeRouter(reply)
    engine = engine_with(router)
    request = TranscriptionRequest(audio=tiny_wav(), mime_type="audio/wav")
    assert run(engine.transcribe(request)).text == "Um, I live in Bandung."
    assert engine._audio_style == "image_url"
    run(engine.transcribe(request))
    assert router.requests[-1]["messages"][0]["content"][1]["type"] == "image_url"
    assert run(engine_with(FakeRouter("<<NO_SPEECH>>")).transcribe(request)).text == ""


# ---------------------------------------------------------------- speaking
def test_converse_and_speaking_evaluation() -> None:
    router = FakeRouter("**Hi there!** I'm Maya. What do you like to do on weekends?")
    reply = run(
        engine_with(router).converse(
            ConversationRequest(
                persona_name="Maya",
                persona_role="a friendly student",
                behavior_instructions="Be kind.",
                topic="hobbies",
                title="Hobbies chat",
                instructions="Talk about hobbies.",
                cefr_level="A2",
                history=[],
            )
        )
    )
    assert reply.text == "Hi there! I'm Maya. What do you like to do on weekends?"
    assert router.requests[0]["messages"][0]["role"] == "system"

    evaluation_reply = {
        "summary": "Nice chat.",
        "criteria": [
            {
                "code": "fluency_coherence",
                "assessed": True,
                "score": 7,
                "feedback": "claims to know",
            },
            {"code": "lexical_resource", "assessed": True, "score": 6.4, "feedback": "Good words."},
            {
                "code": "grammatical_range_accuracy",
                "assessed": True,
                "score": 5.5,
                "feedback": "Some errors.",
            },
            {"code": "pronunciation", "assessed": False, "score": None, "feedback": "Needs audio."},
        ],
    }
    request = SpeakingEvaluationRequest(
        title="Hobbies",
        instructions="Talk.",
        cefr_level="A2",
        turns=[
            ConversationTurn(sender="assistant", text="Hi!"),
            ConversationTurn(sender="user", text="I like football."),
        ],
        recordings=[],
        criteria=speaking_rubric.CRITERIA,
        score_min=0,
        score_max=9,
        score_step=0.5,
    )
    result = run(engine_with(FakeRouter(evaluation_reply)).evaluate_speaking(request))
    verdict = speaking.validate_evaluation(request, result, audio_assessed=False)
    by_code = {c.code: c for c in result.criteria}
    assert (
        by_code["fluency_coherence"].assessed is False
    )  # transcript-only engine never scores audio criteria
    assert by_code["lexical_resource"].score == 6.5
    assert len(verdict.verdicts) == 4


def test_rate_limit_waits_and_retries(monkeypatch) -> None:
    from app.ai import router as router_module
    from app.ai.contracts import WritingPromptRequest

    waits = []

    async def no_sleep(seconds):
        waits.append(seconds)

    monkeypatch.setattr(router_module.asyncio, "sleep", no_sleep)
    quota = httpx.Response(
        503,
        json={"error": "[gemini] [429]: You exceeded your current quota (reset after 6s)"},
    )
    router = FakeRouter(quota, quota, '{"title": "T", "instructions": "I"}')
    engine = engine_with(router, router_rate_limit_retries=3)
    result = run(
        engine.generate_writing_prompt(
            WritingPromptRequest(
                topic="t", difficulty="beginner", cefr_level="A2", target_word_count=None
            )
        )
    )
    assert result.title == "T" and waits == [7.0, 7.0]

    with pytest.raises(AIError) as error:
        run(
            engine_with(FakeRouter(quota), router_rate_limit_retries=2).generate_writing_prompt(
                WritingPromptRequest(
                    topic="t", difficulty="beginner", cefr_level="A2", target_word_count=None
                )
            )
        )
    assert error.value.code == "AI_RATE_LIMITED" and error.value.retryable
