#!/bin/bash
# Double-clickable macOS launcher — prefers a Python with a modern Tk (8.6+),
# falls back to any Python that has Tkinter at all.
cd "$(dirname "$0")" || exit 1
for min in 8.6 0; do
    for py in python3 /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3; do
        command -v "$py" >/dev/null 2>&1 || continue
        if "$py" -c "import sys, tkinter; sys.exit(0 if tkinter.TkVersion >= $min else 1)" 2>/dev/null; then
            exec "$py" run.py "$@"
        fi
    done
done
echo "No Python with Tkinter found. Install one with: brew install python-tk"
read -r -p "Press Enter to close..."
