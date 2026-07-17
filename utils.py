from pathlib import Path

def file_size(path: Path) -> float:
    """Helper to get file size in KB."""
    return path.stat().st_size / 1024