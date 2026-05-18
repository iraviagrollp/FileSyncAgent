import logging
import time
from datetime import date
from pathlib import Path
from typing import Optional

from pywinauto import Application, Desktop
from pywinauto.keyboard import send_keys

from config import Config
from .reports import FILENAME_PREFIX

# Actual OS window title for FUSIL (both login screen and main window use this title).
# "IRAVIAGROLIFELLP" is a label rendered *inside* the window, not the OS window title.
_FUSIL_TITLE = "Fusil"
_LOGIN_BUTTON = "LOGIN"

# Timing constants (seconds) — increase on a slow machine
_READY_TIMEOUT = 30  # max seconds to wait for FUSIL main/login window to appear
_ACTION_WAIT = 1.5   # between UI steps
_EXPORT_WAIT = 12    # after Ctrl+X, waiting for file to be written
_VIEW_WAIT = 3       # after clicking View, waiting for data to load
_MENU_WAIT = 0.8     # between individual menu clicks (fallback path)


class FusilExporter:

    def __init__(self, config: Config, log: logging.Logger, export_date: date):
        self.config = config
        self.log = log
        self.export_date = export_date
        self.date_str = export_date.strftime("%d-%m-%Y")  # UI input format: DD-MM-YYYY
        self.app: Optional[Application] = None
        self.main_win = None
        self.exported_files: list[dict] = []
        self.no_data_reports: list[str] = []  # skipped — no data on this date (not a failure)
        self.failed_reports: list[str] = []   # errored unexpectedly

    # ------------------------------------------------------------------
    # Launch + login
    # ------------------------------------------------------------------

    def launch(self):
        self.log.info("Launching FUSIL: %s", self.config.fusil_exe_path)
        self.app = Application(backend="uia").start(
            self.config.fusil_exe_path,
            wait_for_idle=False,
        )
        # Small initial pause — give the OS time to create the process window
        # before we start polling. The real wait happens in _handle_login_if_needed.
        time.sleep(2)

    def _handle_login_if_needed(self):
        """
        Poll for the FUSIL window (title='Fusil') for up to _READY_TIMEOUT seconds.
        If the window has a LOGIN button it's the login screen — enter credentials.
        If it has no LOGIN button it's already on the main screen — proceed directly.
        """
        self.log.info("Waiting for FUSIL window (up to %ds)", _READY_TIMEOUT)
        deadline = time.time() + _READY_TIMEOUT
        desktop = Desktop(backend="uia")

        while time.time() < deadline:
            for win in desktop.windows():
                try:
                    if win.window_text() != _FUSIL_TITLE:
                        continue
                    # Found the FUSIL window
                    if win.child_window(title=_LOGIN_BUTTON, control_type="Button").exists(timeout=0):
                        self.log.info("Login screen detected — entering credentials")
                        self._do_login(win)
                    else:
                        self.log.info("FUSIL ready — already authenticated")
                    return
                except Exception as exc:
                    self.log.debug("Window scan error: %s", exc)
                    continue
            time.sleep(1)

        self.log.warning("FUSIL window not found within %ds — proceeding anyway", _READY_TIMEOUT)

    def _do_login(self, login_win):
        """Type credentials into the login form and click LOGIN."""
        try:
            # Use descendants() — Edit controls are inside a nested panel
            edits = login_win.descendants(control_type="Edit")
            if len(edits) >= 2:
                # index 0 = username, index 1 = password (top-to-bottom order)
                edits[0].triple_click_input()
                edits[0].type_keys(self.config.fusil_username, with_spaces=True)
                time.sleep(0.2)
                edits[1].set_focus()
                edits[1].type_keys(self.config.fusil_password, with_spaces=True)
            elif len(edits) == 1:
                edits[0].set_focus()
                edits[0].type_keys(self.config.fusil_password, with_spaces=True)
            else:
                self.log.warning("No Edit controls found on login screen")
                return
            time.sleep(0.4)
            login_win.child_window(title=_LOGIN_BUTTON, control_type="Button").click_input()
            self.log.info("Login submitted — waiting for main window")
            time.sleep(4)
        except Exception as exc:
            self.log.warning("Login failed: %s", exc)

    def connect(self):
        self._handle_login_if_needed()
        self.log.info("Connecting to FUSIL main window")
        self.main_win = Desktop(backend="uia").window(title=_FUSIL_TITLE)
        self.main_win.wait("ready", timeout=30)
        self.main_win.set_focus()
        self.log.info("Main window ready")

    # ------------------------------------------------------------------
    # Menu navigation
    # ------------------------------------------------------------------

    def _navigate_menu(self, menu_path: list[str]):
        """
        Navigate a menu path such as ["Reports", "RGF", "Sales", "RGF Sales Book"].
        Tries pywinauto's menu_select first; falls back to clicking items one by one.
        """
        self.log.info("Menu: %s", " → ".join(menu_path))
        self.main_win.set_focus()
        time.sleep(0.3)
        try:
            self.main_win.menu_select("->".join(menu_path))
        except Exception as exc:
            self.log.info("menu_select failed (%s) — using manual clicks", exc)
            self._navigate_menu_by_clicks(menu_path)
        time.sleep(_ACTION_WAIT)

    def _navigate_menu_by_clicks(self, menu_path: list[str]):
        desktop = Desktop(backend="uia")
        current = self.main_win
        for label in menu_path:
            current.child_window(title=label, control_type="MenuItem").click_input()
            time.sleep(_MENU_WAIT)
            try:
                current = desktop.window(control_type="Menu", found_index=0)
            except Exception:
                current = self.main_win

    # ------------------------------------------------------------------
    # Date setting
    # ------------------------------------------------------------------

    def _set_dates(self):
        """Set From Date and To Date to self.date_str (DD-MM-YYYY)."""
        self.log.info("Setting dates to %s", self.date_str)
        date_fields = []
        try:
            for ctrl in self.main_win.descendants(control_type="Edit"):
                try:
                    val = ctrl.get_value()
                    if val and "-" in val and len(val) >= 8:
                        date_fields.append(ctrl)
                except Exception:
                    continue
        except Exception as exc:
            self.log.warning("Could not enumerate date fields: %s", exc)

        if len(date_fields) < 2:
            self.log.warning("Expected 2 date fields, found %d — View may use wrong date", len(date_fields))
            return

        for field in date_fields[:2]:
            field.triple_click_input()
            time.sleep(0.2)
            field.type_keys(self.date_str, with_spaces=False)
            time.sleep(0.2)
            send_keys("{TAB}")
            time.sleep(0.3)

    # ------------------------------------------------------------------
    # View + export
    # ------------------------------------------------------------------

    def _get_row_count(self) -> int:
        """
        Read the 'Count=N' indicator in FUSIL's report status bar.
        Returns the count, or -1 if the control cannot be found.
        """
        try:
            for ctrl in self.main_win.descendants(control_type="Text"):
                try:
                    text = ctrl.window_text().strip()
                    if text.startswith("Count="):
                        return int(text.split("=")[1])
                except (ValueError, IndexError):
                    continue
        except Exception:
            pass
        return -1

    def _click_view(self):
        """Click the View (F1) button, or press F1 as fallback."""
        try:
            self.main_win.child_window(title_re="View.*", control_type="Button").click_input()
        except Exception:
            send_keys("{F1}")
        time.sleep(_VIEW_WAIT)
        self.log.info("View loaded")

    def _trigger_export(self):
        """Press Ctrl+X and dismiss the success dialog."""
        self.log.info("Exporting (Ctrl+X)")
        self.main_win.set_focus()
        send_keys("^x")
        self.log.info("Waiting up to %ds for export to complete", _EXPORT_WAIT)
        time.sleep(_EXPORT_WAIT)
        try:
            dialog = Desktop(backend="uia").window(title="Message")
            dialog.wait("ready", timeout=10)
            dialog.child_window(title="No", control_type="Button").click_input()
            self.log.info("Export dialog dismissed")
        except Exception as exc:
            self.log.warning("Could not dismiss export dialog: %s", exc)
        time.sleep(1)

    # ------------------------------------------------------------------
    # File detection
    # ------------------------------------------------------------------

    def _find_exported_file(self, report_type: str, exported_after: float) -> Optional[Path]:
        """Return the most-recently-modified .xlsx written after exported_after (epoch seconds).
        Filtering by time prevents returning a stale file from a previous run."""
        folder = Path(self.config.export_folder)
        candidates = [
            p for p in folder.glob(f"{FILENAME_PREFIX[report_type]}*.xlsx")
            if p.stat().st_mtime >= exported_after
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda p: p.stat().st_mtime)

    # ------------------------------------------------------------------
    # Per-report entry point
    # ------------------------------------------------------------------

    def export_report(self, report: dict) -> Optional[Path]:
        report_type = report["type"]
        menu_path = report["menu_path"]

        if menu_path is None:
            self.log.warning("Skipping %s — menu path not configured", report_type)
            return None

        self.log.info("=== %s ===", report_type.upper())
        try:
            self._navigate_menu(menu_path)
            self._set_dates()
            self._click_view()

            count = self._get_row_count()
            if count == 0:
                # FUSIL blocks export when there is no data — this is expected
                # (e.g. no sales on a holiday). Skip without alerting.
                self.log.info("No data for %s on %s (Count=0) — skipping", report_type, self.date_str)
                self.no_data_reports.append(report_type)
                return None
            if count == -1:
                self.log.warning("Could not read row count for %s — attempting export anyway", report_type)

            export_started = time.time()
            self._trigger_export()

            path = self._find_exported_file(report_type, exported_after=export_started)
            if path:
                self.log.info("File found: %s", path.name)
                self.exported_files.append({"type": report_type, "local_path": path})
            else:
                self.log.error("No exported file found for %s in %s", report_type, self.config.export_folder)
                self.failed_reports.append(report_type)
            return path

        except Exception as exc:
            self.log.error("Export failed for %s: %s", report_type, exc, exc_info=True)
            self.failed_reports.append(report_type)
            return None

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def close(self):
        try:
            win = self.main_win or Desktop(backend="uia").window(title=_FUSIL_TITLE)
            win.close()
            time.sleep(2)
            self.log.info("FUSIL closed")
        except Exception as exc:
            self.log.warning("Could not close FUSIL cleanly: %s", exc)
