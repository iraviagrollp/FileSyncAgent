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
fusil_wins = [w for w in desktop.windows() if w.window_text() == "Fusil"]
print(f"\nFUSIL windows found: {len(fusil_wins)}")

if not fusil_wins:
    print("No window titled 'Fusil' found — is FUSIL open?")
    sys.exit(1)

win = fusil_wins[0]

# Use friendly_class_name() — control_type() is not available on all wrappers
print("\n=== All descendants (friendly_class_name + window_text) ===")
try:
    for ctrl in win.descendants():
        try:
            fcn = ctrl.friendly_class_name()
            title = ctrl.window_text()
            auto_id = ""
            try:
                auto_id = ctrl.automation_id()
            except Exception:
                pass
            marker = " <<<" if any(k in title for k in ("Reports", "Masters", "File", "Transactions", "Search", "Sales", "Purchase")) else ""
            print(f"  [{fcn:<20}] title={repr(title):<40} auto_id={repr(auto_id)}{marker}")
        except Exception as e:
            print(f"  [error: {e}]")
except Exception as e:
    print(f"FAILED: {e}")

print("\n=== Done ===")
