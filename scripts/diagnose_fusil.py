"""
FUSIL diagnostic — run this with FUSIL already open (login screen visible).
DO NOT run via the agent — open FUSIL manually first, then run this script.

Usage:
    python scripts\diagnose_fusil.py

Paste the full output back to Claude.
"""
import sys
import time

print(f"Python: {sys.version}")
print(f"Platform: {sys.platform}\n")

try:
    import pywinauto
    print(f"pywinauto: {pywinauto.__version__}\n")
except Exception as e:
    print(f"pywinauto import failed: {e}")
    sys.exit(1)

from pywinauto import Application, Desktop

# ── 1. All top-level windows (both backends) ──────────────────────────────
for backend in ("uia", "win32"):
    print(f"=== Desktop({backend!r}).windows() ===")
    try:
        wins = Desktop(backend=backend).windows()
        print(f"  Total windows found: {len(wins)}")
        for w in wins:
            try:
                print(f"  pid={w.process_id():6d}  title={repr(w.window_text()):<40}  class={repr(w.class_name())}")
            except Exception as e:
                print(f"  [error reading window props: {e}]")
    except Exception as e:
        print(f"  FAILED: {e}")
    print()

# ── 2. Connect by exe name (both backends) ────────────────────────────────
for backend in ("uia", "win32"):
    print(f"=== Application({backend!r}).connect(path='FUSILINFINITY.exe') ===")
    try:
        app = Application(backend=backend).connect(path="FUSILINFINITY.exe")
        wins = app.windows()
        print(f"  Connected. Windows in process: {len(wins)}")
        for w in wins:
            try:
                print(f"  title={repr(w.window_text())}  class={repr(w.class_name())}")
            except Exception as e:
                print(f"  [error: {e}]")
    except Exception as e:
        print(f"  FAILED: {e}")
    print()

# ── 3. Full control tree of any FUSIL-related window ─────────────────────
print("=== Control tree of FUSIL windows (uia backend) ===")
try:
    desktop = Desktop(backend="uia")
    fusil_wins = [
        w for w in desktop.windows()
        if "FUSIL" in (w.window_text() or "") or "IRAVI" in (w.window_text() or "")
    ]
    if not fusil_wins:
        print("  No windows with FUSIL or IRAVI in title found.")
        print("  Trying all windows with non-empty title...")
        fusil_wins = [w for w in desktop.windows() if w.window_text()]

    for win in fusil_wins[:3]:  # cap at 3 to avoid flooding output
        print(f"\n  Window: {repr(win.window_text())} (pid={win.process_id()})")
        try:
            for ctrl in win.descendants():
                try:
                    print(f"    [{ctrl.control_type():<20}] title={repr(ctrl.window_text()):<30} auto_id={repr(ctrl.automation_id())}")
                except Exception:
                    pass
        except Exception as e:
            print(f"    descendants() failed: {e}")
except Exception as e:
    print(f"  FAILED: {e}")

print("\n=== Done — paste everything above back to Claude ===")
