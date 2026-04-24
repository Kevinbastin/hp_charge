# Battery Guard — Complete Setup Guide

> Cross-platform battery monitor with Telegram phone notifications.
> Works on **Windows 10/11** and **Ubuntu Linux 20.04+**

---

## Table of Contents

1. [Install Python](#1-install-python)
2. [Install Dependencies](#2-install-dependencies)
3. [Create a Telegram Bot](#3-create-a-telegram-bot)
4. [Run the App](#4-run-the-app)
5. [Auto-Start on Boot](#5-auto-start-on-boot)
6. [Troubleshooting](#6-troubleshooting)

---

## 1. Install Python

### Windows

1. Download Python 3.10+ from [python.org/downloads](https://www.python.org/downloads/)
2. **Check** "Add Python to PATH" during install
3. Verify:
   ```
   python --version
   ```

### Ubuntu Linux

```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv python3-tk -y
python3 --version
```

> [!IMPORTANT]
> On Ubuntu, `python3-tk` is required for the GUI. Install it with `sudo apt install python3-tk`.

---

## 2. Install Dependencies

Navigate to the project folder and install:

```bash
cd /path/to/hp_charge
pip install -r requirements.txt
```

On Ubuntu, if `pip` installs to a different location:
```bash
pip3 install -r requirements.txt
```

### What Gets Installed

| Package | Purpose |
|---|---|
| `psutil` | Read battery status |
| `customtkinter` | Modern dark-themed UI |
| `pystray` | System tray icon |
| `Pillow` | Tray icon image generation |
| `requests` | Telegram API calls |

---

## 3. Create a Telegram Bot

This enables **phone notifications** with vibration & sound.

### Step 1: Create the Bot

1. Open Telegram on your phone
2. Search for **@BotFather** and start a chat
3. Send: `/newbot`
4. Enter a name: `Battery Guard`
5. Enter a username: `YourName_BatteryGuard_bot` (must end with `bot`)
6. BotFather will reply with your **Bot Token** — copy it!

   Example: `7123456789:AAF1x2y3z4a5b6c7d8e9f0`

### Step 2: Get Your Chat ID

1. Search for **@userinfobot** on Telegram and start a chat
2. Send: `/start`
3. It will reply with your **Chat ID** (a number like `123456789`)

### Step 3: Activate the Bot

1. Go to your new bot's chat (search its username)
2. Press **Start** — this allows the bot to send you messages

### Step 4: Enter Credentials in Battery Guard

- On first launch, the Setup Wizard will ask for the Token and Chat ID
- You can also enter them later via **Settings (⚙)**
- Click **Test Notification** to verify it works

---

## 4. Run the App

### Windows
```
python battery_guard.py
```

### Ubuntu Linux
```bash
python3 battery_guard.py
```

### What you'll see:
- Dark dashboard with a circular battery gauge
- Live battery %, charging status, and time estimate
- System tray icon showing battery %
- On first launch: a setup wizard for Telegram

---

## 5. Auto-Start on Boot

### Option A: Use the Built-in Toggle

1. Open Battery Guard → click **⚙ Settings**
2. Enable **🚀 Run on system startup**
3. Click **Save**

This automatically registers the app:
- **Windows**: Adds to Registry `HKCU\...\Run`
- **Linux**: Creates `~/.config/autostart/battery-guard.desktop`

### Option B: Manual Setup

#### Windows — Task Scheduler

1. Press `Win + R` → type `taskschd.msc`
2. Click **Create Basic Task**
3. Name: `Battery Guard`
4. Trigger: **When I log on**
5. Action: **Start a program**
6. Program: `pythonw`
7. Arguments: `"C:\path\to\battery_guard.py"`
8. Finish

#### Ubuntu — Systemd User Service

```bash
mkdir -p ~/.config/systemd/user

cat > ~/.config/systemd/user/battery-guard.service << 'EOF'
[Unit]
Description=Battery Guard Monitor
After=graphical-session.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /path/to/battery_guard.py
Restart=on-failure
RestartSec=5
Environment=DISPLAY=:0

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable battery-guard.service
systemctl --user start battery-guard.service
```

Replace `/path/to/battery_guard.py` with the actual path.

---

## 6. Troubleshooting

### "No battery detected"
- You're running on a desktop PC without a battery
- The app requires a laptop battery to function

### Tray icon not showing (Ubuntu)
Install the GNOME tray extension:
```bash
sudo apt install gnome-shell-extension-appindicator -y
```
Then log out and back in.

### No sound on Ubuntu
```bash
sudo apt install pulseaudio-utils alsa-utils -y
```

### Telegram test fails
- Double-check the Bot Token and Chat ID
- Make sure you pressed **Start** in the bot's chat
- Check your internet connection

### GUI looks small on HiDPI
Set scaling before running:
```bash
export GDK_SCALE=2
python3 battery_guard.py
```

---

## Quick Reference

| Action | How |
|---|---|
| Open settings | Click ⚙ in top bar |
| Minimize to tray | Close the window (X button) |
| Open from tray | Right-click tray icon → Open App |
| Test alerts | Right-click tray icon → Test Notification |
| Exit completely | Right-click tray icon → Exit |

---

**Made with ❤ — Battery Guard v1.0**
