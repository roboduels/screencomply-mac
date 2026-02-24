"""
System integrity monitoring worker for ScreenComply Lite.
Cross-platform: supports Windows and macOS.
"""

import time as _time_module
import collections
import subprocess
import os
import platform
from PyQt5 import QtCore

PLATFORM = platform.system()  # "Windows", "Darwin", "Linux"


class SystemIntegrityWorker(QtCore.QThread):
    """Worker thread for system integrity checks."""

    def __init__(self, logger=None, interval=5.0, parent=None):
        super().__init__(parent)
        self.logger = logger
        self._stop_requested = False
        self._interval = interval
        self._prev_titles = {}
        self._switch_history = collections.deque(maxlen=500)
        self._total_switches = 0
        self._ext_cache_time = 0.0
        self._ext_cache_str = "  (no extension scan yet)"

    def stop(self):
        self._stop_requested = True

    def run(self):
        while not self._stop_requested:
            try:
                results = {
                    'browser_info': self._get_browser_info(),
                    'browser_stats': self._get_browser_stats(),
                    'network_info': self._get_network_info(),
                    'programs_info': self._get_running_programs(),
                }

                if self.logger:
                    self.logger.log_system_integrity(results)

            except Exception:
                pass

            for _ in range(int(self._interval * 10)):
                if self._stop_requested:
                    break
                _time_module.sleep(0.1)

    # ──────────────────────────────────────────────────────
    # Extension summary
    # ──────────────────────────────────────────────────────

    def _get_extension_summary(self, now_ts):
        """Scan common Chromium extension folders (10-second cache)."""
        if now_ts - self._ext_cache_time < 10.0:
            return self._ext_cache_str

        if PLATFORM == "Windows":
            local = os.getenv("LOCALAPPDATA") or ""
            if not local:
                self._ext_cache_time = now_ts
                self._ext_cache_str = "  (LOCALAPPDATA not found)"
                return self._ext_cache_str
            roots = {
                "Chrome": os.path.join(local, "Google", "Chrome", "User Data", "Default", "Extensions"),
                "Brave":  os.path.join(local, "BraveSoftware", "Brave-Browser", "User Data", "Default", "Extensions"),
                "Edge":   os.path.join(local, "Microsoft", "Edge", "User Data", "Default", "Extensions"),
            }
        elif PLATFORM == "Darwin":
            home = os.path.expanduser("~")
            app_support = os.path.join(home, "Library", "Application Support")
            roots = {
                "Chrome":   os.path.join(app_support, "Google", "Chrome", "Default", "Extensions"),
                "Brave":    os.path.join(app_support, "BraveSoftware", "Brave-Browser", "Default", "Extensions"),
                "Edge":     os.path.join(app_support, "Microsoft Edge", "Default", "Extensions"),
                "Chromium": os.path.join(app_support, "Chromium", "Default", "Extensions"),
            }
        else:
            self._ext_cache_str = "  (extension scan not supported on this OS)"
            self._ext_cache_time = now_ts
            return self._ext_cache_str

        lines = []
        for name, path in roots.items():
            if not os.path.isdir(path):
                continue
            try:
                ids = [d for d in os.listdir(path) if os.path.isdir(os.path.join(path, d))]
                lines.append(f"  * {name}: ~{len(ids)} extension(s)")
            except Exception as e:
                lines.append(f"  * {name}: error scanning ({e})")

        self._ext_cache_str = "\n".join(lines) if lines else "  (no extension roots found)"
        self._ext_cache_time = now_ts
        return self._ext_cache_str

    # ──────────────────────────────────────────────────────
    # Browser stats
    # ──────────────────────────────────────────────────────

    def _get_browser_stats(self):
        if PLATFORM == "Windows":
            return self._get_browser_stats_windows()
        elif PLATFORM == "Darwin":
            return self._get_browser_stats_macos()
        return "Browser stats not supported on this OS."

    def _get_browser_stats_windows(self):
        try:
            import ctypes
            from ctypes import wintypes
        except ImportError:
            return "Browser stats require Windows ctypes."

        user32 = ctypes.windll.user32
        EnumWindows = user32.EnumWindows
        EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        IsWindowVisible = user32.IsWindowVisible
        GetWindowTextW = user32.GetWindowTextW
        GetWindowTextLengthW = user32.GetWindowTextLengthW

        TITLE_PATTERNS = {
            "Chrome":   [" - Google Chrome", " - Chrome"],
            "Brave":    [" - Brave"],
            "Edge":     [" - Microsoft Edge", " - MS Edge", " - Edge"],
            "Firefox":  [" - Mozilla Firefox", " - Firefox"],
            "Opera":    [" - Opera"],
            "Chromium": [" - Chromium"],
            "Vivaldi":  [" - Vivaldi"],
        }

        def classify_browser(title):
            tl = title.lower()
            for name, patterns in TITLE_PATTERNS.items():
                for pat in patterns:
                    if pat.lower() in tl:
                        return name
            return None

        browser_titles = {}
        devtools_open = False
        extensions_page_open = False

        @EnumWindowsProc
        def enum_proc(hwnd, lParam):
            nonlocal devtools_open, extensions_page_open
            try:
                if not IsWindowVisible(hwnd):
                    return True
                length = GetWindowTextLengthW(hwnd)
                if length == 0:
                    return True
                buff = ctypes.create_unicode_buffer(length + 1)
                GetWindowTextW(hwnd, buff, length + 1)
                title = buff.value.strip()
                if not title:
                    return True
                if classify_browser(title):
                    hval = int(hwnd)
                    browser_titles[hval] = title
                    tl = title.lower()
                    if "devtools" in tl or "developer tools" in tl:
                        devtools_open = True
                    if "extensions" in tl or "extension" in tl:
                        extensions_page_open = True
            except Exception:
                pass
            return True

        EnumWindows(enum_proc, 0)

        now = _time_module.time()
        prev = self._prev_titles
        for hwnd, new_title in browser_titles.items():
            old_title = prev.get(hwnd)
            if old_title and old_title != new_title:
                self._total_switches += 1
                self._switch_history.append(now)

        while self._switch_history and now - self._switch_history[0] > 60:
            self._switch_history.popleft()

        self._prev_titles = browser_titles
        last_60 = len(self._switch_history)
        ext_summary = self._get_extension_summary(now)

        lines = [
            f"Tab switches (last 60s): {last_60}",
            f"Total tab switches: {self._total_switches}",
            "",
            f"DevTools detected: {'YES' if devtools_open else 'NO'}",
            f"Extensions/settings page open: {'YES' if extensions_page_open else 'NO'}",
            "",
            "Extensions (approx, from disk):",
            ext_summary or "  (no extension folders found)",
        ]
        return "\n".join(lines)

    def _get_browser_stats_macos(self):
        """macOS browser stats via process inspection and extension disk scan."""
        now = _time_module.time()

        try:
            ps_out = subprocess.check_output(
                ["ps", "-ax", "-o", "comm="], timeout=5
            ).decode(errors="ignore")
        except Exception:
            ps_out = ""

        BROWSER_PROCS = {
            "Chrome":  ["Google Chrome"],
            "Brave":   ["Brave Browser"],
            "Firefox": ["firefox", "Firefox"],
            "Edge":    ["Microsoft Edge"],
            "Safari":  ["Safari"],
            "Opera":   ["Opera"],
        }

        running_browsers = set()
        for browser, procs in BROWSER_PROCS.items():
            for proc in procs:
                if proc in ps_out:
                    running_browsers.add(browser)
                    break

        ext_summary = self._get_extension_summary(now)

        lines = [
            "Tab switches (last 60s): N/A (requires Accessibility permission on macOS)",
            "Total tab switches: N/A",
            "",
            "Running Browsers:",
            *(f"  * {b}" for b in sorted(running_browsers)) if running_browsers else ["  (none detected)"],
            "",
            "Extensions (approx, from disk):",
            ext_summary or "  (no extension folders found)",
        ]
        return "\n".join(lines)

    # ──────────────────────────────────────────────────────
    # Running programs
    # ──────────────────────────────────────────────────────

    def _get_running_programs(self):
        if PLATFORM == "Windows":
            return self._get_running_programs_windows()
        elif PLATFORM == "Darwin":
            return self._get_running_programs_macos()
        return "Process listing not supported on this OS."

    def _get_running_programs_windows(self):
        out = []
        try:
            raw = subprocess.check_output(
                "tasklist /FO CSV /NH", shell=True, timeout=5
            ).decode(errors="ignore").splitlines()

            processes = []
            for line in raw:
                cols = [c.strip('"') for c in line.split('","')]
                if len(cols) >= 2:
                    name = cols[0]
                    pid = cols[1]
                    mem = cols[4] if len(cols) >= 5 else ""
                    processes.append((name, pid, mem))

            processes.sort(key=lambda x: x[0].lower())
            cluely_running = any("cluely" in p[0].lower() for p in processes)
            out.append(f"Cluely Detected: {'YES' if cluely_running else 'NO'}\n")
            out.append("Running Programs:")
            for name, pid, mem in processes:
                out.append(f"  * {name}  (PID {pid})  Mem: {mem}")
        except subprocess.TimeoutExpired:
            out.append("Tasklist timed out")
        except Exception as e:
            out.append("Error reading tasklist: " + str(e))
        return "\n".join(out)

    def _get_running_programs_macos(self):
        out = []
        try:
            raw = subprocess.check_output(
                ["ps", "-ax", "-o", "pid=,comm="], timeout=5
            ).decode(errors="ignore").splitlines()

            processes = []
            for line in raw:
                parts = line.strip().split(None, 1)
                if len(parts) >= 2:
                    pid, name = parts[0], parts[1]
                    name = os.path.basename(name)
                    processes.append((name, pid))

            processes.sort(key=lambda x: x[0].lower())
            cluely_running = any("cluely" in p[0].lower() for p in processes)
            out.append(f"Cluely Detected: {'YES' if cluely_running else 'NO'}\n")
            out.append("Running Programs:")
            for name, pid in processes:
                out.append(f"  * {name}  (PID {pid})")
        except subprocess.TimeoutExpired:
            out.append("ps timed out")
        except Exception as e:
            out.append("Error reading process list: " + str(e))
        return "\n".join(out)

    # ──────────────────────────────────────────────────────
    # Browser info (open windows)
    # ──────────────────────────────────────────────────────

    def _get_browser_info(self):
        if PLATFORM == "Windows":
            return self._get_browser_info_windows()
        elif PLATFORM == "Darwin":
            return self._get_browser_info_macos()
        return "Browser window enumeration not supported on this OS."

    def _get_browser_info_windows(self):
        try:
            import ctypes
            from ctypes import wintypes
        except ImportError:
            return "ctypes not available"

        user32 = ctypes.windll.user32
        EnumWindows = user32.EnumWindows
        EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        IsWindowVisible = user32.IsWindowVisible
        GetWindowTextW = user32.GetWindowTextW
        GetWindowTextLengthW = user32.GetWindowTextLengthW

        TITLE_PATTERNS = {
            "Chrome":   [" - Google Chrome", " - Chrome"],
            "Brave":    [" - Brave"],
            "Edge":     [" - Microsoft Edge", " - MS Edge", " - Edge"],
            "Firefox":  [" - Mozilla Firefox", " - Firefox"],
            "Opera":    [" - Opera"],
            "Chromium": [" - Chromium"],
            "Vivaldi":  [" - Vivaldi"],
        }

        browser_windows = []

        def classify_browser(title):
            for name, patterns in TITLE_PATTERNS.items():
                for pat in patterns:
                    if pat.lower() in title.lower():
                        return name
            return None

        @EnumWindowsProc
        def enum_proc(hwnd, lParam):
            try:
                if not IsWindowVisible(hwnd):
                    return True
                length = GetWindowTextLengthW(hwnd)
                if length == 0:
                    return True
                buff = ctypes.create_unicode_buffer(length + 1)
                GetWindowTextW(hwnd, buff, length + 1)
                title = buff.value.strip()
                if not title:
                    return True
                browser_name = classify_browser(title)
                if browser_name:
                    browser_windows.append((browser_name, title))
            except Exception:
                pass
            return True

        EnumWindows(enum_proc, 0)

        if not browser_windows:
            return "No supported browser windows detected."

        from collections import defaultdict
        grouped = defaultdict(list)
        for name, title in browser_windows:
            grouped[name].append(title)

        lines = []
        for name, titles in grouped.items():
            lines.append(f"{name}: {len(titles)} window(s)")
            for t in titles[:10]:
                if len(t) > 120:
                    t = t[:117] + "..."
                lines.append(f"  * {t}")
            if len(titles) > 10:
                lines.append(f"  * (+{len(titles) - 10} more)")
            lines.append("")
        return "\n".join(lines).strip()

    def _get_browser_info_macos(self):
        """macOS: get window titles via AppleScript, fall back to ps if blocked."""
        script = """tell application "System Events"
    set output to {}
    repeat with proc in (every process whose background only is false)
        try
            set pname to name of proc
            set wins to every window of proc
            repeat with w in wins
                try
                    set wtitle to name of w
                    if wtitle is not "" then
                        set end of output to pname & "|" & wtitle
                    end if
                end try
            end repeat
        end try
    end repeat
    return output
end tell
"""
        try:
            result = subprocess.check_output(
                ["osascript", "-e", script], timeout=10, stderr=subprocess.DEVNULL
            ).decode(errors="ignore").strip()

            BROWSER_NAMES = {
                "Google Chrome", "Brave Browser", "Firefox",
                "Microsoft Edge", "Safari", "Opera", "Chromium",
            }

            from collections import defaultdict
            grouped = defaultdict(list)

            if result:
                for entry in result.split(", "):
                    if "|" in entry:
                        pname, title = entry.split("|", 1)
                        pname, title = pname.strip(), title.strip()
                        for bname in BROWSER_NAMES:
                            if bname.lower() in pname.lower():
                                grouped[pname].append(title)
                                break

            if not grouped:
                return self._get_browser_info_macos_ps_fallback()

            lines = []
            for name, titles in grouped.items():
                lines.append(f"{name}: {len(titles)} window(s)")
                for t in titles[:10]:
                    if len(t) > 120:
                        t = t[:117] + "..."
                    lines.append(f"  * {t}")
                if len(titles) > 10:
                    lines.append(f"  * (+{len(titles) - 10} more)")
                lines.append("")
            return "\n".join(lines).strip()

        except Exception:
            return self._get_browser_info_macos_ps_fallback()

    def _get_browser_info_macos_ps_fallback(self):
        """Detect open browsers via ps (no window titles)."""
        try:
            ps_out = subprocess.check_output(
                ["ps", "-ax", "-o", "comm="], timeout=5
            ).decode(errors="ignore")
        except Exception:
            return "Unable to enumerate browser windows."

        BROWSER_PROCS = {
            "Google Chrome":  "Google Chrome",
            "Brave Browser":  "Brave Browser",
            "Firefox":        "firefox",
            "Microsoft Edge": "Microsoft Edge",
            "Safari":         "Safari",
            "Opera":          "Opera",
        }

        found = [b for b, proc in BROWSER_PROCS.items() if proc in ps_out]

        if not found:
            return "No supported browser windows detected."

        return (
            "Detected running browsers (window titles require Accessibility permission):\n"
            + "\n".join(f"  * {b}" for b in found)
        )

    # ──────────────────────────────────────────────────────
    # Network info
    # ──────────────────────────────────────────────────────

    def _get_network_info(self):
        if PLATFORM == "Windows":
            return self._get_network_info_windows()
        elif PLATFORM == "Darwin":
            return self._get_network_info_macos()
        return "Network enumeration not supported on this OS."

    def _get_network_info_windows(self):
        import re
        out = []
        timeout = 3

        try:
            netsh_out = subprocess.check_output(
                "netsh interface show interface", shell=True, timeout=timeout
            ).decode(errors="ignore")
            out.append("Interfaces:")
            for line in netsh_out.splitlines():
                if "Connected" in line or "Disconnected" in line:
                    out.append("  " + line.strip())
            out.append("")
        except Exception as e:
            out.append(f"Interface Error: {e}")

        try:
            wifi_info = subprocess.check_output(
                "netsh wlan show interfaces", shell=True, timeout=timeout
            ).decode(errors="ignore")
            ssid = None
            state = None
            for line in wifi_info.splitlines():
                if "State" in line:
                    state = line.split(":", 1)[1].strip()
                if "SSID" in line and "BSSID" not in line:
                    ssid = line.split(":", 1)[1].strip()
            out.append(f"Wi-Fi State: {state or 'Unknown'}")
            out.append(f"Connected SSID: {ssid or 'None'}")
            out.append("")
        except Exception:
            out.append("Wi-Fi: No adapter or Wi-Fi disabled.\n")

        try:
            nets = subprocess.check_output(
                "netsh wlan show networks", shell=True, timeout=timeout
            ).decode(errors="ignore")
            ssids = []
            for line in nets.splitlines():
                if "SSID" in line and "BSSID" not in line:
                    val = line.split(":", 1)[1].strip()
                    if val:
                        ssids.append(val)
            if ssids:
                out.append("Nearby Networks:")
                for s in ssids[:10]:
                    out.append(f"  * {s}")
                if len(ssids) > 10:
                    out.append(f"  * (+{len(ssids)-10} more)")
                out.append("")
        except Exception:
            out.append("Nearby Networks: Not available.\n")

        try:
            arp = subprocess.check_output("arp -a", shell=True, timeout=timeout).decode()
            devices = [l for l in arp.splitlines() if re.search(r"([0-9A-Fa-f]{2}-){5}", l)]
            out.append(f"LAN Devices Found: {len(devices)}")
            for d in devices[:5]:
                out.append("  " + d.strip())
            if len(devices) > 5:
                out.append(f"  (+{len(devices)-5} more)")
            out.append("")
        except Exception as e:
            out.append(f"ARP Error: {e}")

        return "\n".join(out)

    def _get_network_info_macos(self):
        import re
        out = []
        timeout = 3

        # Active interfaces
        try:
            ifconfig = subprocess.check_output(["ifconfig"], timeout=timeout).decode(errors="ignore")
            active = []
            current_iface = None
            for line in ifconfig.splitlines():
                if line and not line.startswith(("\t", " ")):
                    current_iface = line.split(":")[0]
                if "status: active" in line and current_iface:
                    active.append(current_iface)
            out.append("Active Interfaces: " + (", ".join(active) if active else "none"))
            out.append("")
        except Exception as e:
            out.append(f"Interface Error: {e}")

        # Wi-Fi SSID
        try:
            wifi = subprocess.check_output(
                ["networksetup", "-getairportnetwork", "en0"], timeout=timeout
            ).decode(errors="ignore").strip()
            out.append(f"Wi-Fi: {wifi}")
            out.append("")
        except Exception:
            out.append("Wi-Fi: Not available or not connected.\n")

        # Nearby networks via airport utility
        airport_path = (
            "/System/Library/PrivateFrameworks/Apple80211.framework"
            "/Versions/Current/Resources/airport"
        )
        if os.path.exists(airport_path):
            try:
                nets = subprocess.check_output(
                    [airport_path, "-s"], timeout=timeout
                ).decode(errors="ignore")
                ssids = []
                for line in nets.splitlines()[1:]:  # skip header
                    parts = line.strip().split()
                    if parts:
                        ssids.append(parts[0])
                if ssids:
                    out.append("Nearby Networks:")
                    for s in ssids[:10]:
                        out.append(f"  * {s}")
                    out.append("")
            except Exception:
                out.append("Nearby Networks: Not available.\n")
        else:
            out.append("Nearby Networks: airport utility not found.\n")

        # ARP (same syntax on macOS)
        try:
            arp = subprocess.check_output(["arp", "-a"], timeout=timeout).decode()
            devices = [l for l in arp.splitlines() if " at " in l and "incomplete" not in l]
            out.append(f"LAN Devices Found: {len(devices)}")
            for d in devices[:5]:
                out.append("  " + d.strip())
            if len(devices) > 5:
                out.append(f"  (+{len(devices)-5} more)")
            out.append("")
        except Exception as e:
            out.append(f"ARP Error: {e}")

        return "\n".join(out)
