"""
Diagnostic script — run this with FUSIL already open (login screen visible).
Prints everything pywinauto can see so we can fix the detection logic.

Usage:
    python scripts\diagnose_fusil.py
"""
import sys
import time
from pywinauto import Application, Desktop

print("\n=== STEP 1: All visible top-level windows ===")
desktop = Desktop(backend="uia")
for win in desktop.windows():
    try:
        print(f"  title={repr(win.window_text())}  class={repr(win.class_name())}  visible={win.is_visible()}")
    except Exception as e:
        print(f"  [error reading window: {e}]")

print("\n=== STEP 2: Try connecting to FUSIL process by exe name ===")
try:
    app = Application(backend="uia").connect(path="FUSILINFINITY.exe")
    print("  Connected via process name.")
    wins = app.windows()
    print(f"  Windows found: {len(wins)}")
    for w in wins:
        try:
            print(f"    title={repr(w.window_text())}  class={repr(w.class_name())}")
        except Exception as e:
            print(f"    [error: {e}]")
except Exception as e:
    print(f"  Failed: {e}")

print("\n=== STEP 3: Dump all descendants of each FUSIL window ===")
try:
    app = Application(backend="uia").connect(path="FUSILINFINITY.exe")
    for win in app.windows():
        try:
            title = win.window_text()
            print(f"\n  Window: {repr(title)}")
            for ctrl in win.descendants():
                try:
                    print(f"    [{ctrl.control_type()}]  title={repr(ctrl.window_text())}  auto_id={repr(ctrl.automation_id())}")
                except Exception:
                    pass
        except Exception as e:
            print(f"  [error: {e}]")
except Exception as e:
    print(f"  Failed: {e}")
