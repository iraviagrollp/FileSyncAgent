import logging
import subprocess
import time
from datetime import date
from pathlib import Path
from typing import Optional

import win32api
import win32con
import win32gui
from pywinauto import Application, Desktop
from pywinauto.keyboard import send_keys

_WM_SETTEXT = 0x000C

from config import Config
from .reports import FILENAME_PREFIX


# Actual OS window title for FUSIL (both login screen and main window use this title).
# "IRAVIAGROLIFELLP" is a label rendered *inside* the window, not the OS window title.
_FUSIL_TITLE = "Fusil"
_LOGIN_BUTTON = "LOGIN"

# Timing constants (seconds) — increase on a slow machine
_READY_TIMEOUT = 60  # max seconds to wait for FUSIL main/login window to appear
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
        self.no_data_reports: list[str] = []   # skipped — no data on this date (not a failure)
        self.failed_reports: list[str] = []    # errored unexpectedly
        self.report_comments: dict[str, str] = {}  # per-report comment for summary

    # ------------------------------------------------------------------
    # Launch + login
    # ------------------------------------------------------------------

    def _kill_existing_fusil_instances(self):
        """Terminate any running FUSILINFINITY.exe processes before launching a fresh one."""
        exe_name = Path(self.config.fusil_exe_path).name  # e.g. "FUSILINFINITY.exe"
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {exe_name}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True,
        )
        running = [
            line for line in result.stdout.splitlines()
            if exe_name.lower() in line.lower()
        ]
        if not running:
            self.log.info("No existing FUSIL instances found")
            return
        self.log.info("Found %d existing FUSIL instance(s) — terminating", len(running))
        subprocess.run(["taskkill", "/F", "/IM", exe_name], capture_output=True)
        time.sleep(2)
        self.log.info("Existing FUSIL instance(s) closed")

    def launch(self):
        self._kill_existing_fusil_instances()
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
        Detects the login screen by counting Edit fields: >=2 means the login form
        is showing (username + password); 1 means the main screen (search box only).
        Raises LoginError if credentials are submitted but the screen does not clear.
        """
        self.log.info("Waiting for FUSIL window (up to %ds)", _READY_TIMEOUT)
        deadline = time.time() + _READY_TIMEOUT
        desktop = Desktop(backend="uia")

        while time.time() < deadline:
            for win in desktop.windows():
                # Step 1: title check — its own try so a bad window doesn't
                # prevent us from scanning the rest
                try:
                    if win.window_text() != _FUSIL_TITLE:
                        continue
                except Exception as exc:
                    self.log.debug("Could not read window title: %s", exc)
                    continue

                # Step 2: FUSIL window found — detect login screen by counting
                # Edit fields. Login screen has 4 (confirmed on this machine).
                # Main screen has 1 (search box only).
                self.log.info("FUSIL window found (pid=%s)", win.process_id())
                edit_count = 0
                try:
                    edit_count = len(win.descendants(control_type="Edit"))
                except Exception as exc:
                    self.log.debug("Edit field count failed: %s", exc)

                self.log.info("Edit fields visible: %d", edit_count)
                if edit_count > 1:
                    self.log.info("Login screen detected — entering credentials")
                    self._do_login(win)
                    # No post-login verification: the main screen also has multiple Edit
                    # fields so count-based checks cause false LoginErrors. Wrong credentials
                    # will surface as menu navigation failures downstream.
                    self.log.info("Login submitted — proceeding to main screen")
                else:
                    self.log.info("No login screen — already authenticated")
                return

            time.sleep(1)

        self.log.warning("FUSIL window not found within %ds — proceeding anyway", _READY_TIMEOUT)

    def _do_login(self, login_win):
        """Type credentials into the login form and click LOGIN."""
        try:
            edits = login_win.descendants(control_type="Edit")
            self.log.info("Login form has %d Edit controls", len(edits))

            # Identify fields by current value:
            #   username field = pre-filled (non-empty)
            #   password field = empty
            username_field = None
            password_field = None
            for edit in edits:
                try:
                    val = (edit.get_value() or "").strip()
                    if val and username_field is None:
                        username_field = edit
                    elif not val and password_field is None:
                        password_field = edit
                except Exception:
                    continue

            # Fallback: assign by position if value-based detection didn't find both
            if username_field is None and password_field is None:
                if len(edits) < 1:
                    self.log.warning("No Edit controls found on login screen")
                    return
                password_field = edits[-1]
                if len(edits) >= 2:
                    username_field = edits[0]

            # Fill username via UIA ValuePattern (no cursor), fallback to type_keys
            if username_field:
                try:
                    username_field.set_edit_text(self.config.fusil_username)
                except Exception:
                    username_field.click_input()
                    username_field.type_keys("^a")
                    username_field.type_keys(self.config.fusil_username, with_spaces=True)
                time.sleep(0.2)

            # Fill password
            try:
                password_field.set_edit_text(self.config.fusil_password)
            except Exception:
                password_field.click_input()
                password_field.type_keys(self.config.fusil_password, with_spaces=True)
            time.sleep(0.4)

            # Click LOGIN — invoke (no cursor), fall back to Enter
            try:
                self._invoke_or_click(
                    login_win.child_window(title=_LOGIN_BUTTON, control_type="Button")
                )
            except Exception:
                self.log.debug("LOGIN button not found via UIA — pressing Enter")
                send_keys("{ENTER}")

            self.log.info("Login submitted — waiting for main window")
            time.sleep(4)
        except Exception as exc:
            # Log at WARNING without exc details — exception messages from pywinauto
            # can echo typed keys, which would put the password in the log file.
            self.log.warning("Login credential entry failed — check credentials or FUSIL UI state")
            self.log.debug("Login exception detail: %s", exc)

    def connect(self):
        self._handle_login_if_needed()
        self.log.info("Connecting to FUSIL main window")
        self.main_win = Desktop(backend="uia").window(title=_FUSIL_TITLE, found_index=0)
        self.main_win.wait("ready", timeout=30)
        self.main_win.set_focus()

        # Wait for the navigation controls to appear in the UIA tree.
        # main_win.wait("ready") only checks the window exists — FUSIL's
        # menu controls (MainMenu1) take additional time to load after login.
        self.log.info("Waiting for navigation controls to load")
        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                if self.main_win.child_window(auto_id="MainMenu1").exists(timeout=0):
                    self.log.info("Navigation controls ready")
                    break
            except Exception:
                pass
            time.sleep(0.5)
        else:
            self.log.warning("Navigation controls did not appear within 20s — proceeding anyway")

    # ------------------------------------------------------------------
    # Menu navigation
    # ------------------------------------------------------------------

    def _navigate_menu(self, menu_path: list[str]):
        """
        Navigate to a report screen.
        Primary:  search box (txtSearchMenu) — cursor-free, works headless.
        Fallback: hamburger menu walk — requires display for UIA tree population.
        """
        self.log.info("Menu: %s", " -> ".join(menu_path))
        self.main_win.set_focus()

        if self._navigate_via_search(menu_path[-1]):
            return

        self.log.info("Search navigation failed — falling back to hamburger menu")
        self._open_hamburger_menu()
        self._navigate_menu_by_clicks(menu_path)
        self.log.info("Waiting 5s for report screen to load")
        time.sleep(5)

    def _find_edit_near_top(self, main_hwnd: int) -> Optional[int]:
        """Find the search Edit HWND via Win32 enumeration — no UIA, works headless."""
        main_rect = win32gui.GetWindowRect(main_hwnd)
        candidates = []

        def cb(hwnd, _):
            try:
                if "edit" in win32gui.GetClassName(hwnd).lower():
                    r = win32gui.GetWindowRect(hwnd)
                    rel_y = r[1] - main_rect[1]
                    if 0 <= rel_y < 60:
                        candidates.append((hwnd, r[0], rel_y))
            except Exception:
                pass
            return True

        try:
            win32gui.EnumChildWindows(main_hwnd, cb, None)
        except Exception:
            pass
        if not candidates:
            return None
        candidates.sort(key=lambda x: (x[2], x[1]))
        return candidates[0][0]

    def _find_child_by_text(self, parent_hwnd: int, text: str) -> Optional[int]:
        """Find a child HWND whose window text matches — no UIA, works headless."""
        found = []

        def cb(hwnd, _):
            try:
                if win32gui.GetWindowText(hwnd) == text:
                    found.append(hwnd)
            except Exception:
                pass
            return True

        try:
            win32gui.EnumChildWindows(parent_hwnd, cb, None)
        except Exception:
            pass
        return found[0] if found else None

    def _navigate_via_search(self, screen_name: str) -> bool:
        """
        Navigate to a screen using FUSIL's search box.

        Primary path — Win32 only (fully headless, no UIA, no cursor):
          1. Find search Edit HWND via EnumChildWindows
          2. WM_SETTEXT → triggers FUSIL TextChanged → shows "Search Menu" popup
          3. FindWindow("Search Menu") → find result HWND → PostMessage click

        Fallback — UIA (requires active display session):
          set_edit_text() + Desktop.window("Search Menu") + invoke()
        """
        main_hwnd = self.main_win.handle

        # --- Win32 primary path ---
        search_hwnd = self._find_edit_near_top(main_hwnd)
        if search_hwnd:
            try:
                win32api.SendMessage(search_hwnd, _WM_SETTEXT, 0, screen_name)
                self.log.info("Search (Win32): set text '%s' on HWND %d", screen_name, search_hwnd)
                time.sleep(1.5)

                popup_hwnd = None
                deadline = time.time() + 5
                while time.time() < deadline:
                    h = win32gui.FindWindow(None, "Search Menu")
                    if h:
                        popup_hwnd = h
                        break
                    time.sleep(0.3)

                if popup_hwnd:
                    result_hwnd = self._find_child_by_text(popup_hwnd, screen_name)
                    if result_hwnd:
                        rect = win32gui.GetClientRect(result_hwnd)
                        cx = max(rect[2] // 2, 1)
                        cy = max(rect[3] // 2, 1)
                        self._post_click(result_hwnd, cx, cy)
                        self.log.info("Search (Win32): clicked '%s' — waiting 5s", screen_name)
                        time.sleep(5)
                        return True
                    self.log.warning("Search (Win32): result '%s' not in popup", screen_name)
                    try:
                        win32gui.PostMessage(popup_hwnd, win32con.WM_CLOSE, 0, 0)
                    except Exception:
                        pass
                else:
                    self.log.warning("Search (Win32): popup did not appear for '%s'", screen_name)
                    try:
                        win32api.SendMessage(search_hwnd, _WM_SETTEXT, 0, "")
                    except Exception:
                        pass
            except Exception as exc:
                self.log.warning("Search (Win32) failed: %s", exc)
        else:
            self.log.debug("Search Edit HWND not found via Win32 enumeration")

        # --- UIA fallback ---
        search = self._find_by_descendants(self.main_win, auto_id="txtSearchMenu")
        if search is None:
            ids = []
            try:
                for ctrl in self.main_win.descendants():
                    try:
                        aid = ctrl.element_info.automation_id
                        if aid:
                            ids.append(aid)
                    except Exception:
                        pass
            except Exception:
                pass
            self.log.warning("Search box not found (UIA fallback). Available auto_ids: %s", ids[:30])
            return False
        try:
            search.set_edit_text(screen_name)
            self.log.info("Search (UIA): typed '%s' — waiting for popup", screen_name)
            time.sleep(1.5)

            desktop = Desktop(backend="uia")
            popup = None
            deadline = time.time() + 5
            while time.time() < deadline:
                try:
                    w = desktop.window(title="Search Menu")
                    if w.exists(timeout=0):
                        popup = w
                        break
                except Exception:
                    pass
                time.sleep(0.3)

            if popup is None:
                self.log.warning("Search (UIA): popup did not appear for '%s'", screen_name)
                try:
                    search.set_edit_text("")
                except Exception:
                    pass
                return False

            result = self._find_by_descendants(popup, title=screen_name)
            if result is None:
                self.log.warning("Search (UIA): result '%s' not found in popup", screen_name)
                try:
                    popup.close()
                except Exception:
                    pass
                return False

            self._invoke_or_click(result)
            self.log.info("Search (UIA): clicked '%s' — waiting 5s", screen_name)
            time.sleep(5)
            return True

        except Exception as exc:
            self.log.warning("Search (UIA) failed for '%s': %s", screen_name, exc)
            try:
                search.set_edit_text("")
            except Exception:
                pass
            return False

    def _find_by_descendants(self, win, auto_id: str = "", title: str = "") -> object:
        """
        Find a control by iterating descendants — more reliable than child_window()
        for 32-bit .NET apps under 64-bit UIA where child_window() criteria fail.
        Tries element_info.automation_id directly as well as the .automation_id() method
        because the method can raise on some virtual UIA elements.
        """
        for ctrl in win.descendants():
            try:
                if auto_id:
                    aid = None
                    try:
                        aid = ctrl.automation_id()
                    except Exception:
                        pass
                    if aid is None:
                        try:
                            aid = ctrl.element_info.automation_id
                        except Exception:
                            pass
                    if aid == auto_id:
                        return ctrl
                if title and not auto_id and ctrl.window_text() == title:
                    return ctrl
            except Exception:
                continue
        return None

    def _post_click(self, hwnd: int, x: int, y: int):
        """Send a left-click via PostMessage — does NOT call SetCursorPos so it
        works when the RDP session is minimized or the display is inactive."""
        lparam = x | (y << 16)
        win32gui.PostMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lparam)
        time.sleep(0.05)
        win32gui.PostMessage(hwnd, win32con.WM_LBUTTONUP, 0, lparam)

    def _invoke_or_click(self, ctrl):
        """UIA Invoke (no cursor required) with click_input fallback."""
        try:
            ctrl.invoke()
        except Exception:
            ctrl.click_input()

    def _open_hamburger_menu(self):
        """
        Open the navigation panel by clicking the ≡ hamburger button.

        Strategy (in order):
        1. ChildWindowFromPoint — finds the actual child HWND at (17,14) and
           PostMessages to it with correctly converted coords. Works headless.
        2. UIA invoke on auto_id='MainMenu' — cursor-free but element may not
           be in UIA tree in headless sessions.
        3. click_input at (17,14) — works when RDP display is active; fails headless.
        """
        hwnd = self.main_win.handle

        # Strategy 1: PostMessage to correct child HWND via ChildWindowFromPoint
        try:
            child = win32gui.ChildWindowFromPoint(hwnd, (17, 14))
            if child and child != hwnd:
                screen_pt = win32gui.ClientToScreen(hwnd, (17, 14))
                child_pt  = win32gui.ScreenToClient(child, screen_pt)
                self._post_click(child, child_pt[0], child_pt[1])
                self.log.info("Hamburger: PostMessage to child HWND at %s", child_pt)
                time.sleep(_MENU_WAIT * 2)
                return
        except Exception as exc:
            self.log.debug("ChildWindowFromPoint failed: %s", exc)

        # Strategy 2: UIA invoke on hamburger element (auto_id='MainMenu')
        hamburger = self._find_by_descendants(self.main_win, auto_id="MainMenu")
        if hamburger is not None:
            try:
                hamburger.invoke()
                self.log.info("Hamburger menu opened (UIA invoke)")
                time.sleep(_MENU_WAIT * 2)
                return
            except Exception as exc:
                self.log.warning("Hamburger UIA invoke failed: %s", exc)

        # Strategy 3: click_input (requires active display — works with RDP open)
        try:
            self.main_win.click_input(coords=(17, 14))
            self.log.info("Hamburger menu opened (click_input fallback)")
            time.sleep(_MENU_WAIT * 2)
        except Exception as exc:
            self.log.warning("Hamburger click_input failed: %s", exc)

    def _navigate_menu_by_clicks(self, menu_path: list[str]):
        """
        Click each item in menu_path using descendants() iteration.
        child_window() criteria fail for virtual UIA elements in this 32-bit app.
        After each click, check if a popup submenu appears on the Desktop.
        """
        desktop = Desktop(backend="uia")
        current = self.main_win

        for label in menu_path:
            ctrl = self._find_by_descendants(current, title=label)
            if ctrl is None:
                raise RuntimeError(f"Menu item not found: '{label}'")
            self._invoke_or_click(ctrl)
            time.sleep(_ACTION_WAIT)  # wait for sub-items to load into UIA tree

            # After each click, check if a submenu popup appeared
            try:
                popup = desktop.window(control_type="Menu", found_index=0)
                if popup.exists(timeout=1):
                    current = popup
                    continue
            except Exception:
                pass
            current = self.main_win

    # ------------------------------------------------------------------
    # Date setting
    # ------------------------------------------------------------------

    def _find_date_fields(self) -> list:
        """Return Edit controls whose current value looks like a date (DD-MM-YYYY)."""
        fields = []
        try:
            for ctrl in self.main_win.descendants(control_type="Edit"):
                try:
                    val = ctrl.get_value()
                    if val and "-" in val and len(val) >= 8:
                        fields.append(ctrl)
                except Exception:
                    continue
        except Exception as exc:
            self.log.warning("Could not enumerate date fields: %s", exc)
        return fields

    def _fill_date_field(self, field):
        """Set a date field via UIA ValuePattern (no cursor needed), TAB to confirm."""
        try:
            field.set_edit_text(self.date_str)
        except Exception:
            # Fallback: cursor-based input (requires active display)
            field.click_input()
            field.type_keys("^a")
            time.sleep(0.2)
            field.type_keys(self.date_str, with_spaces=False)
        time.sleep(0.2)
        send_keys("{TAB}")
        time.sleep(0.3)

    def _set_dates(self, date_mode: str):
        """Set date field(s) according to the report's date_mode."""
        if date_mode == "none":
            return

        self.log.info("Setting dates to %s (mode: %s)", self.date_str, date_mode)
        fields = self._find_date_fields()

        if date_mode == "from_to":
            if len(fields) < 2:
                self.log.warning("Expected 2 date fields, found %d — View may use wrong date", len(fields))
                return
            for field in fields[:2]:
                self._fill_date_field(field)

        elif date_mode == "as_at":
            if not fields:
                self.log.warning("No date field found for as_at mode")
                return
            self._fill_date_field(fields[0])

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

    def _click_view(self, view_mode: str = "f1"):
        """Load data for the report.
        view_mode='f1'   — click View (F1); also dismisses 'no data' dialog.
        view_mode='auto' — data loads on navigation; no click needed (Customer Accounts).
        """
        if view_mode == "auto":
            self.log.info("View auto-loaded — no click needed")
            return

        try:
            self._invoke_or_click(
                self.main_win.child_window(title_re="View.*", control_type="Button")
            )
        except Exception:
            send_keys("{F1}")
        time.sleep(_VIEW_WAIT)

        # Dismiss "Data not found for given options." if it appeared
        try:
            ok = self._find_by_descendants(self.main_win, title="OK")
            if ok:
                self._invoke_or_click(ok)
                self.log.info("Dismissed 'no data' dialog")
        except Exception:
            pass

        self.log.info("View loaded")

    def _trigger_export(self, export_key: str = "^x"):
        """Press the export shortcut and dismiss any dialogs that follow.

        Ctrl+X (standard): FUSIL exports directly and shows a "success" dialog.
        Ctrl+O (Customer Accounts): FUSIL shows a Save As dialog; press Enter to
        accept the pre-filled filename and export folder, then waits for the file.
        """
        key_label = export_key.replace("^", "Ctrl+").upper()
        self.log.info("Exporting (%s)", key_label)
        self.main_win.set_focus()
        send_keys(export_key)

        # Ctrl+O opens a Save As dialog — wait for it then press Enter.
        # The dialog is modal and focused with the filename pre-filled,
        # so Enter activates the Save button without needing UIA lookup.
        if export_key == "^o":
            self.log.info("Waiting for Save As dialog")
            time.sleep(3)
            send_keys("{ENTER}")
            self.log.info("Save As accepted")
            time.sleep(2)

        self.log.info("Waiting up to %ds for export to complete", _EXPORT_WAIT)
        time.sleep(_EXPORT_WAIT)

        # Dismiss "Export file generated successfully. Do you want open the file?"
        try:
            no_btn = self._find_by_descendants(self.main_win, title="No")
            if no_btn:
                self._invoke_or_click(no_btn)
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

        date_mode  = report.get("date_mode",  "from_to")
        view_mode  = report.get("view_mode",  "f1")
        export_key = report.get("export_key", "^x")

        self.log.info("=== %s ===", report_type.upper())
        try:
            self._navigate_menu(menu_path)
            self._set_dates(date_mode)
            self._click_view(view_mode)

            count = self._get_row_count()
            if count == 0:
                self.log.info("No data for %s on %s (Count=0) — skipping", report_type, self.date_str)
                self.no_data_reports.append(report_type)
                self.report_comments[report_type] = "No Export - No Data"
                return None
            if count == -1:
                self.log.warning("Could not read row count for %s — attempting export anyway", report_type)

            export_started = time.time()
            self._trigger_export(export_key)

            path = self._find_exported_file(report_type, exported_after=export_started)
            if path:
                self.log.info("File found: %s", path.name)
                self.exported_files.append({"type": report_type, "local_path": path})
                self.report_comments[report_type] = "Export Successful"
            else:
                self.log.error("No exported file found for %s in %s", report_type, self.config.export_folder)
                self.failed_reports.append(report_type)
                self.report_comments[report_type] = "File not found after export"
            return path

        except Exception as exc:
            self.log.error("Export failed for %s: %s", report_type, exc, exc_info=True)
            self.failed_reports.append(report_type)
            self.report_comments[report_type] = f"{type(exc).__name__}: {exc}"
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
