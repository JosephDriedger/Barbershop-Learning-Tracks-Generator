import os

# Run any Qt code without a display (CI and headless machines).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
