# AI Glasses — Setup Guide

## Prerequisites
- Raspberry Pi Zero 2W with Raspberry Pi OS Lite (64-bit)
- SSH access to the Pi over Wi-Fi
- A VPS (Hetzner, etc.) with Python 3.11+
- Anthropic API key (claude.ai → API settings)
- n8n running on your VPS (optional)

---

## 1. Backend (Hetzner VPS)

```bash
git clone https://github.com/admin398e/ai-glasses.git
cd ai-glasses/backend

pip install -r requirements.txt

cp .env.example .env
nano .env   # Add ANTHROPIC_API_KEY and N8N_URL

# Run (dev)
uvicorn server:app --host 0.0.0.0 --port 8765

# Run (production with auto-restart)
pip install supervisor
# Or use a systemd service (see below)
```

### Systemd service (VPS)
```ini
# /etc/systemd/system/ai-glasses.service
[Unit]
Description=AI Glasses Backend
After=network.target

[Service]
WorkingDirectory=/opt/ai-glasses/backend
EnvironmentFile=/opt/ai-glasses/backend/.env
ExecStart=/usr/bin/uvicorn server:app --host 0.0.0.0 --port 8765
Restart=always

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl enable ai-glasses && sudo systemctl start ai-glasses
```

---

## 2. Firmware (Raspberry Pi Zero 2W)

```bash
# On the Pi
git clone https://github.com/admin398e/ai-glasses.git
cd ai-glasses/firmware

pip install -r requirements.txt

cp config.py config.py.bak
nano config.py   # Set BACKEND_WS_URL and BACKEND_HTTP_URL

# Test run (framebuffer — run as root or video group)
python main.py

# Auto-start on boot
sudo nano /etc/rc.local
# Add before "exit 0":
#   cd /home/pi/ai-glasses/firmware && python main.py &
```

### Add Pi user to video group (for framebuffer access)
```bash
sudo usermod -aG video pi
# Log out and back in
```

---

## 3. Companion App

Open a browser and go to:
```
http://YOUR_SERVER_IP:8765/app
```
Works on phone or desktop. No install needed.

---

## 4. Testing without hardware

On your Mac/Linux machine:
```bash
cd firmware
pip install -r requirements.txt pygame
python main.py
# A pygame window opens showing the HUD
```

---

## 5. n8n integration

In n8n, create a workflow with an HTTP Request node:
- Method: POST
- URL: `http://YOUR_SERVER_IP:8765/hook/notification`
- Body: `{"text": "{{ $json.message }}"}`

This pushes any notification from n8n directly onto the glasses HUD.
