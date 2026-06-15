# AI Glasses

Open-source AR glasses powered by Raspberry Pi Zero 2W, FastAPI, and Claude AI.

Phase 5 — AI engine proxied through backend (Pi never holds Claude API key).

## Architecture

```
┌──────────────────────┐        WebSocket        ┌────────────────────────┐
│  Raspberry Pi Zero 2W│ ──────────────────────▶ │   Hetzner VPS          │
│  firmware/           │                         │   backend/server.py    │
│  ├─ main.py          │ ◀────────────────────── │   ├─ /ws  (glasses)    │
│  ├─ display.py       │      HUD overlays        │   ├─ /companion        │
│  ├─ hud.py           │                         │   ├─ /ai/*  REST       │
│  ├─ wifi_client.py   │                         │   └─ /hook/* webhooks  │
│  └─ ai_engine.py     │                         └──────────┬─────────────┘
└──────────────────────┘                                    │
                                                            │ Anthropic API
         📱 Companion Web App                               ▼
         companion/index.html ──────────────▶  claude-sonnet-4-6
         (served at /app)
```

## Repo structure

```
ai-glasses/
├── firmware/          # Pi Zero 2W Python firmware
│   ├── main.py        # Coordinator — asyncio event loop
│   ├── display.py     # Framebuffer (fb0) + Pygame fallback
│   ├── hud.py         # HUD overlay renderer (PIL)
│   ├── wifi_client.py # WebSocket client with auto-reconnect
│   ├── ai_engine.py   # REST calls to backend AI endpoints
│   ├── requirements.txt
│   └── config.py      # ⚠️  NOT committed — see .gitignore
├── backend/           # FastAPI server (Hetzner VPS)
│   ├── server.py      # WebSocket hub + REST routes
│   ├── ai_bridge.py   # Claude API wrapper
│   ├── n8n_hooks.py   # Outbound n8n webhook helpers
│   ├── requirements.txt
│   └── .env.example   # Copy to .env and fill in secrets
├── companion/
│   └── index.html     # Mobile web control panel
├── docs/
│   ├── setup.md       # Full setup guide (VPS + Pi + companion)
│   └── security.md    # Known vulnerabilities + mitigations
├── hardware/
│   └── BOM.md         # Bill of materials with suppliers + prices
└── .gitignore
```

## Quick start

### 1 — Backend (Hetzner VPS)
```bash
git clone https://github.com/admin398e/ai-glasses.git
cd ai-glasses/backend
pip install -r requirements.txt
cp .env.example .env && nano .env   # add ANTHROPIC_API_KEY + N8N_URL
uvicorn server:app --host 0.0.0.0 --port 8765
```

### 2 — Firmware (Pi Zero 2W)
```bash
cd ai-glasses/firmware
pip install -r requirements.txt
# copy config.py.example to config.py and set BACKEND_WS_URL
python main.py
```

### 3 — Companion app
Open `http://YOUR_SERVER_IP:8765/app` in any browser.

### 4 — Test without hardware
```bash
pip install pygame
python firmware/main.py   # opens a pygame window
```

See [docs/setup.md](docs/setup.md) for the full guide including systemd service setup and n8n integration.

## Security

Known vulnerabilities are documented in [docs/security.md](docs/security.md) — none are exploited, all have proposed mitigations. Do not expose port 8765 to the public internet without adding WebSocket authentication first.

## Hardware

See [hardware/BOM.md](hardware/BOM.md). Total build cost estimate: £900–£1,500 across all phases.

## License

MIT
