import logging
import time
from datetime import date
from pathlib import Path
from typing import Optional

from pywinauto import Application, Desktop
from pywinauto.keyboard import send_keys

from config import Config
from .reports import FILENAME_PREFIX

# Window identifiers
_MAIN_TITLE = "IRAVIAGROLIFELLP"
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
        Poll until either the main window or the login screen is accessible (up to
        _READY_TIMEOUT seconds). Handles machines where FUSIL takes a while to render.
        """
        self.log.info("Waiting for FUSIL to become ready (up to %ds)", _READY_TIMEOUT)
        deadline = time.time() + _READY_TIMEOUT
        login_win = None
        desktop = Desktop(backend="uia")

        while time.time() < deadline:
            # Search all desktop windows — handles child-process spawning.
            # _MAIN_TITLE and _LOGIN_BUTTON are specific enough to avoid false matches.
            for win in desktop.windows():
                try:
                    title = win.window_text()
                    if _MAIN_TITLE in title:
                        self.log.info("No login screen — already authenticated")
                        return
                    if win.child_window(title=_LOGIN_BUTTON, control_type="Button").exists(timeout=0):
                        login_win = win
                        break
                except Exception as exc:
                    self.log.debug("Skipping window during scan: %s", exc)
                    continue

            if login_win:
                break
            time.sleep(1)

        if login_win is None:
            self.log.warning(
                "Neither main window nor login screen appeared within %ds — proceeding",
                _READY_TIMEOUT,
            )
            return

        self.log.info("Login screen detected — entering credentials")
        try:
            # Use descendants() — Edit controls are inside a nested panel, not direct children
            edits = login_win.descendants(control_type="Edit")
            if len(edits) >= 2:
                # index 0 = username, index 1 = password (top-to-bottom in the form)
                edits[0].triple_click_input()
                edits[0].type_keys(self.config.fusil_username, with_spaces=True)
                time.sleep(0.2)
                edits[1].set_focus()
                edits[1].type_keys(self.config.fusil_password, with_spaces=True)
            elif len(edits) == 1:
                edits[0].set_focus()
                edits[0].type_keys(self.config.fusil_password, with_spaces=True)
            else:
                self.log.warning("No Edit controls found on login screen — skipping credential entry")
                return
            time.sleep(0.4)
            login_win.child_window(title=_LOGIN_BUTTON, control_type="Button").click_input()
            self.log.info("Login submitted — waiting for main window")
            time.sleep(4)
        except Exception as exc:
            self.log.warning("Login credential entry failed: %s", exc)

    def connect(self):
        self._handle_login_if_needed()
        self.log.info("Connecting to main window (%s)", _MAIN_TITLE)
        self.main_win = Desktop(backend="uia").window(title_re=f".*{_MAIN_TITLE}.*")
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
            if self.main_win:
                self.main_win.close()
                time.sleep(2)
            self.log.info("FUSIL closed")
        except Exception as exc:
            self.log.warning("Could not close FUSIL cleanly: %s", exc)
