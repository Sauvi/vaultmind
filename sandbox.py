import os

WORKSPACE_ROOT = os.path.abspath("workspace")
INPUT_DIR = os.path.join(WORKSPACE_ROOT, "input")
OUTPUT_DIR = os.path.join(WORKSPACE_ROOT, "output")


def is_safe_input(file_path: str) -> bool:
    """Check if a file path is inside the allowed input directory."""
    return os.path.abspath(file_path).startswith(INPUT_DIR)


def is_safe_output(file_path: str) -> bool:
    """Check if an output path is inside the allowed output directory."""
    return os.path.abspath(file_path).startswith(OUTPUT_DIR)


def is_allowed(file_path: str) -> bool:
    """Legacy alias — checks input path only (backward compat)."""
    return is_safe_input(file_path)
