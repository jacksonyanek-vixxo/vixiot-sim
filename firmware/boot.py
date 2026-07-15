"""MicroPython boot hook — extend sys.path for core package."""

try:
    import sys
    if "/" not in sys.path:
        sys.path.append("/")
except Exception:
    pass

# Before first successful deploy, pause so mpremote can connect after reset.
# deploy.sh creates `.deployed` on the device when finished.
try:
    import os
    import time
    if ".deployed" not in os.listdir():
        time.sleep(5)
except Exception:
    pass
