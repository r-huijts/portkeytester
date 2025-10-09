# Portkey AI Gateway Tester

A command-line tool to test multiple models through the Portkey AI gateway using the Portkey Python SDK.

## Features

- 🔑 Test Portkey API keys
- 🎯 Support for multiple model slugs (chat completions & embeddings)
- ⚙️ Optional config ID/header support
- 📊 Clear success/error reporting
- 🚀 Dynamic model routing via Portkey
- 🔢 Dedicated embeddings endpoint testing

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

### Testing Chat Completions

Run the chat completions test script:
```bash
python test_portkey.py
```

The script will interactively prompt you for:

1. **Portkey API Key**: Your `x-portkey-api-key` value
2. **Config ID** (optional): Portkey config ID for virtual keys/routing rules
3. **Model Slugs**: Comma-separated list of model identifiers

### Testing Embeddings

**Important**: Embeddings models use a different endpoint (`/embeddings`) than chat completions (`/chat/completions`). Use the dedicated embeddings test script:

```bash
python test_embeddings.py
```

The embeddings script will prompt you for:

1. **Portkey API Key**: Your `x-portkey-api-key` value
2. **Config ID** (optional): Portkey config ID for virtual keys/routing rules
3. **Embeddings Model Slugs**: Comma-separated list of embeddings model identifiers
4. **Test Texts**: Text inputs to generate embeddings for

### Example Session - Chat Completions

```
🔑 Portkey AI Gateway Tester
============================================================

Enter your Portkey API key: pK2Zc0yDl4Mc+Engm1xQOfWWS5y0
Enter config ID (optional, press Enter to skip): 
Enter model slugs (comma-separated): mistral-medium, gpt-4, claude-3-opus

🔧 Initializing Portkey client...

📊 Testing 3 model(s)...

🧪 Testing model: mistral-medium
------------------------------------------------------------
✅ Success!
   Response: Hello! I can hear you loud and clear. How can I assist you today?
   Model used: mistral-medium
   Tokens used: CompletionUsage(completion_tokens=15, prompt_tokens=25, total_tokens=40)

🧪 Testing model: gpt-4
------------------------------------------------------------
✅ Success!
   Response: Hello!
   Model used: gpt-4
   Tokens used: CompletionUsage(completion_tokens=2, prompt_tokens=25, total_tokens=27)

...
```

### Example Session - Embeddings

```
🔢 Portkey AI Gateway Embeddings Tester
============================================================

Enter your Portkey API key: pK2Zc0yDl4Mc+Engm1xQOfWWS5y0
Enter config ID (optional, press Enter to skip): 
Enter embeddings model slugs (comma-separated): text-embedding-ada-002, text-embedding-3-small

Enter text(s) to embed (one per line, empty line to finish):
  Text 1: Hello, world!
  Text 2: Testing embeddings
  Text 3: 

🔧 Initializing Portkey client...

📊 Testing 2 embeddings model(s) with 2 text(s)...

🧪 Testing embeddings model: text-embedding-ada-002
------------------------------------------------------------
✅ Embeddings Success! API Key is working.
   Requested model: text-embedding-ada-002
   Response from model: text-embedding-ada-002
   ⏱️  Response time: 0.45s
   
   Number of embeddings: 2
   Embedding dimensions: 1536
   Sample (first 5 dims): [0.0234, -0.0156, 0.0089, -0.0234, 0.0167...]
   Tokens used: Usage(prompt_tokens=8, total_tokens=8)

...
```

## Example Model Slugs

Depending on your Portkey configuration, you can test various models:

### Chat Completion Models
- **OpenAI**: `gpt-4`, `gpt-4-turbo`, `gpt-3.5-turbo`
- **Anthropic**: `claude-3-opus`, `claude-3-sonnet`, `claude-3-haiku`
- **Mistral**: `mistral-medium`, `mistral-small`, `mistral-tiny`
- **Custom slugs**: Any model slug configured in your Portkey dashboard

### Embeddings Models
- **OpenAI**: `text-embedding-ada-002`, `text-embedding-3-small`, `text-embedding-3-large`
- **Cohere**: `embed-english-v3.0`, `embed-multilingual-v3.0`
- **Custom slugs**: Any embeddings model configured in your Portkey dashboard

> **Note**: Embeddings models require the `/embeddings` endpoint, not the `/chat/completions` endpoint. Always use `test_embeddings.py` for testing embeddings models.

## How It Works

### Chat Completions (`test_portkey.py`)
1. The script initializes a Portkey client with your API key
2. For each model slug, it sends a test chat completion request to `/chat/completions`
3. Portkey dynamically routes the request to the appropriate provider
4. The script validates the response and reports success/failure
5. A summary shows overall test results

### Embeddings (`test_embeddings.py`)
1. The script initializes a Portkey client with your API key
2. For each embeddings model, it sends text inputs to the `/embeddings` endpoint
3. Portkey routes the request to the configured embeddings provider
4. The script displays embedding dimensions and sample vectors
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
    "input": "Text to embed",
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

## License

Free to use for testing your Portkey configurations.

