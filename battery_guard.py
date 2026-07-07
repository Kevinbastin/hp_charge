#!/usr/bin/env python3
"""
Battery Guard — Cross-Platform Battery Monitor with Telegram Notifications
Works on Windows 10/11 and Ubuntu Linux 20.04+
"""

import json
import math
import os
import platform
import subprocess
import sys
import threading
import time
import tkinter as tk
from datetime import datetime, timedelta
from pathlib import Path

import customtkinter as ctk
import psutil
import requests
from PIL import Image, ImageDraw, ImageFont
from smart_alerts import SmartAlerts

# ─── Platform Detection ──────────────────────────────────────────────────────
IS_WINDOWS = platform.system() == "Windows"
IS_LINUX = platform.system() == "Linux"

if IS_WINDOWS:
    import winsound

# ─── Config File Path ────────────────────────────────────────────────────────
CONFIG_DIR = Path.home() / ".battery_guard"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CONFIG = {
    "upper_threshold": 80,
    "lower_threshold": 20,
    "telegram_token": "",
    "telegram_chat_id": "",
    "smart_alerts_enabled": True,
    "whatsapp_phone": "",
    "whatsapp_apikey": "",
    "ntfy_topic": "",
    "quiet_hours_enabled": False,
    "sound_enabled": True,
    "auto_hibernate": False,
    "run_on_startup": False,
    "first_launch_done": False,
}


def load_config():
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                saved = json.load(f)
            cfg = DEFAULT_CONFIG.copy()
            cfg.update(saved)
            return cfg
        except Exception:
            return DEFAULT_CONFIG.copy()
    return DEFAULT_CONFIG.copy()


def apply_hardware_charging_threshold(upper_limit):
    """
    Attempts to write the upper charging threshold directly to the Linux kernel sysfs interface.
    This enables hardware-level charging cutoff without requiring the user to unplug!
    Supports HP, Lenovo, ASUS, and Dell kernel modules.
    """
    if not IS_LINUX:
        return
    sysfs_paths = [
        "/sys/class/power_supply/BAT0/charge_control_end_threshold",
        "/sys/class/power_supply/BAT0/charge_stop_threshold",
        "/sys/class/power_supply/BAT1/charge_control_end_threshold",
        "/sys/class/power_supply/BAT1/charge_stop_threshold",
    ]
    for path in sysfs_paths:
        if os.path.exists(path):
            try:
                with open(path, "w") as f:
                    f.write(str(int(upper_limit)))
                print(f"[Hardware Cutoff] Successfully set kernel charging limit {upper_limit}% on {path}")
                break
            except Exception as e:
                print(f"[Hardware Cutoff] Notice: Could not write kernel threshold to {path}: {e}")

def save_config(cfg):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)
    try:
        os.chmod(CONFIG_FILE, 0o600)
    except Exception:
        pass
    apply_hardware_charging_threshold(cfg.get("upper_threshold", 80))


# ─── Premium Color Palette ───────────────────────────────────────────────────
C = {
    # Backgrounds
    "bg":          "#0B0E14",
    "bg_surface":  "#111621",
    "bg_card":     "#161B28",
    "bg_card_alt": "#1C2333",
    "bg_hover":    "#1E2738",
    "bg_input":    "#0F1319",

    # Borders
    "border":      "#1E293B",
    "border_focus":"#3B82F6",

    # Accent colors
    "blue":        "#3B82F6",
    "blue_hover":  "#2563EB",
    "cyan":        "#06B6D4",
    "cyan_dim":    "#0891B2",

    # Status colors
    "green":       "#10B981",
    "green_dim":   "#059669",
    "yellow":      "#F59E0B",
    "yellow_dim":  "#D97706",
    "red":         "#EF4444",
    "red_dim":     "#DC2626",
    "orange":      "#F97316",

    # Text
    "text":        "#F1F5F9",
    "text_dim":    "#94A3B8",
    "text_muted":  "#64748B",

    # Buttons
    "btn_primary": "#3B82F6",
    "btn_success": "#10B981",
    "btn_danger":  "#EF4444",
}

# ─── Font Helpers ─────────────────────────────────────────────────────────────
FONT_FAMILY = "Segoe UI" if IS_WINDOWS else "Ubuntu"
FONT_MONO = "Cascadia Code" if IS_WINDOWS else "Ubuntu Mono"

def font(size, weight="normal"):
    return (FONT_FAMILY, size, weight)

def font_bold(size):
    return (FONT_FAMILY, size, "bold")

def font_mono(size):
    return (FONT_MONO, size)

# ─── Telegram Helper ─────────────────────────────────────────────────────────

def send_telegram(token, chat_id, message):
    if not token or not chat_id:
        return False, "Telegram not configured"
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        resp = requests.post(url, json={
            "chat_id": chat_id, "text": message, "parse_mode": "HTML",
        }, timeout=10)
        if resp.status_code == 200 and resp.json().get("ok"):
            return True, ""
        return False, resp.text
    except Exception as e:
        return False, str(e)


# ─── Cross-Platform Beep ─────────────────────────────────────────────────────

def beep_once():
    try:
        if IS_WINDOWS:
            winsound.Beep(1000, 500)
        elif IS_LINUX:
            for cmd in [
                ["paplay", "/usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga"],
                ["aplay", "-D", "default", "/usr/share/sounds/alsa/Front_Center.wav"],
            ]:
                try:
                    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return
                except FileNotFoundError:
                    continue
            print("\a", flush=True)
    except Exception:
        print("\a", flush=True)


# ─── Battery Health & Diagnostics ────────────────────────────────────────────

def get_battery_diagnostics():
    diag = {
        "health": "100%",
        "cycles": "0 cycles",
        "capacity_now": "N/A",
        "capacity_design": "N/A",
        "voltage": "N/A",
        "tech": "Li-ion"
    }
    try:
        if IS_LINUX:
            base = "/sys/class/power_supply/BAT0/"
            if os.path.exists(base):
                try:
                    ef = float(open(base + "energy_full").read().strip()) / 1e6
                    efd = float(open(base + "energy_full_design").read().strip()) / 1e6
                    diag["capacity_now"] = f"{ef:.1f} Wh"
                    diag["capacity_design"] = f"{efd:.1f} Wh"
                    if efd > 0:
                        health_pct = min(100, int((ef / efd) * 100))
                        diag["health"] = f"{health_pct}%"
                        wear_pct = max(0, 100 - health_pct)
                        diag["wear_percent"] = f"{wear_pct}%"
                        diag["wear_forecast"] = f"Est. lifespan: ~{max(6, int((100 - wear_pct) * 0.45))} months remaining"
                except Exception:
                    pass
                try:
                    cycles = open(base + "cycle_count").read().strip()
                    diag["cycles"] = f"{cycles} cycles"
                except Exception:
                    pass
                try:
                    volts = float(open(base + "voltage_now").read().strip()) / 1e6
                    diag["voltage"] = f"{volts:.1f} V"
                except Exception:
                    pass
                try:
                    diag["tech"] = open(base + "technology").read().strip()
                except Exception:
                    pass
                try:
                    tz = "/sys/class/thermal/thermal_zone0/temp"
                    if os.path.exists(tz):
                        t = float(open(tz).read().strip()) / 1000.0
                        diag["temp"] = f"{t:.1f}°C"
                except Exception:
                    pass
        elif IS_WINDOWS:
            diag["health"] = "100%"
            diag["cycles"] = "Good"
            diag["temp"] = "Normal"
            diag["wear_percent"] = "0%"
            diag["wear_forecast"] = "Optimal condition"
    except Exception:
        pass
    if "temp" not in diag:
        diag["temp"] = "N/A"
    if "wear_percent" not in diag:
        diag["wear_percent"] = "0%"
        diag["wear_forecast"] = "Optimal condition"

    try:
        bat = psutil.sensors_battery()
        if bat:
            target_limit = 80 if bat.power_plugged else 20
            time_str, desc_str, _ = drain_predictor.predict(bat.percent, bat.power_plugged, target_limit)
            diag["time_left"] = time_str
            diag["time_to_target"] = f"{time_str} ({desc_str})"
        else:
            diag["time_left"] = "Calculating..."
            diag["time_to_target"] = "Calculating draw..."
    except Exception:
        diag["time_left"] = "N/A"
        diag["time_to_target"] = "N/A"

    return diag


# ─── Historical Time-Series Drain Predictor ──────────────────────────────────

class HistoricalDrainPredictor:
    """
    Lightweight, low-RAM, local time-series pattern predictor.
    Instead of instantaneous OS calculations that swing wildly when you launch an app,
    this logs historical drain/charge rates by (day_of_week, hour_of_day) in an exponentially
    weighted moving average (EMA). It predicts when you will hit your target thresholds
    based on your personalized historical routine (e.g. 'typical Tuesday afternoon usage').
    """
    def __init__(self):
        self.history_file = Path.home() / ".battery_guard" / "drain_history.json"
        self.history_data = self._load()
        self._last_log_time = 0
        self._last_log_percent = -1
        self._last_log_charging = None

    def _load(self):
        if self.history_file.exists():
            try:
                with open(self.history_file, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"discharge": {}, "charge": {}}

    def _save(self):
        try:
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.history_file, "w") as f:
                json.dump(self.history_data, f, indent=2)
            try:
                os.chmod(self.history_file, 0o600)
            except Exception:
                pass
        except Exception:
            pass

    def log_sample(self, percent, is_charging):
        now = time.time()
        if self._last_log_percent == -1 or self._last_log_charging != is_charging:
            self._last_log_time = now
            self._last_log_percent = percent
            self._last_log_charging = is_charging
            return

        elapsed_hours = (now - self._last_log_time) / 3600.0
        if elapsed_hours >= (3.0 / 60.0) and abs(percent - self._last_log_percent) >= 1:
            rate_per_hour = abs(percent - self._last_log_percent) / max(0.01, elapsed_hours)
            if 0.5 <= rate_per_hour <= 100.0:
                dt = datetime.now()
                key = f"{dt.weekday()}_{dt.hour}"
                bucket = "charge" if is_charging else "discharge"
                if key not in self.history_data[bucket]:
                    self.history_data[bucket][key] = {"rate": round(rate_per_hour, 2), "samples": 1}
                else:
                    old_rate = self.history_data[bucket][key]["rate"]
                    new_rate = round(0.7 * old_rate + 0.3 * rate_per_hour, 2)
                    self.history_data[bucket][key]["rate"] = new_rate
                    self.history_data[bucket][key]["samples"] += 1
                self._save()
            self._last_log_time = now
            self._last_log_percent = percent

    def predict(self, current_percent, is_charging, target_percent):
        dt = datetime.now()
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        day_str = day_names[dt.weekday()]
        
        if 5 <= dt.hour < 12:
            period_str = "morning"
        elif 12 <= dt.hour < 17:
            period_str = "afternoon"
        elif 17 <= dt.hour < 22:
            period_str = "evening"
        else:
            period_str = "night"

        bucket = "charge" if is_charging else "discharge"
        key = f"{dt.weekday()}_{dt.hour}"
        
        rate_per_hour = None
        desc = f"Based on typical {day_str} {period_str} usage"
        
        if key in self.history_data[bucket] and self.history_data[bucket][key]["samples"] >= 2:
            rate_per_hour = self.history_data[bucket][key]["rate"]
        else:
            all_rates = [v["rate"] for v in self.history_data[bucket].values() if v["samples"] >= 1]
            if all_rates:
                rate_per_hour = sum(all_rates) / len(all_rates)
                desc = "Based on your historical average pattern"
            else:
                rate_per_hour = 45.0 if is_charging else 12.0
                desc = "Based on baseline pattern (learning in progress...)"

        if rate_per_hour <= 0:
            return ("Calculating...", "Gathering pattern data...", 0)

        remaining_pct = abs(target_percent - current_percent)
        hours_remaining = remaining_pct / rate_per_hour
        total_mins = int(hours_remaining * 60)
        
        hrs = total_mins // 60
        mins = total_mins % 60
        
        target_time = dt + timedelta(minutes=total_mins)
        clock_str = target_time.strftime("%I:%M %p").lstrip("0")
        
        if hrs > 0:
            time_str = f"{hrs}h {mins}m (around {clock_str})"
        else:
            time_str = f"{mins}m (around {clock_str})"
            
        return (time_str, desc, total_mins)

# Global singleton instance
drain_predictor = HistoricalDrainPredictor()


# ─── Tray Icon ───────────────────────────────────────────────────────────────

def create_tray_icon_image(percent, color="#10B981"):
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([2, 2, 62, 62], fill=color, outline="#FFFFFF", width=2)
    text = str(int(percent))
    try:
        fnt = ImageFont.truetype("arial.ttf", 24)
    except (IOError, OSError):
        try:
            fnt = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
        except (IOError, OSError):
            fnt = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), text, font=fnt)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((64 - tw) / 2, (64 - th) / 2 - 2), text, fill="#FFFFFF", font=fnt)
    return img


class TrayManager:
    def __init__(self, app):
        self.app = app
        self.icon = None
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        try:
            import pystray
            from pystray import MenuItem, Menu

            battery = psutil.sensors_battery()
            pct = battery.percent if battery else 50
            color = self._pct_color(pct)

            def on_open(icon, item):
                self.app.after(0, self.app.show_window)
            def on_test(icon, item):
                self.app.after(0, self.app.test_notification)
            def on_exit(icon, item):
                icon.stop()
                self.app.after(0, self.app.quit_app)

            menu = Menu(
                MenuItem(f"Battery: {int(pct)}%", None, enabled=False),
                Menu.SEPARATOR,
                MenuItem("Open App", on_open, default=True),
                MenuItem("Test Notification", on_test),
                Menu.SEPARATOR,
                MenuItem("Exit", on_exit),
            )
            self.icon = pystray.Icon("BatteryGuard", create_tray_icon_image(pct, color),
                                     "Battery Guard", menu)
            self.icon.run()
        except Exception as e:
            print(f"[Tray] Error: {e}")

    def update(self, percent):
        if self.icon:
            try:
                import pystray
                from pystray import MenuItem, Menu
                color = self._pct_color(percent)
                self.icon.icon = create_tray_icon_image(percent, color)
                self.icon.title = f"Battery Guard — {int(percent)}%"
                def on_open(icon, item):
                    self.app.after(0, self.app.show_window)
                def on_test(icon, item):
                    self.app.after(0, self.app.test_notification)
                def on_exit(icon, item):
                    icon.stop()
                    self.app.after(0, self.app.quit_app)
                self.icon.menu = Menu(
                    MenuItem(f"Battery: {int(percent)}%", None, enabled=False),
                    Menu.SEPARATOR,
                    MenuItem("Open App", on_open, default=True),
                    MenuItem("Test Notification", on_test),
                    Menu.SEPARATOR,
                    MenuItem("Exit", on_exit),
                )
            except Exception:
                pass

    def stop(self):
        if self.icon:
            try:
                self.icon.stop()
            except Exception:
                pass

    @staticmethod
    def _pct_color(pct):
        if pct > 80:
            return C["red"]
        elif pct > 70:
            return C["yellow"]
        return C["green"]


# ─── Alert Popup ─────────────────────────────────────────────────────────────

class AlertPopup(ctk.CTkToplevel):
    def __init__(self, parent, alert_type, percent, on_snooze, on_dismiss):
        super().__init__(parent)
        self.on_snooze = on_snooze
        self.on_dismiss = on_dismiss
        self._beeping = True
        self._destroyed = False

        self.title("Battery Guard — Alert")
        self.geometry("500x420")
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.configure(fg_color=C["bg"])
        self.protocol("WM_DELETE_WINDOW", self._snooze)
        self.after(100, lambda: (self.focus_force(), self.lift()))

        # Top accent stripe
        if alert_type == "high":
            accent = C["red"]
            icon_text = "⚡"
            title = "UNPLUG CHARGER"
            subtitle = f"Battery reached {int(percent)}%"
            detail = "To preserve battery health, disconnect the charger now."
        else:
            accent = C["orange"]
            icon_text = "🔋"
            title = "LOW BATTERY"
            subtitle = f"Battery is at {int(percent)}%"
            detail = "Connect your charger to avoid losing work."

        # Accent bar
        bar = ctk.CTkFrame(self, height=4, fg_color=accent, corner_radius=0)
        bar.pack(fill="x")

        # Main content
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(expand=True, fill="both", padx=40, pady=20)

        # Icon circle
        icon_frame = ctk.CTkFrame(content, width=80, height=80,
                                   fg_color=C["bg_card"], corner_radius=40,
                                   border_width=2, border_color=accent)
        icon_frame.pack(pady=(10, 15))
        icon_frame.pack_propagate(False)
        ctk.CTkLabel(icon_frame, text=icon_text, font=("Segoe UI Emoji", 36)).place(
            relx=0.5, rely=0.5, anchor="center")

        # Title
        ctk.CTkLabel(content, text=title, font=font_bold(26),
                     text_color=accent).pack(pady=(0, 4))

        # Subtitle
        ctk.CTkLabel(content, text=subtitle, font=font(16),
                     text_color=C["text"]).pack(pady=(0, 4))

        # Detail
        ctk.CTkLabel(content, text=detail, font=font(13),
                     text_color=C["text_muted"]).pack(pady=(0, 8))

        # Time
        ctk.CTkLabel(content, text=datetime.now().strftime("%I:%M %p · %B %d, %Y"),
                     font=font(12), text_color=C["text_muted"]).pack(pady=(0, 20))

        # Buttons
        btn_frame = ctk.CTkFrame(content, fg_color="transparent")
        btn_frame.pack(fill="x")

        ctk.CTkButton(btn_frame, text="Snooze 5 min", width=200, height=44,
                      font=font_bold(14), corner_radius=8,
                      fg_color=C["bg_card"], border_width=1,
                      border_color=C["border"],
                      hover_color=C["bg_hover"],
                      text_color=C["text"],
                      command=self._snooze).pack(side="left", padx=(0, 8), expand=True, fill="x")

        dismiss_text = "I unplugged it" if alert_type == "high" else "I plugged it in"
        ctk.CTkButton(btn_frame, text=dismiss_text, width=200, height=44,
                      font=font_bold(14), corner_radius=8,
                      fg_color=C["btn_success"],
                      hover_color=C["green_dim"],
                      command=self._dismiss_action).pack(side="left", padx=(8, 0), expand=True, fill="x")

        # Start beep
        self._beep_thread = threading.Thread(target=self._beep_loop, daemon=True)
        self._beep_thread.start()

    def _beep_loop(self):
        while self._beeping and not self._destroyed:
            if self.master and hasattr(self.master, 'config_data') and \
               self.master.config_data.get("sound_enabled", True):
                beep_once()
            time.sleep(5)

    def _snooze(self):
        self._beeping = False
        self._destroyed = True
        self.on_snooze()
        try: self.destroy()
        except: pass

    def _dismiss_action(self):
        self._beeping = False
        self._destroyed = True
        self.on_dismiss()
        try: self.destroy()
        except: pass

    def close(self):
        self._beeping = False
        self._destroyed = True
        try: self.destroy()
        except: pass


# ─── First Launch Wizard ─────────────────────────────────────────────────────

class SetupWizard(ctk.CTkToplevel):
    def __init__(self, parent, config, on_complete):
        super().__init__(parent)
        self.config = config
        self.on_complete = on_complete

        self.title("Battery Guard — Setup")
        self.geometry("480x560")
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.configure(fg_color=C["bg"])
        self.protocol("WM_DELETE_WINDOW", self._skip)
        self.after(100, lambda: self.focus_force())

        # Top accent
        ctk.CTkFrame(self, height=3, fg_color=C["blue"], corner_radius=0).pack(fill="x")

        # Header area
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=40, pady=(30, 0))

        ctk.CTkLabel(header, text="Setup Notifications",
                     font=font_bold(22), text_color=C["text"],
                     anchor="w").pack(fill="x")
        ctk.CTkLabel(header, text="Connect your Telegram bot to receive battery alerts on your phone.",
                     font=font(13), text_color=C["text_muted"],
                     anchor="w", wraplength=400).pack(fill="x", pady=(4, 0))

        # Form card
        card = ctk.CTkFrame(self, fg_color=C["bg_card"], corner_radius=10,
                            border_width=1, border_color=C["border"])
        card.pack(fill="x", padx=40, pady=(20, 0))

        # Token field
        ctk.CTkLabel(card, text="Bot Token", font=font_bold(12),
                     text_color=C["text_dim"], anchor="w").pack(padx=20, pady=(16, 0), fill="x")
        ctk.CTkLabel(card, text="From @BotFather on Telegram", font=font(11),
                     text_color=C["text_muted"], anchor="w").pack(padx=20, pady=(2, 0), fill="x")
        self.token_entry = ctk.CTkEntry(card, placeholder_text="Paste your bot token here",
                                        height=40, font=font_mono(12),
                                        fg_color=C["bg_input"], border_width=1,
                                        border_color=C["border"],
                                        corner_radius=6)
        self.token_entry.pack(padx=20, pady=(6, 0), fill="x")
        if self.config.get("telegram_token"):
            self.token_entry.insert(0, self.config["telegram_token"])

        # Separator
        ctk.CTkFrame(card, height=1, fg_color=C["border"]).pack(fill="x", padx=20, pady=(16, 0))

        # Chat ID field
        ctk.CTkLabel(card, text="Chat ID", font=font_bold(12),
                     text_color=C["text_dim"], anchor="w").pack(padx=20, pady=(12, 0), fill="x")
        ctk.CTkLabel(card, text="From @userinfobot on Telegram", font=font(11),
                     text_color=C["text_muted"], anchor="w").pack(padx=20, pady=(2, 0), fill="x")
        self.chat_entry = ctk.CTkEntry(card, placeholder_text="Your numeric chat ID",
                                       height=40, font=font_mono(12),
                                       fg_color=C["bg_input"], border_width=1,
                                       border_color=C["border"],
                                       corner_radius=6)
        self.chat_entry.pack(padx=20, pady=(6, 16), fill="x")
        if self.config.get("telegram_chat_id"):
            self.chat_entry.insert(0, self.config["telegram_chat_id"])

        # Status
        self.status_label = ctk.CTkLabel(self, text="", font=font(12), text_color=C["green"])
        self.status_label.pack(pady=(12, 0))

        # Buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=40, pady=(12, 0))

        ctk.CTkButton(btn_frame, text="Test Connection", height=42,
                      font=font_bold(13), corner_radius=8,
                      fg_color=C["bg_card"], border_width=1,
                      border_color=C["border"],
                      hover_color=C["bg_hover"],
                      text_color=C["text"],
                      command=self._test).pack(side="left", expand=True, fill="x", padx=(0, 6))

        ctk.CTkButton(btn_frame, text="Save & Continue", height=42,
                      font=font_bold(13), corner_radius=8,
                      fg_color=C["btn_primary"],
                      hover_color=C["blue_hover"],
                      command=self._save).pack(side="left", expand=True, fill="x", padx=(6, 0))

        # Skip link
        ctk.CTkButton(self, text="Skip for now", width=100, height=30,
                      font=font(12), fg_color="transparent",
                      hover_color=C["bg_surface"],
                      text_color=C["text_muted"],
                      command=self._skip).pack(pady=(8, 16))

    def _test(self):
        token = self.token_entry.get().strip()
        chat_id = self.chat_entry.get().strip()
        if not token or not chat_id:
            self.status_label.configure(text="Please fill in both fields", text_color=C["yellow"])
            return
        self.status_label.configure(text="Sending test message...", text_color=C["cyan"])
        self.update()
        ok, err = send_telegram(token, chat_id,
                                "✅ <b>Battery Guard</b> connected successfully!\nYou'll receive battery alerts here.")
        if ok:
            self.status_label.configure(text="✓ Connected! Check your Telegram.", text_color=C["green"])
        else:
            self.status_label.configure(text=f"✗ Failed: {err[:55]}", text_color=C["red"])

    def _save(self):
        self.config["telegram_token"] = self.token_entry.get().strip()
        self.config["telegram_chat_id"] = self.chat_entry.get().strip()
        self.config["first_launch_done"] = True
        save_config(self.config)
        self.status_label.configure(text="✓ Setup complete!", text_color=C["green"])
        self.after(600, self._finish)

    def _skip(self):
        self.config["first_launch_done"] = True
        save_config(self.config)
        self._finish()

    def _finish(self):
        self.on_complete()
        try: self.destroy()
        except: pass


# ─── Settings Panel ──────────────────────────────────────────────────────────

class SettingsPanel(ctk.CTkToplevel):
    def __init__(self, parent, config, on_save):
        super().__init__(parent)
        self.config = config.copy()
        self.on_save = on_save

        self.title("Battery Guard — Settings")
        self.geometry("480x660")
        self.resizable(False, False)
        self.configure(fg_color=C["bg"])
        self.attributes("-topmost", True)
        self.after(100, lambda: self.focus_force())

        # Top accent
        ctk.CTkFrame(self, height=3, fg_color=C["blue"], corner_radius=0).pack(fill="x")

        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=30, pady=(20, 0))
        ctk.CTkLabel(header, text="Settings", font=font_bold(22),
                     text_color=C["text"], anchor="w").pack(fill="x")

        # Scroll area
        scroll = ctk.CTkScrollableFrame(self, fg_color=C["bg"],
                                         scrollbar_button_color=C["bg_card"])
        scroll.pack(fill="both", expand=True, padx=20, pady=(10, 0))

        # Fix Linux/X11 & Windows mousewheel scrolling across all child widgets
        def _on_mousewheel(event):
            try:
                if event.num == 4 or getattr(event, "delta", 0) > 0:
                    scroll._parent_canvas.yview_scroll(-1, "units")
                elif event.num == 5 or getattr(event, "delta", 0) < 0:
                    scroll._parent_canvas.yview_scroll(1, "units")
            except Exception:
                pass

        self.bind_all("<Button-4>", _on_mousewheel, add="+")
        self.bind_all("<Button-5>", _on_mousewheel, add="+")
        self.bind_all("<MouseWheel>", _on_mousewheel, add="+")

        def _cleanup_binds(event):
            if event.widget == self:
                try:
                    self.unbind_all("<Button-4>")
                    self.unbind_all("<Button-5>")
                    self.unbind_all("<MouseWheel>")
                except Exception:
                    pass
        self.bind("<Destroy>", _cleanup_binds)

        # ── Alert Thresholds ──
        self._section(scroll, "Alert Thresholds")

        card1 = self._card(scroll)

        ctk.CTkLabel(card1, text="Charge alert (unplug)", font=font(12),
                     text_color=C["text_dim"], anchor="w").pack(padx=16, pady=(12, 0), fill="x")
        slider_frame1 = ctk.CTkFrame(card1, fg_color="transparent")
        slider_frame1.pack(fill="x", padx=16, pady=(4, 0))
        self.upper_slider = ctk.CTkSlider(slider_frame1, from_=50, to=100, number_of_steps=50,
                                           fg_color=C["bg"], progress_color=C["red"],
                                           button_color=C["red"], button_hover_color=C["red_dim"])
        self.upper_slider.set(self.config["upper_threshold"])
        self.upper_slider.pack(side="left", fill="x", expand=True)
        self.upper_label = ctk.CTkLabel(slider_frame1, text=f"{int(self.config['upper_threshold'])}%",
                                        font=font_bold(13), text_color=C["red"], width=44)
        self.upper_label.pack(side="right", padx=(8, 0))
        self.upper_slider.configure(command=lambda v: self.upper_label.configure(text=f"{int(v)}%"))

        ctk.CTkFrame(card1, height=1, fg_color=C["border"]).pack(fill="x", padx=16, pady=(12, 0))

        ctk.CTkLabel(card1, text="Low battery alert (plug in)", font=font(12),
                     text_color=C["text_dim"], anchor="w").pack(padx=16, pady=(10, 0), fill="x")
        slider_frame2 = ctk.CTkFrame(card1, fg_color="transparent")
        slider_frame2.pack(fill="x", padx=16, pady=(4, 12))
        self.lower_slider = ctk.CTkSlider(slider_frame2, from_=5, to=50, number_of_steps=45,
                                           fg_color=C["bg"], progress_color=C["orange"],
                                           button_color=C["orange"], button_hover_color=C["yellow_dim"])
        self.lower_slider.set(self.config["lower_threshold"])
        self.lower_slider.pack(side="left", fill="x", expand=True)
        self.lower_label = ctk.CTkLabel(slider_frame2, text=f"{int(self.config['lower_threshold'])}%",
                                        font=font_bold(13), text_color=C["orange"], width=44)
        self.lower_label.pack(side="right", padx=(8, 0))
        self.lower_slider.configure(command=lambda v: self.lower_label.configure(text=f"{int(v)}%"))

        # ── Telegram ──
        self._section(scroll, "Telegram")

        card2 = self._card(scroll)

        ctk.CTkLabel(card2, text="Bot Token", font=font(12),
                     text_color=C["text_dim"], anchor="w").pack(padx=16, pady=(12, 0), fill="x")
        self.token_entry = ctk.CTkEntry(card2, placeholder_text="Paste bot token",
                                        height=38, font=font_mono(12),
                                        fg_color=C["bg_input"], border_width=1,
                                        border_color=C["border"], corner_radius=6)
        self.token_entry.pack(padx=16, pady=(4, 0), fill="x")
        if self.config.get("telegram_token"):
            self.token_entry.insert(0, self.config["telegram_token"])

        ctk.CTkLabel(card2, text="Chat ID", font=font(12),
                     text_color=C["text_dim"], anchor="w").pack(padx=16, pady=(10, 0), fill="x")
        self.chat_entry = ctk.CTkEntry(card2, placeholder_text="Your chat ID",
                                       height=38, font=font_mono(12),
                                       fg_color=C["bg_input"], border_width=1,
                                       border_color=C["border"], corner_radius=6)
        self.chat_entry.pack(padx=16, pady=(4, 0), fill="x")
        if self.config.get("telegram_chat_id"):
            self.chat_entry.insert(0, self.config["telegram_chat_id"])

        self.tg_status = ctk.CTkLabel(card2, text="", font=font(11))
        self.tg_status.pack(padx=16, pady=(6, 0))

        ctk.CTkButton(card2, text="Send Test", height=36, font=font_bold(12),
                      corner_radius=6, fg_color=C["bg_card_alt"], border_width=1,
                      border_color=C["border"], hover_color=C["bg_hover"],
                      text_color=C["text"],
                      command=self._test_tg).pack(padx=16, pady=(4, 14), fill="x")

        # ── Push Alerts (ntfy & WhatsApp) ──
        self._section(scroll, "Push Alerts (ntfy & WhatsApp)")

        card_wa = self._card(scroll)

        ctk.CTkLabel(card_wa, text="ntfy Topic (Free, Instant & Rings Phone 🔔)", font=font_bold(12),
                     text_color=C["green"], anchor="w").pack(padx=16, pady=(12, 0), fill="x")
        self.ntfy_entry = ctk.CTkEntry(card_wa, placeholder_text="e.g. my-battery-alert-8841",
                                       height=38, font=font_mono(12),
                                       fg_color=C["bg_input"], border_width=1,
                                       border_color=C["border"], corner_radius=6)
        self.ntfy_entry.pack(padx=16, pady=(4, 0), fill="x")
        if self.config.get("ntfy_topic"):
            self.ntfy_entry.insert(0, self.config["ntfy_topic"])

        ctk.CTkButton(card_wa, text="Send Test ntfy Alert 🔔", height=36, font=font_bold(12),
                      corner_radius=6, fg_color=C["btn_primary"], hover_color=C["blue_hover"],
                      text_color="white",
                      command=self._test_ntfy).pack(padx=16, pady=(6, 10), fill="x")

        ctk.CTkFrame(card_wa, height=1, fg_color=C["border"]).pack(fill="x", padx=16, pady=4)

        ctk.CTkLabel(card_wa, text="Enterprise Webhook URL (Slack / Teams / Discord)", font=font_bold(12),
                     text_color=C["blue"], anchor="w").pack(padx=16, pady=(8, 0), fill="x")
        self.webhook_entry = ctk.CTkEntry(card_wa, placeholder_text="https://hooks.slack.com/services/...",
                                          height=38, font=font_mono(11),
                                          fg_color=C["bg_input"], border_width=1,
                                          border_color=C["border"], corner_radius=6)
        self.webhook_entry.pack(padx=16, pady=(4, 12), fill="x")
        if self.config.get("webhook_url"):
            self.webhook_entry.insert(0, self.config["webhook_url"])

        ctk.CTkLabel(card_wa, text="WhatsApp Number(s)", font=font(12),
                     text_color=C["text_dim"], anchor="w").pack(padx=16, pady=(8, 0), fill="x")
        self.wa_phone_entry = ctk.CTkEntry(card_wa, placeholder_text="e.g. +1234567890",
                                           height=38, font=font_mono(12),
                                           fg_color=C["bg_input"], border_width=1,
                                           border_color=C["border"], corner_radius=6)
        self.wa_phone_entry.pack(padx=16, pady=(4, 0), fill="x")
        if self.config.get("whatsapp_phone"):
            self.wa_phone_entry.insert(0, self.config["whatsapp_phone"])

        ctk.CTkLabel(card_wa, text="WhatsApp API Key / Instance ID (Green API or CallMeBot)", font=font(12),
                     text_color=C["text_dim"], anchor="w").pack(padx=16, pady=(10, 0), fill="x")
        self.wa_key_entry = ctk.CTkEntry(card_wa, placeholder_text="e.g. 1101823456/d75b3a... (Green API) or 123456",
                                         height=38, font=font_mono(11),
                                         fg_color=C["bg_input"], border_width=1,
                                         border_color=C["border"], corner_radius=6)
        self.wa_key_entry.pack(padx=16, pady=(4, 0), fill="x")
        if self.config.get("whatsapp_apikey"):
            self.wa_key_entry.insert(0, self.config["whatsapp_apikey"])

        self.wa_status = ctk.CTkLabel(card_wa, text="", font=font(11))
        self.wa_status.pack(padx=16, pady=(6, 0))

        ctk.CTkButton(card_wa, text="Send Test WhatsApp", height=36, font=font_bold(12),
                      corner_radius=6, fg_color=C["bg_card_alt"], border_width=1,
                      border_color=C["border"], hover_color=C["bg_hover"],
                      text_color=C["text"],
                      command=self._test_wa).pack(padx=16, pady=(4, 14), fill="x")

        # ── Cellular SMS Alerts ──
        self._section(scroll, "Cellular SMS Alerts (Fast2SMS / Twilio)")
        card_sms = self._card(scroll)
        ctk.CTkLabel(card_sms, text="Phone Number for SMS", font=font(12),
                     text_color=C["text_dim"], anchor="w").pack(padx=16, pady=(12, 0), fill="x")
        self.sms_phone_entry = ctk.CTkEntry(card_sms, placeholder_text="e.g. +1234567890",
                                            height=38, font=font_mono(12),
                                            fg_color=C["bg_input"], border_width=1,
                                            border_color=C["border"], corner_radius=6)
        self.sms_phone_entry.pack(padx=16, pady=(4, 0), fill="x")
        if self.config.get("sms_phone"):
            self.sms_phone_entry.insert(0, self.config["sms_phone"])

        ctk.CTkLabel(card_sms, text="SMS API Key (Fast2SMS or Twilio SID:Token:From)", font=font(12),
                     text_color=C["text_dim"], anchor="w").pack(padx=16, pady=(10, 0), fill="x")
        self.sms_key_entry = ctk.CTkEntry(card_sms, placeholder_text="Fast2SMS API Key or Twilio SID:Token:From",
                                          height=38, font=font_mono(11),
                                          fg_color=C["bg_input"], border_width=1,
                                          border_color=C["border"], corner_radius=6)
        self.sms_key_entry.pack(padx=16, pady=(4, 0), fill="x")
        if self.config.get("sms_apikey"):
            self.sms_key_entry.insert(0, self.config["sms_apikey"])

        ctk.CTkButton(card_sms, text="Send Test SMS 💬", height=36, font=font_bold(12),
                      corner_radius=6, fg_color=C["bg_card_alt"], border_width=1,
                      border_color=C["border"], hover_color=C["bg_hover"],
                      text_color=C["text"],
                      command=self._test_sms).pack(padx=16, pady=(10, 14), fill="x")

        # ── Automated Voice Calls ──
        self._section(scroll, "Automated Voice Calls (CallMeBot / Twilio)")
        card_call = self._card(scroll)
        ctk.CTkLabel(card_call, text="Phone Number to Call", font=font(12),
                     text_color=C["text_dim"], anchor="w").pack(padx=16, pady=(12, 0), fill="x")
        self.call_phone_entry = ctk.CTkEntry(card_call, placeholder_text="e.g. +1234567890",
                                             height=38, font=font_mono(12),
                                             fg_color=C["bg_input"], border_width=1,
                                             border_color=C["border"], corner_radius=6)
        self.call_phone_entry.pack(padx=16, pady=(4, 0), fill="x")
        if self.config.get("phone_call_number"):
            self.call_phone_entry.insert(0, self.config["phone_call_number"])

        ctk.CTkLabel(card_call, text="Call API Key (CallMeBot or Twilio SID:Token:From)", font=font(12),
                     text_color=C["text_dim"], anchor="w").pack(padx=16, pady=(10, 0), fill="x")
        self.call_key_entry = ctk.CTkEntry(card_call, placeholder_text="CallMeBot API Key or Twilio SID:Token:From",
                                           height=38, font=font_mono(11),
                                           fg_color=C["bg_input"], border_width=1,
                                           border_color=C["border"], corner_radius=6)
        self.call_key_entry.pack(padx=16, pady=(4, 0), fill="x")
        if self.config.get("phone_call_apikey"):
            self.call_key_entry.insert(0, self.config["phone_call_apikey"])

        ctk.CTkButton(card_call, text="Send Test Phone Call 📞", height=36, font=font_bold(12),
                      corner_radius=6, fg_color=C["bg_card_alt"], border_width=1,
                      border_color=C["border"], hover_color=C["bg_hover"],
                      text_color=C["text"],
                      command=self._test_call).pack(padx=16, pady=(10, 14), fill="x")

        # ── Enterprise SMTP Email Dispatcher ──
        self._section(scroll, "Enterprise SMTP Email Alerts")
        card_email = self._card(scroll)
        ctk.CTkLabel(card_email, text="Sender Email Address", font=font(12),
                     text_color=C["text_dim"], anchor="w").pack(padx=16, pady=(12, 0), fill="x")
        self.email_sender_entry = ctk.CTkEntry(card_email, placeholder_text="e.g. yourname@gmail.com",
                                               height=38, font=font_mono(12),
                                               fg_color=C["bg_input"], border_width=1,
                                               border_color=C["border"], corner_radius=6)
        self.email_sender_entry.pack(padx=16, pady=(4, 0), fill="x")
        if self.config.get("email_sender"):
            self.email_sender_entry.insert(0, self.config["email_sender"])

        ctk.CTkLabel(card_email, text="SMTP Password (e.g. Gmail App Password)", font=font(12),
                     text_color=C["text_dim"], anchor="w").pack(padx=16, pady=(10, 0), fill="x")
        self.email_pwd_entry = ctk.CTkEntry(card_email, placeholder_text="16-character App Password",
                                            height=38, font=font_mono(11), show="•",
                                            fg_color=C["bg_input"], border_width=1,
                                            border_color=C["border"], corner_radius=6)
        self.email_pwd_entry.pack(padx=16, pady=(4, 0), fill="x")
        if self.config.get("email_password"):
            self.email_pwd_entry.insert(0, self.config["email_password"])

        ctk.CTkLabel(card_email, text="Recipient Email Address", font=font(12),
                     text_color=C["text_dim"], anchor="w").pack(padx=16, pady=(10, 0), fill="x")
        self.email_recip_entry = ctk.CTkEntry(card_email, placeholder_text="e.g. admin@company.com",
                                              height=38, font=font_mono(12),
                                              fg_color=C["bg_input"], border_width=1,
                                              border_color=C["border"], corner_radius=6)
        self.email_recip_entry.pack(padx=16, pady=(4, 0), fill="x")
        if self.config.get("email_recipient"):
            self.email_recip_entry.insert(0, self.config["email_recipient"])

        ctk.CTkButton(card_email, text="Send Test Email 📧", height=36, font=font_bold(12),
                      corner_radius=6, fg_color=C["bg_card_alt"], border_width=1,
                      border_color=C["border"], hover_color=C["bg_hover"],
                      text_color=C["text"],
                      command=self._test_email).pack(padx=16, pady=(10, 14), fill="x")

        # ── Preferences ──
        self._section(scroll, "Preferences")

        card3 = self._card(scroll)
        self.sound_var = ctk.BooleanVar(value=self.config.get("sound_enabled", True))
        self._toggle_row(card3, "Sound alerts", self.sound_var)
        ctk.CTkFrame(card3, height=1, fg_color=C["border"]).pack(fill="x", padx=16)
        self.quiet_var = ctk.BooleanVar(value=self.config.get("quiet_hours_enabled", False))
        self._toggle_row(card3, "Quiet hours (00:00-07:00 no popups)", self.quiet_var)
        ctk.CTkFrame(card3, height=1, fg_color=C["border"]).pack(fill="x", padx=16)
        self.hibernate_var = ctk.BooleanVar(value=self.config.get("auto_hibernate", False))
        self._toggle_row(card3, "Auto suspend at limit", self.hibernate_var)
        ctk.CTkFrame(card3, height=1, fg_color=C["border"]).pack(fill="x", padx=16)
        self.voice_var = ctk.BooleanVar(value=self.config.get("voice_enabled", False))
        self._toggle_row(card3, "Voice speech announcements 🗣️", self.voice_var)
        ctk.CTkFrame(card3, height=1, fg_color=C["border"]).pack(fill="x", padx=16)
        self.eco_var = ctk.BooleanVar(value=self.config.get("eco_mode_enabled", False))
        self._toggle_row(card3, "Auto Linux Eco-Mode (power-saver at 20%) ⚡", self.eco_var)
        ctk.CTkFrame(card3, height=1, fg_color=C["border"]).pack(fill="x", padx=16)
        self.startup_var = ctk.BooleanVar(value=self.config.get("run_on_startup", False))
        self._toggle_row(card3, "Launch on startup", self.startup_var)

        # Save
        ctk.CTkButton(self, text="Save Settings", height=44, font=font_bold(14),
                      corner_radius=8, fg_color=C["btn_primary"],
                      hover_color=C["blue_hover"],
                      command=self._save).pack(padx=30, pady=(8, 16), fill="x")

    def _section(self, parent, text):
        ctk.CTkLabel(parent, text=text.upper(), font=font_bold(11),
                     text_color=C["text_muted"], anchor="w").pack(padx=12, pady=(16, 4), fill="x")

    def _card(self, parent):
        card = ctk.CTkFrame(parent, fg_color=C["bg_card"], corner_radius=10,
                            border_width=1, border_color=C["border"])
        card.pack(fill="x", padx=4, pady=2)
        return card

    def _toggle_row(self, parent, text, var):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=10)
        ctk.CTkLabel(row, text=text, font=font(13), text_color=C["text"]).pack(side="left")
        ctk.CTkSwitch(row, text="", variable=var, onvalue=True, offvalue=False,
                      width=44, height=22,
                      fg_color=C["bg"], progress_color=C["green"],
                      button_color=C["text"]).pack(side="right")

    def _test_tg(self):
        token = self.token_entry.get().strip()
        chat_id = self.chat_entry.get().strip()
        if not token or not chat_id:
            self.tg_status.configure(text="Fill in both fields", text_color=C["yellow"])
            return
        self.tg_status.configure(text="Sending...", text_color=C["cyan"])
        self.update()
        ok, err = send_telegram(token, chat_id, "🧪 <b>Battery Guard</b> — Test notification!")
        if ok:
            self.tg_status.configure(text="✓ Sent successfully", text_color=C["green"])
        else:
            self.tg_status.configure(text=f"✗ {err[:45]}", text_color=C["red"])

    def _test_wa(self):
        phone = self.wa_phone_entry.get().strip()
        apikey = self.wa_key_entry.get().strip()
        if not phone or not apikey:
            self.wa_status.configure(text="Fill in phone and API key", text_color=C["yellow"])
            return
        self.wa_status.configure(text="Sending test...", text_color=C["cyan"])
        self.update()
        try:
            import urllib.parse
            import requests
            import re
            phones = [p.strip() for p in phone.split(",") if p.strip()]
            keys = [k.strip() for k in apikey.split(",") if k.strip()]
            success_count = 0
            for i, p in enumerate(phones):
                k = keys[i] if i < len(keys) else (keys[0] if keys else "")
                if "/" in k or ":" in k:
                    parts = re.split(r'[/:]', k, maxsplit=1)
                    inst_num = re.sub(r'\D', '', parts[0].strip())
                    token = parts[1].strip()
                    subdomain = inst_num[:4] if len(inst_num) >= 4 else "api"
                    url = f"https://{subdomain}.api.green-api.com/waInstance{inst_num}/sendMessage/{token}"
                    chat_id = p if "@" in p else f"{p.lstrip('+')}@c.us"
                    payload = {"chatId": chat_id, "message": "🧪 *Battery Guard* — Test WhatsApp notification (Green API)!"}
                    resp = requests.post(url, json=payload, timeout=8)
                    if resp.status_code in (200, 201) and "idMessage" in resp.text:
                        success_count += 1
                    else:
                        self.wa_status.configure(text=f"✗ Error {resp.status_code}: {resp.text[:35]}", text_color=C["red"])
                        return
                else:
                    text = urllib.parse.quote("🧪 *Battery Guard* — Test WhatsApp notification!")
                    url = f"https://api.callmebot.com/whatsapp.php?phone={p}&text={text}&apikey={k}"
                    resp = requests.get(url, timeout=8)
                    if resp.status_code == 200:
                        success_count += 1
                    else:
                        self.wa_status.configure(text=f"✗ Error {resp.status_code}: {resp.text[:30]}", text_color=C["red"])
                        return
            if success_count > 0:
                self.wa_status.configure(text=f"✓ Sent to {success_count} recipient(s)!", text_color=C["green"])
        except Exception as e:
            self.wa_status.configure(text=f"✗ {str(e)[:40]}", text_color=C["red"])

    def _test_ntfy(self):
        topic = self.ntfy_entry.get().strip()
        if not topic:
            self.wa_status.configure(text="Please enter a secret topic name", text_color=C["yellow"])
            return
        self.wa_status.configure(text="Sending test alert to ntfy...", text_color=C["cyan"])
        self.update()
        try:
            import requests
            topics = [t.strip() for t in topic.split(",") if t.strip()]
            success_count = 0
            for t in topics:
                url = f"https://ntfy.sh/{t}"
                headers = {"Title": "Battery Guard Test", "Priority": "high", "Tags": "bell,zap"}
                resp = requests.post(url, data="✓ ntfy notification is working perfectly! Your phone will ring for battery alerts.".encode("utf-8"), headers=headers, timeout=8)
                if resp.status_code == 200:
                    success_count += 1
                else:
                    self.wa_status.configure(text=f"✗ Error {resp.status_code}: {resp.text[:30]}", text_color=C["red"])
                    return
            if success_count > 0:
                self.wa_status.configure(text=f"✓ Sent to {success_count} ntfy topic(s)! Check your phone 🔔", text_color=C["green"])
        except Exception as e:
            self.wa_status.configure(text=f"✗ {str(e)[:40]}", text_color=C["red"])

    def _test_sms(self):
        phone = self.sms_phone_entry.get().strip()
        key = self.sms_key_entry.get().strip()
        if not phone or not key:
            self.wa_status.configure(text="Please enter SMS phone and API key", text_color=C["yellow"])
            return
        self.wa_status.configure(text="Sending test SMS...", text_color=C["cyan"])
        self.update()
        try:
            import requests
            if ":" in key and key.count(":") >= 2:
                parts = key.split(":")
                sid, token, from_num = parts[0].strip(), parts[1].strip(), parts[2].strip()
                url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
                resp = requests.post(url, auth=(sid, token), data={"From": from_num, "To": phone, "Body": "🧪 [Battery Guard] Test SMS Alert!"}, timeout=8)
            else:
                url = "https://www.fast2sms.com/dev/bulkV2"
                headers = {"authorization": key}
                payload = {"route": "q", "message": "🧪 [Battery Guard] Test SMS Alert!", "language": "english", "flash": 0, "numbers": phone}
                resp = requests.post(url, headers=headers, json=payload, timeout=8)
            if resp.status_code in (200, 201):
                self.wa_status.configure(text="✓ Test SMS sent successfully! 💬", text_color=C["green"])
            else:
                self.wa_status.configure(text=f"✗ Error {resp.status_code}: {resp.text[:30]}", text_color=C["red"])
        except Exception as e:
            self.wa_status.configure(text=f"✗ {str(e)[:40]}", text_color=C["red"])

    def _test_call(self):
        phone = self.call_phone_entry.get().strip()
        key = self.call_key_entry.get().strip()
        if not phone or not key:
            self.wa_status.configure(text="Please enter call phone and API key", text_color=C["yellow"])
            return
        self.wa_status.configure(text="Triggering automated voice call...", text_color=C["cyan"])
        self.update()
        try:
            import requests, urllib.parse
            if ":" in key and key.count(":") >= 2:
                parts = key.split(":")
                sid, token, from_num = parts[0].strip(), parts[1].strip(), parts[2].strip()
                url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Calls.json"
                twiml = "<Response><Say>This is a test call from Battery Guard Enterprise.</Say></Response>"
                resp = requests.post(url, auth=(sid, token), data={"From": from_num, "To": phone, "Twiml": twiml}, timeout=8)
            else:
                text = urllib.parse.quote("This is a test call from Battery Guard Enterprise.")
                url = f"https://api.callmebot.com/start.php?phone={phone}&text={text}&apikey={key}&lang=en-US-Standard-B&rpt=2"
                resp = requests.get(url, timeout=8)
            if resp.status_code in (200, 201):
                self.wa_status.configure(text="✓ Voice call triggered! Answer your phone 📞", text_color=C["green"])
            else:
                self.wa_status.configure(text=f"✗ Error {resp.status_code}: {resp.text[:30]}", text_color=C["red"])
        except Exception as e:
            self.wa_status.configure(text=f"✗ {str(e)[:40]}", text_color=C["red"])

    def _test_email(self):
        sender = self.email_sender_entry.get().strip()
        pwd = self.email_pwd_entry.get().strip()
        recip = self.email_recip_entry.get().strip()
        if not sender or not pwd or not recip:
            self.wa_status.configure(text="Please enter sender, password, and recipient", text_color=C["yellow"])
            return
        self.wa_status.configure(text="Sending test email...", text_color=C["cyan"])
        self.update()
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            msg = MIMEMultipart("alternative")
            msg["Subject"] = "🧪 [Battery Guard Enterprise] Test Email Notification"
            msg["From"] = sender
            msg["To"] = recip
            html = """<div style='font-family: Arial; padding: 20px; background: #1e1e2e; color: #cdd6f4;'><h2 style='color: #89b4fa;'>⚡ Battery Guard Test Email</h2><p>Your enterprise email notification pipeline is working perfectly!</p></div>"""
            msg.attach(MIMEText(html, "html"))
            with smtplib.SMTP("smtp.gmail.com", 587, timeout=10) as smtp:
                smtp.starttls()
                smtp.login(sender, pwd)
                smtp.send_message(msg)
            self.wa_status.configure(text="✓ Test email sent successfully! 📧", text_color=C["green"])
        except Exception as e:
            self.wa_status.configure(text=f"✗ {str(e)[:40]}", text_color=C["red"])

    def _save(self):
        self.config["upper_threshold"] = int(self.upper_slider.get())
        self.config["lower_threshold"] = int(self.lower_slider.get())
        self.config["telegram_token"] = self.token_entry.get().strip()
        self.config["telegram_chat_id"] = self.chat_entry.get().strip()
        self.config["ntfy_topic"] = self.ntfy_entry.get().strip()
        self.config["webhook_url"] = self.webhook_entry.get().strip()
        self.config["whatsapp_phone"] = self.wa_phone_entry.get().strip()
        self.config["whatsapp_apikey"] = self.wa_key_entry.get().strip()
        self.config["sms_enabled"] = bool(self.sms_phone_entry.get().strip() and self.sms_key_entry.get().strip())
        self.config["sms_phone"] = self.sms_phone_entry.get().strip()
        self.config["sms_apikey"] = self.sms_key_entry.get().strip()
        self.config["phone_call_enabled"] = bool(self.call_phone_entry.get().strip() and self.call_key_entry.get().strip())
        self.config["phone_call_number"] = self.call_phone_entry.get().strip()
        self.config["phone_call_apikey"] = self.call_key_entry.get().strip()
        self.config["email_enabled"] = bool(self.email_sender_entry.get().strip() and self.email_pwd_entry.get().strip() and self.email_recip_entry.get().strip())
        self.config["email_sender"] = self.email_sender_entry.get().strip()
        self.config["email_password"] = self.email_pwd_entry.get().strip()
        self.config["email_recipient"] = self.email_recip_entry.get().strip()
        self.config["quiet_hours_enabled"] = self.quiet_var.get()
        self.config["sound_enabled"] = self.sound_var.get()
        self.config["voice_enabled"] = self.voice_var.get()
        self.config["eco_mode_enabled"] = self.eco_var.get()
        self.config["auto_hibernate"] = self.hibernate_var.get()
        self.config["run_on_startup"] = self.startup_var.get()
        save_config(self.config)
        self.on_save(self.config)
        self._configure_startup(self.config["run_on_startup"])
        try: self.destroy()
        except: pass

    def _configure_startup(self, enable):
        try:
            if IS_WINDOWS:
                import winreg
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                     r"Software\Microsoft\Windows\CurrentVersion\Run",
                                     0, winreg.KEY_SET_VALUE)
                if enable:
                    winreg.SetValueEx(key, "BatteryGuard", 0, winreg.REG_SZ,
                                      f'"{sys.executable}" "{os.path.abspath(sys.argv[0])}"')
                else:
                    try: winreg.DeleteValue(key, "BatteryGuard")
                    except FileNotFoundError: pass
                winreg.CloseKey(key)
            elif IS_LINUX:
                autostart_dir = Path.home() / ".config" / "autostart"
                desktop_file = autostart_dir / "battery-guard.desktop"
                if enable:
                    autostart_dir.mkdir(parents=True, exist_ok=True)
                    desktop_file.write_text(
                        f"[Desktop Entry]\nType=Application\nName=Battery Guard\n"
                        f"Exec=\"{sys.executable}\" \"{os.path.abspath(sys.argv[0])}\"\n"
                        f"Hidden=false\nNoDisplay=false\n"
                        f"X-GNOME-Autostart-enabled=true\n"
                        f"Comment=Cross-platform battery monitor\n")
                else:
                    if desktop_file.exists():
                        desktop_file.unlink()
        except Exception as e:
            print(f"[Startup] {e}")


# ─── Main Dashboard ──────────────────────────────────────────────────────────

class BatteryGuardApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.config_data = load_config()
        self._percent_history = []

        self.title("Battery Guard")
        self.geometry("440x680")
        self.minsize(420, 640)
        self.configure(fg_color=C["bg"])

        # Center window
        self.update_idletasks()
        w, h = 440, 680
        x = (self.winfo_screenwidth() // 2) - (w // 2)
        y = (self.winfo_screenheight() // 2) - (h // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

        # Initialize Smart Alerts
        self.smart_alerts = SmartAlerts(
            low_threshold=self.config_data.get("lower_threshold", 20),
            high_threshold=self.config_data.get("upper_threshold", 80),
            enabled=self.config_data.get("smart_alerts_enabled", True),
            whatsapp_phone=self.config_data.get("whatsapp_phone", ""),
            whatsapp_apikey=self.config_data.get("whatsapp_apikey", ""),
            ntfy_topic=self.config_data.get("ntfy_topic", ""),
            quiet_hours_enabled=self.config_data.get("quiet_hours_enabled", False),
        )
        self.smart_alerts.voice_enabled = self.config_data.get("voice_enabled", False)
        self.smart_alerts.webhook_url = self.config_data.get("webhook_url", "")
        self.smart_alerts.sms_enabled = self.config_data.get("sms_enabled", False)
        self.smart_alerts.sms_phone = self.config_data.get("sms_phone", "")
        self.smart_alerts.sms_apikey = self.config_data.get("sms_apikey", "")
        self.smart_alerts.phone_call_enabled = self.config_data.get("phone_call_enabled", False)
        self.smart_alerts.phone_call_number = self.config_data.get("phone_call_number", "")
        self.smart_alerts.phone_call_apikey = self.config_data.get("phone_call_apikey", "")
        self.smart_alerts.email_enabled = self.config_data.get("email_enabled", False)
        self.smart_alerts.email_smtp_server = self.config_data.get("email_smtp_server", "smtp.gmail.com")
        self.smart_alerts.email_smtp_port = self.config_data.get("email_smtp_port", 587)
        self.smart_alerts.email_sender = self.config_data.get("email_sender", "")
        self.smart_alerts.email_password = self.config_data.get("email_password", "")
        self.smart_alerts.email_recipient = self.config_data.get("email_recipient", "")

        # State
        self.battery_percent = 0
        self.is_charging = False
        self.secs_left = -1
        self.alert_active = False
        self.alert_type = None
        self.alert_popup = None
        self.snooze_until = 0
        self.last_telegram_time = 0
        self.glow_phase = 0
        self._glow_running = False
        self._running = True

        self.protocol("WM_DELETE_WINDOW", self.hide_to_tray)

        self._build_ui()

        # Start tray before monitoring
        self.tray = TrayManager(self)
        self.tray.start()

        self._update_battery()
        self._update_clock()

        if not self.config_data.get("first_launch_done"):
            self.after(500, self._show_wizard)

    def _build_ui(self):
        # ── Header bar ──
        header = ctk.CTkFrame(self, fg_color=C["bg_surface"], height=52, corner_radius=0)
        header.pack(fill="x")
        header.pack_propagate(False)

        # App name
        name_frame = ctk.CTkFrame(header, fg_color="transparent")
        name_frame.pack(side="left", padx=16)
        ctk.CTkLabel(name_frame, text="●", font=font(12), text_color=C["green"]).pack(side="left", padx=(0, 6))
        ctk.CTkLabel(name_frame, text="Battery Guard", font=font_bold(15),
                     text_color=C["text"]).pack(side="left")

        # Clock
        self.clock_label = ctk.CTkLabel(header, text="", font=font(13),
                                        text_color=C["text_muted"])
        self.clock_label.pack(side="right", padx=16)

        # Quit / Shut down button
        ctk.CTkButton(header, text="⏻", width=36, height=36,
                      font=font(16), fg_color="transparent",
                      hover_color=C["red_dim"], text_color=C["red"],
                      corner_radius=8,
                      command=self.quit_app).pack(side="right", padx=(0, 4))

        # Settings button
        ctk.CTkButton(header, text="⚙", width=36, height=36,
                      font=font(16), fg_color="transparent",
                      hover_color=C["bg_hover"], text_color=C["text_dim"],
                      corner_radius=8,
                      command=self._open_settings).pack(side="right", padx=(0, 2))

        # Thin accent line under header
        ctk.CTkFrame(self, height=1, fg_color=C["border"], corner_radius=0).pack(fill="x")

        # ── Main content area ──
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=24, pady=16)

        # ── Smart Alerts Toggle Banner ──
        sa_card = ctk.CTkFrame(main, fg_color=C["bg_card"], corner_radius=10,
                               border_width=1, border_color=C["border"])
        sa_card.pack(fill="x", pady=(0, 10))
        sa_inner = ctk.CTkFrame(sa_card, fg_color="transparent")
        sa_inner.pack(padx=16, pady=12, fill="x")

        sa_text_frame = ctk.CTkFrame(sa_inner, fg_color="transparent")
        sa_text_frame.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(sa_text_frame, text="Smart Alerts", font=font_bold(14),
                     text_color=C["text"], anchor="w").pack(fill="x")
        self.sa_status_label = ctk.CTkLabel(sa_text_frame, text="Checking...", font=font(11),
                                            text_color=C["text_muted"], anchor="w")
        self.sa_status_label.pack(fill="x")

        self.sa_switch_var = ctk.BooleanVar(value=self.config_data.get("smart_alerts_enabled", True))
        self.sa_switch = ctk.CTkSwitch(sa_inner, text="", variable=self.sa_switch_var,
                                       onvalue=True, offvalue=False, width=44, height=22,
                                       fg_color=C["bg"], progress_color=C["green"],
                                       button_color=C["text"], command=self._on_sa_toggle)
        self.sa_switch.pack(side="right")
        self._update_sa_status_display()

        # ── Battery Gauge ──
        gauge_container = ctk.CTkFrame(main, fg_color="transparent")
        gauge_container.pack(pady=(10, 16))

        self.gauge_size = 220
        canvas_size = self.gauge_size + 50
        self.canvas = tk.Canvas(gauge_container, width=canvas_size, height=canvas_size,
                                bg=C["bg"], highlightthickness=0)
        self.canvas.pack()
        self._draw_gauge(0, C["green"])

        # ── Info Cards ──
        cards = ctk.CTkFrame(main, fg_color="transparent")
        cards.pack(fill="x")

        # -- Charging card --
        charge_card = ctk.CTkFrame(cards, fg_color=C["bg_card"], corner_radius=10,
                                   border_width=1, border_color=C["border"])
        charge_card.pack(fill="x", pady=(0, 8))

        charge_inner = ctk.CTkFrame(charge_card, fg_color="transparent")
        charge_inner.pack(padx=16, pady=14, fill="x")

        # Status indicator dot + icon
        indicator_frame = ctk.CTkFrame(charge_inner, fg_color="transparent")
        indicator_frame.pack(side="left", padx=(0, 14))
        self.charge_dot = ctk.CTkFrame(indicator_frame, width=40, height=40,
                                        fg_color=C["bg_card_alt"], corner_radius=8)
        self.charge_dot.pack()
        self.charge_dot.pack_propagate(False)
        self.charge_icon = ctk.CTkLabel(self.charge_dot, text="⚡",
                                        font=("Segoe UI Emoji", 18))
        self.charge_icon.place(relx=0.5, rely=0.5, anchor="center")

        charge_text = ctk.CTkFrame(charge_inner, fg_color="transparent")
        charge_text.pack(side="left", fill="x", expand=True)

        self.charge_status_label = ctk.CTkLabel(charge_text, text="Detecting...",
                                                 font=font_bold(14),
                                                 text_color=C["text"], anchor="w")
        self.charge_status_label.pack(fill="x")
        self.charge_detail_label = ctk.CTkLabel(charge_text, text="",
                                                 font=font(11),
                                                 text_color=C["text_muted"], anchor="w")
        self.charge_detail_label.pack(fill="x")

        # -- Time estimate card --
        time_card = ctk.CTkFrame(cards, fg_color=C["bg_card"], corner_radius=10,
                                 border_width=1, border_color=C["border"])
        time_card.pack(fill="x", pady=(0, 8))

        time_inner = ctk.CTkFrame(time_card, fg_color="transparent")
        time_inner.pack(padx=16, pady=14, fill="x")

        time_indicator = ctk.CTkFrame(time_inner, fg_color="transparent")
        time_indicator.pack(side="left", padx=(0, 14))
        time_dot = ctk.CTkFrame(time_indicator, width=40, height=40,
                                fg_color=C["bg_card_alt"], corner_radius=8)
        time_dot.pack()
        time_dot.pack_propagate(False)
        ctk.CTkLabel(time_dot, text="⏱", font=("Segoe UI Emoji", 18)).place(
            relx=0.5, rely=0.5, anchor="center")

        time_text = ctk.CTkFrame(time_inner, fg_color="transparent")
        time_text.pack(side="left", fill="x", expand=True)

        self.time_estimate_label = ctk.CTkLabel(time_text, text="Estimating...",
                                                 font=font_bold(14),
                                                 text_color=C["text"], anchor="w")
        self.time_estimate_label.pack(fill="x")
        self.time_detail_label = ctk.CTkLabel(time_text, text="",
                                               font=font(11),
                                               text_color=C["text_muted"], anchor="w")
        self.time_detail_label.pack(fill="x")

        # ── Battery Health / Diagnostics Card ──
        diag = get_battery_diagnostics()
        diag_card = ctk.CTkFrame(main, fg_color=C["bg_card"], corner_radius=10,
                                 border_width=1, border_color=C["border"])
        diag_card.pack(fill="x", pady=(4, 6))

        diag_inner = ctk.CTkFrame(diag_card, fg_color="transparent")
        diag_inner.pack(padx=14, pady=10, fill="x")

        diag_dot = ctk.CTkFrame(diag_inner, width=32, height=32,
                                fg_color=C["bg_card_alt"], corner_radius=8)
        diag_dot.pack(side="left", padx=(0, 12))
        diag_dot.pack_propagate(False)
        ctk.CTkLabel(diag_dot, text="🏥", font=("Segoe UI Emoji", 16)).place(
            relx=0.5, rely=0.5, anchor="center")

        diag_text = ctk.CTkFrame(diag_inner, fg_color="transparent")
        diag_text.pack(side="left", fill="x", expand=True)

        self.diag_title_label = ctk.CTkLabel(diag_text, text=f"Battery Health: Normal ({diag.get('health', '100%')})",
                                             font=font_bold(13), text_color=C["text"], anchor="w")
        self.diag_title_label.pack(fill="x")
        self.diag_detail_label = ctk.CTkLabel(diag_text, text=f"Capacity: {diag.get('capacity_now', 'N/A')} · {diag.get('cycles', '0 cycles')}",
                                              font=font(11), text_color=C["text_muted"], anchor="w")
        self.diag_detail_label.pack(fill="x")

        # Analytics Button
        ctk.CTkButton(diag_inner, text="Details...", width=80, height=28,
                      font=font_bold(11), fg_color=C["bg_card_alt"],
                      hover_color=C["bg_hover"], text_color=C["blue"],
                      corner_radius=6,
                      command=self._show_analytics).pack(side="right", padx=(4, 0))

        # ── Status bar ──
        self.status_card = ctk.CTkFrame(main, fg_color=C["bg_card"], corner_radius=10,
                                         border_width=1, border_color=C["border"])
        self.status_card.pack(fill="x", pady=(4, 0))

        status_inner = ctk.CTkFrame(self.status_card, fg_color="transparent")
        status_inner.pack(padx=16, pady=12, fill="x")

        self.status_dot = ctk.CTkLabel(status_inner, text="●", font=font(10),
                                        text_color=C["green"])
        self.status_dot.pack(side="left", padx=(0, 8))
        self.alert_bar_label = ctk.CTkLabel(status_inner, text="Monitoring active",
                                            font=font(13), text_color=C["text_dim"],
                                            anchor="w")
        self.alert_bar_label.pack(side="left", fill="x", expand=True)

        # ── Footer ──
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=24, pady=(0, 12))

        os_name = "Windows" if IS_WINDOWS else "Linux" if IS_LINUX else platform.system()
        ctk.CTkLabel(footer, text=f"v1.0 · {os_name}",
                     font=font(11), text_color=C["text_muted"]).pack(side="left")

    # ─── Gauge Drawing ───────────────────────────────────────────────────────

    def _draw_gauge(self, percent, color):
        self.canvas.delete("all")
        pad = 25
        size = self.gauge_size
        canvas_size = size + pad * 2
        cx, cy = canvas_size / 2, canvas_size / 2
        r = size / 2

        # Glow rings during alert
        if self.alert_active:
            alpha = abs(math.sin(self.glow_phase * 0.12))
            for i in range(4):
                offset = (4 - i) * 5
                intensity = int(30 + 50 * alpha)
                glow_c = f"#{intensity:02x}0015"
                self.canvas.create_oval(pad - offset, pad - offset,
                                        size + pad + offset, size + pad + offset,
                                        outline=glow_c, width=2)

        # Background track (subtle)
        self.canvas.create_oval(pad, pad, size + pad, size + pad,
                                outline=C["bg_card_alt"], width=10)

        # Progress arc
        if percent > 0:
            extent = -1 * (percent / 100) * 360
            self.canvas.create_arc(pad, pad, size + pad, size + pad,
                                   start=90, extent=extent,
                                   outline=color, width=10, style="arc")

        # Clean inner circle
        inner = 16
        self.canvas.create_oval(pad + inner, pad + inner,
                                size + pad - inner, size + pad - inner,
                                fill=C["bg"], outline=C["bg"])

        # Percentage
        self.canvas.create_text(cx, cy - 12,
                                text=f"{int(percent)}",
                                fill=C["text"], font=(FONT_FAMILY, 48, "bold"))
        self.canvas.create_text(cx, cy + 28,
                                text="percent",
                                fill=C["text_muted"], font=(FONT_FAMILY, 12))

    def _on_sa_toggle(self):
        enabled = self.sa_switch_var.get()
        self.smart_alerts.set_enabled(enabled)
        self.config_data["smart_alerts_enabled"] = enabled
        save_config(self.config_data)
        self._update_sa_status_display()

    def _update_sa_status_display(self):
        if not self.sa_switch_var.get():
            self.sa_status_label.configure(text="Disabled — No alerts will fire", text_color=C["text_muted"])
        else:
            ntfy = self.config_data.get("ntfy_topic", "").strip()
            apikey = self.config_data.get("whatsapp_apikey", "").strip()
            if ntfy and apikey:
                self.sa_status_label.configure(text="✓ ntfy, WhatsApp & Popups active 🔔", text_color=C["green"])
            elif ntfy:
                self.sa_status_label.configure(text="✓ ntfy & Popups active 🔔", text_color=C["green"])
            elif apikey:
                self.sa_status_label.configure(text="✓ WhatsApp & Popups active", text_color=C["green"])
            else:
                self.sa_status_label.configure(text="⚠️ Configure ntfy or WhatsApp in Settings ⚙ · Popups active", text_color=C["yellow"])

    def _get_gauge_color(self, percent):
        if percent > 80:
            return C["red"]
        elif percent > 70:
            return C["yellow"]
        return C["green"]

    # ─── Battery Polling ─────────────────────────────────────────────────────

    def _update_battery(self):
        if not self._running:
            return
        try:
            battery = psutil.sensors_battery()
            if battery:
                self.battery_percent = battery.percent
                self.is_charging = battery.power_plugged
                self.secs_left = battery.secsleft if battery.secsleft != psutil.POWER_TIME_UNLIMITED else -1

                # Software fallback estimator when Linux ACPI returns -1
                now_ts = time.time()
                self._percent_history.append((now_ts, self.battery_percent, self.is_charging))
                self._percent_history = [x for x in self._percent_history if now_ts - x[0] <= 3600 and x[2] == self.is_charging]

                if self.secs_left <= 0 and len(self._percent_history) >= 2:
                    old_ts, old_pct, _ = self._percent_history[0]
                    if self.is_charging and self.battery_percent > old_pct and now_ts > old_ts:
                        rate = (self.battery_percent - old_pct) / (now_ts - old_ts)
                        if rate > 0:
                            self.secs_left = (100 - self.battery_percent) / rate
                    elif not self.is_charging and old_pct > self.battery_percent and now_ts > old_ts:
                        rate = (old_pct - self.battery_percent) / (now_ts - old_ts)
                        if rate > 0:
                            self.secs_left = self.battery_percent / rate

                # Wire into the existing poll loop (Phase 3)
                self.smart_alerts.update(self.battery_percent, self.is_charging)

                color = self._get_gauge_color(self.battery_percent)
                self._draw_gauge(self.battery_percent, color)

                if self.is_charging:
                    self.charge_icon.configure(text="⚡")
                    self.charge_status_label.configure(text="Charging", text_color=C["green"])
                    self.charge_detail_label.configure(text="Connected to power source")
                else:
                    self.charge_icon.configure(text="🔋")
                    self.charge_status_label.configure(text="On Battery", text_color=C["yellow"])
                    self.charge_detail_label.configure(text="Running on battery power")

                drain_predictor.log_sample(self.battery_percent, self.is_charging)
                target_limit = self.smart_alerts.high_threshold if self.is_charging else self.smart_alerts.low_threshold
                if self.is_charging and self.battery_percent >= 100:
                    self.time_estimate_label.configure(text="Fully charged")
                    self.time_detail_label.configure(text="Battery at 100%")
                else:
                    time_str, desc_str, _ = drain_predictor.predict(self.battery_percent, self.is_charging, target_limit)
                    self.time_estimate_label.configure(text=time_str)
                    self.time_detail_label.configure(text=desc_str)

                # Update clean standard health summary
                live_diag = get_battery_diagnostics()
                health_val = live_diag.get('health', '100%')
                self.diag_title_label.configure(text=f"Battery Health: Normal ({health_val})")
                self.diag_detail_label.configure(text=f"Capacity: {live_diag.get('capacity_now', 'N/A')} · {live_diag.get('cycles', '0 cycles')}")

                # Auto Linux Eco-Mode
                if self.config_data.get("eco_mode_enabled", False) and IS_LINUX:
                    if self.battery_percent <= self.smart_alerts.low_threshold and not self.is_charging:
                        os.system("powerprofilesctl set power-saver 2>/dev/null")
                    elif self.is_charging or self.battery_percent > self.smart_alerts.low_threshold + 5:
                        os.system("powerprofilesctl set balanced 2>/dev/null")

                self.tray.update(self.battery_percent)
                self._check_alerts()
            else:
                self.charge_status_label.configure(text="No battery found", text_color=C["red"])
        except Exception as e:
            print(f"[Battery] {e}")

        if self.alert_active and not self._glow_running:
            self._glow_running = True
            self.after(100, self._animate_glow)

        # ── Adaptive Polling Rate ──
        # Speed up polling to every 2 seconds when close to thresholds or under heavy load
        low_thresh = self.smart_alerts.low_threshold
        high_thresh = self.smart_alerts.high_threshold
        if (not self.is_charging and self.battery_percent <= low_thresh + 8) or \
           (self.is_charging and self.battery_percent >= high_thresh - 5):
            poll_interval = 2000
        else:
            poll_interval = 10000
        self.after(poll_interval, self._update_battery)

    def _animate_glow(self):
        if not self.alert_active or not self._running:
            self._glow_running = False
            return
        self.glow_phase += 1
        self._draw_gauge(self.battery_percent, self._get_gauge_color(self.battery_percent))
        self.after(100, self._animate_glow)

    def _check_alerts(self):
        now = time.time()
        if now < self.snooze_until:
            remaining = int((self.snooze_until - now) / 60) + 1
            self.alert_bar_label.configure(text=f"Snoozed · {remaining} min left")
            self.status_dot.configure(text_color=C["yellow"])
            return

        upper = self.config_data.get("upper_threshold", 80)
        lower = self.config_data.get("lower_threshold", 20)

        triggered = False
        alert_type = None
        if self.battery_percent >= upper and self.is_charging:
            triggered, alert_type = True, "high"
        elif self.battery_percent <= lower and not self.is_charging:
            triggered, alert_type = True, "low"

        if triggered and not self.alert_active:
            self.alert_active = True
            self.alert_type = alert_type
            self.glow_phase = 0

            if alert_type == "high":
                self.alert_bar_label.configure(text=f"Alert · Battery at {int(self.battery_percent)}%")
            else:
                self.alert_bar_label.configure(text=f"Alert · Low battery {int(self.battery_percent)}%")
            self.status_dot.configure(text_color=C["red"])
            self.status_card.configure(border_color=C["red"])

            self._show_alert_popup(alert_type)
            self._send_alert_telegram(alert_type)

            if self.config_data.get("auto_hibernate"):
                # 5-second delay between alert firing and suspend call gives WhatsApp/Telegram/ntfy requests and voice announcements time to complete before OS suspend
                self.after(5000, self._hibernate)

        elif triggered and self.alert_active:
            if now - self.last_telegram_time >= 300:
                self._send_alert_telegram(alert_type)

        elif not triggered and self.alert_active:
            self._clear_alert()

        if not triggered and not self.alert_active:
            self.alert_bar_label.configure(text="Monitoring active")
            self.status_dot.configure(text_color=C["green"])
            self.status_card.configure(border_color=C["border"])

    def _show_alert_popup(self, alert_type):
        if self.alert_popup:
            try: self.alert_popup.close()
            except: pass
        self.alert_popup = AlertPopup(self, alert_type, self.battery_percent,
                                      on_snooze=self._on_snooze, on_dismiss=self._on_dismiss)
        self.show_window()

    def _send_alert_telegram(self, alert_type):
        token = self.config_data.get("telegram_token", "")
        chat_id = self.config_data.get("telegram_chat_id", "")
        if not token or not chat_id:
            return
        now_str = datetime.now().strftime("%I:%M %p")
        pct = int(self.battery_percent)
        if alert_type == "high":
            msg = (f"⚡ <b>Battery at {pct}%! Unplug now!</b>\n\n"
                   f"🕐 {now_str}\n🔋 {pct}% · Charging\n\n<i>— Battery Guard</i>")
        else:
            msg = (f"🪫 <b>Battery Low! {pct}% remaining</b>\n\n"
                   f"🕐 {now_str}\n🔋 {pct}% · Not charging\n\n"
                   f"<b>Plug in your charger!</b>\n\n<i>— Battery Guard</i>")
        self.last_telegram_time = time.time()
        threading.Thread(target=send_telegram, args=(token, chat_id, msg), daemon=True).start()

    def _on_snooze(self):
        self.snooze_until = time.time() + 300
        self.alert_active = False
        self.alert_popup = None
        self.alert_bar_label.configure(text="Snoozed for 5 minutes")
        self.status_dot.configure(text_color=C["yellow"])
        self.status_card.configure(border_color=C["yellow"])

    def _on_dismiss(self):
        self.alert_active = False
        self.alert_popup = None
        self.snooze_until = 0
        self.alert_bar_label.configure(text="Monitoring active")
        self.status_dot.configure(text_color=C["green"])
        self.status_card.configure(border_color=C["border"])

    def _clear_alert(self):
        self.alert_active = False
        if self.alert_popup:
            try: self.alert_popup.close()
            except: pass
            self.alert_popup = None
        self.alert_bar_label.configure(text="Monitoring active")
        self.status_dot.configure(text_color=C["green"])
        self.status_card.configure(border_color=C["border"])

    def _hibernate(self):
        try:
            if IS_WINDOWS: os.system("shutdown /h")
            elif IS_LINUX: os.system("systemctl suspend")
        except Exception as e:
            print(f"[Hibernate] {e}")

    def _update_clock(self):
        if not self._running:
            return
        self.clock_label.configure(text=datetime.now().strftime("%I:%M %p"))
        self.after(1000, self._update_clock)

    def _show_analytics(self):
        win = ctk.CTkToplevel(self)
        win.title("Battery Diagnostics")
        win.geometry("440x520")
        win.configure(fg_color=C["bg"])
        win.attributes("-topmost", True)
        win.resizable(False, False)

        ctk.CTkFrame(win, height=3, fg_color=C["blue"], corner_radius=0).pack(fill="x")
        ctk.CTkLabel(win, text="Battery Diagnostics", font=font_bold(16), text_color=C["text"]).pack(pady=(16, 10))

        diag = get_battery_diagnostics()
        card = ctk.CTkFrame(win, fg_color=C["bg_card"], corner_radius=10, border_width=1, border_color=C["border"])
        card.pack(fill="both", expand=True, padx=20, pady=6)

        def add_row(k, v):
            r = ctk.CTkFrame(card, fg_color="transparent")
            r.pack(fill="x", padx=16, pady=5)
            ctk.CTkLabel(r, text=k, font=font(12), text_color=C["text_dim"]).pack(side="left")
            ctk.CTkLabel(r, text=v, font=font_bold(12), text_color=C["text"]).pack(side="right")

        add_row("Health Status:", f"Normal ({diag.get('health', '100%')})")
        add_row("Design Capacity:", diag.get('capacity_design', 'N/A'))
        add_row("Full Charge Capacity:", diag.get('capacity_now', 'N/A'))
        add_row("Charge Cycles:", diag.get('cycles', '0 cycles'))
        add_row("Wear Degradation:", diag.get('wear_percent', '0%'))
        add_row("Lifespan Forecast:", diag.get('wear_forecast', 'Est. ~45 months'))
        add_row("Temperature:", diag.get('temp', 'N/A'))
        add_row("Voltage:", diag.get('voltage', 'N/A'))
        add_row("Chemistry:", diag.get('tech', 'Li-ion'))
        add_row("Charging Thresholds:", f"{self.smart_alerts.low_threshold}% Low / {self.smart_alerts.high_threshold}% High")
        add_row("Time to Target:", diag.get('time_to_target', 'Calculating...'))
        add_row("Prediction Engine:", "Historical Time-Series EMA (Local & Lightweight)")

        def export_csv():
            try:
                import csv
                out_path = os.path.expanduser("~/Desktop/Battery_Guard_Enterprise_Report.csv")
                with open(out_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(["Metric", "Value", "Timestamp"])
                    writer.writerow(["Battery Health", diag.get('health', '100%'), time.strftime("%Y-%m-%d %H:%M:%S")])
                    writer.writerow(["Design Capacity", diag.get('capacity_design', 'N/A'), ""])
                    writer.writerow(["Current Capacity", diag.get('capacity_now', 'N/A'), ""])
                    writer.writerow(["Charge Cycles", diag.get('cycles', '0 cycles'), ""])
                    writer.writerow(["Voltage", diag.get('voltage', 'N/A'), ""])
                    writer.writerow(["Temperature", diag.get('temp', 'N/A'), ""])
                    writer.writerow(["Technology", diag.get('tech', 'Li-ion'), ""])
                    writer.writerow(["Eco-Mode Status", "Enabled" if self.config_data.get("eco_mode_enabled") else "Disabled", ""])
                self.alert_bar_label.configure(text="✓ Exported report to Desktop!", text_color=C["green"])
                win.destroy()
            except Exception as e:
                print(f"[Export] {e}")

        btn_frame = ctk.CTkFrame(win, fg_color="transparent")
        btn_frame.pack(pady=16)
        ctk.CTkButton(btn_frame, text="📥 Export CSV", height=38, font=font_bold(13), fg_color=C["bg_card_alt"],
                      hover_color=C["bg_hover"], text_color=C["green"], command=export_csv).pack(side="left", padx=6)
        ctk.CTkButton(btn_frame, text="Close", height=38, font=font_bold(13), fg_color=C["btn_primary"],
                      hover_color=C["blue_hover"], command=win.destroy).pack(side="left", padx=6)

    def _open_settings(self):
        SettingsPanel(self, self.config_data, self._on_settings_save)

    def _on_settings_save(self, new_config):
        self.config_data = new_config
        self.smart_alerts.low_threshold = self.config_data.get("lower_threshold", 20)
        self.smart_alerts.high_threshold = self.config_data.get("upper_threshold", 80)
        self.smart_alerts.whatsapp_phone = self.config_data.get("whatsapp_phone", "")
        self.smart_alerts.whatsapp_apikey = self.config_data.get("whatsapp_apikey", "")
        self.smart_alerts.ntfy_topic = self.config_data.get("ntfy_topic", "")
        self.smart_alerts.quiet_hours_enabled = self.config_data.get("quiet_hours_enabled", False)
        self._update_sa_status_display()

    def _show_wizard(self):
        SetupWizard(self, self.config_data, self._on_wizard_complete)

    def _on_wizard_complete(self):
        self.config_data = load_config()

    def show_window(self):
        try:
            self.deiconify()
            self.state("normal")
            self.attributes("-topmost", True)
            self.lift()
            self.focus_force()
            self.after(250, lambda: self.attributes("-topmost", False))
        except Exception:
            pass

    def hide_to_tray(self):
        self.withdraw()

    def test_notification(self):
        try:
            self.smart_alerts._trigger_alert("high", self.battery_percent or 85)
        except Exception as e:
            print(f"[Test] {e}")
        if self.config_data.get("sound_enabled", True):
            beep_once()

    def quit_app(self):
        self._running = False
        self.tray.stop()
        try: self.destroy()
        except: pass
        os._exit(0)


# ─── Entry Point ──────────────────────────────────────────────────────────────

def main():
    if "--daemon" in sys.argv or "--headless" in sys.argv:
        print("[Enterprise Daemon] Starting Battery Guard in headless server mode...", flush=True)
        config = load_config()
        sa = SmartAlerts(
            low_threshold=config.get("lower_threshold", 20),
            high_threshold=config.get("upper_threshold", 80),
            enabled=config.get("smart_alerts_enabled", True),
            whatsapp_phone=config.get("whatsapp_phone", ""),
            whatsapp_apikey=config.get("whatsapp_apikey", ""),
            ntfy_topic=config.get("ntfy_topic", ""),
            quiet_hours_enabled=config.get("quiet_hours_enabled", False),
        )
        sa.voice_enabled = config.get("voice_enabled", False)
        sa.webhook_url = config.get("webhook_url", "")
        sa.sms_enabled = config.get("sms_enabled", False)
        sa.sms_phone = config.get("sms_phone", "")
        sa.sms_apikey = config.get("sms_apikey", "")
        sa.phone_call_enabled = config.get("phone_call_enabled", False)
        sa.phone_call_number = config.get("phone_call_number", "")
        sa.phone_call_apikey = config.get("phone_call_apikey", "")
        sa.email_enabled = config.get("email_enabled", False)
        sa.email_smtp_server = config.get("email_smtp_server", "smtp.gmail.com")
        sa.email_smtp_port = config.get("email_smtp_port", 587)
        sa.email_sender = config.get("email_sender", "")
        sa.email_password = config.get("email_password", "")
        sa.email_recipient = config.get("email_recipient", "")
        while True:
            try:
                bat = psutil.sensors_battery()
                if bat:
                    sa.update(bat.percent, bat.power_plugged)
                    drain_predictor.log_sample(bat.percent, bat.power_plugged)
            except Exception as e:
                print(f"[Daemon Error] {e}")
            if bat and ((not bat.power_plugged and bat.percent <= sa.low_threshold + 8) or (bat.power_plugged and bat.percent >= sa.high_threshold - 5)):
                time.sleep(2)
            else:
                time.sleep(10)
        return

    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    app = BatteryGuardApp()
    app.mainloop()

if __name__ == "__main__":
    main()
