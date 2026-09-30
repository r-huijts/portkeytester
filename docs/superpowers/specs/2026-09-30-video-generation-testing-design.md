# Video Generation Testing — Design

## Goal

Extend the Portkey CLI tester so users can smoke-test Portkey’s async video generation API: create a job, poll until complete, and surface the returned video URL(s).

## Approach

Extend the existing `test_portkey.py` CLI (same pattern as TTS/STT). Use raw HTTP via `urllib` for `/v1/videos` — the Portkey Python SDK is not assumed to expose this endpoint.

## UX / input flow

When the user selects **Video** as the endpoint type:

1. Portkey API key (existing prompt)
2. Config ID remains optional (existing); video HTTP calls do not use it
3. **Provider header** (new, required for video) — e.g. `@openroutervideomodels`
4. Model slug(s), comma-separated (existing) — each slug runs its own create→poll cycle
5. Prompt is **hardcoded** (no user input), e.g. `"A serene mountain landscape at sunset with clouds drifting by"`

Endpoint menu:

1. Chat Completions  
2. Embeddings  
3. Text-to-Speech (TTS)  
4. Speech-to-Text (STT)  
5. Video  
6. Auto-detect based on slug  

Auto-detect must **not** attempt video. Video is explicit selection only.

## API flow

### Create

- `POST https://api.portkey.ai/v1/videos`
- Headers: `Content-Type: application/json`, `x-portkey-api-key`, `x-portkey-provider`
- Body: `{ "model": "<slug>", "prompt": "<hardcoded sample>" }`
- Success shape: `{ "id": "gen-vid-...", "status": "pending", "polling_url": "..." }`
- Fail fast if response lacks `id`

### Poll

- Poll via the **Portkey gateway**, not the OpenRouter `polling_url` from the create response
- `POST https://api.portkey.ai/v1/videos/{id}`
- Same headers and body as create

### Status handling

| Response | Action |
|----------|--------|
| `status == "pending"` (or other non-terminal) | Keep polling |
| `status == "completed"` and `unsigned_urls` non-empty | Success; store URLs |
| `status == "completed"` but `unsigned_urls` missing/empty | Fail: completed without URLs |
| `status` in `failed` / `error` / `cancelled` | Fail with structured error |
| HTTP error | Fail with structured error |
| Timeout | Fail with timeout error |

### Polling strategy

- Interval: **5 seconds**
- Timeout: **8 minutes** from create
- Progress spinner shows latest `status` via existing `on_status_update` callback

### Completed response (reference)

```json
{
  "status": "completed",
  "id": "gen-vid-...",
  "unsigned_urls": [
    "https://openrouter.ai/api/v1/videos/.../content?index=0"
  ],
  "generation_id": "gen-vid-...",
  "polling_url": "https://openrouter.ai/api/v1/videos/...",
  "usage": { "is_byok": false, "cost": 0.63 }
}
```

## Results & errors

**Success panel** includes: model, provider, job `id`, total response time (create through completion), `usage.cost` when present, and each URL from `unsigned_urls` as plain text.

**Summary table:** Endpoint column = `video`; Details = first URL truncated (or error type on failure).

**Errors** use the same structured dict as other endpoints: `type`, `message`, `status_code`, `body`. Do not log or print API keys.

## Code changes

Primary file: `test_portkey.py`. Short README note for the new endpoint option.

| Piece | Responsibility |
|-------|----------------|
| `get_provider_header()` | Prompt for required `x-portkey-provider` when video is selected |
| `test_video_generation(...)` | Create + poll loop; returns success/details compatible with `test_model` |
| `get_target_endpoint_type()` | Add Video option; shift Auto-detect to 6 |
| `get_endpoint_priorities()` / `test_model()` | Accept `video`; when forced, only call video path |
| Result rendering | Video-specific success fields (`unsigned_urls`, cost, job id) |

Video path uses raw HTTP with the Portkey API key + provider header. The Portkey SDK client may still be initialized for non-video endpoints; video does not depend on SDK methods.

## Out of scope

- Downloading or playing the video file
- OpenRouter direct auth (`Authorization: Bearer`, `x-portkey-custom-host`)
- Auto-detecting video from model slug
- User-editable prompt

## Success criteria

1. User can select Video, enter API key, provider, and model slug(s), and run without other new prompts.
2. Create then poll via Portkey until `completed` or timeout/failure.
3. On success, `unsigned_urls` appear in detailed results and summary.
4. Existing chat / embeddings / TTS / STT flows are unchanged.
5. No API keys or secrets are committed or hardcoded.
