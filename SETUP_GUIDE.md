# Battery Guard — Enterprise Deployment & Operations Guide

This document provides technical instructions for deploying, configuring, and operating Battery Guard across Linux (Ubuntu 20.04+) and Windows workstation environments.

---

## Table of Contents

1. [Architecture & Prerequisites](#1-architecture--prerequisites)
2. [System Dependency Installation](#2-system-dependency-installation)
3. [Python Environment Setup](#3-python-environment-setup)
4. [Notification Channel Configuration](#4-notification-channel-configuration)
5. [Hardware Diagnostics & Compliance Export](#5-hardware-diagnostics--compliance-export)
6. [Service Execution & Deployment Modes](#6-service-execution--deployment-modes)
7. [Automated Boot Persistence](#7-automated-boot-persistence)
8. [Operational Troubleshooting](#8-operational-troubleshooting)

---

## 1. Architecture & Prerequisites

Battery Guard is designed as a modular hardware monitoring daemon. It requires access to ACPI power supply sysfs interfaces on Linux (`/sys/class/power_supply/`) or Windows battery sensor APIs via `psutil`.

### Minimum Hardware & OS Requirements
- **Linux:** Ubuntu 20.04 LTS or newer (or Debian 11+ equivalent)
- **Windows:** Windows 10 (64-bit) or Windows 11
- **Python:** Runtime version 3.10 or later
- **Hardware:** Laptop battery or Desktop uninterruptible power supply (UPS) with ACPI telemetry bindings

---

## 2. System Dependency Installation

Before setting up the Python environment, install required OS-level packages for GUI rendering, speech synthesis, desktop notifications, and power management.

### Ubuntu Linux (Debian/APT)
```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv python3-tk libnotify-bin speech-dispatcher power-profiles-daemon -y
```

### Windows
Ensure Python 3.10+ is installed from python.org with the **Add Python to PATH** option checked during installation.

---

## 3. Python Environment Setup

Navigate to the workspace root and initialize an isolated virtual environment to prevent dependency conflicts with system packages.

### Linux
```bash
cd /path/to/hp_charge
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Windows
```powershell
cd C:\path\to\hp_charge
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### Package Architecture
| Library | Purpose |
| :--- | :--- |
| `psutil` | Polling system power states, battery percentages, and AC line status |
| `customtkinter` | Rendering high-DPI dark-themed graphical interfaces |
| `pystray` | Managing persistent system tray indicators and AppIndicator bindings |
| `Pillow` | Dynamically generating tray icon bitmaps based on charge levels |
| `requests` | Executing HTTP POST/GET requests for webhooks, Telegram, Green API, and CallMeBot |
| `plyer` | Interfacing with native OS notification daemons (DBus / Win32) |

---

## 4. Notification Channel Configuration

Battery Guard supports multi-channel notification dispatching with zero polling overhead or background RAM footprint when disabled.

### Option A: Push Notifications via ntfy (Recommended for Mobile)
1. Install the **ntfy** client application on iOS or Android.
2. Subscribe to a secure, unique topic string (e.g., `corp-workstation-8841-alerts`).
3. In Battery Guard, navigate to **Settings** and input the topic string under **ntfy Topic**.
4. Select **Send Test ntfy Alert** to verify end-to-end delivery.

### Option B: Enterprise Webhooks (Slack, Teams, Discord)
1. Generate an Incoming Webhook URL from your corporate messaging platform or DevOps monitoring pipeline.
2. In Battery Guard **Settings**, paste the endpoint into the **Enterprise Webhook URL** field.
3. When alerts trigger, Battery Guard transmits structured JSON payloads containing severity level, battery percentage, and UTC timestamps.

### Option C: WhatsApp Dispatching via Green API (Recommended) or CallMeBot
#### Method 1: Green API (Free Tier, Instant Setup, No Third-Party Waiting)
1. Register an account at [green-api.com](https://green-api.com/).
2. From your dashboard, copy your instant **Instance ID** (a number like `1101823456`) and **API Token**.
3. Scan the displayed QR code using WhatsApp on your phone (**Settings → Linked Devices → Link a Device**).
4. In Battery Guard **Settings**, input your WhatsApp phone number in international format (e.g., `919876543210`) and enter your credentials in the API Key field formatted as: `instanceId/apiToken` (e.g., `1101823456/d75b3a66374942...`).

#### Method 2: CallMeBot (Legacy Fallback)
1. Add `+34 644 59 71 30` to your mobile contacts.
2. Send the message `I allow callmebot to send me messages` via WhatsApp to receive an alphanumeric API Key.
3. In Battery Guard **Settings**, input your phone number and the alphanumeric API Key.
4. *Multi-Recipient Support:* Input comma-separated phone numbers and corresponding keys to dispatch alerts to multiple administrators simultaneously.

### Option D: Telegram Bot API
1. Initiate a conversation with `@BotFather` on Telegram and execute `/newbot` to generate a Bot Token.
2. Query `@userinfobot` to retrieve your personal or group **Chat ID**.
3. Input both values into the setup wizard or **Settings** panel and select **Test Notification**.

---

## 5. Hardware Diagnostics & Compliance Export

Battery Guard interfaces directly with kernel sysfs endpoints to monitor battery wear and thermal stress.

### Telemetry Inspection
Open the primary dashboard and select **Analytics** to view:
- **Battery Health:** Actual capacity relative to factory design specifications.
- **Charge Cycles:** Total full charge/discharge cycles logged by the hardware controller.
- **Thermal Temperature:** Live ACPI/CPU thermal readings (`/sys/class/thermal/`), enabling proactive mitigation of thermal degradation.

### Compliance Audit Logging & CSV Export
All threshold violations and charging state transitions are appended to an immutable JSON-lines log at `~/.battery_guard/audit.jsonl`. 

To generate an executive compliance report for asset tracking or hardware warranty validation:
1. Open the **Analytics** dialog.
2. Select **Export CSV**.
3. A formatted spreadsheet will be generated at `~/Desktop/Battery_Guard_Enterprise_Report.csv`.

---

## 6. Service Execution & Deployment Modes

### Graphical Desktop Mode (GUI)
Launches the interactive monitoring interface and system tray indicator.

#### Linux
```bash
python3 battery_guard.py
```

#### Windows
```powershell
python battery_guard.py
```

### Headless Daemon Mode (Server / Remote)
Designed for remote Linux servers, SSH workstations, or UPS-backed systems lacking a graphical desktop. Runs silently as a background process:
```bash
python3 battery_guard.py --daemon
```

---

## 7. Automated Boot Persistence

### Option A: Built-in Application Preference
1. Open **Settings** within the GUI.
2. Check **Run on system startup** and select **Save**.
   - *Windows:* Writes a startup string to Registry `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`.
   - *Linux:* Generates a XDG autostart desktop entry at `~/.config/autostart/battery-guard.desktop`.

### Option B: Linux Systemd User Service (For Headless/Daemon Mode)
To run Battery Guard as an automated background systemd service:

```bash
mkdir -p ~/.config/systemd/user

cat > ~/.config/systemd/user/battery-guard.service << 'EOF'
[Unit]
Description=Battery Guard Daemon Service
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /path/to/hp_charge/battery_guard.py --daemon
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable battery-guard.service
systemctl --user start battery-guard.service
```

*Note:* Replace `/path/to/hp_charge/` with the absolute path to your repository installation.

---

## 8. Operational Troubleshooting

| Symptom | Root Cause | Remediation |
| :--- | :--- | :--- |
| `No battery detected` CLI error | Missing ACPI kernel bindings or desktop hardware | Verify kernel modules via `ls /sys/class/power_supply/`. |
| Missing system tray icon | Desktop environment lacks AppIndicator support | On GNOME, install `gnome-shell-extension-appindicator` and re-login. |
| Audible speech synthesis fails | Speech Dispatcher daemon not running | Execute `sudo apt install speech-dispatcher alsa-utils -y`. |
| Interface scaling issues on HiDPI | GTK/Tkinter scaling factor mismatch | Export environment variable before launch: `export GDK_SCALE=2`. |
| Webhook delivery timeouts | Network firewall blocking outbound HTTP POST | Verify outbound connectivity on port 443 via `curl -I <webhook_url>`. |

---

**Battery Guard Enterprise Deployment Guide — Version 1.0**
