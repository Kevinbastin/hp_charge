# Battery Guard

Battery Guard is a cross-platform battery monitoring application with a modern dark interface, Telegram notifications, system tray support, and configurable alerts for charging and low battery conditions.

It is designed for laptops running Windows 10/11 or Ubuntu Linux 20.04+.

## Features

- Live battery percentage monitoring
- Charging and discharging status detection
- Estimated time remaining or time to full charge
- Custom alert thresholds for high and low battery levels
- Telegram notifications for remote alerts
- Optional sound alerts
- Alert popups with snooze and dismiss actions
- System tray icon with quick actions
- First-run setup wizard
- Optional startup launch on Windows and Linux
- Optional automatic suspend when the battery reaches the configured upper limit

## Screenshots

No screenshots are included in this repository yet. Add them here if you want to document the interface visually.

## Requirements

- Python 3.10 or later recommended
- A laptop battery, since the app uses system battery sensors
- Internet access for Telegram notifications
- On Linux, `python3-tk` may be required for the GUI

### Python packages

The project depends on:

- `psutil`
- `customtkinter`
- `pystray`
- `Pillow`
- `requests`

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/Kevinbastin/hp_charge.git
cd hp_charge
```

### 2. Create and activate a virtual environment

Linux:

```bash
python3 -m venv venv
source venv/bin/activate
```

Windows:

```powershell
python -m venv venv
venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

If you are on Ubuntu and the GUI does not start, install Tk support:

```bash
sudo apt install python3-tk -y
```

## Running the application

Linux:

```bash
python3 battery_guard.py
```

Windows:

```powershell
python battery_guard.py
```

## First launch

On the first launch, Battery Guard opens a setup wizard where you can enter your Telegram bot token and chat ID.

You can also open the settings panel later from the gear button in the app.

## Telegram setup

To receive battery alerts on your phone:

1. Open Telegram and chat with @BotFather
2. Create a new bot using `/newbot`
3. Copy the bot token provided by BotFather
4. Open Telegram and chat with @userinfobot
5. Start the bot and copy your chat ID
6. Open Battery Guard and enter both values in the setup wizard or settings panel
7. Use the test notification button to verify the connection

## How the alerts work

Battery Guard monitors battery state in the background and triggers alerts based on your configured thresholds.

Default values:

- High battery alert: 80 percent
- Low battery alert: 20 percent

### High battery alert

When the battery reaches or exceeds the upper threshold while charging, the app will:

- Show an alert popup
- Optionally play a sound
- Send a Telegram message if configured
- Optionally suspend the machine after a short delay if auto suspend is enabled

### Low battery alert

When the battery reaches or goes below the lower threshold while not charging, the app will:

- Show an alert popup
- Optionally play a sound
- Send a Telegram message if configured

## System tray behavior

The app minimizes to the system tray when the window is closed.

Tray menu options include:

- Open App
- Test Notification
- Exit

## Settings

The settings panel lets you configure:

- Charge alert threshold
- Low battery alert threshold
- Telegram bot token
- Telegram chat ID
- Sound alerts
- Auto suspend at limit
- Launch on startup

## Startup on boot

Battery Guard can be configured to launch automatically when you log in.

### Windows

The app creates a registry startup entry under the current user profile.

### Linux

The app creates a desktop autostart file in:

```bash
~/.config/autostart/battery-guard.desktop
```

## Configuration file

User settings are stored in:

```bash
~/.battery_guard/config.json
```

This file is created automatically after the first save.

## Project files

- `battery_guard.py`: Main application
- `requirements.txt`: Python dependencies
- `SETUP_GUIDE.md`: Detailed setup guide
- `README.md`: Project overview and usage

## Troubleshooting

### No battery detected

This usually means the app is running on a desktop PC or a system where battery sensors are not available.

### Telegram notifications do not arrive

Check the following:

- Bot token is correct
- Chat ID is correct
- You pressed Start in the bot chat
- The device has internet access

### No tray icon on Linux

Some desktop environments require tray or AppIndicator support to be enabled.

### No sound alerts on Linux

Install audio utilities:

```bash
sudo apt install pulseaudio-utils alsa-utils -y
```

### GUI looks too small on high-DPI displays

Try increasing scaling before launching the app:

```bash
export GDK_SCALE=2
python3 battery_guard.py
```

## Notes

- The app is intended for laptops with a real battery sensor
- Telegram messages are sent through the Telegram Bot API
- The application runs continuously in the background while monitoring is active

## License

No license file is included in this repository. Add one if you plan to publish or distribute the project.
