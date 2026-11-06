# Audio transcription

Transcribes audio with `openai/whisper-large-v3` through OpenRouter.

## Setup

Requires Docker. The image is built automatically on first run, which takes a
few minutes, and it includes Python, ffmpeg and the dependencies.

```bash
mkdir meet-audio
echo 'OPENROUTER_API_KEY=sk-or-...' > .env
```

## Usage

1. Put an audio file in `meet-audio/`, under any name and at any length.
2. From the project root, run `./transcribe.sh meet-audio/<name>.m4a`.

The audio must be inside the project folder, because the container can't see
anything else. A path like `~/Downloads/<name>.m4a` fails with "Audio file not
found", so move the file into `meet-audio/` first and use a relative path.

The script prints where the transcript went: `transcripts/<name>.txt`. If that
name is taken, it adds a suffix such as `<name>_2.txt`, so nothing is overwritten.
The audio file stays where it is.

The language defaults to Russian. For anything else, pass an ISO-639-1 code:

```bash
./transcribe.sh meet-audio/<name>.m4a --language en
```

If a run fails, no transcript is written, but finished chunks are kept in
`.transcribe-cache/`. Run the same command again to resume from where it stopped.

## Notes

- Long recordings are split into chunks of up to 5 minutes, at pauses where
  possible, and sent 4 at a time.
- Audio, transcripts and the chunk cache are gitignored, so they stay on this
  machine. That covers `meet-audio/`, `transcripts/`, `.transcribe-cache/`, and
  audio anywhere else in the project.

## Privacy

Recordings are uploaded to OpenRouter, which can route them to DeepInfra, Together
or Groq. Review your OpenRouter privacy settings and these providers' data
policies before transcribing sensitive audio.
