#!/usr/bin/env python3
"""Transcribe one audio file into transcripts/. The audio is left in place."""

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dotenv import load_dotenv
from openai import AuthenticationError, OpenAI, OpenAIError

BASE_URL = "https://openrouter.ai/api/v1"
API_KEY_VAR = "OPENROUTER_API_KEY"
MODEL = "openai/whisper-large-v3"
DEFAULT_LANGUAGE = "ru"

# OpenRouter allows 25 MB and about 60 s of processing per request. Five minutes
# of 16 kHz mono WAV is under 10 MB. Cuts land on a pause in the last minute of
# each chunk so words aren't split, falling back to a hard cut if there is none.
MAX_CHUNK_SECONDS = 300
MIN_CHUNK_SECONDS = 240
SILENCE_FILTER = "silencedetect=noise=-30dB:d=0.4"
PARALLEL_REQUESTS = 4

ROOT = Path(__file__).resolve().parent
TRANSCRIPT_DIR = ROOT / "transcripts"
CACHE_DIR = ROOT / ".transcribe-cache"


def free_transcript_path(audio: Path) -> Path:
    """Pick a transcript path that overwrites nothing."""
    path = TRANSCRIPT_DIR / f"{audio.stem}.txt"
    n = 1
    while path.exists():
        n += 1
        path = TRANSCRIPT_DIR / f"{audio.stem}_{n}.txt"
    return path


def duration_seconds(audio: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(audio)],
        check=True, capture_output=True, text=True,
    )
    return float(result.stdout.strip())


def find_pauses(audio: Path) -> list[float]:
    """Return the midpoint of each silent stretch, in seconds."""
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(audio), "-vn",
         "-af", SILENCE_FILTER, "-f", "null", "-"],
        check=True, capture_output=True, text=True,
    )
    starts = re.findall(r"silence_start: ([\d.]+)", result.stderr)
    ends = re.findall(r"silence_end: ([\d.]+)", result.stderr)
    return [(float(s) + float(e)) / 2 for s, e in zip(starts, ends)]


def choose_cuts(duration: float, pauses: list[float]) -> list[float]:
    cuts = []
    position = 0.0
    while duration - position > MAX_CHUNK_SECONDS:
        earliest = position + MIN_CHUNK_SECONDS
        latest = position + MAX_CHUNK_SECONDS
        candidates = [p for p in pauses if earliest <= p <= latest]
        position = candidates[-1] if candidates else latest
        cuts.append(position)
    return cuts


def split_into_chunks(audio: Path, cuts: list[float], chunk_dir: Path) -> list[Path]:
    command = ["ffmpeg", "-loglevel", "error", "-i", str(audio), "-vn",
               "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le"]
    if cuts:
        command += ["-f", "segment", "-segment_times",
                    ",".join(f"{c:.3f}" for c in cuts),
                    str(chunk_dir / "chunk_%04d.wav")]
    else:
        command.append(str(chunk_dir / "chunk_0000.wav"))
    subprocess.run(command, check=True)
    return sorted(chunk_dir.glob("chunk_*.wav"))


def chunk_cache_dir(audio: Path, language: str, cuts: list[float]) -> Path:
    """Name a folder for finished chunks, unique to this audio and these settings."""
    with audio.open("rb") as f:
        digest = hashlib.file_digest(f, "sha256")
    digest.update(f"{MODEL}|{language}|{cuts}".encode())
    return CACHE_DIR / f"{audio.stem}-{digest.hexdigest()[:16]}"


def transcribe(client: OpenAI, audio: Path, language: str) -> tuple[str, Path]:
    """Return the transcript and the cache folder to delete once it is saved."""
    duration = duration_seconds(audio)
    print(f"Transcribing {audio.name} ({duration / 60:.1f} min)...", flush=True)

    cuts = choose_cuts(duration, find_pauses(audio))
    cache_dir = chunk_cache_dir(audio, language, cuts)
    cache_dir.mkdir(parents=True, exist_ok=True)

    def transcribe_chunk(chunk: Path) -> str:
        cached = cache_dir / f"{chunk.stem}.txt"
        if cached.exists():
            return cached.read_text(encoding="utf-8")
        result = client.audio.transcriptions.create(
            model=MODEL, file=chunk, language=language,
        )
        text = result.text.strip()
        # Rename into place so an interrupted write can't pass as a finished chunk.
        partial = cached.with_suffix(".partial")
        partial.write_text(text, encoding="utf-8")
        partial.replace(cached)
        return text

    with tempfile.TemporaryDirectory() as tmp:
        chunks = split_into_chunks(audio, cuts, Path(tmp))
        resumed = len(list(cache_dir.glob("chunk_*.txt")))
        if resumed:
            print(f"  Resuming: {resumed}/{len(chunks)} chunks already done", flush=True)

        parts = []
        with ThreadPoolExecutor(PARALLEL_REQUESTS) as pool:
            for i, text in enumerate(pool.map(transcribe_chunk, chunks), 1):
                print(f"  Chunk {i}/{len(chunks)} done", flush=True)
                parts.append(text)

    return "\n\n".join(part for part in parts if part), cache_dir


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio", type=Path, help="audio file, e.g. meet-audio/standup.m4a")
    parser.add_argument(
        "--language", default=DEFAULT_LANGUAGE,
        help="ISO-639-1 language code of the speech, e.g. en (default: %(default)s)",
    )
    args = parser.parse_args()
    audio = args.audio.resolve()

    if not audio.is_file():
        print(f"Audio file not found: {audio}")
        return 1

    missing_tools = [tool for tool in ("ffmpeg", "ffprobe") if not shutil.which(tool)]
    if missing_tools:
        print(f"Missing {' and '.join(missing_tools)}. Install ffmpeg and try again.")
        return 1

    load_dotenv(ROOT / ".env")
    api_key = os.environ.get(API_KEY_VAR)
    if not api_key:
        print(f"{API_KEY_VAR} is not set. Add it to {ROOT / '.env'} (get a key at https://openrouter.ai/keys)")
        return 1

    client = OpenAI(base_url=BASE_URL, api_key=api_key, timeout=180, max_retries=5)
    retry_hint = "Finished chunks are saved. Run the same command again to resume."
    try:
        text, cache_dir = transcribe(client, audio, args.language)
    except subprocess.CalledProcessError:
        print(f"ffmpeg could not read {audio}. Is it a valid audio file?")
        return 1
    except AuthenticationError:
        print(f"OpenRouter rejected the API key. Check {API_KEY_VAR} in {ROOT / '.env'}.")
        print(retry_hint)
        return 1
    except OpenAIError as error:
        print(f"Transcription request failed: {error}")
        print(retry_hint)
        return 1

    TRANSCRIPT_DIR.mkdir(exist_ok=True)
    transcript = free_transcript_path(audio)
    transcript.write_text(text + "\n", encoding="utf-8")
    shutil.rmtree(cache_dir)

    print(f"\nTranscript: {transcript}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
