# Audio transcription

Transcribes audio with `openai/whisper-large-v3` through OpenRouter. It runs in
Docker, so Python and ffmpeg don't need to be installed on your machine.

## Setup

- [Docker](https://docs.docker.com/get-docker/), with the daemon running. Check
  with `docker info`.
- An OpenRouter API key with credit, from <https://openrouter.ai/keys>.

### 1. Clone the repo

```bash
git clone https://github.com/alik-r/meet-transcribe.git
cd meet-transcribe
```

### 2. Add your API key

```bash
echo 'OPENROUTER_API_KEY=sk-or-...' > .env
```

The key has to be in this file. A variable exported in your shell doesn't reach
the container.

### 3. Create the audio folder

```bash
mkdir meet-audio
```

### 4. Build the Docker image

```bash
docker build --tag meet-transcribe .
```

The first build takes a few minutes and produces an image of about 900 MB. You
can skip this step, because `transcribe.sh` builds the image on every run. That
is near-instant unless `Dockerfile` or `requirements.txt` has changed.

## Usage

### 1. Add a recording

Put the file in `meet-audio/`. It can have any name and length, in any format
ffmpeg can read. For a video file, only the audio is used.

```bash
cp ~/Downloads/standup.m4a meet-audio/
```

The file must be inside the project folder, because the container can't see
anything else. A path like `~/Downloads/standup.m4a` fails with "Audio file not
found".

### 2. Transcribe it

Run this from the project root:

```bash
./transcribe.sh meet-audio/standup.m4a
```

Progress is printed as each chunk finishes, and the last line gives the
transcript's location:

```text
Transcribing standup.m4a (12.3 min)...
  Chunk 1/3 done
  Chunk 2/3 done
  Chunk 3/3 done

Transcript: /path/to/meet-transcribe/transcripts/standup.txt
```

If `standup.txt` already exists, the new transcript is saved as `standup_2.txt`,
so nothing is overwritten. The audio file stays where it is.

### Choose a language

The language defaults to Russian. For anything else, pass an ISO-639-1 code:

```bash
./transcribe.sh meet-audio/standup.m4a --language en
```

Each run takes one language and one file. To see all options, run
`./transcribe.sh --help`.

### Resume a failed run

If a run fails, no transcript is written, but finished chunks are kept in
`.transcribe-cache/`. Run the same command again to continue from where it
stopped. Changing `--language` or the audio file starts from the beginning.

### Run without the script

`transcribe.sh` wraps these two commands, which you can also run yourself from
the project root:

```bash
docker build --tag meet-transcribe .

docker run --rm --init \
    --user "$(id -u):$(id -g)" \
    --volume "$PWD:$PWD" \
    --workdir "$PWD" \
    meet-transcribe python transcribe.py meet-audio/standup.m4a --language en
```

The `--user` option keeps the output files owned by you. The `--volume` option
mounts the project at the same path, so the paths the script prints are also
valid on your machine.

The image contains only Python, ffmpeg and the dependencies. The code, `.env`
and audio come from the mounted folder at run time, so you don't need to rebuild
after editing `transcribe.py`.

To remove the image, run `docker image rm meet-transcribe`.

## Troubleshooting

| Message | What to do |
| --- | --- |
| `Audio file not found` | Move the file into `meet-audio/`, and run from the project root with a relative path. |
| `OPENROUTER_API_KEY is not set` | Create `.env` in the project root, as in [step 2](#2-add-your-api-key). |
| `OpenRouter rejected the API key` | Check the key in `.env`, then run the same command again. |
| `ffmpeg could not read ...` | The file is damaged or isn't audio. Check that it plays. |
| `Transcription request failed` | Read the error that follows it, such as no credit or a network problem, then run the same command again to resume. |
| `permission denied` on the Docker socket | Run `sudo usermod -aG docker $USER`, then log out and back in. |
| `Cannot connect to the Docker daemon` | Start Docker Desktop, or the Docker service. |

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
