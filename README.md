# Portkey AI Gateway Tester

A command-line tool to smoke-test models through the [Portkey AI gateway](https://portkey.ai/docs/api-reference/inference-api/introduction). It walks you through API key entry, endpoint selection, and model slugs, then reports pass/fail with response times and useful details.

## Features

- Test **chat**, **embeddings**, **TTS**, **STT**, and **video** generation
- Optional Portkey **config ID** for virtual keys / routing
- **Auto-detect** endpoint from the model slug (video must be selected explicitly)
- Automatic **fallback** across endpoints when auto-detect is wrong
- Rich terminal UI: spinners, tables, success/error panels
- Video: create → poll → download via Portkey into a local `video/` folder

## Installation

### Quick setup (recommended)

```bash
source ./install.sh
```

Creates a venv, installs dependencies, and activates the environment. Or run `./install.sh` without `source` to set up without activating.

### Manual setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Usage

```bash
python test_portkey.py
```

### Prompts (in order)

| Step | Prompt | Notes |
|------|--------|--------|
| 1 | Portkey API key | Required (`x-portkey-api-key`) |
| 2 | Config ID | Optional — press Enter to skip (recommended for video routing) |
| 3 | Endpoint type | See menu below |
| 4 | Video prompt | **Video only** — Enter = default meme prompt, or type your own |
| 5 | Model slugs | Comma-separated (video: use a known route slug, e.g. `veo`) |

### Endpoint menu

```
1. Chat Completions (default)
2. Embeddings
3. Text-to-Speech (TTS)
4. Speech-to-Text (STT)
5. Video
6. Auto-detect based on slug
```

| Choice | What it does |
|--------|----------------|
| **Chat** | Short chat completion (“Say Hello…”) |
| **Embeddings** | Embedding request + raw HTTP diagnostics |
| **TTS** | Speech synthesis; checks that audio bytes are returned |
| **STT** | Transcription of a generated silent WAV |
| **Video** | Async create + poll + download through Portkey (see below) |
| **Auto-detect** | Picks an endpoint from the slug; falls back if the first choice fails |

### Auto-detect rules

| Slug contains | Endpoint tried first |
|---------------|----------------------|
| `embed` | Embeddings |
| `tts` | Text-to-Speech |
| `whisper` | Speech-to-Text |
| *(anything else)* | Chat |

**Video is never auto-detected** — choose menu option `5`.

Examples: `cohere-embed-v3` → embeddings · `tts-1` → TTS · `whisper-1` → STT · `mistral-large` → chat.

## Endpoint details

### Chat Completions

Sends a small chat request. Retries with `max_completion_tokens` if the provider rejects `max_tokens`. Results show response preview and token usage when available.

### Embeddings

Calls `/embeddings` and prints dimension size. Also runs a raw HTTP probe for debugging gateway responses.

### Text-to-Speech (TTS)

Calls the speech API with a fixed sample phrase and reports audio byte size on success.

### Speech-to-Text (STT)

Generates a short silent WAV, sends it to transcriptions, and shows the returned text.

### Video

Flow (config chooses the upstream provider — no `x-portkey-provider` header):

1. `POST https://api.portkey.ai/v1/videos` — create job with `model` + `x-portkey-metadata: {"video_route":"<route>"}`
2. `GET https://api.portkey.ai/v1/videos/{id}` — poll every 5s (8 minute timeout); same metadata so GETs still route correctly
3. `GET https://api.portkey.ai/v1/videos/{id}/content` — download through Portkey with the same metadata

**Routing:** the tester maps model slug → `metadata.video_route` via `VIDEO_ROUTES` (currently `veo` → `veo`). Your Portkey config should use conditional routing on `metadata.video_route` (and optionally `params.model`) to select the video target. Pass your config ID when prompted so create/poll/download share the same config.

**Default prompt** (overridable): a meme-style clip of a CS student celebrating when code finally compiles.

**Saved files** go under `video/` in the project root:

```text
video/portkey-video-YYYYMMDD-HHMMSS-<model-slug>.mp4
```

That folder is gitignored. Results also show the Portkey content URL.

Example video session:

```text
Enter config ID (optional, press Enter to skip): YOUR_CONFIG_ID
Enter choice (1-6): 5
Enter video prompt (optional, press Enter for default):
Enter model slugs (comma-separated): veo

… spinner with humorous wait messages …

✅ veo - video
Video route: veo
Saved locally: .../video/portkey-video-20260930-134512-veo.mp4
```

## Example model slugs

These depend on your Portkey dashboard / virtual keys:

- **Chat**: `gpt-4`, `gpt-4-turbo`, `mistral-medium`, `claude-3-sonnet`, …
- **Embeddings**: `text-embedding-3-small`, `cohere-embed-v3`, …
- **TTS**: `tts-1`, `tts-1-hd`
- **STT**: `whisper-1`
- **Video**: `veo` (maps to `metadata.video_route=veo` in config; add more entries in `VIDEO_ROUTES` as you add targets)

## How it works

1. Initialize the Portkey client with your API key (and optional config ID).
2. For each model slug, call the selected (or auto-detected) endpoint.
3. On auto-detect failure, try other endpoints in priority order (not used for forced Video).
4. Print per-model status, detailed panels for successes, and a summary table.
5. Exit `0` if all passed, `1` if any failed, `130` on Ctrl+C.

## Plain HTTP / curl examples

### Chat

```bash
curl --request POST \
  --url https://api.portkey.ai/v1/chat/completions \
  --header 'content-type: application/json' \
  --header 'x-portkey-api-key: YOUR_API_KEY_HERE' \
  --data '{
    "messages": [{"role": "user", "content": "Say hello!"}],
    "model": "mistral-medium"
  }'
```

Add `--header 'x-portkey-config: YOUR_CONFIG_ID'` when using a config.

### Embeddings

```bash
curl --request POST \
  --url https://api.portkey.ai/v1/embeddings \
  --header 'content-type: application/json' \
  --header 'x-portkey-api-key: YOUR_API_KEY_HERE' \
  --data '{
    "input": ["Hello, world!"],
    "model": "text-embedding-3-small"
  }'
```

### Video (create + poll + download)

Uses Portkey conditional config + metadata (not `x-portkey-provider`):

```bash
# Create
curl --request POST \
  --url https://api.portkey.ai/v1/videos \
  --header 'content-type: application/json' \
  --header 'x-portkey-api-key: YOUR_API_KEY_HERE' \
  --header 'x-portkey-config: YOUR_CONFIG_ID' \
  --header 'x-portkey-metadata: {"video_route":"veo"}' \
  --data '{"model":"veo","prompt":"a rubber duck debugging at 3am"}'

# Poll (replace JOB_ID) — metadata keeps the same video route on GET
curl --request GET \
  --url https://api.portkey.ai/v1/videos/JOB_ID \
  --header 'x-portkey-api-key: YOUR_API_KEY_HERE' \
  --header 'x-portkey-config: YOUR_CONFIG_ID' \
  --header 'x-portkey-metadata: {"video_route":"veo"}'

# Download
curl --request GET \
  --url 'https://api.portkey.ai/v1/videos/JOB_ID/content?index=0' \
  --header 'x-portkey-api-key: YOUR_API_KEY_HERE' \
  --header 'x-portkey-config: YOUR_CONFIG_ID' \
  --header 'x-portkey-metadata: {"video_route":"veo"}' \
  --output video/out.mp4
```


## Exit codes

| Code | Meaning |
|------|---------|
| `0` | All tests passed |
| `1` | One or more tests failed |
| `130` | Interrupted (Ctrl+C) |

## Troubleshooting

| Issue | What to check |
|-------|----------------|
| Invalid API key | Key active in Portkey dashboard |
| Model not found | Slug configured / virtual key correct |
| Video `403` / Cloudflare `1010` | Unusual; the CLI sets a custom User-Agent — retry or check WAF |
| Video poll `404` | Poll must be **GET** `/v1/videos/{id}` via Portkey |
| Video wrong provider / default model | Ensure config ID is set and `metadata.video_route` matches a condition (e.g. `veo`) |
| Unknown video model slug | Use a key from `VIDEO_ROUTES` (currently `veo`) or add a mapping |
| OpenRouter URL needs login | Use Portkey content URL or the file under `video/` |
| Config errors | Config ID exists and is allowed for your key |

## Requirements

- Python 3.7+
- `portkey-ai`
- `rich`

## License

MIT — see [LICENSE](LICENSE).
