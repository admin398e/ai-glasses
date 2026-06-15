# AI Glasses — Security Analysis

This document identifies known vulnerabilities in the AI Glasses system architecture,
explains how they work, and describes how they are mitigated.
**None of these are exploited in the codebase.** They are documented so the project
can be hardened before any production or public use.

---

## 1. WebSocket connection — no authentication (HIGH)

**How it works:**
The Pi connects to `ws://SERVER:8765/ws` with no token or secret. Any device on the
network (or the public internet if port 8765 is open) can connect and send commands
to the glasses — including injecting arbitrary text onto the HUD, triggering false
navigation instructions, or causing a denial-of-service by spamming the render loop.

**Attack scenario:**
An attacker on the same Wi-Fi network sends `{"type":"navigate","data":{"instruction":"Turn left"}}`.
The glasses display the false instruction. Depending on context (pedestrian, cyclist),
this is a safety risk.

**Mitigation (implement before public use):**
```python
# In server.py — add token check on WebSocket upgrade
from fastapi import Header, HTTPException

@app.websocket("/ws")
async def glasses_ws(websocket: WebSocket, token: str = None):
    if token != os.environ["WS_SECRET"]:
        await websocket.close(code=4001)
        return
    await websocket.accept()
    ...
```
And in firmware `wifi_client.py`:
```python
ws_url = f"ws://SERVER:8765/ws?token={SECRET_TOKEN}"
```

---

## 2. API key on the Pi SD card (HIGH)

**How it works (current design mitigates this partially):**
In the current architecture, the Pi does NOT hold the Claude API key — all AI calls
go to the backend. However, the backend URL + WebSocket token would be stored in
`config.py` on the SD card. If the glasses are lost or stolen, removing the SD card
gives the attacker full access to your backend server.

**Attack scenario:**
Lost glasses → SD card removed → attacker reads `config.py` → has full backend URL
and token → can send arbitrary commands to other paired glasses or access your n8n
webhooks.

**Mitigation:**
- Encrypt `config.py` at rest using the Pi's CPU serial as the decryption key
  (not perfect, but raises the bar significantly):
```bash
# On Pi: encrypt
openssl enc -aes-256-cbc -in config.py -out config.enc -k $(cat /proc/cpuinfo | grep Serial | awk '{print $3}')
# Load at runtime and decrypt in memory — never write decrypted key to disk
```
- Implement remote wipe via n8n webhook: if glasses go offline unexpectedly for >1h,
  trigger a webhook that revokes the WS token on the backend.

---

## 3. n8n webhook endpoints — no HMAC signature (MEDIUM)

**How it works:**
`/hook/notification` and `/hook/navigate` accept unauthenticated POST requests from
anyone who knows the URL. An attacker who discovers the URL can spam the glasses
with false notifications or navigation prompts.

**Attack scenario:**
Attacker calls `POST /hook/notification {"text": "Your password is being stolen"}` —
message appears on HUD.

**Mitigation:**
Add HMAC-SHA256 signature verification. n8n supports this natively:
```python
import hmac, hashlib

N8N_WEBHOOK_SECRET = os.environ["N8N_WEBHOOK_SECRET"]

def verify_n8n_signature(body: bytes, signature: str) -> bool:
    expected = hmac.new(N8N_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
```

---

## 4. HUD content injection via unsanitised text (MEDIUM)

**How it works:**
The HUD renderer displays whatever text it receives from the WebSocket without
sanitisation. If the rendering layer ever moves to HTML/web (e.g. a browser-based
display), unsanitised strings could trigger XSS.

In the current PIL/framebuffer implementation this is not an XSS risk, but very
long strings or Unicode control characters could crash the renderer or produce
confusing output (e.g. right-to-left override characters).

**Mitigation:**
```python
import unicodedata

def sanitise_hud_text(text: str, max_len: int = 80) -> str:
    # Strip control characters and right-to-left override
    cleaned = ''.join(c for c in text if unicodedata.category(c) not in ('Cc', 'Cf'))
    return cleaned[:max_len]
```

---

## 5. Replay attack on WebSocket (LOW–MEDIUM)

**How it works:**
Once an attacker captures a valid WebSocket message (e.g. via Wi-Fi sniffing on an
unencrypted network), they can replay it later. Without timestamps or nonces, the
server cannot distinguish a replayed packet from a fresh one.

**Mitigation:**
- Use `wss://` (TLS) — stops sniffing entirely
- Add a timestamp and nonce to each message; reject duplicates or messages older
  than 5 seconds

---

## 6. Physical access = full compromise (LOW — inherent to hardware)

**How it works:**
The Pi Zero 2W boots from a standard SD card. Anyone with physical access can boot
it in single-user mode or mount the card on another machine to read all files.

This is inherent to the Pi platform. It is not a software bug — it is a hardware
architecture property.

**Mitigations (layered):**
- SD card encryption (see §2)
- Remote credential revocation via n8n
- Accept that prototype hardware is not suitable for storing high-value secrets

---

## Summary table

| # | Vulnerability | Severity | Status |
|---|--------------|----------|--------|
| 1 | No WebSocket auth | HIGH | ⚠️ Document — fix before production |
| 2 | Credentials on SD card | HIGH | ⚠️ Partially mitigated by backend-only key |
| 3 | Unsigned n8n webhooks | MEDIUM | ⚠️ Fix before public deploy |
| 4 | HUD content injection | MEDIUM | ✅ Low risk on framebuffer; add sanitiser |
| 5 | WebSocket replay | LOW–MED | ✅ Use wss:// |
| 6 | Physical SD access | LOW | ⚠️ Accept on prototype; encrypt for v1.0 |

All of these are **documented only**. None are used, triggered, or demonstrated in
any part of this codebase.
