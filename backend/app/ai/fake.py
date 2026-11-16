"""Deterministic stand-in engine for development and tests. Never used in production.

It lets the app and the Flutter client exercise complete flows before a model is
chosen. Its feedback comes from a few fixed rules and is labelled as illustrative.
"""

import io
import math
import re
import wave

from app.ai.contracts import (
    CorrectionResult,
    CriterionScore,
    WritingEvaluation,
    WritingEvaluationRequest,
    WritingPrompt,
    WritingPromptRequest,
)
from app.ai.engine import AIError

PAST = {"go": "went", "eat": "ate", "see": "saw", "come": "came", "buy": "bought"}
RULES = [
    # (pattern, group, replacement function, category, title, explanation, example)
    (
        re.compile(r"\b(i)\b"),
        1,
        lambda _: "I",
        "spelling",
        "Capital I",
        "The pronoun 'I' is always written as a capital letter.",
        "My friend and I went home.",
    ),
    (
        re.compile(r"\b(?:we|you|they)\s+(was)\b", re.IGNORECASE),
        1,
        lambda _: "were",
        "grammar",
        "Subject-verb agreement",
        "Use 'were' with we, you and they.",
        "We were late for class.",
    ),
    (
        re.compile(
            r"\b(?:yesterday|last \w+)\b[^.!?]*?\b(I|we|you|they|he|she)\s+(go|eat|see|come|buy)\b",
            re.IGNORECASE,
        ),
        2,
        lambda word: PAST[word.lower()],
        "grammar",
        "Past tense",
        "Words like 'yesterday' show the past, so the verb should be in the past tense.",
        "Last week, she went to the library.",
    ),
    (
        re.compile(r"\b(\w+)(\s+\1)\b", re.IGNORECASE),
        2,
        lambda _: "",
        "style",
        "Repeated word",
        "The same word appears twice in a row.",
        "This is the best day.",
    ),
]


def _clamp(value: float, request: WritingEvaluationRequest) -> float:
    stepped = round(value / request.score_step) * request.score_step
    return max(request.score_min, min(request.score_max, stepped))


def _find_corrections(text: str) -> list[CorrectionResult]:
    found: list[CorrectionResult] = []
    for pattern, group, replace, category, title, explanation, example in RULES:
        for match in pattern.finditer(text):
            start, end = match.span(group)
            found.append(
                CorrectionResult(
                    start=start,
                    end=end,
                    original=text[start:end],
                    replacement=replace(match.group(group)),
                    category=category,
                    title=title,
                    explanation=explanation,
                    example=example,
                )
            )
    found.sort(key=lambda c: (c.start, c.end))
    kept: list[CorrectionResult] = []
    for correction in found:
        if not kept or correction.start >= kept[-1].end:
            kept.append(correction)
    return kept


def _apply(text: str, corrections: list[CorrectionResult]) -> str:
    for correction in reversed(corrections):
        text = text[: correction.start] + correction.replacement + text[correction.end :]
    return text


# --- Reading (development stand-in) ----------------------------------------------------

FACTS = [
    (
        "Daeng",
        "brought a blue kite to the festival",
        "What did Daeng bring to the festival?",
        "A blue kite",
        ["A red ball", "A new book", "A small radio"],
    ),
    (
        "Rina",
        "met her friends near the old market",
        "Where did Rina meet her friends?",
        "Near the old market",
        ["At the beach", "In the library", "At the bus station"],
    ),
    (
        "Andi",
        "bought a chicken sandwich for lunch",
        "What did Andi buy for lunch?",
        "A chicken sandwich",
        ["A bowl of noodles", "Fried rice", "A bottle of water"],
    ),
    (
        "Mira",
        "helped her teacher clean the classroom",
        "Who did Mira help?",
        "Her teacher",
        ["Her brother", "The shopkeeper", "Her neighbour"],
    ),
    (
        "Budi",
        "took the morning bus to school",
        "How did Budi go to school?",
        "By the morning bus",
        ["On foot", "By bicycle", "In his father's car"],
    ),
    (
        "Sari",
        "wrote a letter to her grandmother",
        "Who did Sari write a letter to?",
        "Her grandmother",
        ["Her teacher", "Her best friend", "Her cousin"],
    ),
]
VOCABULARY = [
    ("gathered", "came together in one place", "Many people gathered in the park."),
    ("curious", "wanting to know or learn something", "The curious cat looked inside the box."),
    ("delicious", "tasting very good", "The soup was delicious."),
    ("journey", "a trip from one place to another", "The journey took two hours."),
    ("grateful", "feeling thankful", "She was grateful for the help."),
    ("bright", "full of light", "The room was bright and warm."),
]
FILLERS = [
    "Everyone gathered to talk about {topic}.",
    "The children were curious and asked many questions.",
    "Later they shared some delicious food together.",
    "For some of them it was a long journey from home.",
    "They felt grateful for a happy day.",
    "The sky was bright over the town.",
]
STOPWORDS = {"the", "a", "an", "to", "of", "in", "on", "at", "by", "her", "his", "for"}


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z']+", text.lower()) if w not in STOPWORDS}


async def _generate_reading(self, request):
    from app.ai.contracts import GeneratedQuestion, GeneratedVocabulary, ReadingPackage

    self._maybe_fail()
    sentences, questions = [f"This is a short story about {request.topic}."], []
    for index, kind in enumerate(request.question_types):
        name, action, question, answer, distractors = FACTS[index % len(FACTS)]
        fact = f"{name} {action}."
        sentences.append(fact)
        if kind == "multiple_choice":
            correct = index % 4
            options = distractors[:correct] + [answer] + distractors[correct:]
            questions.append(
                GeneratedQuestion(
                    question_type=kind,
                    question_text=question,
                    options=options,
                    correct_option=correct,
                    explanation=f"The story says: {fact}",
                    evidence_quotes=[fact],
                )
            )
        else:
            questions.append(
                GeneratedQuestion(
                    question_type=kind,
                    question_text=question,
                    reference_answer=answer,
                    explanation=f"The story says: {fact}",
                    evidence_quotes=[fact],
                )
            )
    filler = 0
    while filler < len(FILLERS) or len(" ".join(sentences).split()) < request.target_word_count:
        sentences.append(FILLERS[filler % len(FILLERS)].format(topic=request.topic))
        filler += 1
    paragraphs = [" ".join(sentences[i : i + 4]) for i in range(0, len(sentences), 4)]
    return ReadingPackage(
        title=f"A day of {request.topic}"[:200],
        instructions="Read the story, then answer the questions.",
        passage="\n\n".join(paragraphs),
        questions=questions,
        vocabulary=[
            GeneratedVocabulary(word_or_phrase=w, meaning=m, example_sentence=e)
            for w, m, e in VOCABULARY[: request.vocabulary_count]
        ],
    )


async def _grade_short_answer(self, request):
    from app.ai.contracts import ShortAnswerGrade

    self._maybe_fail()
    expected = _words(request.reference_answer)
    overlap = len(expected & _words(request.response_text)) / max(1, len(expected))
    if overlap >= 0.8:
        points, note = request.max_points, "Your answer matches the key idea."
    elif overlap >= 0.4:
        points, note = request.max_points / 2, "Your answer is partly correct."
    else:
        points, note = 0.0, "Your answer does not match the story."
    points = round(points / request.point_step) * request.point_step
    return ShortAnswerGrade(awarded_points=points, feedback=f"{note} (development engine)")


# --- Listening and speech (development stand-in) ----------------------------------------

SPEAKERS = ["Nadia", "Raka"]
SMALL_TALK = [
    "That sounds fun. I want to hear more about {topic}.",
    "We talked about it with our friends after school.",
    "Everyone had a different idea, and that made it interesting.",
    "I think we should plan something together next week.",
    "Good idea. Let's ask the others tomorrow morning.",
    "Sure. See you at school then.",
]
FAKE_SAMPLE_RATE = 8_000


async def _generate_listening(self, request):
    from app.ai.contracts import GeneratedQuestion, ListeningPackage, ScriptLine

    self._maybe_fail()
    lines, questions = [], []

    def say(text: str) -> None:
        turn = len(lines) % 2
        lines.append(
            ScriptLine(
                speaker=SPEAKERS[turn], voice=request.voices[turn % len(request.voices)], text=text
            )
        )

    say(f"Hi! Do you have a minute to talk about {request.topic}?")
    for index, kind in enumerate(request.question_types):
        name, action, question, answer, distractors = FACTS[index % len(FACTS)]
        fact = f"{name} {action}."
        say(f"Did you hear the news? {fact}")
        common = {
            "question_type": kind,
            "question_text": question,
            "explanation": f"One speaker says: {fact}",
            "evidence_quotes": [fact],
        }
        if kind == "multiple_choice":
            correct = index % 4
            options = distractors[:correct] + [answer] + distractors[correct:]
            questions.append(GeneratedQuestion(**common, options=options, correct_option=correct))
        else:
            questions.append(GeneratedQuestion(**common, reference_answer=answer))
    filler = 0
    while sum(len(line.text.split()) for line in lines) < request.target_word_count:
        say(SMALL_TALK[filler % len(SMALL_TALK)].format(topic=request.topic))
        filler += 1
    return ListeningPackage(
        title=f"A conversation about {request.topic}"[:200],
        instructions="Listen to the conversation, then answer the questions.",
        lines=lines,
        questions=questions,
    )


async def _synthesize_speech(self, request):
    """Real, decodable WAV: a short beep per line, then silence as long as the line."""
    from app.ai.contracts import SpeechAudio

    self._maybe_fail()
    frames = bytearray()
    for segment in request.segments:
        pitch = 440 + 110 * (sum(map(ord, segment.voice)) % 4)
        for n in range(FAKE_SAMPLE_RATE * 12 // 100):  # 120 ms beep
            frames.append(128 + int(24 * math.sin(2 * math.pi * pitch * n / FAKE_SAMPLE_RATE)))
        seconds = max(0.5, len(segment.text.split()) / 2.5)  # about 150 words per minute
        frames.extend(b"\x80" * int(FAKE_SAMPLE_RATE * seconds))
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(1)
        writer.setframerate(FAKE_SAMPLE_RATE)
        writer.writeframes(bytes(frames))
    return SpeechAudio(audio=buffer.getvalue())


# --- Speaking (development stand-in) -----------------------------------------------------

FOLLOW_UPS = [
    "That's interesting. Can you tell me a bit more about it?",
    "Why do you think so?",
    "What happened after that?",
    "How did you feel about it?",
    "Would you like to do it again? Why or why not?",
]


async def _generate_speaking_prompt(self, request):
    from app.ai.contracts import SpeakingPrompt

    self._maybe_fail()
    return SpeakingPrompt(
        title=f"Talk about {request.topic} with {request.persona_name}"[:200],
        instructions=(
            f"Have a short conversation with {request.persona_name} about {request.topic}. "
            "Answer in full sentences and give examples from your own life."
        ),
    )


async def _converse(self, request):
    from app.ai.contracts import ConversationReply

    self._maybe_fail()
    user_turns = sum(turn.sender == "user" for turn in request.history)
    if user_turns == 0:
        text = (
            f"Hi, I'm {request.persona_name}. Let's talk about {request.topic}. "
            "What do you think about it?"
        )
    else:
        text = FOLLOW_UPS[(user_turns - 1) % len(FOLLOW_UPS)]
    return ConversationReply(text=text)


async def _transcribe(self, request):
    """Cannot recognise speech: returns a labelled placeholder sized by the recording."""
    from app.ai.contracts import Transcription

    self._maybe_fail()
    with wave.open(io.BytesIO(request.audio), "rb") as reader:
        seconds = reader.getnframes() / reader.getframerate()
    if seconds < 0.3:
        return Transcription(text="")
    words = " ".join(["practice"] * max(1, int(seconds * 2)))
    return Transcription(text=f"Development transcript: I talked for a while. {words}.")


async def _evaluate_speaking(self, request):
    from app.ai.contracts import SpeakingCriterionResult, SpeakingEvaluation

    self._maybe_fail()
    words = sum(len(t.text.split()) for t in request.turns if t.sender == "user")
    band = min(request.score_max, 4.0 + min(3.0, words / 40))
    band = round(band / request.score_step) * request.score_step
    results = []
    for criterion in request.criteria:
        if criterion.requires_audio:
            results.append(
                SpeakingCriterionResult(
                    code=criterion.code,
                    assessed=False,
                    feedback="Needs an audio assessor; not judged from the transcript.",
                )
            )
        else:
            results.append(
                SpeakingCriterionResult(
                    code=criterion.code,
                    assessed=True,
                    score=band,
                    feedback=f"{criterion.name}: illustrative development-engine feedback.",
                )
            )
    return SpeakingEvaluation(
        summary=f"Development engine check of {words} spoken words.", criteria=results
    )


class FakeAIEngine:
    name = "fake-engine-v1"
    is_fake = True
    assesses_audio = False

    def __init__(self, fail_with: AIError | None = None, fail_times: int = 0) -> None:
        self.fail_with = fail_with
        self.fail_times = fail_times
        self.calls = 0

    def _maybe_fail(self) -> None:
        self.calls += 1
        if self.fail_with is not None and self.calls <= self.fail_times:
            raise self.fail_with

    async def generate_writing_prompt(self, request: WritingPromptRequest) -> WritingPrompt:
        self._maybe_fail()
        length = (
            f"about {request.target_word_count} words"
            if request.target_word_count
            else ("a short paragraph")
        )
        return WritingPrompt(
            title=f"Writing about {request.topic}"[:200],
            instructions=(
                f"Write {length} in English about {request.topic}. "
                "Describe a personal experience, explain why it matters to you, "
                "and give at least one example."
            ),
        )

    generate_reading = _generate_reading
    grade_short_answer = _grade_short_answer
    generate_listening = _generate_listening
    synthesize_speech = _synthesize_speech
    generate_speaking_prompt = _generate_speaking_prompt
    converse = _converse
    transcribe = _transcribe
    evaluate_speaking = _evaluate_speaking

    async def evaluate_writing(self, request: WritingEvaluationRequest) -> WritingEvaluation:
        self._maybe_fail()
        text = request.response_text
        corrections = _find_corrections(text)
        corrected = _apply(text, corrections)
        words = len(text.split())
        base = 5.0 + min(2.0, words / 100) - 0.5 * min(4, len(corrections))
        offsets = {0: 0.0, 1: 0.5, 2: -0.5, 3: 0.0}
        criteria = [
            CriterionScore(
                code=criterion.code,
                score=_clamp(base + offsets.get(index % 4, 0.0), request),
                feedback=f"{criterion.name}: illustrative feedback from the development engine.",
            )
            for index, criterion in enumerate(request.criteria)
        ]
        found = f"{len(corrections)} point(s) to improve" if corrections else "no rule-based issues"
        return WritingEvaluation(
            summary=f"Development engine check: {found} in {words} words.",
            corrected_text=corrected,
            criteria=criteria,
            corrections=corrections,
        )
