"""Listening and private media rules that need no database."""

import asyncio
import io
import os
import time
import wave

import pytest
from pydantic import ValidationError

from app.ai.contracts import ListeningRequest, ScriptLine, SpeechRequest, SpeechSegment
from app.ai.engine import AIError
from app.ai.fake import FakeAIEngine
from app.core.errors import ApiError
from app.modules.listening import service as listening
from app.modules.listening.schemas import CreateListeningExerciseRequest
from app.modules.media.audio import InvalidAudio, inspect_wav
from app.modules.media.service import parse_range
from app.modules.media.storage import MediaStore

LIMITS = {"max_bytes": 1_000_000, "max_duration_ms": 60_000}


def wav(seconds: float = 1.0, rate: int = 8_000, width: int = 1, channels: int = 1) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(channels)
        writer.setsampwidth(width)
        writer.setframerate(rate)
        writer.writeframes(b"\x80" * int(rate * seconds) * width * channels)
    return buffer.getvalue()


# --- Audio validation ---------------------------------------------------------------------


def test_valid_wav_reports_real_size_and_duration() -> None:
    data = wav(2.5)
    info = inspect_wav(data, **LIMITS)
    assert (info.mime_type, info.size_bytes, info.duration_ms) == ("audio/wav", len(data), 2500)


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"ID3" + b"\x00" * 100,  # an MP3 claiming nothing; signature decides
        b"RIFF" + b"\x00" * 4 + b"AVI " + b"\x00" * 100,
        wav(1.0)[:-500],  # truncated frames
        wav(0.0),  # no frames
        wav(1.0, rate=4_000),  # unsupported rate
    ],
)
def test_invalid_audio_is_rejected(data: bytes) -> None:
    with pytest.raises(InvalidAudio):
        inspect_wav(data, **LIMITS)


def test_audio_bounds() -> None:
    with pytest.raises(InvalidAudio):
        inspect_wav(wav(2.0), max_bytes=1_000, max_duration_ms=60_000)
    with pytest.raises(InvalidAudio):
        inspect_wav(wav(2.0), max_bytes=1_000_000, max_duration_ms=1_000)


def test_fake_tts_produces_decodable_audio_proportional_to_text() -> None:
    engine = FakeAIEngine()
    short = asyncio.run(
        engine.synthesize_speech(
            SpeechRequest(segments=[SpeechSegment(voice="female_1", text="Hi")])
        )
    )
    long = asyncio.run(
        engine.synthesize_speech(
            SpeechRequest(segments=[SpeechSegment(voice="male_1", text="word " * 50)])
        )
    )
    assert (
        inspect_wav(short.audio, **LIMITS).duration_ms
        < inspect_wav(long.audio, **LIMITS).duration_ms
    )


# --- Private storage -------------------------------------------------------------------------


def test_store_generates_keys_and_refuses_paths_outside_root(tmp_path) -> None:
    store = MediaStore(tmp_path)
    key = store.new_key("listening_audio", "wav")
    store.write(key, b"abc")
    assert store.size(key) == 3
    assert b"".join(store.read_range(key, 1, 2)) == b"bc"
    for bad in ("../etc/passwd", "listening_audio/../../x.wav", "/abs/path.wav", "a/b/c.wav"):
        with pytest.raises(ValueError):
            store.path(bad)
    store.delete(key)
    store.delete(key)  # idempotent
    assert store.size(key) is None
    assert [p.name for p in tmp_path.rglob("*") if p.is_file()] == []  # no temp files left


def test_stale_files_lists_only_old_files(tmp_path) -> None:
    store = MediaStore(tmp_path)
    old_key, new_key = (
        store.new_key("listening_audio", "wav"),
        store.new_key("listening_audio", "wav"),
    )
    store.write(old_key, b"1")
    store.write(new_key, b"2")
    temp = tmp_path / "listening_audio" / ".tmp-leftover"
    temp.write_bytes(b"3")
    past = time.time() - 7_200
    for path in (store.path(old_key), temp):
        os.utime(path, (past, past))
    stale = store.stale_files(3_600)
    assert {(key, path.name) for key, path in stale} == {
        (old_key, store.path(old_key).name),
        (None, temp.name),
    }


# --- Byte ranges ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (None, None),
        ("bytes=0-99", (0, 99)),
        ("bytes=100-", (100, 999)),
        ("bytes=-100", (900, 999)),
        ("bytes=-5000", (0, 999)),
        ("bytes=990-5000", (990, 999)),
    ],
)
def test_single_ranges(header, expected) -> None:
    assert parse_range(header, 1_000) == expected


@pytest.mark.parametrize(
    "header",
    ["bytes=1000-", "bytes=5-1", "bytes=-0", "bytes=-", "bytes=0-1,5-9", "items=0-1", "0-1"],
)
def test_unsatisfiable_ranges(header) -> None:
    with pytest.raises(ApiError) as error:
        parse_range(header, 1_000)
    assert error.value.status_code == 416
    assert error.value.code == "RANGE_NOT_SATISFIABLE"


# --- Requests and generated scripts --------------------------------------------------------


def test_plan_rejects_oversized_requests(settings) -> None:
    with pytest.raises(ApiError) as error:
        listening.plan(
            settings, CreateListeningExerciseRequest(difficulty="beginner", question_count=11)
        )
    assert error.value.status_code == 413
    types, target = listening.plan(
        settings,
        CreateListeningExerciseRequest(
            difficulty="beginner",
            question_count=5,
            question_types=["multiple_choice", "short_answer"],
        ),
    )
    assert types == ["multiple_choice", "short_answer"] * 2 + ["multiple_choice"]
    assert target == 100  # 5 questions x 20 words beats the beginner default of 80


def test_request_rejects_repeated_types() -> None:
    with pytest.raises(ValidationError):
        CreateListeningExerciseRequest(
            difficulty="beginner", question_types=["short_answer", "short_answer"]
        )


def _input(types=("multiple_choice", "short_answer")) -> listening.GenerationInput:
    return listening.GenerationInput(
        exercise_id=None,
        owner_id=None,
        topic_id=None,
        tolerance=0.4,
        max_audio_bytes=LIMITS["max_bytes"],
        max_audio_duration_ms=LIMITS["max_duration_ms"],
        request=ListeningRequest(
            topic="Sekolah",
            difficulty="intermediate",
            cefr_level="B1",
            target_word_count=120,
            question_types=list(types),
            voices=["female_1", "male_1"],
        ),
    )


def _package(data):
    return asyncio.run(FakeAIEngine().generate_listening(data.request))


def test_valid_script_gets_transcript_spans() -> None:
    data = _input()
    transcript, evidence = listening.validate_package(data, _package(data))
    assert transcript.startswith("Nadia: ")
    for spans in evidence:
        for span in spans:
            assert transcript[span["start"] : span["end"]] == span["original"]


def _line(**changes) -> ScriptLine:
    return ScriptLine(
        **{"speaker": "Nadia", "voice": "female_1", "text": "Hello there.", **changes}
    )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: {"lines": [*p.lines, _line(voice="robot_9")]},  # voice not offered
        lambda p: {"lines": [*p.lines, _line(voice="male_1")]},  # same speaker, new voice
        lambda p: {"lines": [*p.lines, _line(speaker="Raka: hi")]},  # label injection
        lambda p: {"lines": [*p.lines, _line(text="one\nNadia: two")]},  # fake extra line
        lambda p: {"lines": p.lines[:2]},  # far too short
        lambda p: {"questions": p.questions[::-1]},  # types out of order
        lambda p: {
            "questions": [
                p.questions[0].model_copy(update={"evidence_quotes": ["Never said this."]}),
                *p.questions[1:],
            ]
        },
        lambda p: {
            "lines": [*p.lines] + [_line(speaker=f"Extra {n}", voice="female_1") for n in range(4)]
        },  # too many speakers
    ],
)
def test_invalid_scripts_are_rejected(mutate) -> None:
    data = _input()
    package = _package(data)
    with pytest.raises(AIError) as error:
        listening.validate_package(data, package.model_copy(update=mutate(package)))
    assert error.value.code == "AI_OUTPUT_INVALID"
