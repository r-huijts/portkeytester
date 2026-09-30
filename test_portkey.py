#!/usr/bin/env python3
"""
Portkey AI Gateway Test Script
A CLI tool to test multiple models through the Portkey AI gateway.
"""

import sys
import time
from datetime import datetime
from typing import List, Optional, Tuple, Dict, Any
from portkey_ai import Portkey
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.syntax import Syntax
from rich.rule import Rule
import json
import os
import re
import tempfile
import wave

# Initialize Rich console
console = Console()

VIDEO_SAMPLE_PROMPT = (
    "A sleep-deprived computer science student in a hoodie stares at a laptop at 3am. "
    "Suddenly the code compiles with zero errors — they leap up cheering as confetti "
    "explodes like a sports victory meme, cinematic slow-motion, absurdly dramatic"
)
VIDEO_POLL_INTERVAL_SEC = 5.0
VIDEO_POLL_TIMEOUT_SEC = 480.0  # 8 minutes

VIDEO_WAIT_MESSAGES = (
    "Teaching pixels how to meme...",
    "Negotiating with the GPU hamsters...",
    "The 3am student is almost celebrating...",
    "Compiling vibes into video frames...",
    "Not stuck — just fashionably late...",
    "Asking the model nicely to hurry up...",
    "Still cooking… resistance is futile...",
    "Buffering greatness (yes, still working)...",
    "Almost there* (*technically a guess)...",
    "Summoning confetti for the victory scene...",
    "Render farm is doing cardio...",
    "Convincing the rubber duck this is art...",
    "Stack Overflow has no answers for this wait...",
    "npm install vibes… still resolving...",
    "Waiting for CI — oh wait, wrong pipeline...",
    "The frames are shy; coaxing them out...",
    "Plot twist loading… please hold...",
    "Your patience is being unit-tested...",
    "One does not simply generate a video quickly...",
    "Heroku-dyno energy: still booting...",
    "Turning caffeine into cinema...",
    "The API said 'brb' and meant it...",
    "Polishing each frame with a tiny digital cloth...",
    "In a meeting with Latency, running over...",
    "Good things come to those who poll...",
    "404: Instant gratification not found...",
    "Training the montage sequence...",
    "Don't refresh — we're not a webpage...",
    "Seconds are just unfinished minutes...",
    "The hamster wheel has entered turbo mode...",
)


def _video_wait_status(poll_count: int, api_status: str, elapsed_sec: float) -> str:
    """Rotate humorous wait copy so polling feels alive without leaking job IDs."""
    funny = VIDEO_WAIT_MESSAGES[poll_count % len(VIDEO_WAIT_MESSAGES)]
    return f"{funny} [{api_status}, {int(elapsed_sec)}s]"


def interpret_video_poll_payload(payload: Dict[str, Any]) -> str:
    """Classify a video poll JSON body into a terminal or pending outcome."""
    status = (payload.get("status") or "").lower()
    if status in ("failed", "error", "cancelled", "expired"):
        return "failed"
    if status == "completed":
        urls = payload.get("unsigned_urls") or []
        if isinstance(urls, list) and len(urls) > 0:
            return "completed"
        return "completed_no_urls"
    # pending, in_progress, or unknown → keep polling
    return "pending"


def portkey_video_content_url(video_id: str, index: int = 0) -> str:
    """Build a Portkey gateway URL for video content (not the OpenRouter URL)."""
    return f"https://api.portkey.ai/v1/videos/{video_id}/content?index={index}"


def video_save_path(model_slug: str, index: int = 0, when: Optional[datetime] = None) -> str:
    """Local path under video/: portkey-video-YYYYMMDD-HHMMSS-<model-slug>[-index].mp4"""
    stamp = (when or datetime.now()).strftime("%Y%m%d-%H%M%S")
    safe_slug = re.sub(r"[^a-zA-Z0-9._-]+", "_", model_slug).strip("._-") or "model"
    name = f"portkey-video-{stamp}-{safe_slug}"
    if index > 0:
        name = f"{name}-{index}"
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "video")
    os.makedirs(out_dir, exist_ok=True)
    return os.path.join(out_dir, f"{name}.mp4")


def download_portkey_video(
    api_key: str,
    provider: str,
    video_id: str,
    index: int = 0,
    model_slug: Optional[str] = None,
    dest_path: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    Download video bytes via Portkey gateway and write to disk.

    Returns (success, path_or_error_message).
    """
    import urllib.request
    import urllib.error

    url = portkey_video_content_url(video_id, index)
    if dest_path is None:
        if not model_slug:
            return False, "model_slug or dest_path is required to save video"
        dest_path = video_save_path(model_slug, index)

    req = urllib.request.Request(
        url,
        headers={
            "Accept": "*/*",
            "User-Agent": "portkey-tester/1.0",
            "x-portkey-api-key": api_key,
            "x-portkey-provider": provider,
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            data = resp.read()
            status = resp.status
    except urllib.error.HTTPError as e:
        err_body = e.read().decode(errors="replace")
        return False, f"Download failed HTTP {e.code}: {err_body[:500]}"
    except Exception as e:
        return False, f"Download failed: {e}"

    if status >= 400 or not data:
        return False, f"Download failed HTTP {status} or empty body"

    with open(dest_path, "wb") as f:
        f.write(data)
    return True, dest_path


def portkey_video_request(
    api_key: str,
    provider: str,
    model: str,
    prompt: str,
    video_id: Optional[str] = None,
) -> Tuple[int, Dict[str, Any]]:
    """Create (POST) or poll (GET) against Portkey /v1/videos (raw HTTP)."""
    import urllib.request
    import urllib.error

    headers = {
        "Accept": "application/json",
        "User-Agent": "portkey-tester/1.0",
        "x-portkey-api-key": api_key,
        "x-portkey-provider": provider,
    }

    if video_id:
        # OpenRouter video status is GET /v1/videos/{id} (no body)
        url = f"https://api.portkey.ai/v1/videos/{video_id}"
        req = urllib.request.Request(url, headers=headers, method="GET")
    else:
        url = "https://api.portkey.ai/v1/videos"
        headers["Content-Type"] = "application/json"
        payload = json.dumps({"model": model, "prompt": prompt}).encode()
        req = urllib.request.Request(
            url,
            data=payload,
            headers=headers,
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


def test_video_generation(
    api_key: str,
    provider: str,
    model_slug: str,
    on_status_update=None,
    prompt: Optional[str] = None,
) -> Tuple[bool, Dict[str, Any]]:
    """Create a video job via Portkey and poll until completed or timeout."""
    video_prompt = prompt or VIDEO_SAMPLE_PROMPT
    if on_status_update:
        on_status_update("Queued — meme factory warming up...")

    status, create_body = portkey_video_request(
        api_key=api_key,
        provider=provider,
        model=model_slug,
        prompt=video_prompt,
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

    started = time.time()
    deadline = started + VIDEO_POLL_TIMEOUT_SEC
    poll_count = 0
    while True:
        if time.time() >= deadline:
            return False, {
                "endpoint": "video",
                "error": f"Timeout after {VIDEO_POLL_TIMEOUT_SEC}s waiting for video job",
            }

        if on_status_update:
            on_status_update(
                _video_wait_status(poll_count, "waiting", time.time() - started)
            )

        time.sleep(VIDEO_POLL_INTERVAL_SEC)

        status, poll_body = portkey_video_request(
            api_key=api_key,
            provider=provider,
            model=model_slug,
            prompt=video_prompt,
            video_id=video_id,
        )
        if status >= 400:
            return False, {
                "endpoint": "video",
                "error": f"Poll failed HTTP {status}: {poll_body}",
            }

        outcome = interpret_video_poll_payload(poll_body)
        api_status = str(poll_body.get("status") or outcome)
        if on_status_update:
            on_status_update(
                _video_wait_status(poll_count, api_status, time.time() - started)
            )
        poll_count += 1

        if outcome == "completed":
            usage = poll_body.get("usage")
            cost = None
            if isinstance(usage, dict):
                cost = usage.get("cost")

            upstream_urls = list(poll_body.get("unsigned_urls") or [])
            portkey_urls = [
                portkey_video_content_url(video_id, i) for i in range(len(upstream_urls))
            ]

            if on_status_update:
                on_status_update("Snatching the masterpiece through Portkey...")

            saved_paths = []
            for i in range(len(upstream_urls)):
                ok_dl, path_or_err = download_portkey_video(
                    api_key=api_key,
                    provider=provider,
                    video_id=video_id,
                    index=i,
                    model_slug=model_slug,
                )
                if not ok_dl:
                    return False, {
                        "endpoint": "video",
                        "error": path_or_err,
                    }
                saved_paths.append(path_or_err)

            return True, {
                "endpoint": "video",
                "model": model_slug,
                "id": video_id,
                "prompt": video_prompt,
                "unsigned_urls": portkey_urls,
                "saved_paths": saved_paths,
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


def print_banner():
    """Print a fancy banner because why not."""
    console.print(Panel(
        "[bold cyan]🔑 Portkey AI Gateway Tester[/bold cyan]\n[dim]Professional API testing[/dim]",
        border_style="cyan",
        padding=(1, 2),
        expand=True
    ))


def get_api_key() -> str:
    """Prompt user for Portkey API key."""
    api_key = console.input("[bold]Enter your Portkey API key:[/bold] ").strip()
    if not api_key:
        console.print("[bold red]❌ Error: API key cannot be empty.[/bold red]")
        sys.exit(1)
    return api_key


def get_config_id() -> Optional[str]:
    """Prompt user for optional config ID."""
    config_id = console.input("[bold]Enter config ID[/bold] [dim](optional, press Enter to skip)[/dim]: ").strip()
    return config_id if config_id else None


def get_provider_header() -> str:
    """Prompt for required x-portkey-provider (video mode)."""
    provider = console.input(
        "[bold]Enter x-portkey-provider[/bold] [dim](e.g. @openroutervideomodels)[/dim]: "
    ).strip()
    if not provider:
        console.print("[bold red]❌ Error: Provider cannot be empty for video tests.[/bold red]")
        sys.exit(1)
    return provider


def get_video_prompt() -> str:
    """Optional override for the hardcoded video sample prompt."""
    console.print(
        f"[dim]Default prompt:[/dim] {VIDEO_SAMPLE_PROMPT[:100]}..."
        if len(VIDEO_SAMPLE_PROMPT) > 100
        else f"[dim]Default prompt:[/dim] {VIDEO_SAMPLE_PROMPT}"
    )
    custom = console.input(
        "[bold]Enter video prompt[/bold] [dim](optional, press Enter for default)[/dim]: "
    ).strip()
    return custom if custom else VIDEO_SAMPLE_PROMPT


def get_target_endpoint_type() -> Optional[str]:
    """Prompt user to select the target endpoint type."""
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

def get_model_slugs() -> List[str]:
    """Prompt user for model slugs (comma-separated)."""
    models_input = console.input("[bold]Enter model slugs[/bold] [dim](comma-separated)[/dim]: ").strip()
    if not models_input:
        console.print("[bold red]❌ Error: At least one model slug is required.[/bold red]")
        sys.exit(1)
    
    # Split by comma and clean up whitespace
    model_slugs = [slug.strip() for slug in models_input.split(',') if slug.strip()]
    
    if not model_slugs:
        console.print("[bold red]❌ Error: No valid model slugs provided.[/bold red]")
        sys.exit(1)
    
    return model_slugs


def get_endpoint_priorities(model_slug: str, forced_type: Optional[str] = None) -> List[str]:
    """
    Get a list of endpoints to try in order of priority based on model slug.
    
    Args:
        model_slug: Model identifier
        forced_type: Optional forced endpoint type ('chat', 'embeddings', 'tts', 'stt', 'video')
    
    Returns:
        List of endpoint strings ('chat', 'embeddings', 'tts', 'stt', 'video')
    """
    if forced_type:
        valid_types = ['chat', 'embeddings', 'tts', 'stt', 'video']
        if forced_type in valid_types:
            return [forced_type]

    slug = model_slug.lower()
    if 'embed' in slug:
        return ['embeddings', 'chat', 'tts', 'stt']
    if 'tts' in slug:
        return ['tts', 'chat', 'embeddings', 'stt']
    if 'whisper' in slug:
        return ['stt', 'chat', 'embeddings', 'tts']
    
    # Default priority — video is never auto-detected
    return ['chat', 'embeddings', 'tts', 'stt']

def test_text_to_speech(client: Portkey, model_slug: str) -> Tuple[bool, Dict[str, Any]]:
    """Test text-to-speech endpoint."""
    response = client.audio.speech.create(
        model=model_slug,
        voice="alloy",
        input="Hello, this is a test of the Portkey Audio API."
    )
    
    # The response is a binary stream or object with content
    # For the SDK, it usually returns a response object where we can get bytes
    # Adjusting based on standard OpenAI-compatible SDK behavior which Portkey mimics
    
    content_length = 0
    if hasattr(response, 'content'):
        content_length = len(response.content)
    elif hasattr(response, 'read'):
        content_length = len(response.read())
    elif hasattr(response, 'response') and hasattr(response.response, 'content'):
         content_length = len(response.response.content)
    else:
        # Fallback for some SDK versions, try to cast to bytes if possible or check if it's iterable
        try:
            content_length = len(response)
        except:
            pass

    if content_length > 0:
        return True, {
            'endpoint': 'tts',
            'model': model_slug,
            'audio_size': content_length,
            'usage': None  # TTS usually doesn't return token usage in the same way
        }
    
    return False, {'endpoint': 'tts', 'error': 'No audio content received'}

def test_speech_to_text(client: Portkey, model_slug: str) -> Tuple[bool, Dict[str, Any]]:
    """Test speech-to-text endpoint."""
    # Create a temporary WAV file
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_audio:
        temp_filename = temp_audio.name
        
    try:
        # Generate 1 second of silence/simple audio
        with wave.open(temp_filename, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(44100)
            # Write 1 second of silence (zeros)
            wav_file.writeframes(b'\x00' * 44100 * 2)
            
        with open(temp_filename, "rb") as audio_file:
            response = client.audio.transcriptions.create(
                model=model_slug,
                file=audio_file
            )
        
        if response and hasattr(response, 'text'):
            return True, {
                'endpoint': 'stt',
                'model': model_slug,
                'content': response.text,
                'usage': None
            }
            
        return False, {'endpoint': 'stt', 'error': 'Invalid response structure'}
        
    finally:
        # Cleanup
        if os.path.exists(temp_filename):
            os.unlink(temp_filename)

def _chat_token_limit_param_error(exc: Exception) -> bool:
    """True when the provider rejected the token-limit parameter we sent."""
    msg = str(exc).lower()
    return any(
        needle in msg
        for needle in (
            "max_tokens",
            "max_completion_tokens",
            "unsupported",
            "extra_forbidden",
            "not permitted",
            "unknown parameter",
        )
    )


def test_chat_completion(client: Portkey, model_slug: str) -> Tuple[bool, Dict[str, Any]]:
    """Test chat completion endpoint."""
    messages = [
        {"role": "system", "content": "You are a helpful assistant. Respond briefly."},
        {"role": "user", "content": "Say 'Hello' if you can hear me."},
    ]
    # max_tokens works for most providers (Mistral, Azure, etc.); newer OpenAI models
    # may require max_completion_tokens instead.
    token_limits = ({"max_tokens": 50}, {"max_completion_tokens": 50})
    last_error: Optional[Exception] = None
    response = None
    for limit_kwargs in token_limits:
        try:
            response = client.chat.completions.create(
                messages=messages,
                model=model_slug,
                **limit_kwargs,
            )
            break
        except Exception as e:
            last_error = e
            if not _chat_token_limit_param_error(e):
                raise
    if response is None and last_error is not None:
        raise last_error
    
    if response and hasattr(response, 'choices') and len(response.choices) > 0:
        first_choice = response.choices[0]
        content = first_choice.message.content if hasattr(first_choice.message, 'content') else 'No content'
        
        return True, {
            'endpoint': 'chat',
            'content': content,
            'model': response.model if hasattr(response, 'model') else 'Unknown',
            'usage': response.usage if hasattr(response, 'usage') else None
        }
    
    return False, {'endpoint': 'chat', 'error': 'Invalid response structure'}
def _raw_embeddings_probe(api_key: str, model_slug: str) -> None:
    """Fire a raw HTTP request to Portkey and print everything — bypasses SDK."""
    import urllib.request
    import urllib.error

    url = "https://api.portkey.ai/v1/embeddings"
    payload = json.dumps({"input": ["test"], "model": model_slug}).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-portkey-api-key": api_key,
        },
        method="POST",
    )
    console.print(f"\n[bold yellow]── Raw HTTP probe ({url}) ──[/bold yellow]")
    try:
        with urllib.request.urlopen(req) as resp:
            status = resp.status
            headers = dict(resp.headers)
            body = resp.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        status = e.code
        headers = dict(e.headers)
        body = e.read().decode(errors="replace")
    except Exception as e:
        console.print(f"  [red]Request failed:[/red] {e}")
        return

    console.print(f"  [bold]Status:[/bold] {status}")
    # Print only the interesting Portkey/error headers
    interesting = {k: v for k, v in headers.items()
                   if any(k.lower().startswith(p) for p in
                          ("x-portkey", "grpc", "content", "x-ms", "azureml"))}
    for k, v in interesting.items():
        console.print(f"  [dim]{k}:[/dim] {v}")
    console.print(f"  [bold]Body:[/bold] {body[:800]!r}" if body else "  [bold]Body:[/bold] (empty)")
    console.print(f"[yellow]────────────────────────────────────────────────[/yellow]\n")


def test_embeddings(client: Portkey, model_slug: str) -> Tuple[bool, Dict[str, Any]]:
    """Test embeddings endpoint."""
    # Probe the raw HTTP response first so we always have diagnostics even if the SDK throws.
    _raw_embeddings_probe(client.api_key, model_slug)

    response = client.embeddings.create(
        input=["This is a test embedding request."],
        model=model_slug
    )

    if response and hasattr(response, 'data') and len(response.data) > 0:
        embedding = response.data[0].embedding
        dimension = len(embedding) if hasattr(embedding, '__len__') else 'Unknown'
        
        return True, {
            'endpoint': 'embeddings',
            'dimension': dimension,
            'model': response.model if hasattr(response, 'model') else 'Unknown',
            'usage': response.usage if hasattr(response, 'usage') else None
        }
    
    return False, {
        'endpoint': 'embeddings',
        'error': f'Invalid response — data={getattr(response, "data", "MISSING")!r}',
    }


def test_model(
    client: Portkey,
    model_slug: str,
    forced_type: Optional[str] = None,
    on_status_update=None,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    video_prompt: Optional[str] = None,
) -> Tuple[bool, Dict[str, Any]]:
    """
    Test a single model by auto-detecting and using the appropriate endpoint.
    
    Args:
        client: Initialized Portkey client
        model_slug: Model identifier to test
        forced_type: Optional forced endpoint type
        on_status_update: Optional callback function(msg: str) to update status
        provider: Required for video — value for x-portkey-provider
        api_key: Portkey API key (used for raw HTTP video calls)
        video_prompt: Optional prompt override for video generation
    
    Returns:
        Tuple of (success: bool, details: dict)
    """
    # Get endpoint priorities
    endpoints_to_try = get_endpoint_priorities(model_slug, forced_type)
    
    test_details = {
        'model': model_slug,
        'success': False,
        'endpoint': None,
        'response_model': None,
        'response_time': 0,
        'error': None,
        'content': None,
        'usage': None
    }
    
    try:
        # Measure response time
        start_time = time.time()
        
        success = False
        result = {}
        first_error = None
        
        # Iterate through endpoints
        for i, endpoint in enumerate(endpoints_to_try):
            test_details['endpoint'] = endpoint
            try:
                if i > 0 and on_status_update:
                    on_status_update(f"Trying fallback endpoint {endpoint}...")
                    
                if endpoint == 'chat':
                    success, result = test_chat_completion(client, model_slug)
                elif endpoint == 'embeddings':
                    success, result = test_embeddings(client, model_slug)
                elif endpoint == 'tts':
                    success, result = test_text_to_speech(client, model_slug)
                elif endpoint == 'stt':
                    success, result = test_speech_to_text(client, model_slug)
                elif endpoint == 'video':
                    resolved_key = api_key or getattr(client, 'api_key', None)
                    if not provider:
                        raise ValueError("provider is required for video tests")
                    if not resolved_key:
                        raise ValueError("api_key is required for video tests")
                    success, result = test_video_generation(
                        api_key=resolved_key,
                        provider=provider,
                        model_slug=model_slug,
                        on_status_update=on_status_update,
                        prompt=video_prompt,
                    )
                
                # If we got here without exception, check if it was logically successful
                if success:
                    break
                    
            except Exception as e:
                # Capture the first error as it's likely the most relevant (based on slug detection)
                if first_error is None:
                    first_error = e
                # Continue to next endpoint
                continue
        
        # If we failed all attempts and have an error, raise the first one
        if not success and first_error:
            raise first_error
        
        # Calculate response time
        response_time = time.time() - start_time
        
        # Check for successful response
        if success:
            test_details.update({
                'success': True,
                'endpoint': result['endpoint'],
                'response_model': result.get('model'),
                'response_time': response_time,
                'content': result.get('content'),
                'dimension': result.get('dimension'),
                'audio_size': result.get('audio_size'),
                'usage': result.get('usage'),
                'unsigned_urls': result.get('unsigned_urls'),
                'saved_paths': result.get('saved_paths'),
                'cost': result.get('cost'),
                'id': result.get('id'),
                'prompt': result.get('prompt'),
            })
            return True, test_details
        else:
            test_details['error'] = result.get('error', 'Unknown error')
            test_details['response_time'] = response_time
            return False, test_details
            
    except Exception as e:
        error_info = {
            'type': type(e).__name__,
            'message': str(e),
            'status_code': getattr(e, 'status_code', None),
            'body': getattr(e, 'body', None),
            'code': getattr(e, 'code', None),
        }
        
        test_details.update({
            'error': error_info,
            'response_time': time.time() - start_time
        })
        
        return False, test_details


def main():
    """Main execution flow."""
    print_banner()
    
    # Get user inputs
    api_key = get_api_key()
    config_id = get_config_id()
    target_endpoint = get_target_endpoint_type()
    provider = None
    video_prompt = None
    if target_endpoint == "video":
        provider = get_provider_header()
        video_prompt = get_video_prompt()
    model_slugs = get_model_slugs()
    
    # Initialize Portkey client
    console.print(f"\n[bold cyan]🔧 Initializing Portkey client...[/bold cyan]")
    
    client_kwargs = {"api_key": api_key}
    if config_id:
        client_kwargs["config"] = config_id
        console.print(f"   [dim]Using config ID:[/dim] {config_id}")
    
    if target_endpoint:
        console.print(f"   [dim]Target Endpoint:[/dim] {target_endpoint}")
    if provider:
        console.print(f"   [dim]Provider:[/dim] {provider}")
    
    client = Portkey(**client_kwargs)
    
    # Test each model with progress tracking
    console.print()
    console.print(Rule("[bold cyan]📊 Running Tests[/bold cyan]", style="cyan"))
    console.print()
    
    results = {}
    
    # Run tests with progress UI
    # Video: indeterminate spinner only (bar % = models done, meaningless while polling)
    if target_endpoint == "video":
        progress_cols = (
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
        )
    else:
        progress_cols = (
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
        )

    with Progress(*progress_cols, console=console) as progress:
        task = progress.add_task(
            "[cyan]Testing models...",
            total=None if target_endpoint == "video" else len(model_slugs),
        )

        for model_slug in model_slugs:
            progress.update(task, description=f"[cyan]Testing {model_slug}...")

            def update_status(msg):
                progress.update(task, description=f"[cyan]{model_slug}: {msg}")

            success, details = test_model(
                client,
                model_slug,
                forced_type=target_endpoint,
                on_status_update=update_status,
                provider=provider,
                api_key=api_key,
                video_prompt=video_prompt,
            )
            results[model_slug] = details

            if target_endpoint != "video":
                progress.advance(task)

        progress.update(task, description="[green]✅ Tests completed")
    
    # Progress bar is now hidden - show results
    console.print()
    console.print(Rule("[bold green]✅ Test Results[/bold green]", style="green"))
    console.print()
    
    # Show quick status for each model
    for model_slug, details in results.items():
        if details['success']:
            console.print(f"[green]✅[/green] {model_slug} - [dim]{details['response_time']:.2f}s[/dim] - [cyan]{details['endpoint']}[/cyan]")
        else:
            console.print(f"[red]❌[/red] {model_slug} - [dim]Failed[/dim]")
    
    # Show detailed success information
    successful_models = [(slug, details) for slug, details in results.items() if details['success']]
    if successful_models:
        console.print()
        console.print(Rule("[bold green]📄 Detailed Results[/bold green]", style="green"))
        console.print()
        
        for model_slug, details in successful_models:
            # Create detailed panel for each successful model
            panel_content = []
            
            # Basic info
            panel_content.append(f"[bold]✅ Response Success![/bold]")
            panel_content.append(f"[bold]API Key:[/bold] Working correctly")
            panel_content.append(f"[bold]Requested Slug:[/bold] {model_slug}")
            panel_content.append(f"[bold]Response Model:[/bold] {details['response_model']}")
            panel_content.append(f"[bold]Endpoint Used:[/bold] {details['endpoint']}")
            panel_content.append(f"[bold]Response Time:[/bold] {details['response_time']:.2f}s")
            
            # Check if model matches (for routing verification)
            if details['response_model'] and model_slug != details['response_model']:
                panel_content.append(f"[yellow]⚠️  Model routing detected: {model_slug} → {details['response_model']}[/yellow]")
                panel_content.append("[dim]Please verify this is the expected model routing.[/dim]")
            
            # Usage information
            if details['usage']:
                usage = details['usage']
                usage_text = []
                if hasattr(usage, 'prompt_tokens'):
                    usage_text.append(f"Prompt: {usage.prompt_tokens}")
                if hasattr(usage, 'completion_tokens'):
                    usage_text.append(f"Completion: {usage.completion_tokens}")
                if hasattr(usage, 'total_tokens'):
                    usage_text.append(f"Total: {usage.total_tokens}")
                if usage_text:
                    panel_content.append(f"[bold]Token Usage:[/bold] {', '.join(usage_text)}")
            
            # Content preview
            if details['endpoint'] == 'chat' and details['content']:
                content_preview = details['content'][:100] + "..." if len(details['content']) > 100 else details['content']
                panel_content.append(f"[bold]Response Preview:[/bold]")
                panel_content.append(f"[dim]\"{content_preview}\"[/dim]")
            elif details['endpoint'] == 'embeddings' and details['dimension']:
                panel_content.append(f"[bold]Embedding Dimension:[/bold] {details['dimension']}")
            elif details['endpoint'] == 'tts':
                panel_content.append(f"[bold]Audio Size:[/bold] {details.get('audio_size', 0)} bytes")
                panel_content.append(f"[dim]Audio content received successfully[/dim]")
            elif details['endpoint'] == 'stt':
                panel_content.append(f"[bold]Transcription:[/bold] \"{details.get('content', '')}\"")
            elif details['endpoint'] == 'video':
                panel_content.append(f"[bold]Job ID:[/bold] {details.get('id', 'N/A')}")
                if details.get('prompt'):
                    preview = details['prompt']
                    if len(preview) > 120:
                        preview = preview[:120] + "..."
                    panel_content.append(f"[bold]Prompt:[/bold] [dim]{preview}[/dim]")
                if details.get('cost') is not None:
                    panel_content.append(f"[bold]Cost:[/bold] {details['cost']}")
                urls = details.get('unsigned_urls') or []
                panel_content.append("[bold]Portkey content URL(s):[/bold]")
                for u in urls:
                    panel_content.append(f"[cyan]{u}[/cyan]")
                panel_content.append("[dim]Fetch with your Portkey API key + provider header (browser OpenRouter links will not work).[/dim]")
                saved = details.get('saved_paths') or []
                if saved:
                    panel_content.append("[bold]Saved locally:[/bold]")
                    for p in saved:
                        panel_content.append(f"[green]{p}[/green]")
            
            # Create the panel
            success_panel = Panel(
                "\n".join(panel_content),
                title=f"[bold green]🎯 {model_slug}[/bold green]",
                border_style="green",
                padding=(1, 2),
                expand=True
            )
            console.print(success_panel)
            console.print()
    
    # Summary - Create a beautiful table
    console.print()
    console.print(Rule("[bold cyan]📋 Test Summary[/bold cyan]", style="cyan"))
    console.print()
    
    table = Table(
        show_header=True, 
        header_style="bold cyan", 
        border_style="cyan",
        title="Test Results",
        title_style="bold magenta",
        expand=True
    )
    table.add_column("Status", style="bold", width=10, justify="center")
    table.add_column("Model", style="bold yellow")
    table.add_column("Endpoint", style="cyan")
    table.add_column("Response Time", justify="right", style="green")
    table.add_column("Details", style="dim")
    
    successful = sum(1 for r in results.values() if r['success'])
    failed = len(results) - successful
    
    for model_slug, details in results.items():
        if details['success']:
            if details.get('endpoint') == 'video':
                saved = details.get('saved_paths') or []
                if saved:
                    detail_cell = saved[0]
                else:
                    urls = details.get('unsigned_urls') or []
                    if urls:
                        first = urls[0]
                        detail_cell = (first[:60] + "...") if len(first) > 60 else first
                    else:
                        detail_cell = 'N/A'
            else:
                detail_cell = details['response_model'] or 'N/A'
            table.add_row(
                "[green]✅ PASS[/green]", 
                model_slug,
                details['endpoint'] or 'N/A',
                f"{details['response_time']:.2f}s",
                detail_cell
            )
        else:
            error_msg = details['error']['type'] if isinstance(details['error'], dict) else str(details['error'])
            table.add_row(
                "[red]❌ FAIL[/red]", 
                model_slug,
                'N/A',
                f"{details['response_time']:.2f}s" if details['response_time'] else 'N/A',
                f"[red]{error_msg}[/red]"
            )
    
    console.print(table)
    console.print()
    
    # Detailed results panel for failures
    if failed > 0:
        console.print(Rule("[bold red]Error Details[/bold red]", style="red"))
        console.print()
        
        for model_slug, details in results.items():
            if not details['success'] and details.get('error') is not None:
                error_lines = []
                err = details['error']
                if isinstance(err, dict):
                    error_lines.append(
                        f"[bold red]Error Type:[/bold red] {err.get('type', 'Error')}"
                    )
                    error_lines.append(
                        f"[bold red]Message:[/bold red] {err.get('message', err)}"
                    )
                    if err.get('status_code'):
                        error_lines.append(
                            f"[bold red]HTTP Status:[/bold red] {err['status_code']}"
                        )
                    if err.get('body'):
                        body_str = json.dumps(err['body'], indent=2)
                        error_lines.append("[bold red]Details:[/bold red]")
                        error_lines.append(body_str)
                else:
                    error_lines.append(f"[bold red]Message:[/bold red] {err}")

                error_panel = Panel(
                    "\n".join(error_lines),
                    title=f"[bold red]{model_slug}[/bold red]",
                    border_style="red",
                    padding=(1, 2),
                    expand=True
                )
                console.print(error_panel)
                console.print()
    
    # Total summary panel
    summary_text = f"[bold]Total:[/bold] {successful} passed, {failed} failed"
    summary_style = "green" if failed == 0 else "yellow"
    
    console.print(Panel(
        summary_text,
        border_style=summary_style,
        padding=(0, 2),
        expand=True
    ))
    
    # Exit with appropriate code
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print(f"\n\n[bold yellow]⚠️  Test interrupted by user.[/bold yellow]")
        sys.exit(130)

