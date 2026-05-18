"""
FUSIL diagnostic — run with FUSIL open on the MAIN SCREEN (logged in, menu visible).

Usage:
    python scripts\\diagnose_fusil.py

Paste the full output back to Claude.
"""
import sys
print(f"Python: {sys.version}")

from pywinauto import Desktop

desktop = Desktop(backend="uia")

# ── 1. Find the FUSIL window ──────────────────────────────────────────────
fusil_wins = [w for w in desktop.windows() if w.window_text() == "Fusil"]
print(f"\nFUSIL windows found: {len(fusil_wins)}")
for w in fusil_wins:
    print(f"  pid={w.process_id()}  title={repr(w.window_text())}  class={repr(w.class_name())}")

if not fusil_wins:
    print("No window titled 'Fusil' found — is FUSIL open?")
    sys.exit(1)

win = fusil_wins[0]

# ── 2. Direct children of the main window ────────────────────────────────
print("\n=== Direct children of FUSIL window ===")
try:
    for ctrl in win.children():
        try:
            print(f"  [{ctrl.control_type():<22}] title={repr(ctrl.window_text())}")
        except Exception as e:
            print(f"  [error: {e}]")
except Exception as e:
    print(f"  FAILED: {e}")

# ── 3. All descendants — first 80, focused on menu/toolbar ───────────────
print("\n=== All descendants (menu/toolbar/button types highlighted) ===")
MENU_TYPES = {"MenuBar", "MenuItem", "Menu", "ToolBar", "Button", "Custom"}
try:
    count = 0
    for ctrl in win.descendants():
        count += 1
        if count > 120:
            print("  ... (truncated at 120)")
            break
        try:
            ct = ctrl.control_type()
            title = ctrl.window_text()
            marker = " <<" if ct in MENU_TYPES or title in ("Reports", "Masters", "File", "Transactions") else ""
            print(f"  [{ct:<22}] title={repr(title):<35} auto_id={repr(ctrl.automation_id())}{marker}")
        except Exception as e:
            print(f"  [error reading ctrl: {e}]")
except Exception as e:
    print(f"  FAILED: {e}")

# ── 4. Specifically look for anything with menu-related text ─────────────
print("\n=== Controls whose title contains Reports / Masters / File ===")
try:
    for ctrl in win.descendants():
        try:
            title = ctrl.window_text()
            if any(kw in title for kw in ("Reports", "Masters", "File", "Transactions", "Settings")):
                print(f"  [{ctrl.control_type():<22}] title={repr(title)}  auto_id={repr(ctrl.automation_id())}")
        except Exception:
            pass
except Exception as e:
    print(f"  FAILED: {e}")

print("\n=== Done — paste everything above back to Claude ===")
