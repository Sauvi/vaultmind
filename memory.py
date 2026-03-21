import json
import os

MEMORY_FILE = "memory.json"


def load_memory() -> dict:
    if not os.path.exists(MEMORY_FILE):
        return {}
    try:
        with open(MEMORY_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def save_memory(data: dict) -> None:
    try:
        with open(MEMORY_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except IOError as e:
        print(f"Warning: could not save memory — {e}")


def record_action(file_type: str, action: str) -> None:
    data = load_memory()
    data.setdefault(file_type, {})
    data[file_type][action] = data[file_type].get(action, 0) + 1
    save_memory(data)


def get_suggestion(file_type: str) -> str | None:
    """Return the most-used action for a file type if used 3+ times."""
    data = load_memory()
    actions = data.get(file_type, {})
    if not actions:
        return None
    best_action = max(actions, key=actions.get)
    if actions[best_action] >= 3:
        return best_action
    return None
