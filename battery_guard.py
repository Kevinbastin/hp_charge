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
from datetime import datetime
from pathlib import Path

import customtkinter as ctk
import psutil
import requests
from PIL import Image, ImageDraw, ImageFont

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


def save_config(cfg):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)


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
                MenuItem("Open App", on_open),
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
                    MenuItem("Open App", on_open),
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

        # ── Preferences ──
        self._section(scroll, "Preferences")

        card3 = self._card(scroll)
        self.sound_var = ctk.BooleanVar(value=self.config.get("sound_enabled", True))
        self._toggle_row(card3, "Sound alerts", self.sound_var)
        ctk.CTkFrame(card3, height=1, fg_color=C["border"]).pack(fill="x", padx=16)
        self.hibernate_var = ctk.BooleanVar(value=self.config.get("auto_hibernate", False))
        self._toggle_row(card3, "Auto suspend at limit", self.hibernate_var)
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

    def _save(self):
        self.config["upper_threshold"] = int(self.upper_slider.get())
        self.config["lower_threshold"] = int(self.lower_slider.get())
        self.config["telegram_token"] = self.token_entry.get().strip()
        self.config["telegram_chat_id"] = self.chat_entry.get().strip()
        self.config["sound_enabled"] = self.sound_var.get()
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
                                      f'pythonw "{os.path.abspath(sys.argv[0])}"')
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
                        f"Exec=python3 {os.path.abspath(sys.argv[0])}\n"
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

        self.title("Battery Guard")
        self.geometry("460x740")
        self.minsize(420, 700)
        self.configure(fg_color=C["bg"])

        # Center window
        self.update_idletasks()
        w, h = 460, 740
        x = (self.winfo_screenwidth() // 2) - (w // 2)
        y = (self.winfo_screenheight() // 2) - (h // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

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

        # Settings button
        ctk.CTkButton(header, text="⚙", width=36, height=36,
                      font=font(16), fg_color="transparent",
                      hover_color=C["bg_hover"], text_color=C["text_dim"],
                      corner_radius=8,
                      command=self._open_settings).pack(side="right", padx=(0, 4))

        # Thin accent line under header
        ctk.CTkFrame(self, height=1, fg_color=C["border"], corner_radius=0).pack(fill="x")

        # ── Main content area ──
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=24, pady=16)

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

                if self.secs_left and self.secs_left > 0:
                    hrs = int(self.secs_left // 3600)
                    mins = int((self.secs_left % 3600) // 60)
                    if self.is_charging:
                        self.time_estimate_label.configure(text=f"{hrs}h {mins}m to full")
                        self.time_detail_label.configure(text="Estimated charge time")
                    else:
                        self.time_estimate_label.configure(text=f"{hrs}h {mins}m remaining")
                        self.time_detail_label.configure(text="Estimated battery life")
                else:
                    if self.is_charging:
                        if self.battery_percent >= 100:
                            self.time_estimate_label.configure(text="Fully charged")
                            self.time_detail_label.configure(text="Battery at 100%")
                        else:
                            self.time_estimate_label.configure(text="Calculating...")
                            self.time_detail_label.configure(text="Estimating charge time")
                    else:
                        self.time_estimate_label.configure(text="Calculating...")
                        self.time_detail_label.configure(text="Estimating remaining time")

                self.tray.update(self.battery_percent)
                self._check_alerts()
            else:
                self.charge_status_label.configure(text="No battery found", text_color=C["red"])
        except Exception as e:
            print(f"[Battery] {e}")

        if self.alert_active and not self._glow_running:
            self._glow_running = True
            self.after(100, self._animate_glow)

        self.after(30000, self._update_battery)

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

            if alert_type == "high" and self.config_data.get("auto_hibernate"):
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

    def _open_settings(self):
        SettingsPanel(self, self.config_data, self._on_settings_save)

    def _on_settings_save(self, new_config):
        self.config_data = new_config

    def _show_wizard(self):
        SetupWizard(self, self.config_data, self._on_wizard_complete)

    def _on_wizard_complete(self):
        self.config_data = load_config()

    def show_window(self):
        self.deiconify()
        self.lift()
        self.focus_force()

    def hide_to_tray(self):
        self.withdraw()

    def test_notification(self):
        token = self.config_data.get("telegram_token", "")
        chat_id = self.config_data.get("telegram_chat_id", "")
        if token and chat_id:
            threading.Thread(target=send_telegram,
                             args=(token, chat_id, "🧪 <b>Battery Guard</b> — Test notification!"),
                             daemon=True).start()
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
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    app = BatteryGuardApp()
    app.mainloop()

if __name__ == "__main__":
    main()
