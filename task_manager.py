"""
task_manager.py — VaultMind
Core logic: validates, plans, and executes file actions.
Supports .txt, .pdf, .docx, .md
"""

from pathlib import Path
from sandbox import is_safe_input, is_safe_output
from sandbox import OUTPUT_DIR as _OUTPUT_DIR
from actions import ALLOWED_ACTIONS
from memory import record_action, get_suggestion
from file_reader import SUPPORTED_EXTENSIONS, get_file_info

# Always ensure OUTPUT_DIR is a Path object regardless of platform
OUTPUT_DIR = Path(_OUTPUT_DIR)


def handle_file(file_path: str, action: str = "summarize") -> dict:
    result = {
        "success":    False,
        "file":       file_path,
        "action":     action,
        "output":     None,
        "error":      None,
        "suggestion": None,
    }

    ext = Path(file_path).suffix.lower()

    if ext not in SUPPORTED_EXTENSIONS:
        result["error"] = (
            f"'{ext}' files are not supported. "
            f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )
        return result

    if not is_safe_input(file_path):
        result["error"] = "Access denied — file is outside the workspace."
        return result

    if action not in ALLOWED_ACTIONS:
        result["error"] = f"Action '{action}' is not allowed."
        return result

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    base_name   = Path(file_path).stem + f"_{action}.txt"
    output_path = OUTPUT_DIR / base_name     # Path / str  — always works now

    if not is_safe_output(str(output_path)):
        result["error"] = "Output path rejected by sandbox."
        return result

    try:
        ALLOWED_ACTIONS[action](file_path, str(output_path))
        record_action(ext.lstrip("."), action)
        result["success"] = True
        result["output"]  = str(output_path)

        suggestion = get_suggestion(ext.lstrip("."))
        if suggestion and suggestion != action:
            result["suggestion"] = suggestion

    except Exception as e:
        result["error"] = str(e)

    return result


def get_proposed_plan(file_path: str, action: str = "summarize") -> dict:
    ext         = Path(file_path).suffix.lower()
    base_name   = Path(file_path).stem + f"_{action}.txt"
    output_path = OUTPUT_DIR / base_name     # Path / str — always works
    info        = get_file_info(file_path)

    return {
        "file_path":   file_path,
        "action":      action,
        "output_path": str(output_path),
        "allowed":     (
            is_safe_input(file_path)
            and action in ALLOWED_ACTIONS
            and ext in SUPPORTED_EXTENSIONS
        ),
        "file_info":   info,
    }
