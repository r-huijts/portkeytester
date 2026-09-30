# Portkey AI Gateway Tester

A command-line tool to test multiple models through the Portkey AI gateway using the Portkey Python SDK.

## Features

- 🎯 Support for multiple model types (chat, embeddings, TTS, STT, video)
- 🤖 Auto-detects endpoint type based on model slug (video is explicit only)
- ⚙️ Optional config ID/header support
- 🔒 **Do Not Track support** for sensitive data compliance
- 📊 Clear success/error reporting with response time
- 🚀 Dynamic model routing via Portkey
- 🔄 Automatic fallback if primary endpoint fails
- 🎬 Video generation: create job, poll until complete, print `unsigned_urls`
- 🎨 Beautiful terminal output with Rich library
  - Animated progress bars and spinners
  - Formatted tables with multiple columns
  - Error panels with syntax highlighting
  - Real-time status updates

## Documentation

This tool is built on top of the [Portkey Inference API](https://portkey.ai/docs/api-reference/inference-api/introduction). Portkey provides three ways to integrate:

1. **Portkey SDKs** (Python and JavaScript) - Used by this tool
2. **OpenAI SDK** through Portkey Gateway - Change base URL to `https://api.portkey.ai/v1`
3. **REST API** - Direct HTTP calls to `https://api.portkey.ai/v1`

For more information, visit the [Portkey API Reference](https://portkey.ai/docs/api-reference/inference-api/introduction).

## Installation

### Quick Setup (Recommended)

Run the automated setup script with `source` to keep the virtual environment activated:
```bash
source ./install.sh
```

This will:
- Create a virtual environment
- Install all dependencies
- Activate the virtual environment automatically

Alternatively, run without `source` to just set up without activating:
```bash
./install.sh
```

### Manual Setup

1. Clone or download this repository

2. (Optional) Create a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

Run the test script:
```bash
python test_portkey.py
```

The script will interactively prompt you for:

1. **Portkey API Key**: Your `x-portkey-api-key` value
2. **Config ID** (optional): Portkey config ID for virtual keys/routing rules
3. **Endpoint Type**: Select Chat, Embeddings, TTS, STT, Video, or Auto-detect
4. **Provider** (Video only): Required `x-portkey-provider` value (e.g. `@openroutervideomodels`)
5. **Model Slugs**: Comma-separated list of model identifiers

### Smart Endpoint Detection

The script **automatically detects** which endpoint to use based on the model slug:
- Models containing `"embed"` → Uses **embeddings endpoint** (`/embeddings`)
- Models containing `"tts"` → Uses **text-to-speech endpoint** (`/audio/speech`)
- Models containing `"whisper"` → Uses **speech-to-text endpoint** (`/audio/transcriptions`)
- All other models → Uses **chat completions endpoint** (`/chat/completions`)

**Video** is never auto-detected — select it explicitly from the menu.

**Fallback Logic**: If the auto-detected endpoint fails, the script automatically tries the other endpoint.

**Examples**:
- `cohere-embed-v3` → Auto-detected as embeddings
- `tts-1` → Auto-detected as text-to-speech
- `whisper-1` → Auto-detected as speech-to-text
- `mistral-large` → Auto-detected as chat
- You can test multiple: `mistral-large, tts-1, whisper-1`

### Example Session - Chat Completions

```
🔑 Portkey AI Gateway Tester
============================================================

Enter your Portkey API key: ###
Enter config ID (optional, press Enter to skip): 

Select Endpoint Type:
1. Chat Completions (default)
2. Embeddings
3. Text-to-Speech (TTS)
4. Speech-to-Text (STT)
5. Video
6. Auto-detect based on slug
Enter choice (1-6): 1

Enter model slugs (comma-separated): mistral-large

🔧 Initializing Portkey client...

📊 Testing 1 model(s)...

🧪 Testing model: mistral-large
------------------------------------------------------------
✅ Response Success! API Key is working.
   Requested model: mistral-large
   Endpoint used: chat
   Response from model: mistral-large-2411
   ⏱️  Response time: 1.23s
   ➜ Please verify this is the correct routing for your config.

   Sample response: Hello...
   Tokens used: CompletionUsage(completion_tokens=2, prompt_tokens=25, total_tokens=27)

============================================================
📋 TEST SUMMARY
============================================================
  ✅ PASS - mistral-large

Total: 1 passed, 0 failed
============================================================
```

### Example Session - Embeddings

```
🔑 Portkey AI Gateway Tester
============================================================

Enter your Portkey API key: ###
Enter config ID (optional, press Enter to skip): 
Enter model slugs (comma-separated): cohere-embed-v3

🔧 Initializing Portkey client...

📊 Testing 1 model(s)...

🧪 Testing model: cohere-embed-v3
------------------------------------------------------------
✅ Response Success! API Key is working.
   Requested model: cohere-embed-v3
   Endpoint used: embeddings
   Response from model: Cohere-embed-v3-multilingual
   ⏱️  Response time: 0.87s
   ➜ Please verify this is the correct routing for your config.

   Embedding dimension: 1024
   Tokens used: {...}

============================================================
📋 TEST SUMMARY
============================================================
  ✅ PASS - cohere-embed-v3

Total: 1 passed, 0 failed
============================================================
```

### Example Session - Video

```
🔑 Portkey AI Gateway Tester
============================================================

Enter your Portkey API key: ###
Enter config ID (optional, press Enter to skip): 

Select Endpoint Type:
1. Chat Completions (default)
2. Embeddings
3. Text-to-Speech (TTS)
4. Speech-to-Text (STT)
5. Video
6. Auto-detect based on slug
Enter choice (1-6): 5

Enter x-portkey-provider (e.g. @openroutervideomodels): @openroutervideomodels
Enter model slugs (comma-separated): kwaivgi/kling-v3.0-std

🔧 Initializing Portkey client...
   Target Endpoint: video
   Provider: @openroutervideomodels

📊 Running Tests
... spinner shows create → pending → completed ...

✅ kwaivgi/kling-v3.0-std - 95.12s - video

Job ID: gen-vid-...
Cost: 0.63
Video URL(s):
https://openrouter.ai/api/v1/videos/.../content?index=0
```

Video uses a hardcoded sample prompt, creates a job via `POST /v1/videos`, then polls `POST /v1/videos/{id}` every 5s (8 minute timeout) until `status` is `completed` and prints `unsigned_urls`.

## Example Model Slugs

Depending on your Portkey configuration, you can test various models. The script auto-detects the endpoint type:

### Chat Completion Models (auto-detected)
- **OpenAI**: `gpt-4`, `gpt-4-turbo`, `gpt-3.5-turbo`
- **Anthropic**: `claude-3-opus`, `claude-3-sonnet`, `claude-3-haiku`
- **Mistral**: `mistral-medium`, `mistral-small`, `mistral-tiny`
- **Custom slugs**: Any model slug configured in your Portkey dashboard

### Embeddings Models (auto-detected with "embed" in name)
- **OpenAI**: `text-embedding-ada-002`, `text-embedding-3-small`, `text-embedding-3-large`
- **Cohere**: `cohere-embed-v3`, `embed-english-v3.0`, `embed-multilingual-v3.0`
- **Custom slugs**: Any embeddings model configured in your Portkey dashboard

### Text-to-Speech Models (auto-detected with "tts" in name)
- **OpenAI**: `tts-1`, `tts-1-hd`

### Speech-to-Text Models (auto-detected with "whisper" in name)
- **OpenAI**: `whisper-1`

> **Note**: Models are routed based on their slug name:
> - `"embed"` → `/embeddings`
> - `"tts"` → `/audio/speech`
> - `"whisper"` → `/audio/transcriptions`
> - Others → `/chat/completions`

## How It Works

1. The script initializes a Portkey client with your API key (and optional config ID)
2. For each model slug:
   - **Auto-detects** the endpoint type (chat vs embeddings based on slug name)
   - Sends a test request to the appropriate endpoint
   - If primary endpoint fails, tries the fallback endpoint automatically
   - Measures response time
3. Portkey dynamically routes the request to the configured provider
4. The script validates the response and reports:
   - Success/failure status
   - Which endpoint was used
   - Actual model that responded
   - Response time and token usage
5. A summary shows overall test results

## Plain HTTP/curl Examples

If you prefer not to use the Python SDK, you can test Portkey directly with HTTP requests:

### Chat Completions - Basic Request with API Key

```bash
curl --request POST \
  --url https://api.portkey.ai/v1/chat/completions \
  --header 'content-type: application/json' \
  --header 'x-portkey-api-key: YOUR_API_KEY_HERE' \
  --data '{
    "messages": [
      {
        "role": "system",
        "content": "You are a helpful assistant."
      },
      {
        "role": "user",
        "content": "Say hello!"
      }
    ],
    "model": "mistral-medium"
  }'
```

### Chat Completions - Request with Config ID

```bash
curl --request POST \
  --url https://api.portkey.ai/v1/chat/completions \
  --header 'content-type: application/json' \
  --header 'x-portkey-api-key: YOUR_API_KEY_HERE' \
  --header 'x-portkey-config: YOUR_CONFIG_ID' \
  --data '{
    "messages": [
      {
        "role": "user",
        "content": "Test message"
      }
    ],
    "model": "gpt-4"
  }'
```

### Embeddings - Basic Request

```bash
curl --request POST \
  --url https://api.portkey.ai/v1/embeddings \
  --header 'content-type: application/json' \
  --header 'x-portkey-api-key: YOUR_API_KEY_HERE' \
  --data '{
    "input": ["Hello, world!", "Testing embeddings"],
    "model": "text-embedding-ada-002"
  }'
```

### Embeddings - Request with Config ID

```bash
curl --request POST \
  --url https://api.portkey.ai/v1/embeddings \
  --header 'content-type: application/json' \
  --header 'x-portkey-api-key: YOUR_API_KEY_HERE' \
  --header 'x-portkey-config: YOUR_CONFIG_ID' \
  --data '{
    "input": ["Text to embed"],
    "model": "text-embedding-3-small"
  }'
```

### Testing Multiple Models (bash script)

```bash
#!/bin/bash

API_KEY="YOUR_API_KEY_HERE"
MODELS=("mistral-medium" "gpt-4" "claude-3-opus")

for model in "${MODELS[@]}"; do
  echo "Testing $model..."
  curl --request POST \
    --url https://api.portkey.ai/v1/chat/completions \
    --header 'content-type: application/json' \
    --header "x-portkey-api-key: $API_KEY" \
    --data "{
      \"messages\": [{\"role\": \"user\", \"content\": \"Hello\"}],
      \"model\": \"$model\"
    }"
  echo ""
done
```

## Do Not Track

For sensitive data or privacy compliance, use `debug: false` to prevent logging request/response content:

**Python SDK:**
```python
client = Portkey(api_key="your-key", debug=False)
```

**HTTP Header:**
```bash
--header 'x-portkey-debug: false'
```

Only operational metrics (tokens, cost, latency) are recorded. See [Portkey Do Not Track docs](https://portkey.ai/docs/product/observability/logs#do-not-track).

## Exit Codes

- `0`: All tests passed
- `1`: One or more tests failed
- `130`: User interrupted (Ctrl+C)

## Troubleshooting

**Invalid API Key**: Ensure your Portkey API key is correct and active

**Model Not Found**: Verify the model slug is configured in your Portkey dashboard

**Network Errors**: Check your internet connection and Portkey service status

**Config Errors**: If using a config ID, ensure it exists in your Portkey account

## Requirements

- Python 3.7+
- portkey-ai SDK  
- rich (for beautiful terminal output)

## License

Free to use for testing your Portkey configurations.

