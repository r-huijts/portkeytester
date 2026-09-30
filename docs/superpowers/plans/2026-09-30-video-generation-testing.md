# Video Generation Testing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Video endpoint option to the Portkey CLI tester that creates a video job, polls until complete, and prints `unsigned_urls`.

**Architecture:** Extend `test_portkey.py` with raw `urllib` HTTP helpers for `POST /v1/videos` (create) and `POST /v1/videos/{id}` (poll). Video mode prompts for a required `x-portkey-provider` header; prompt text is hardcoded. Unit-test create/poll logic with mocked HTTP.

**Tech Stack:** Python 3, stdlib `urllib` + `json` + `unittest`/`unittest.mock`, existing Rich CLI patterns, no new dependencies.

## Global Constraints

- Poll via Portkey gateway (`https://api.portkey.ai/v1/videos/{id}`), never the OpenRouter `polling_url`.
- Hardcoded prompt: `"A serene mountain landscape at sunset with clouds drifting by"`.
- Poll every 5 seconds; timeout after 8 minutes from create.
- Auto-detect must not attempt video.
- No API keys hardcoded or committed.
- Do not change behavior of chat / embeddings / TTS / STT.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `test_portkey.py` | CLI + video create/poll + wiring into menu/results |
| `tests/test_video.py` | Unit tests for video HTTP helpers (mocked) |
| `README.md` | Document Video endpoint option and provider prompt |

---

### Task 1: Video HTTP helpers + unit tests

**Files:**
- Create: `tests/test_video.py`
- Modify: `test_portkey.py` (add helpers near other test_* functions; keep existing behavior)

**Interfaces:**
- Produces:
  - `VIDEO_SAMPLE_PROMPT: str` = `"A serene mountain landscape at sunset with clouds drifting by"`
  - `VIDEO_POLL_INTERVAL_SEC: float` = `5.0`
  - `VIDEO_POLL_TIMEOUT_SEC: float` = `480.0`
  - `portkey_video_request(api_key: str, provider: str, model: str, prompt: str, video_id: Optional[str] = None) -> Tuple[int, Dict[str, Any]]`
    - If `video_id` is None → `POST https://api.portkey.ai/v1/videos`
    - Else → `POST https://api.portkey.ai/v1/videos/{video_id}`
    - Returns `(http_status, parsed_json_dict)`; on non-JSON body raise or return empty dict with status
  - `interpret_video_poll_payload(payload: Dict[str, Any]) -> str`
    - Returns one of: `"pending"`, `"completed"`, `"failed"`, `"completed_no_urls"`

- [ ] **Step 1: Create test file with failing tests**

Create `tests/__init__.py` (empty) and `tests/test_video.py`:

```python
import unittest
from unittest.mock import patch, MagicMock
import json
import io

# Import from project root module
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import test_portkey as tp


class TestInterpretVideoPollPayload(unittest.TestCase):
    def test_pending(self):
        self.assertEqual(
            tp.interpret_video_poll_payload({"status": "pending", "id": "gen-vid-1"}),
            "pending",
        )

    def test_completed_with_urls(self):
        self.assertEqual(
            tp.interpret_video_poll_payload({
                "status": "completed",
                "unsigned_urls": ["https://example.com/v.mp4"],
            }),
            "completed",
        )

    def test_completed_without_urls(self):
        self.assertEqual(
            tp.interpret_video_poll_payload({"status": "completed", "unsigned_urls": []}),
            "completed_no_urls",
        )

    def test_failed_statuses(self):
        for status in ("failed", "error", "cancelled"):
            self.assertEqual(
                tp.interpret_video_poll_payload({"status": status}),
                "failed",
            )


class TestPortkeyVideoRequest(unittest.TestCase):
    @patch("urllib.request.urlopen")
    def test_create_posts_to_videos_root(self, mock_urlopen):
        body = {"id": "gen-vid-abc", "status": "pending"}
        resp = MagicMock()
        resp.status = 200
        resp.read.return_value = json.dumps(body).encode()
        resp.__enter__.return_value = resp
        resp.__exit__.return_value = False
        mock_urlopen.return_value = resp

        status, data = tp.portkey_video_request(
            api_key="pk-test",
            provider="@openroutervideomodels",
            model="kwaivgi/kling-v3.0-std",
            prompt=tp.VIDEO_SAMPLE_PROMPT,
        )
        self.assertEqual(status, 200)
        self.assertEqual(data["id"], "gen-vid-abc")

        req = mock_urlopen.call_args[0][0]
        self.assertEqual(req.full_url, "https://api.portkey.ai/v1/videos")
        self.assertEqual(req.get_header("X-portkey-api-key"), "pk-test")
        self.assertEqual(req.get_header("X-portkey-provider"), "@openroutervideomodels")
        self.assertEqual(req.get_method(), "POST")

    @patch("urllib.request.urlopen")
    def test_poll_posts_to_videos_id(self, mock_urlopen):
        body = {"status": "pending", "id": "gen-vid-abc"}
        resp = MagicMock()
        resp.status = 200
        resp.read.return_value = json.dumps(body).encode()
        resp.__enter__.return_value = resp
        resp.__exit__.return_value = False
        mock_urlopen.return_value = resp

        status, data = tp.portkey_video_request(
            api_key="pk-test",
            provider="@openroutervideomodels",
            model="kwaivgi/kling-v3.0-std",
            prompt=tp.VIDEO_SAMPLE_PROMPT,
            video_id="gen-vid-abc",
        )
        self.assertEqual(status, 200)
        req = mock_urlopen.call_args[0][0]
        self.assertEqual(
            req.full_url,
            "https://api.portkey.ai/v1/videos/gen-vid-abc",
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests — expect fail (functions missing)**

```bash
cd /Users/ruud/Documents/Projects/Active/portkeytester
python -m unittest tests.test_video -v
```

Expected: FAIL / ImportError / AttributeError for missing symbols.

- [ ] **Step 3: Implement helpers in `test_portkey.py`**

Add near the top (after imports) or just above `test_text_to_speech`:

```python
VIDEO_SAMPLE_PROMPT = "A serene mountain landscape at sunset with clouds drifting by"
VIDEO_POLL_INTERVAL_SEC = 5.0
VIDEO_POLL_TIMEOUT_SEC = 480.0  # 8 minutes


def interpret_video_poll_payload(payload: Dict[str, Any]) -> str:
    status = (payload.get("status") or "").lower()
    if status in ("failed", "error", "cancelled"):
        return "failed"
    if status == "completed":
        urls = payload.get("unsigned_urls") or []
        if isinstance(urls, list) and len(urls) > 0:
            return "completed"
        return "completed_no_urls"
    return "pending"


def portkey_video_request(
    api_key: str,
    provider: str,
    model: str,
    prompt: str,
    video_id: Optional[str] = None,
) -> Tuple[int, Dict[str, Any]]:
    import urllib.request
    import urllib.error

    url = "https://api.portkey.ai/v1/videos"
    if video_id:
        url = f"{url}/{video_id}"

    payload = json.dumps({"model": model, "prompt": prompt}).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-portkey-api-key": api_key,
            "x-portkey-provider": provider,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode(errors="replace")
            status = resp.status
    except urllib.error.HTTPError as e:
        status = e.code
        raw = e.read().decode(errors="replace")

    try:
        data = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        data = {"raw": raw}
    if not isinstance(data, dict):
        data = {"raw": data}
    return status, data
```

Note: `urllib.request.Request.get_header` normalizes header names; if header asserts fail in tests, assert via `req.headers` keys present in the Request constructor instead (compare the dict passed into `Request(...)` by capturing kwargs, or check `req.header_items()`). Prefer asserting on the `headers=` dict by refactoring slightly if needed — keep tests green without changing API.

- [ ] **Step 4: Re-run unit tests**

```bash
python -m unittest tests.test_video -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add test_portkey.py tests/__init__.py tests/test_video.py
git commit -m "feat: add Portkey video HTTP helpers and unit tests"
```

---

### Task 2: `test_video_generation` create + poll loop

**Files:**
- Modify: `test_portkey.py`
- Modify: `tests/test_video.py`

**Interfaces:**
- Consumes: `portkey_video_request`, `interpret_video_poll_payload`, `VIDEO_*` constants
- Produces:
  - `test_video_generation(api_key: str, provider: str, model_slug: str, on_status_update=None) -> Tuple[bool, Dict[str, Any]]`
  - On success dict keys: `endpoint`=`"video"`, `model`, `id`, `unsigned_urls`, `cost` (optional), `usage`
  - On logical failure: `(False, {endpoint, error})` or raise for unexpected exceptions (match other endpoints)

- [ ] **Step 1: Add failing tests for poll loop**

Append to `tests/test_video.py`:

```python
class TestVideoGeneration(unittest.TestCase):
    @patch("test_portkey.time.sleep", return_value=None)
    @patch("test_portkey.portkey_video_request")
    def test_create_then_poll_until_completed(self, mock_req, _sleep):
        mock_req.side_effect = [
            (200, {"id": "gen-vid-1", "status": "pending"}),
            (200, {"status": "pending", "id": "gen-vid-1"}),
            (200, {
                "status": "completed",
                "id": "gen-vid-1",
                "unsigned_urls": ["https://example.com/v"],
                "usage": {"cost": 0.63},
            }),
        ]
        ok, details = tp.test_video_generation(
            api_key="pk",
            provider="@openroutervideomodels",
            model_slug="kwaivgi/kling-v3.0-std",
        )
        self.assertTrue(ok)
        self.assertEqual(details["endpoint"], "video")
        self.assertEqual(details["unsigned_urls"], ["https://example.com/v"])
        self.assertEqual(details["cost"], 0.63)
        self.assertEqual(mock_req.call_count, 3)

    @patch("test_portkey.time.sleep", return_value=None)
    @patch("test_portkey.portkey_video_request")
    def test_create_missing_id_fails(self, mock_req, _sleep):
        mock_req.return_value = (200, {"status": "pending"})
        ok, details = tp.test_video_generation("pk", "@prov", "model")
        self.assertFalse(ok)
        self.assertIn("error", details)

    @patch("test_portkey.VIDEO_POLL_TIMEOUT_SEC", 0.0)
    @patch("test_portkey.VIDEO_POLL_INTERVAL_SEC", 0.0)
    @patch("test_portkey.time.sleep", return_value=None)
    @patch("test_portkey.portkey_video_request")
    def test_timeout(self, mock_req, _sleep):
        def side_effect(api_key, provider, model, prompt, video_id=None):
            return 200, {"id": "gen-vid-1", "status": "pending"}

        mock_req.side_effect = side_effect
        ok, details = tp.test_video_generation("pk", "@prov", "model")
        self.assertFalse(ok)
        self.assertIn("timeout", str(details.get("error", "")).lower())
```

Note: with `VIDEO_POLL_TIMEOUT_SEC = 0.0`, the loop must hit the deadline check after create (before or after first sleep) and return a timeout error. If the implementation only checks the deadline at the top of the poll loop after sleep, that still exits immediately when timeout is 0.

- [ ] **Step 2: Run tests — expect fail**

```bash
python -m unittest tests.test_video.TestVideoGeneration -v
```

Expected: AttributeError / fail — `test_video_generation` missing.

- [ ] **Step 3: Implement `test_video_generation`**

```python
def test_video_generation(
    api_key: str,
    provider: str,
    model_slug: str,
    on_status_update=None,
) -> Tuple[bool, Dict[str, Any]]:
    """Create a video job via Portkey and poll until completed or timeout."""
    if on_status_update:
        on_status_update("Creating video job...")

    status, create_body = portkey_video_request(
        api_key=api_key,
        provider=provider,
        model=model_slug,
        prompt=VIDEO_SAMPLE_PROMPT,
    )
    if status >= 400:
        return False, {
            "endpoint": "video",
            "error": f"Create failed HTTP {status}: {create_body}",
        }
    video_id = create_body.get("id")
    if not video_id:
        return False, {
            "endpoint": "video",
            "error": f"Create response missing id: {create_body}",
        }

    deadline = time.time() + VIDEO_POLL_TIMEOUT_SEC
    while True:
        if on_status_update:
            on_status_update(f"Polling {video_id} ({create_body.get('status', 'pending')})...")

        if time.time() > deadline:
            return False, {
                "endpoint": "video",
                "error": f"Timeout after {VIDEO_POLL_TIMEOUT_SEC}s waiting for {video_id}",
            }

        time.sleep(VIDEO_POLL_INTERVAL_SEC)

        status, poll_body = portkey_video_request(
            api_key=api_key,
            provider=provider,
            model=model_slug,
            prompt=VIDEO_SAMPLE_PROMPT,
            video_id=video_id,
        )
        if status >= 400:
            return False, {
                "endpoint": "video",
                "error": f"Poll failed HTTP {status}: {poll_body}",
            }

        outcome = interpret_video_poll_payload(poll_body)
        if on_status_update:
            on_status_update(f"Status: {poll_body.get('status', outcome)}")

        if outcome == "completed":
            usage = poll_body.get("usage")
            cost = None
            if isinstance(usage, dict):
                cost = usage.get("cost")
            return True, {
                "endpoint": "video",
                "model": model_slug,
                "id": video_id,
                "unsigned_urls": list(poll_body.get("unsigned_urls") or []),
                "cost": cost,
                "usage": usage,
            }
        if outcome == "completed_no_urls":
            return False, {
                "endpoint": "video",
                "error": f"Completed without unsigned_urls: {poll_body}",
            }
        if outcome == "failed":
            return False, {
                "endpoint": "video",
                "error": f"Video job failed: {poll_body}",
            }
        # pending — loop
```

Important: first poll should happen after the first sleep (or optionally poll immediately once). Spec says interval 5s — sleeping before first poll is fine. For the unit test that expects 3 calls (1 create + 2 polls), the implementation must poll at least twice before completed — the mock side_effect handles that.

Adjust timeout test: patch `VIDEO_POLL_TIMEOUT_SEC` to a tiny value and `time.time` if needed so the loop exits quickly without many iterations. Prefer:

```python
@patch("test_portkey.time.time", side_effect=[0.0, 0.0, 1.0])  # create path then past deadline
```

or set timeout to `0` and check deadline immediately after first sleep. Keep the test deterministic and fast.

- [ ] **Step 4: Run all video unit tests**

```bash
python -m unittest tests.test_video -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add test_portkey.py tests/test_video.py
git commit -m "feat: add video create-and-poll test loop"
```

---

### Task 3: Wire Video into CLI menu, `test_model`, and results

**Files:**
- Modify: `test_portkey.py` (`get_target_endpoint_type`, `get_endpoint_priorities`, `test_model`, `main`, success/summary rendering)
- Modify: `README.md` (features + usage)

**Interfaces:**
- Consumes: `test_video_generation`
- Produces:
  - `get_provider_header() -> str` (required, non-empty)
  - Menu option 5 = `video`, option 6 = auto-detect (`None`)
  - `main()` prompts for provider when `target_endpoint == 'video'` and passes `api_key` + `provider` into video path

- [ ] **Step 1: Add `get_provider_header` and update menu**

```python
def get_provider_header() -> str:
    """Prompt for required x-portkey-provider (video mode)."""
    provider = console.input(
        "[bold]Enter x-portkey-provider[/bold] [dim](e.g. @openroutervideomodels)[/dim]: "
    ).strip()
    if not provider:
        console.print("[bold red]❌ Error: Provider cannot be empty for video tests.[/bold red]")
        sys.exit(1)
    return provider


def get_target_endpoint_type() -> Optional[str]:
    console.print("\n[bold]Select Endpoint Type:[/bold]")
    console.print("1. [cyan]Chat Completions[/cyan] (default)")
    console.print("2. [cyan]Embeddings[/cyan]")
    console.print("3. [cyan]Text-to-Speech[/cyan] (TTS)")
    console.print("4. [cyan]Speech-to-Text[/cyan] (STT)")
    console.print("5. [cyan]Video[/cyan]")
    console.print("6. [dim]Auto-detect based on slug[/dim]")

    choice = console.input("[bold]Enter choice (1-6):[/bold] ").strip()

    if choice == "1" or not choice:
        return "chat"
    if choice == "2":
        return "embeddings"
    if choice == "3":
        return "tts"
    if choice == "4":
        return "stt"
    if choice == "5":
        return "video"
    if choice == "6":
        return None
    return None
```

Update `get_endpoint_priorities` valid_types to include `'video'`. Do **not** add video to auto-detect priority lists.

- [ ] **Step 2: Wire `test_model` and `main`**

In `test_model`, add optional `api_key` / `provider` kwargs (or pass provider only when forced_type is video). Cleanest approach matching current signature:

Change `test_model` to accept `provider: Optional[str] = None` and when `forced_type == 'video'` (or endpoint == video):

```python
elif endpoint == "video":
    if not provider:
        raise ValueError("provider is required for video tests")
    success, result = test_video_generation(
        api_key=client.api_key,
        provider=provider,
        model_slug=model_slug,
        on_status_update=on_status_update,
    )
```

Use `client.api_key` if available; if SDK attribute differs, pass `api_key` from `main` explicitly:

```python
def test_model(..., provider: Optional[str] = None, api_key: Optional[str] = None):
```

and call `test_video_generation(api_key=api_key or getattr(client, "api_key", None), ...)`.

In `main`:

```python
provider = None
if target_endpoint == "video":
    provider = get_provider_header()

# ... later ...
success, details = test_model(
    client,
    model_slug,
    forced_type=target_endpoint,
    on_status_update=update_status,
    provider=provider,
    api_key=api_key,
)
```

When merging success details into `test_details`, also copy `unsigned_urls`, `cost`, `id` from `result`.

- [ ] **Step 3: Render video results**

In the success panel block, add:

```python
elif details["endpoint"] == "video":
    panel_content.append(f"[bold]Job ID:[/bold] {details.get('id', 'N/A')}")
    if details.get("cost") is not None:
        panel_content.append(f"[bold]Cost:[/bold] {details['cost']}")
    urls = details.get("unsigned_urls") or []
    panel_content.append("[bold]Video URL(s):[/bold]")
    for u in urls:
        panel_content.append(f"[cyan]{u}[/cyan]")
```

In the summary table Details column for success:

```python
if details["endpoint"] == "video":
    urls = details.get("unsigned_urls") or []
    detail_cell = (urls[0][:60] + "...") if urls and len(urls[0]) > 60 else (urls[0] if urls else "N/A")
else:
    detail_cell = details["response_model"] or "N/A"
```

Ensure `test_details` stores `unsigned_urls`, `cost`, `id` on success (update the `test_details.update({...})` block).

- [ ] **Step 4: Update README**

In Features and Usage sections:

- Features: mention Video generation (create + poll)
- Usage step 3: include Video; note that Video also prompts for `x-portkey-provider`
- Add a short subsection **Example Session - Video** showing menu choice 5, provider `@openroutervideomodels`, model slug, and that results include `unsigned_urls`
- Note: Auto-detect does not select Video

- [ ] **Step 5: Smoke-check CLI help path (no live API)**

```bash
python -c "import test_portkey as t; assert t.get_endpoint_priorities('x', 'video') == ['video']; assert 'video' not in t.get_endpoint_priorities('kling-video')"
python -m unittest tests.test_video -v
```

Expected: priorities for forced video are `['video']`; auto-detect for a kling-like slug does **not** include video; tests PASS.

- [ ] **Step 6: Commit**

```bash
git add test_portkey.py README.md
git commit -m "feat: wire Video endpoint into CLI menu and results"
```

---

## Spec coverage (self-review)

| Spec requirement | Task |
|------------------|------|
| Video menu option + provider prompt | Task 3 |
| Hardcoded prompt | Task 1 (`VIDEO_SAMPLE_PROMPT`) |
| Create POST `/v1/videos` | Task 1–2 |
| Poll POST `/v1/videos/{id}` via Portkey | Task 1–2 |
| 5s / 8 min polling | Task 1 constants + Task 2 loop |
| `unsigned_urls` + cost in results | Task 2–3 |
| No auto-detect video | Task 3 |
| Existing endpoints unchanged | Task 3 (additive only) |
| No secrets committed | Global + code uses prompts only |
| README note | Task 3 |

## Placeholder / consistency check

- Function names consistent: `portkey_video_request`, `interpret_video_poll_payload`, `test_video_generation`, `get_provider_header`
- Outcome strings: `pending` | `completed` | `completed_no_urls` | `failed`
- No TBD/TODO left in plan steps
