"""
Pomodoro Menu Bar Timer
"""

import rumps
import subprocess
import threading
import json
import os
import datetime

# ── Paths ──────────────────────────────────────────────────────────────────────
CONFIG_PATH = os.path.expanduser("~/.pomobar.json")

SYSTEM_SOUNDS_DIR = "/System/Library/Sounds"
SOUND_OPTIONS = ["Ping", "Basso", "Blow", "Bottle", "Frog", "Funk",
                 "Glass", "Hero", "Morse", "Pop", "Purr", "Sosumi",
                 "Submarine", "Tink"]

# ── Defaults ───────────────────────────────────────────────────────────────────
DEFAULT_CONFIG = {
    "pomodoro_min": 25,
    "short_break_min": 5,
    "long_break_min": 15,
    "long_break_interval": 4,
    "auto_start_breaks": False,
    "auto_start_pomodoros": False,
    "alarm_enabled": True,
    "alarm_sound": "Ping",
    "alarm_volume": 50,       # 0-100
    "alarm_repeat": 1,
    "ticking_enabled": False,
    "ticking_sound": "Tink",
    "ticking_volume": 20,     # 0-100
    "show_mode_icon": True,
    "focused_today_sec": 0,
    "focused_date": "",
}


def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                saved = json.load(f)
            return {**DEFAULT_CONFIG, **saved}
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)


def save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


def play_sound(name, volume=50, repeat=1):
    """Play a macOS system sound using afplay in a background thread."""
    path = os.path.join(SYSTEM_SOUNDS_DIR, f"{name}.aiff")
    if not os.path.exists(path):
        return
    vol = max(0, min(volume, 100)) / 100.0

    def _play():
        for _ in range(repeat):
            subprocess.run(
                ["afplay", "-v", str(vol), path],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )

    threading.Thread(target=_play, daemon=True).start()


# ── Mode Constants ─────────────────────────────────────────────────────────────
POMODORO = "pomodoro"
SHORT_BREAK = "short_break"
LONG_BREAK = "long_break"

MODE_LABELS = {
    POMODORO: "Pomodoro",
    SHORT_BREAK: "Short Break",
    LONG_BREAK: "Long Break",
}

MODE_ICONS = {
    POMODORO: "🍅",
    SHORT_BREAK: "☕",
    LONG_BREAK: "🌴",
}

DURATION_KEYS = {
    POMODORO: "pomodoro_min",
    SHORT_BREAK: "short_break_min",
    LONG_BREAK: "long_break_min",
}


class PomodoroApp(rumps.App):

    def __init__(self):
        super().__init__("🍅", quit_button=None)

        self.cfg = load_config()

        today = datetime.date.today().isoformat()
        if self.cfg["focused_date"] != today:
            self.cfg["focused_today_sec"] = 0
            self.cfg["focused_date"] = today
            save_config(self.cfg)

        # ── State ──────────────────────────────────────────────────────────
        self.mode = POMODORO
        self.remaining = self.cfg["pomodoro_min"] * 60
        self.running = False
        self.pomodoro_count = 0  # completed pomodoros in current cycle

        # ── Timers ─────────────────────────────────────────────────────────
        self.timer = rumps.Timer(self._tick, 1)
        self.tick_sound_timer = rumps.Timer(self._play_tick_sound, 1)

        # ── Build menu ─────────────────────────────────────────────────────
        self._build_menu()
        self._update_title()

    # ══════════════════════════════════════════════════════════════════════════
    #  Menu Construction
    # ══════════════════════════════════════════════════════════════════════════

    def _build_menu(self):
        self.start_pause_item = rumps.MenuItem("Start", callback=self._toggle_start_pause)
        self.skip_item = rumps.MenuItem("Skip", callback=self._skip)
        self.reset_item = rumps.MenuItem("Reset", callback=self._reset)

        # ── Mode submenu ───────────────────────────────────────────────────
        self.mode_menu = rumps.MenuItem("Mode")
        self.mode_items = {}
        for key, label in MODE_LABELS.items():
            icon = MODE_ICONS[key]
            mins = self.cfg[DURATION_KEYS[key]]
            item = rumps.MenuItem(
                f"{icon}  {label} ({mins} min)",
                callback=self._make_mode_cb(key),
            )
            item.state = 1 if key == self.mode else 0
            self.mode_items[key] = item
            self.mode_menu.add(item)

        # ── Settings submenu ───────────────────────────────────────────────
        self.settings_menu = rumps.MenuItem("Settings")

        #  Durations
        dur_menu = rumps.MenuItem("Timer Durations")
        dur_menu.add(rumps.MenuItem("Pomodoro Duration…", callback=self._set_pomodoro_dur))
        dur_menu.add(rumps.MenuItem("Short Break Duration…", callback=self._set_short_break_dur))
        dur_menu.add(rumps.MenuItem("Long Break Duration…", callback=self._set_long_break_dur))
        dur_menu.add(rumps.MenuItem("Long Break Interval…", callback=self._set_long_break_interval))
        self.settings_menu.add(dur_menu)
        self.settings_menu.add(rumps.separator)

        #  Auto-start toggles
        self.auto_break_item = rumps.MenuItem("Auto-start Breaks", callback=self._toggle_auto_breaks)
        self.auto_break_item.state = self.cfg["auto_start_breaks"]
        self.settings_menu.add(self.auto_break_item)

        self.auto_pomo_item = rumps.MenuItem("Auto-start Pomodoros", callback=self._toggle_auto_pomodoros)
        self.auto_pomo_item.state = self.cfg["auto_start_pomodoros"]
        self.settings_menu.add(self.auto_pomo_item)
        self.settings_menu.add(rumps.separator)

        self.show_icon_item = rumps.MenuItem("Show Mode Icon", callback=self._toggle_show_icon)
        self.show_icon_item.state = self.cfg["show_mode_icon"]
        self.settings_menu.add(self.show_icon_item)
        self.settings_menu.add(rumps.separator)

        #  Alarm
        alarm_menu = rumps.MenuItem("Alarm")

        self.alarm_enabled_item = rumps.MenuItem("Enabled", callback=self._toggle_alarm)
        self.alarm_enabled_item.state = self.cfg["alarm_enabled"]
        alarm_menu.add(self.alarm_enabled_item)

        alarm_sound_menu = rumps.MenuItem("Sound")
        self.alarm_sound_items = {}
        for s in SOUND_OPTIONS:
            item = rumps.MenuItem(s, callback=self._make_alarm_sound_cb(s))
            item.state = 1 if s == self.cfg["alarm_sound"] else 0
            self.alarm_sound_items[s] = item
            alarm_sound_menu.add(item)
        alarm_menu.add(alarm_sound_menu)

        self.alarm_volume_item = rumps.MenuItem(f"Volume: {self.cfg['alarm_volume']}…", callback=self._set_alarm_volume)
        alarm_menu.add(self.alarm_volume_item)
        self.alarm_repeat_item = rumps.MenuItem(f"Repeat: {self.cfg['alarm_repeat']}…", callback=self._set_alarm_repeat)
        alarm_menu.add(self.alarm_repeat_item)
        alarm_menu.add(rumps.MenuItem("Test Alarm", callback=self._test_alarm))
        self.settings_menu.add(alarm_menu)

        #  Ticking
        tick_menu = rumps.MenuItem("Ticking Sound")

        self.tick_enabled_item = rumps.MenuItem("Enabled", callback=self._toggle_ticking)
        self.tick_enabled_item.state = self.cfg["ticking_enabled"]
        tick_menu.add(self.tick_enabled_item)

        tick_sound_menu = rumps.MenuItem("Sound")
        self.tick_sound_items = {}
        for s in SOUND_OPTIONS:
            item = rumps.MenuItem(s, callback=self._make_tick_sound_cb(s))
            item.state = 1 if s == self.cfg["ticking_sound"] else 0
            self.tick_sound_items[s] = item
            tick_sound_menu.add(item)
        tick_menu.add(tick_sound_menu)

        self.tick_volume_item = rumps.MenuItem(f"Volume: {self.cfg['ticking_volume']}…", callback=self._set_ticking_volume)
        tick_menu.add(self.tick_volume_item)
        self.settings_menu.add(tick_menu)

        # ── Session counter & focus time ───────────────────────────────────
        self.session_display = rumps.MenuItem(self._session_text(), callback=None)
        self.focused_display = rumps.MenuItem(self._focused_text(), callback=None)

        # ── Quit ───────────────────────────────────────────────────────────
        quit_item = rumps.MenuItem("Quit", callback=rumps.quit_application)

        # ── Assemble ───────────────────────────────────────────────────────
        self.menu = [
            self.start_pause_item,
            self.skip_item,
            self.reset_item,
            rumps.separator,
            self.mode_menu,
            rumps.separator,
            self.session_display,
            self.focused_display,
            rumps.separator,
            self.settings_menu,
            rumps.separator,
            quit_item,
        ]

    # ══════════════════════════════════════════════════════════════════════════
    #  Display Helpers
    # ══════════════════════════════════════════════════════════════════════════

    def _format_time(self, seconds):
        m, s = divmod(max(0, seconds), 60)
        return f"{m:02d}:{s:02d}"

    def _update_title(self):
        if self.cfg["show_mode_icon"]:
            self.title = f"{MODE_ICONS[self.mode]} {self._format_time(self.remaining)}"
        else:
            self.title = self._format_time(self.remaining)

    def _session_text(self):
        return f"Sessions: {self.pomodoro_count}/{self.cfg['long_break_interval']}"

    def _focused_text(self):
        sec = self.cfg["focused_today_sec"]
        h, rem = divmod(sec, 3600)
        m = rem // 60
        if h > 0:
            return f"Focused today: {h}h {m}m"
        return f"Focused today: {m}m"

    # ══════════════════════════════════════════════════════════════════════════
    #  Core Timer Logic
    # ══════════════════════════════════════════════════════════════════════════

    def _tick(self, _):
        if not self.running:
            return
        today = datetime.date.today().isoformat()
        if self.cfg["focused_date"] != today:
            self.cfg["focused_today_sec"] = 0
            self.cfg["focused_date"] = today
            save_config(self.cfg)
            self.focused_display.title = self._focused_text()
        self.remaining -= 1
        self._update_title()
        if self.remaining <= 0:
            self._on_timer_complete()

    def _on_timer_complete(self):
        self._stop_timer()

        if self.mode == POMODORO:
            elapsed = self.cfg["pomodoro_min"] * 60 - max(0, self.remaining)
            self.cfg["focused_today_sec"] += max(0, elapsed)
            self.cfg["focused_date"] = datetime.date.today().isoformat()
            save_config(self.cfg)
            self.focused_display.title = self._focused_text()

        if self.cfg["alarm_enabled"]:
            play_sound(
                self.cfg["alarm_sound"],
                self.cfg["alarm_volume"],
                self.cfg["alarm_repeat"],
            )

        if self.mode == POMODORO:
            self.pomodoro_count += 1
            self.session_display.title = self._session_text()

            if self.pomodoro_count % self.cfg["long_break_interval"] == 0:
                next_mode = LONG_BREAK
            else:
                next_mode = SHORT_BREAK

            self._switch_mode(next_mode)

            if self.cfg["auto_start_breaks"]:
                self._start_timer()
            else:
                rumps.notification(
                    "Pomodoro Complete!",
                    f"Session #{self.pomodoro_count} done",
                    f"Time for a {MODE_LABELS[next_mode].lower()}!",
                )
        else:
            self._switch_mode(POMODORO)

            if self.cfg["auto_start_pomodoros"]:
                self._start_timer()
            else:
                rumps.notification("Break Over!", "", "Time to focus!")

    def _start_timer(self):
        self.running = True
        self.start_pause_item.title = "Pause"
        self.timer.start()
        if self.cfg["ticking_enabled"]:
            self.tick_sound_timer.start()

    def _stop_timer(self):
        self.running = False
        self.start_pause_item.title = "Start"
        self.timer.stop()
        self.tick_sound_timer.stop()

    def _duration_for_mode(self, mode):
        return self.cfg[DURATION_KEYS[mode]] * 60

    def _switch_mode(self, mode):
        for k, item in self.mode_items.items():
            item.state = 1 if k == mode else 0
        self.mode = mode
        self.remaining = self._duration_for_mode(mode)
        self._update_title()

    # ══════════════════════════════════════════════════════════════════════════
    #  Control Callbacks
    # ══════════════════════════════════════════════════════════════════════════

    def _toggle_start_pause(self, _):
        if self.running:
            self._stop_timer()
        else:
            self._start_timer()

    def _skip(self, _):
        self._stop_timer()
        self._on_timer_complete()

    def _reset(self, _):
        self._stop_timer()
        self.pomodoro_count = 0
        self.session_display.title = self._session_text()
        self.remaining = self._duration_for_mode(self.mode)
        self._update_title()

    def _make_mode_cb(self, mode_key):
        def cb(_):
            if self.running:
                self._stop_timer()
            self._switch_mode(mode_key)
        return cb

    # ══════════════════════════════════════════════════════════════════════════
    #  Settings Callbacks
    # ══════════════════════════════════════════════════════════════════════════

    def _prompt_int(self, title, message, default):
        script = (
            f'display dialog "{message}" '
            f'default answer "{default}" '
            f'with title "{title}" '
            f'buttons {{"Cancel", "Save"}} default button "Save"'
        )
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            return None
        for part in result.stdout.strip().split(", "):
            if part.startswith("text returned:"):
                try:
                    val = int(part.split(":", 1)[1].strip())
                    if val > 0:
                        return val
                except ValueError:
                    pass
        return None

    def _set_duration(self, mode, title, message):
        key = DURATION_KEYS[mode]
        val = self._prompt_int(title, message, self.cfg[key])
        if val:
            self.cfg[key] = val
            save_config(self.cfg)
            label = MODE_LABELS[mode]
            icon = MODE_ICONS[mode]
            self.mode_items[mode].title = f"{icon}  {label} ({val} min)"
            if self.mode == mode and not self.running:
                self.remaining = val * 60
                self._update_title()

    def _set_pomodoro_dur(self, _):
        self._set_duration(POMODORO, "Pomodoro Duration", "Focus session length (minutes):")

    def _set_short_break_dur(self, _):
        self._set_duration(SHORT_BREAK, "Short Break Duration", "Short break length (minutes):")

    def _set_long_break_dur(self, _):
        self._set_duration(LONG_BREAK, "Long Break Duration", "Long break length (minutes):")

    def _set_long_break_interval(self, _):
        val = self._prompt_int(
            "Long Break Interval",
            "Pomodoros before long break:",
            self.cfg["long_break_interval"],
        )
        if val:
            self.cfg["long_break_interval"] = val
            save_config(self.cfg)
            self.session_display.title = self._session_text()

    # Auto-start
    def _toggle_auto_breaks(self, sender):
        self.cfg["auto_start_breaks"] = not self.cfg["auto_start_breaks"]
        sender.state = self.cfg["auto_start_breaks"]
        save_config(self.cfg)

    def _toggle_auto_pomodoros(self, sender):
        self.cfg["auto_start_pomodoros"] = not self.cfg["auto_start_pomodoros"]
        sender.state = self.cfg["auto_start_pomodoros"]
        save_config(self.cfg)

    def _toggle_show_icon(self, sender):
        self.cfg["show_mode_icon"] = not self.cfg["show_mode_icon"]
        sender.state = self.cfg["show_mode_icon"]
        save_config(self.cfg)
        self._update_title()

    # Alarm
    def _toggle_alarm(self, sender):
        self.cfg["alarm_enabled"] = not self.cfg["alarm_enabled"]
        sender.state = self.cfg["alarm_enabled"]
        save_config(self.cfg)

    def _make_alarm_sound_cb(self, sound_name):
        def cb(_):
            self.cfg["alarm_sound"] = sound_name
            for s, item in self.alarm_sound_items.items():
                item.state = 1 if s == sound_name else 0
            save_config(self.cfg)
            play_sound(sound_name, self.cfg["alarm_volume"])
        return cb

    def _set_alarm_volume(self, _):
        val = self._prompt_int("Alarm Volume", "Volume (0–100):", self.cfg["alarm_volume"])
        if val is not None:
            self.cfg["alarm_volume"] = max(0, min(100, val))
            save_config(self.cfg)
            self.alarm_volume_item.title = f"Volume: {self.cfg['alarm_volume']}…"

    def _set_alarm_repeat(self, _):
        val = self._prompt_int("Alarm Repeat", "Number of times to repeat:", self.cfg["alarm_repeat"])
        if val:
            self.cfg["alarm_repeat"] = val
            save_config(self.cfg)
            self.alarm_repeat_item.title = f"Repeat: {self.cfg['alarm_repeat']}…"

    def _test_alarm(self, _):
        play_sound(self.cfg["alarm_sound"], self.cfg["alarm_volume"], self.cfg["alarm_repeat"])

    # Ticking
    def _toggle_ticking(self, sender):
        self.cfg["ticking_enabled"] = not self.cfg["ticking_enabled"]
        sender.state = self.cfg["ticking_enabled"]
        save_config(self.cfg)
        if self.running:
            if self.cfg["ticking_enabled"]:
                self.tick_sound_timer.start()
            else:
                self.tick_sound_timer.stop()

    def _make_tick_sound_cb(self, sound_name):
        def cb(_):
            self.cfg["ticking_sound"] = sound_name
            for s, item in self.tick_sound_items.items():
                item.state = 1 if s == sound_name else 0
            save_config(self.cfg)
            play_sound(sound_name, self.cfg["ticking_volume"])
        return cb

    def _set_ticking_volume(self, _):
        val = self._prompt_int("Ticking Volume", "Volume (0–100):", self.cfg["ticking_volume"])
        if val is not None:
            self.cfg["ticking_volume"] = max(0, min(100, val))
            save_config(self.cfg)
            self.tick_volume_item.title = f"Volume: {self.cfg['ticking_volume']}…"

    def _play_tick_sound(self, _):
        if self.running and self.cfg["ticking_enabled"]:
            play_sound(self.cfg["ticking_sound"], self.cfg["ticking_volume"])


if __name__ == "__main__":
    PomodoroApp().run()