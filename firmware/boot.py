"""MicroPython boot hook — extend sys.path for core package."""

try:
    import sys
    if "/core" not in sys.path:
        sys.path.append("/")
except Exception:
    pass
