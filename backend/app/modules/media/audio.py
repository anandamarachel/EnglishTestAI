"""Audio validation from the actual bytes, never from a file name or claimed MIME type."""

import io
import wave
from dataclasses import dataclass


class InvalidAudio(ValueError):
    pass


@dataclass(frozen=True)
class AudioInfo:
    mime_type: str
    extension: str
    size_bytes: int
    duration_ms: int


def inspect_wav(data: bytes, *, max_bytes: int, max_duration_ms: int) -> AudioInfo:
    """PCM WAV only for now: signature, header and every frame must decode."""
    if len(data) > max_bytes:
        raise InvalidAudio("too large")
    if len(data) < 44 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise InvalidAudio("not a WAV file")
    try:
        with wave.open(io.BytesIO(data), "rb") as reader:
            channels = reader.getnchannels()
            width = reader.getsampwidth()
            rate = reader.getframerate()
            frames = reader.getnframes()
            if not (1 <= channels <= 2 and 1 <= width <= 3 and 8_000 <= rate <= 48_000):
                raise InvalidAudio("unsupported format")
            if frames <= 0:
                raise InvalidAudio("empty audio")
            decoded = reader.readframes(frames)
    except (wave.Error, EOFError) as error:
        raise InvalidAudio("undecodable") from error
    if len(decoded) != frames * channels * width:
        raise InvalidAudio("truncated audio")
    duration_ms = frames * 1000 // rate
    if duration_ms > max_duration_ms:
        raise InvalidAudio("too long")
    return AudioInfo("audio/wav", "wav", len(data), duration_ms)
