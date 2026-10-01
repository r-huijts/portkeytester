# Cursor → Portkey → Kimi K2.7 Code Proxy

This README describes how an OpenAI-compatible proxy was set up so **Cursor IDE** can connect to **Portkey** via a public HTTPS endpoint, and through Portkey use the model **`kimi-k2.7-code`**.

## Background / why this proxy was needed

The original situation was that an **API key for Portkey AI Gateway** was available, along with access to a **Kimi model**. The goal was to use this model from Cursor.

The problem was that the Portkey model in question:

```text
kimi-k2.7-code
```

was a **native/reserved model name** inside Cursor. As a result, this name could not simply be added as a normal custom model in Cursor.

Normally you can solve this kind of situation within **Portkey** itself: in Portkey you create a configuration that uses a custom model name, and Portkey then maps that name to the actual provider/model. In this case, however, there was **no access to the Portkey dashboard or Portkey configuration**, only an API key.

Therefore a small custom proxy was chosen that performs exactly that translation:

```text
Cursor model:
kimi-k2.7-code-portkey

        ↓ proxy translates

Portkey model:
kimi-k2.7-code
```

### First attempt: local proxy

The first solution was a local Python/FastAPI proxy on a Windows PC:

```text
Cursor
  ↓
http://127.0.0.1:8000/v1
  ↓
local Python proxy
  ↓
Portkey
  ↓
Kimi
```

The local proxy worked technically: direct testing via PowerShell showed that the proxy could send requests to Portkey and receive a valid Kimi response.

Cursor could not use this local proxy, however. Cursor returned:

```text
Provider returned error: Access to private networks is forbidden
```

A local `127.0.0.1` endpoint was therefore not allowed from Cursor's infrastructure.

### Intermediate step: temporary public test

Before the real proxy was built, a temporary hostname was first used to prove that Cursor can reach a public HTTPS endpoint:

```text
https://cursortest.example.com/v1
```

Caddy returned fixed OpenAI-compatible JSON responses there (see [step 3](#3-temporary-public-cursor-test)). Only after that was the real proxy deployed.

### Final solution: public proxy

The same proxy was therefore eventually deployed on a public **VPS** and exposed as an HTTPS endpoint via Caddy:

```text
Cursor
  │
  │ HTTPS
  ▼
https://cursor-proxy.example.com/v1
  │
  ▼
Caddy (VPS)
  │
  ▼
Python FastAPI/Uvicorn proxy
  │
  │ translates model name
  ▼
Portkey
  │
  ▼
kimi-k2.7-code
```

The proxy solves two problems at once:

1. Cursor gets a public HTTPS endpoint instead of a local/private endpoint.
2. The Cursor model name `kimi-k2.7-code-portkey` is translated to the real Portkey model `kimi-k2.7-code`.

The final architecture:

```text
Cursor
  │
  │ HTTPS
  ▼
https://cursor-proxy.example.com/v1
  │
  ▼
Caddy (VPS)
  │
  │ HTTP
  ▼
Python FastAPI/Uvicorn proxy
  │
  │ HTTPS
  ▼
https://api.portkey.ai/v1
  │
  ▼
Portkey
  │
  ▼
kimi-k2.7-code
```

## 1. Why a proxy?

Cursor blocked a local endpoint such as:

```text
http://127.0.0.1:8000/v1
```

with:

```text
Provider returned error: Access to private networks is forbidden
```

Cursor requires a publicly reachable endpoint for custom providers. That is why the proxy was placed on a public VPS.

In addition, Cursor has a reserved/native model name:

```text
kimi-k2.7-code
```

Therefore a different model name is used in Cursor:

```text
kimi-k2.7-code-portkey
```

The proxy rewrites that name to:

```text
kimi-k2.7-code
```

before the request is sent to Portkey.

---

# 2. Requirements

On the VPS:

- Ubuntu
- Docker
- existing Caddy container
- public DNS domain
- Python 3
- Portkey API key
- Portkey supports the model `kimi-k2.7-code`

In this setup:

```text
Server IPv4:         <SERVER_IPV4>
Docker host gateway: 10.0.0.1
Caddy container:     caddy
Proxy directory:     /root/cursor-portkey-proxy
Proxy hostname:      cursor-proxy.example.com
```

DNS:

```text
cursor-proxy.example.com → <SERVER_IPV4>
```

---

# 3. Temporary public Cursor test

Before the real proxy was built, it was first proven that Cursor can reach a **public HTTPS endpoint**.

A temporary hostname was used for that:

```text
cursortest.example.com
```

That hostname returned fixed OpenAI-compatible JSON responses via Caddy. No Python proxy was needed yet.

## DNS

Create an A record:

```text
cursortest.example.com → <SERVER_IPV4>
```

With an existing wildcard Caddy config, no separate TLS certificate needs to be configured.

## Caddy test routes

Temporarily add this to the existing Caddy site, **before** `respond "Not Found" 404`:

```caddy
@cursortestchat {
    host cursortest.example.com
    path /v1/chat/completions
}
handle @cursortestchat {
    respond "{\"id\":\"chatcmpl-test\",\"object\":\"chat.completion\",\"created\":1790497000,\"model\":\"test-model\",\"choices\":[{\"index\":0,\"message\":{\"role\":\"assistant\",\"content\":\"Hello from VPS\"},\"finish_reason\":\"stop\"}],\"usage\":{\"prompt_tokens\":1,\"completion_tokens\":3,\"total_tokens\":4}}" 200
}

@cursortest host cursortest.example.com
handle @cursortest {
    respond "{\"object\":\"list\",\"data\":[{\"id\":\"test-model\",\"object\":\"model\",\"owned_by\":\"test\"}]}" 200
}
```

The chat route is intentionally placed before the general host route, so `/v1/chat/completions` gets the chat response and other paths (such as `/v1/models`) get the models list.

Then:

```bash
docker exec caddy caddy validate --config /etc/caddy/Caddyfile
docker exec caddy caddy reload --config /etc/caddy/Caddyfile
```

## Test from Windows 11 with PowerShell

```powershell
nslookup cursortest.example.com
```

Expected:

```text
Address: <SERVER_IPV4>
```

Then:

```powershell
Invoke-RestMethod https://cursortest.example.com/v1/models
```

Expected output:

```text
object data
------ ----
list {@{id=test-model; object=model; owned_by=test}}
```

## Test in Cursor

In Cursor, for the custom OpenAI-compatible provider:

```text
Base URL:
https://cursortest.example.com/v1

API Key:
anything (does not matter for this test)

Model:
test-model
```

If Cursor gets a valid response with this (for example `Hello from VPS`), it is proven that Cursor can reach a public HTTPS endpoint on the VPS.

After that, the real Python proxy could be built. The temporary `cursortest` routes are cleaned up later in step 20.

---

# 4. Test Portkey directly first

Before the proxy was built, it was verified that the Portkey API key actually has access to the model. This was done with the **Portkey AI Gateway Tester** from this repository:

```bash
python test_portkey.py
```

Portkey test settings:

```text
API key:      Portkey API key
Config ID:    empty
Endpoint:     auto-detect
Model slug:   kimi-k2.7-code
```

The test returned:

```text
PASS
model: kimi-k2.7-code
endpoint: chat
```

This confirmed that the problem was not with Portkey/Kimi.

---

# 5. Install the Python proxy

Directory:

```bash
mkdir -p /root/cursor-portkey-proxy
cd /root/cursor-portkey-proxy
```

Python virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
```

Packages:

```bash
pip install -r requirements.txt
```

---

# 6. Proxy code

File:

```text
/root/cursor-portkey-proxy/proxy.py
```

The proxy is environment-variable driven. It exposes `/v1/models` and `/v1/chat/completions`, supports streaming and non-streaming chat completions, and adds structured logging, diagnostics, request IDs, and a `/health` endpoint.

- `CURSOR_MODEL` is the model name advertised to Cursor.
- `PORTKEY_MODEL` is the real upstream model name sent to Portkey.
- `PROXY_API_KEY`, when set, secures the endpoints with `Authorization: Bearer <PROXY_API_KEY>`.
- `PORTKEY_API_KEY` is used for upstream Portkey requests.

The source file lives in this repository at:

```text
cursor-portkey-proxy/proxy.py
```

---

# 7. Environment variables

The real Portkey API key does **not** belong in the Python source code.

Create the environment file:

```text
/etc/cursor-portkey-proxy.env
```

A documented example is in this repository at:

```text
cursor-portkey-proxy/cursor-portkey-proxy.env.example
```

Required variables:

```text
PORTKEY_API_KEY=<real Portkey API key>
PROXY_API_KEY=<your own random proxy key>
```

Optional variables (shown with their defaults):

```text
PORTKEY_URL=https://api.portkey.ai/v1
CURSOR_MODEL=kimi-k2.7-code-portkey
PORTKEY_MODEL=kimi-k2.7-code
HOST=0.0.0.0
PORT=8000
FORCE_NONSTREAM=false
KEEPALIVE_INTERVAL=10
UPSTREAM_TIMEOUT=3600
```

A new random proxy key can be created with:

```bash
openssl rand -hex 32
```

File permissions:

```bash
chmod 600 /etc/cursor-portkey-proxy.env
```

Verify:

```bash
ls -l /etc/cursor-portkey-proxy.env
```

Expected:

```text
-rw------- 1 root root ...
```

### Important

The proxy key was shared in chat during testing. It was therefore treated as compromised and replaced with a new random key.

The **Portkey API key** must remain secret and must never be used in Cursor.

Cursor only receives the custom `PROXY_API_KEY`.

---

# 8. First local proxy test

During the first test, Uvicorn was started manually.

First load the environment variables:

```bash
set -a
source /etc/cursor-portkey-proxy.env
set +a
```

Then start the proxy:

```bash
cd /root/cursor-portkey-proxy
source venv/bin/activate

uvicorn proxy:app --host 127.0.0.1 --port 8000
```

In a second terminal you can then test whether `/v1/models` works:

```bash
curl -s \
  -H "Authorization: Bearer <PROXY_API_KEY>" \
  http://127.0.0.1:8000/v1/models
```

Expected response:

```json
{
  "object": "list",
  "data": [
    {
      "id": "kimi-k2.7-code-portkey",
      "object": "model",
      "owned_by": "portkey"
    }
  ]
}
```

Then a chat request:

```bash
curl -s \
  -H "Authorization: Bearer <PROXY_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "kimi-k2.7-code-portkey",
    "messages": [
      {
        "role": "user",
        "content": "Reply with exactly: Hello from Kimi."
      }
    ]
  }' \
  http://127.0.0.1:8000/v1/chat/completions
```

The response should among other things indicate:

```text
model: kimi-k2.7-code
```

This proves that the proxy can receive local requests, translate the model name, and reach Portkey/Kimi.

The binding was later changed because Caddy running in Docker needs to reach the proxy.

The final binding is:

```text
10.0.0.1:8000
```

That is the Docker host gateway.

---

# 9. Why not `0.0.0.0:8000`?

An earlier version listened on:

```text
0.0.0.0:8000
```

That means the proxy listens on all network interfaces, including the public server interface.

That is unnecessary.

The current configuration listens only on:

```text
10.0.0.1:8000
```

Check:

```bash
ss -ltnp | grep :8000
```

Expected output:

```text
LISTEN ... 10.0.0.1:8000 ...
```

Not:

```text
0.0.0.0:8000
```

Caddy can reach the proxy via the Docker network, while port 8000 does not need to be directly available via the public IP.

---

# 10. Caddy

The Caddy container already had access to:

```text
host.docker.internal
```

The host gateway is:

```text
10.0.0.1
```

The final Caddy route:

```caddy
@cursorproxy host cursor-proxy.example.com
handle @cursorproxy {
    reverse_proxy host.docker.internal:8000
}
```

This route is placed before the catch-all:

```caddy
respond "Not Found" 404
```

After changes:

```bash
docker exec caddy caddy validate --config /etc/caddy/Caddyfile
```

Then:

```bash
docker exec caddy caddy reload --config /etc/caddy/Caddyfile
```

Caddy provides HTTPS for:

```text
https://cursor-proxy.example.com
```

---

# 11. Test Caddy → proxy

First verify that Caddy can reach the host proxy:

```bash
docker exec caddy curl -4 \
  -H "Authorization: Bearer <PROXY_API_KEY>" \
  http://host.docker.internal:8000/v1/models
```

Expected response:

```json
{
  "object": "list",
  "data": [
    {
      "id": "kimi-k2.7-code-portkey",
      "object": "model",
      "owned_by": "portkey"
    }
  ]
}
```

A `401 Unauthorized` without a key or with an incorrect key means the connection works, but authentication does not.

---

# 12. Test a full chat request

From a Windows 11 PC with PowerShell that can reach the public URL:

```powershell
$headers = @{
    Authorization = "Bearer <PROXY_API_KEY>"
    "Content-Type" = "application/json"
}

$body = @{
    model = "kimi-k2.7-code-portkey"
    messages = @(
        @{
            role = "user"
            content = "Reply with exactly: Hello from Kimi."
        }
    )
} | ConvertTo-Json -Depth 5

Invoke-RestMethod `
    -Uri "https://cursor-proxy.example.com/v1/chat/completions" `
    -Method Post `
    -Headers $headers `
    -Body $body
```

The response should among other things indicate:

```text
model: kimi-k2.7-code
```

This proves that:

```text
HTTPS → Caddy → proxy → Portkey → Kimi
```

works.

---

# 13. Systemd service

The proxy is not permanently started with a manual `uvicorn` command.

File:

```text
/etc/systemd/system/cursor-portkey-proxy.service
```

Contents:

```ini
[Unit]
Description=Cursor Portkey Proxy
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/root/cursor-portkey-proxy
EnvironmentFile=/etc/cursor-portkey-proxy.env
ExecStart=/root/cursor-portkey-proxy/venv/bin/uvicorn proxy:app --host 10.0.0.1 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

After creating/changing:

```bash
systemctl daemon-reload
```

Enable and start immediately:

```bash
systemctl enable --now cursor-portkey-proxy
```

---

# 14. Check status

```bash
systemctl status cursor-portkey-proxy --no-pager
```

Expected:

```text
Active: active (running)
```

And:

```bash
ss -ltnp | grep :8000
```

Expected:

```text
LISTEN ... 10.0.0.1:8000 ...
```

Because the service is `enabled`, it starts automatically after a reboot.

---

# 15. View proxy logs

Because Uvicorn runs under systemd, the logs go to journald.

Live:

```bash
journalctl -u cursor-portkey-proxy -f
```

For example:

```text
INFO: 10.0.4.2:12345 - "GET /v1/models HTTP/1.1" 200 OK
INFO: 10.0.4.2:12346 - "POST /v1/chat/completions HTTP/1.1" 200 OK
```

Last 100 lines:

```bash
journalctl -u cursor-portkey-proxy -n 100 --no-pager
```

HTTP requests only:

```bash
journalctl -u cursor-portkey-proxy --no-pager | grep 'HTTP/1.1'
```

Live HTTP requests only:

```bash
journalctl -u cursor-portkey-proxy -f | grep --line-buffered 'HTTP/1.1'
```

---

# 16. Cursor configuration

In Cursor, do **not** use the real Portkey model as the custom model name.

Use:

```text
Base URL:
https://cursor-proxy.example.com/v1

API Key:
<PROXY_API_KEY>

Model:
kimi-k2.7-code-portkey
```

The proxy translates:

```text
kimi-k2.7-code-portkey
```

to:

```text
kimi-k2.7-code
```

and sends this to Portkey.

The Portkey API key therefore remains entirely on the VPS.

---

# 17. Final architecture

```text
                    INTERNET
                       │
                       │ HTTPS
                       ▼
        cursor-proxy.example.com
                       │
                       ▼
             ┌─────────────────┐
             │ Caddy (VPS)     │
             │                 │
             │ TLS termination │
             └────────┬────────┘
                      │
                      │ HTTP
                      │ 10.0.0.1:8000
                      ▼
             ┌─────────────────┐
             │ FastAPI/Uvicorn │
             │ Cursor Proxy    │
             └────────┬────────┘
                      │
                      │ HTTPS
                      │ API key
                      ▼
             ┌─────────────────┐
             │    Portkey      │
             └────────┬────────┘
                      │
                      ▼
             ┌─────────────────┐
             │ kimi-k2.7-code  │
             └─────────────────┘
```

---

# 18. Important security points

## Portkey API key

The Portkey API key exists only on the server:

```text
/etc/cursor-portkey-proxy.env
```

and is loaded by systemd.

Not in:

- Cursor
- `proxy.py`
- Caddyfile
- Git
- README
- chat messages

## Proxy API key

Cursor uses:

```text
PROXY_API_KEY
```

The proxy checks:

```http
Authorization: Bearer <PROXY_API_KEY>
```

Without a correct key:

```http
401 Unauthorized
```

## Port 8000

The proxy listens only on:

```text
10.0.0.1:8000
```

Not on:

```text
0.0.0.0:8000
```

Public traffic therefore goes via:

```text
443 → Caddy → 10.0.0.1:8000
```

---

# 19. Troubleshooting

## Cursor returns "Access to private networks is forbidden"

Do not use:

```text
http://127.0.0.1:8000/v1
```

or:

```text
http://192.168.x.x/...
```

Cursor must use a public HTTPS endpoint:

```text
https://cursor-proxy.example.com/v1
```

---

## Cursor returns "Empty provider response"

First check:

```bash
journalctl -u cursor-portkey-proxy -f
```

See whether requests are coming in.

Also:

```bash
docker logs caddy --tail 100
```

can be useful.

---

## 401 Unauthorized

Check:

1. `PROXY_API_KEY` in `/etc/cursor-portkey-proxy.env`
2. The API key configured in Cursor
3. The API key used in test commands

After changes:

```bash
systemctl restart cursor-portkey-proxy
```

---

## Service is not running

```bash
systemctl status cursor-portkey-proxy --no-pager
```

Detailed logs:

```bash
journalctl -u cursor-portkey-proxy -n 100 --no-pager
```

---

## Check whether port 8000 is listening

```bash
ss -ltnp | grep :8000
```

Correct:

```text
10.0.0.1:8000
```

---

## Caddy reload

After Caddy configuration changes:

```bash
docker exec caddy caddy validate --config /etc/caddy/Caddyfile
docker exec caddy caddy reload --config /etc/caddy/Caddyfile
```

---

# 20. Clean up temporary test configuration

In [step 3](#3-temporary-public-cursor-test), a temporary hostname was used:

```text
cursortest.example.com
```

with fixed Caddy responses for `/v1/models` and `/v1/chat/completions`.

Once the final proxy works, remove the temporary Caddy routes:

```caddy
@cursortestchat { ... }
handle @cursortestchat { ... }

@cursortest host cursortest.example.com
handle @cursortest { ... }
```

Then validate and reload again:

```bash
docker exec caddy caddy validate --config /etc/caddy/Caddyfile
docker exec caddy caddy reload --config /etc/caddy/Caddyfile
```

Optionally, the DNS A record for `cursortest.example.com` can also be removed.

The final hostname is:

```text
cursor-proxy.example.com
```

---

# 21. Useful management commands

### Start service

```bash
systemctl start cursor-portkey-proxy
```

### Stop

```bash
systemctl stop cursor-portkey-proxy
```

### Restart

```bash
systemctl restart cursor-portkey-proxy
```

### Status

```bash
systemctl status cursor-portkey-proxy --no-pager
```

### Live logs

```bash
journalctl -u cursor-portkey-proxy -f
```

### Recent logs

```bash
journalctl -u cursor-portkey-proxy -n 100 --no-pager
```

### Listening port

```bash
ss -ltnp | grep :8000
```

---

# 22. End result

The working configuration uses:

```text
Cursor
  Base URL: https://cursor-proxy.example.com/v1
  Model:    kimi-k2.7-code-portkey
  API key:  your own PROXY_API_KEY
```

The VPS uses:

```text
Caddy
  ↓
10.0.0.1:8000
  ↓
FastAPI/Uvicorn
  ↓
https://api.portkey.ai/v1
  ↓
kimi-k2.7-code
```

The proxy runs as:

```text
systemd service: cursor-portkey-proxy
```

and starts automatically after a reboot.

The final proxy is therefore independent of a manually opened SSH terminal and can be used from Cursor as long as the VPS, Caddy, Portkey, and DNS are available.
