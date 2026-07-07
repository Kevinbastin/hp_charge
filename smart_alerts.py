#!/usr/bin/env python3
"""
Smart Alerts — Standalone Battery Alert Logic
Handles edge-triggered alerts with hysteresis for desktop popups, WhatsApp, and ntfy.sh push notifications.
No GUI dependencies, no threading, no timers.
"""

import datetime
from pathlib import Path
import time
import urllib.parse


class SmartAlerts:
    """
    Manages battery threshold monitoring and alert dispatching.

    Responsibilities:
      - Holds low/high thresholds, enabled flag, and already-fired state flags.
      - Implements edge-triggered logic with hysteresis to prevent flicker-spam.
      - Dispatches alerts via desktop popups (plyer), WhatsApp (CallMeBot), and instant push alerts (ntfy.sh).
      - Enforces strict resilience: timeouts, lazy imports, no persistent sockets, quiet logging.
      - Optional additions: 2-minute cooldown, quiet hours (00:00-07:00), multi-recipient support.
    """

    def __init__(
        self,
        low_threshold=20,
        high_threshold=80,
        enabled=True,
        whatsapp_phone="",
        whatsapp_apikey="",
        ntfy_topic="",
        hysteresis=2,
        cooldown_seconds=120,
        quiet_hours_enabled=False,
    ):
        self.low_threshold = low_threshold
        self.high_threshold = high_threshold
        self.enabled = enabled
        self.whatsapp_phone = whatsapp_phone
        self.whatsapp_apikey = whatsapp_apikey
        self.ntfy_topic = ntfy_topic
        self.hysteresis = hysteresis

        # Optional enhancements
        self.cooldown_seconds = cooldown_seconds
        self._last_alert_time = 0
        self.quiet_hours_enabled = quiet_hours_enabled
        self.quiet_start_hour = 0
        self.quiet_end_hour = 7
        self.voice_enabled = False
        self.webhook_url = ""
        self.sms_enabled = False
        self.sms_phone = ""
        self.sms_apikey = ""
        self.phone_call_enabled = False
        self.phone_call_number = ""
        self.phone_call_apikey = ""
        self.email_enabled = False
        self.email_smtp_server = "smtp.gmail.com"
        self.email_smtp_port = 587
        self.email_sender = ""
        self.email_password = ""
        self.email_recipient = ""

        # State flags: fire once when crossing threshold, reset only after crossing hysteresis line
        self._low_fired = False
        self._high_fired = False

    def set_enabled(self, enabled):
        """
        Toggles alert monitoring on or off.
        Toggling off resets the already-fired flags so re-enabling later starts clean.
        """
        self.enabled = bool(enabled)
        if not self.enabled:
            self._low_fired = False
            self._high_fired = False

    def update(self, percent, is_charging):
        """
        Main update entry point to be called from the polling loop.

        Args:
            percent (float/int): Current battery percentage (0-100).
            is_charging (bool): Whether the battery is currently plugged in and charging.
        """
        # Very first line checks the enabled flag and returns immediately if off
        if not self.enabled:
            return

        # ── Hysteresis Reset Logic ──
        # Reset low alert flag if battery recovered past hysteresis point OR charger connected
        if self._low_fired and (percent >= self.low_threshold + self.hysteresis or is_charging):
            self._low_fired = False

        # Reset high alert flag if battery dropped below hysteresis point OR charger disconnected
        if self._high_fired and (percent <= self.high_threshold - self.hysteresis or not is_charging):
            self._high_fired = False

        # ── Cooldown Check ──
        # Backstop in case hysteresis alone isn't enough on a noisy battery reading
        now = time.time()
        if now - self._last_alert_time < self.cooldown_seconds:
            return

        # ── Edge-Triggered Alert Logic ──
        # Trigger low battery alert: crossing below or at low threshold while discharging
        if not self._low_fired and percent <= self.low_threshold and not is_charging:
            self._low_fired = True
            self._last_alert_time = now
            self._trigger_alert("low", percent)
        # Trigger high battery alert: crossing above or at high threshold while charging
        elif not self._high_fired and percent >= self.high_threshold and is_charging:
            self._high_fired = True
            self._last_alert_time = now
            self._trigger_alert("high", percent)

    def _trigger_alert(self, alert_type, percent):
        """Dispatches notifications asynchronously in parallel across all channels."""
        try:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
                executor.submit(self._send_popup, alert_type, percent)
                executor.submit(self._send_whatsapp, alert_type, percent)
                executor.submit(self._send_ntfy, alert_type, percent)
                executor.submit(self._send_voice, alert_type, percent)
                executor.submit(self._send_webhook, alert_type, percent)
                executor.submit(self._send_sms, alert_type, percent)
                executor.submit(self._send_phone_call, alert_type, percent)
                executor.submit(self._send_email, alert_type, percent)
        except Exception as e:
            self._log_failure(f"Parallel dispatch error: {e}")
            self._send_popup(alert_type, percent)
            self._send_whatsapp(alert_type, percent)
            self._send_ntfy(alert_type, percent)
            self._send_voice(alert_type, percent)
            self._send_webhook(alert_type, percent)
            self._send_sms(alert_type, percent)
            self._send_phone_call(alert_type, percent)
            self._send_email(alert_type, percent)
        self._log_audit_event(alert_type, percent)

    def _send_webhook(self, alert_type, percent):
        if not getattr(self, "webhook_url", "") or not str(self.webhook_url).startswith("http"):
            return
        try:
            import requests
            if alert_type == "high":
                text = f"[Enterprise Alert] ⚡ Battery reached {int(percent)}%. Disconnect charger."
            else:
                text = f"[Enterprise Alert] 🔋 Low Battery Warning: {int(percent)}%. Connect charger."
            payload = {
                "text": text,
                "content": text,
                "alert_type": alert_type,
                "battery_percent": int(percent),
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }
            requests.post(self.webhook_url, json=payload, timeout=5)
        except Exception as e:
            self._log_failure(f"Webhook dispatch failed: {e}")

    def _log_audit_event(self, alert_type, percent):
        try:
            audit_file = os.path.expanduser("~/.battery_guard/audit.jsonl")
            os.makedirs(os.path.dirname(audit_file), exist_ok=True)
            import json
            entry = {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "event": f"alert_{alert_type}",
                "percent": int(percent),
                "status": "triggered"
            }
            with open(audit_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
            try:
                os.chmod(audit_file, 0o600)
            except Exception:
                pass
        except Exception:
            pass

    def _send_voice(self, alert_type, percent):
        if not getattr(self, "voice_enabled", False):
            return
        try:
            if alert_type == "high":
                msg = f"Warning: Battery reached {int(percent)} percent. Please disconnect your charger."
            else:
                msg = f"Warning: Low battery at {int(percent)} percent. Please connect your charger."
            if IS_LINUX:
                os.system(f'spd-say "{msg}" 2>/dev/null &')
            elif IS_WINDOWS:
                os.system(f'mshta vbscript:Execute("CreateObject(""SAPI.SpVoice"").Speak(""" & "{msg}" & """)(window.close)") 2>/dev/null &')
        except Exception as e:
            self._log_failure(f"Voice announcement failed: {e}")

    def _send_popup(self, alert_type, percent):
        """
        Sends a desktop notification popup.
        Lazy imports plyer inside the method so it only loads into memory when an alert fires.
        Silenced during quiet hours (midnight–7am) if enabled.
        """
        if self.quiet_hours_enabled:
            current_hour = datetime.datetime.now().hour
            if self.quiet_start_hour <= current_hour < self.quiet_end_hour:
                self._log_failure("Popup notification silenced due to Quiet Hours (00:00 - 07:00).")
                return

        try:
            # Lazy import inside function
            from plyer import notification

            if alert_type == "high":
                title = "⚡ Unplug Charger Now"
                message = f"Battery reached {int(percent)}%. Disconnect charger to protect battery life."
            else:
                title = "🔋 Low Battery Warning"
                message = f"Battery dropped to {int(percent)}%. Connect charger to avoid shutting down."

            notification.notify(
                title=title,
                message=message,
                app_name="Battery Guard",
                timeout=10,
            )
        except Exception as e:
            self._log_failure(f"Popup notification failed: {e}")

    def _send_whatsapp(self, alert_type, percent):
        """
        Sends a WhatsApp notification using Green API (recommended) or CallMeBot API.
        Supports multiple recipients via comma-separated numbers and keys.
        For Green API, format apikey as: instanceId/apiToken (e.g. 1101823456/d75b3a66...).
        Uses a one-off request per alert (no persistent session) with an 8-second timeout.
        """
        if not self.whatsapp_phone or not self.whatsapp_apikey:
            self._log_failure("WhatsApp notification skipped: phone or apikey not configured.")
            return

        try:
            # Lazy import requests to keep startup light
            import requests
            import re

            if alert_type == "high":
                text = f"⚡ Battery at {int(percent)}%! Please unplug your charger now to preserve battery health."
            else:
                text = f"🔋 Low Battery Warning! Battery is at {int(percent)}%. Please plug in your charger now."

            encoded_text = urllib.parse.quote(text)

            # Support comma-separated recipients
            phones = [p.strip() for p in str(self.whatsapp_phone).split(",") if p.strip()]
            keys = [k.strip() for k in str(self.whatsapp_apikey).split(",") if k.strip()]

            for i, phone in enumerate(phones):
                key = keys[i] if i < len(keys) else (keys[0] if keys else "")
                if not phone or not key:
                    continue

                if "/" in key or ":" in key:
                    parts = re.split(r'[/:]', key, maxsplit=1)
                    inst_num = re.sub(r'\D', '', parts[0].strip())
                    token = parts[1].strip()
                    subdomain = inst_num[:4] if len(inst_num) >= 4 else "api"
                    url = f"https://{subdomain}.api.green-api.com/waInstance{inst_num}/sendMessage/{token}"
                    chat_id = phone if "@" in phone else f"{phone.lstrip('+')}@c.us"
                    payload = {"chatId": chat_id, "message": text}
                    response = requests.post(url, json=payload, timeout=8)
                    if response.status_code not in (200, 201) or "idMessage" not in response.text:
                        self._log_failure(f"Green API send failed for {phone} with status {response.status_code}: {response.text}")
                else:
                    url = (
                        f"https://api.callmebot.com/whatsapp.php"
                        f"?phone={phone}&text={encoded_text}&apikey={key}"
                    )
                    response = requests.get(url, timeout=8)
                    if response.status_code != 200:
                        self._log_failure(f"WhatsApp send failed for {phone} with status {response.status_code}: {response.text}")
        except Exception as e:
            self._log_failure(f"WhatsApp notification failed: {e}")

    def _send_ntfy(self, alert_type, percent):
        """
        Sends an instant push notification to ntfy.sh topic.
        Supports multiple comma-separated topics.
        Uses Priority: high and custom tags/titles so the phone rings loudly.
        """
        if not self.ntfy_topic:
            self._log_failure("ntfy notification skipped: topic not configured.")
            return

        try:
            import requests
            topics = [t.strip() for t in str(self.ntfy_topic).split(",") if t.strip()]
            for topic in topics:
                url = f"https://ntfy.sh/{topic}"
                if alert_type == "high":
                    title = "Battery Guard - Unplug Charger Now!"
                    message = f"Battery reached {int(percent)}%. Disconnect charger to protect battery health."
                    priority = "high"
                    tags = "zap,warning,battery"
                else:
                    title = "Battery Guard - Low Battery Warning!"
                    message = f"Battery dropped to {int(percent)}%. Connect charger immediately."
                    priority = "high"
                    tags = "battery,exclamation"

                headers = {
                    "Title": title,
                    "Priority": priority,
                    "Tags": tags,
                }
                response = requests.post(url, data=message.encode("utf-8"), headers=headers, timeout=8)
                if response.status_code != 200:
                    self._log_failure(f"ntfy send failed for topic {topic} with status {response.status_code}: {response.text}")
        except Exception as e:
            self._log_failure(f"ntfy notification failed: {e}")

    def _send_sms(self, alert_type, percent):
        if not getattr(self, "sms_enabled", False) or not getattr(self, "sms_phone", "") or not getattr(self, "sms_apikey", ""):
            return
        try:
            import requests
            phone = str(self.sms_phone).strip()
            key = str(self.sms_apikey).strip()
            if alert_type == "high":
                text = f"[Battery Guard] ⚡ Battery at {int(percent)}%. Please disconnect charger now!"
            else:
                text = f"[Battery Guard] 🔋 Low Battery Warning: {int(percent)}%. Please connect charger!"

            # Fast2SMS or Twilio support (if key has colons like AccountSID:AuthToken:FromNumber, use Twilio)
            if ":" in key and key.count(":") >= 2:
                parts = key.split(":")
                sid, token, from_num = parts[0].strip(), parts[1].strip(), parts[2].strip()
                url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
                requests.post(url, auth=(sid, token), data={"From": from_num, "To": phone, "Body": text}, timeout=8)
            else:
                # Default to Fast2SMS (popular global & Indian SMS gateway)
                url = "https://www.fast2sms.com/dev/bulkV2"
                headers = {"authorization": key}
                payload = {"route": "q", "message": text, "language": "english", "flash": 0, "numbers": phone}
                requests.post(url, headers=headers, json=payload, timeout=8)
        except Exception as e:
            self._log_failure(f"SMS dispatch failed: {e}")

    def _send_phone_call(self, alert_type, percent):
        if not getattr(self, "phone_call_enabled", False) or not getattr(self, "phone_call_number", "") or not getattr(self, "phone_call_apikey", ""):
            return
        try:
            import requests
            phone = str(self.phone_call_number).strip()
            key = str(self.phone_call_apikey).strip()
            if alert_type == "high":
                text = f"Alert! Your laptop battery is at {int(percent)} percent. Please unplug your charger now."
            else:
                text = f"Alert! Low battery warning at {int(percent)} percent. Please plug in your charger now."
            encoded_text = urllib.parse.quote(text)

            # CallMeBot Phone Call API or Twilio Voice
            if ":" in key and key.count(":") >= 2:
                parts = key.split(":")
                sid, token, from_num = parts[0].strip(), parts[1].strip(), parts[2].strip()
                url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Calls.json"
                twiml = f"<Response><Say>{text}</Say></Response>"
                requests.post(url, auth=(sid, token), data={"From": from_num, "To": phone, "Twiml": twiml}, timeout=8)
            else:
                # Default to CallMeBot Phone Call API
                url = f"https://api.callmebot.com/start.php?phone={phone}&text={encoded_text}&apikey={key}&lang=en-US-Standard-B&rpt=2"
                requests.get(url, timeout=8)
        except Exception as e:
            self._log_failure(f"Automated voice call dispatch failed: {e}")

    def _send_email(self, alert_type, percent):
        if not getattr(self, "email_enabled", False) or not getattr(self, "email_sender", "") or not getattr(self, "email_password", "") or not getattr(self, "email_recipient", ""):
            return
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart

            sender = str(self.email_sender).strip()
            pwd = str(self.email_password).strip()
            recipient = str(self.email_recipient).strip()
            server = getattr(self, "email_smtp_server", "smtp.gmail.com")
            port = int(getattr(self, "email_smtp_port", 587))

            subject = f"🚨 [Battery Guard Enterprise] {'High Battery Warning' if alert_type == 'high' else 'Low Battery Alert'} — {int(percent)}%"
            html = f"""
            <div style="font-family: Arial, sans-serif; padding: 20px; background-color: #1e1e2e; color: #cdd6f4; border-radius: 8px;">
                <h2 style="color: {'#f38ba8' if alert_type == 'high' else '#fab387'};">
                    ⚡ Battery Guard Enterprise Alert
                </h2>
                <p style="font-size: 16px;">
                    Your workstation battery has reached critical threshold: <strong>{int(percent)}%</strong>.
                </p>
                <div style="background-color: #181825; padding: 15px; border-radius: 6px; margin: 20px 0;">
                    <p><strong>Status:</strong> {'Charging (Disconnect required)' if alert_type == 'high' else 'Discharging (Connect required)'}</p>
                    <p><strong>Timestamp:</strong> {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                </div>
                <p style="font-size: 12px; color: #6c7086;">Generated automatically by Battery Guard Enterprise Telemetry.</p>
            </div>
            """
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = sender
            msg["To"] = recipient
            msg.attach(MIMEText(html, "html"))

            with smtplib.SMTP(server, port, timeout=10) as smtp:
                smtp.starttls()
                smtp.login(sender, pwd)
                smtp.send_message(msg)
        except Exception as e:
            self._log_failure(f"SMTP Email dispatch failed: {e}")

    def _log_failure(self, message):
        """
        Logs failures quietly to a log file and stderr rather than surfacing errors to the GUI/user.
        """
        try:
            log_dir = Path.home() / ".battery_guard"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / "alerts.log"
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] {message}\n")
            try:
                os.chmod(log_file, 0o600)
            except Exception:
                pass
        except Exception:
            pass
        print(f"[SmartAlerts Quiet Log] {message}")
