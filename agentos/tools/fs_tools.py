import os

def list_files(directory: str) -> list[str]:
    """Lists all files in a directory."""
    try:
        return os.listdir(directory)
    except Exception as e:
        return [f"Error: {e}"]

def read_file(path: str) -> str:
    """Reads the text content of a file."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"Error: {e}"

def write_file(path: str, content: str) -> str:
    """Writes text content to a file, replacing it if it exists."""
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return "Success"
    except Exception as e:
        return f"Error: {e}"
