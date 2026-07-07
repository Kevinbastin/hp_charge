# Battery Guard

Battery Guard is an enterprise-grade, cross-platform power management and diagnostic monitoring daemon designed for Linux (Ubuntu 20.04+) and Windows workstations. It combines real-time hardware telemetry, automated Linux power profile switching, multi-channel notification dispatching, and compliance audit logging into a single lightweight service.

## Overview

Modern laptop batteries and UPS systems degrade prematurely due to chronic overcharging and excessive thermal stress. Battery Guard addresses this by enforcing user-defined charging thresholds, automating system power states, and dispatching structured telemetry to corporate communication channels and audit logs.

## Key Capabilities

- **Hardware Telemetry & Thermal Monitoring:** Real-time tracking of battery health degradation percentage, cycle counts, voltage, design vs. actual Wh capacity, and ACPI motherboard/CPU thermal sensors (`/sys/class/thermal/`).
- **Multi-Channel Alert Dispatcher:** Edge-triggered notification pipeline supporting desktop popups (`plyer`), webhook endpoints (Slack, Microsoft Teams, Discord), WhatsApp messaging (multi-recipient support), Telegram bots, and ntfy push alerts. Includes built-in hysteresis and anti-flap filtering.
- **Automated Linux Power Management:** Dynamic OS power profile switching via `powerprofilesctl` (automatically enforcing `power-saver` mode at low thresholds and restoring `balanced` upon charging) and automated sleep/suspend safeguards at critical limits.
- **Compliance Audit Logging & Reporting:** Immutable JSON-lines event logging (`~/.battery_guard/audit.jsonl`) and one-click CSV spreadsheet report generation for hardware asset tracking and warranty compliance (SOC 2 / ISO 27001 ready).
- **Audible Alert Synthesis:** Native text-to-speech warnings via Ubuntu Speech Dispatcher (`spd-say`) or Windows SAPI.
- **Headless Daemon Execution:** Command-line support (`--daemon`) for remote Linux servers, workstations, and UPS monitoring without a graphical user interface.
- **System Tray & Window Management:** Persistent desktop integration with Ubuntu AppIndicator left-click menu support and Wayland/GNOME foreground window restoration.

## System Architecture

Battery Guard operates as a background polling engine with decoupled UI and alerting layers:
- `battery_guard.py`: Core application controller, Tkinter/CustomTkinter dashboard, system tray manager, and OS power state automation.
- `smart_alerts.py`: Standalone notification dispatcher handling network requests, cooldown timers, quiet hours filtering, and webhook payloads.

## System Requirements

- **Operating System:** Ubuntu Linux 20.04+ (or compatible Debian-based distributions) / Windows 10/11
- **Runtime:** Python 3.10 or later
- **System Libraries (Linux):** `python3-tk`, `libnotify-bin` (for desktop popups), `speech-dispatcher` (for speech synthesis), and `power-profiles-daemon` (for eco-mode automation)

### Python Dependencies

- `psutil` — System hardware and battery sensor access
- `customtkinter` — Dark-themed UI framework
- `pystray` — System tray and AppIndicator integration
- `Pillow` — Dynamic tray icon rendering
- `requests` — HTTP POST webhook and API communication
- `plyer` — Cross-platform desktop notifications

## Installation

### 1. Clone Repository

```bash
git clone https://github.com/Kevinbastin/hp_charge.git
cd hp_charge
```

### 2. Environment Setup

#### Linux
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

If running on Ubuntu GUI, ensure Tkinter support is installed:
```bash
sudo apt install python3-tk -y
```

#### Windows
```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

## Deployment Modes

### Graphical Desktop Mode (GUI)

Launches the full interactive dashboard, analytics dialog, and system tray indicator:

#### Linux
```bash
python3 battery_guard.py
```

#### Windows
```powershell
python battery_guard.py
```

### Headless Server Mode (Daemon)

Designed for remote Linux servers, SSH environments, or headless workstations monitoring UPS backups. Runs without a GUI while continuing all webhook, push, and audit logging pipelines:

```bash
python3 battery_guard.py --daemon
```

## Configuration Reference

User preferences and hardware thresholds are persisted in JSON format at:
```bash
~/.battery_guard/config.json
```

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `upper_threshold` | Integer | `80` | Battery percentage trigger for high charge warnings |
| `lower_threshold` | Integer | `20` | Battery percentage trigger for low battery warnings |
| `smart_alerts_enabled` | Boolean | `true` | Master switch for push, webhook, and voice notifications |
| `webhook_url` | String | `""` | Enterprise endpoint for Slack, Teams, or Discord JSON payloads |
| `ntfy_topic` | String | `""` | Topic identifier for ntfy push notification delivery |
| `whatsapp_phone` | String | `""` | Comma-separated international phone numbers for Green API or CallMeBot |
| `whatsapp_apikey` | String | `""` | Comma-separated keys: format as `instanceId/apiToken` for Green API or alphanumeric for CallMeBot |
| `telegram_token` | String | `""` | Telegram Bot API authentication token |
| `telegram_chat_id` | String | `""` | Target Telegram Chat ID or Channel ID |
| `eco_mode_enabled` | Boolean | `false` | Automatically toggle Linux `power-saver` profile at low battery |
| `auto_hibernate` | Boolean | `false` | Automatically suspend system 5 seconds after critical alert |
| `voice_enabled` | Boolean | `false` | Enable spoken text-to-speech audio warnings |
| `quiet_hours_enabled` | Boolean | `false` | Suppress desktop popups and sound between 00:00 and 07:00 |
| `run_on_startup` | Boolean | `false` | Automatically launch service on user desktop login |

## Audit Logging & Compliance Export

Battery Guard logs all threshold crossings and system power events to an immutable JSON-lines log:
```bash
~/.battery_guard/audit.jsonl
```

Each log entry is structured as follows:
```json
{"timestamp": "2026-07-07 12:30:00", "event": "alert_high", "percent": 81, "status": "triggered"}
```

To generate a human-readable compliance report for hardware lifecycle auditing or warranty claims, open the **Analytics** window in the GUI and select **Export CSV**. A timestamped spreadsheet will be saved to `~/Desktop/Battery_Guard_Enterprise_Report.csv`.

## Troubleshooting

### Sensor Not Detected
If the CLI reports `No battery detected`, verify that ACPI power supply modules are loaded in the Linux kernel (`ls /sys/class/power_supply/`) or that the system is not a desktop PC lacking a UPS sensor binding.

### Missing Tray Icon on Linux
GNOME Shell requires AppIndicator support to display system tray icons. Install the extension:
```bash
sudo apt install gnome-shell-extension-appindicator -y
```

### Audio Synthesis Failures
If audible alerts fail on Ubuntu, install Speech Dispatcher and ALSA utilities:
```bash
sudo apt install speech-dispatcher alsa-utils -y
```

### High-DPI Display Scaling
If interface elements appear too small on Linux HiDPI monitors, set the GTK scale factor before launch:
```bash
export GDK_SCALE=2
python3 battery_guard.py
```

## License

This project is open-source software. Add an appropriate license file (e.g., MIT, Apache 2.0, or GPLv3) before public distribution.
