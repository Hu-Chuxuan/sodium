import re
import base64
import hashlib
from pathlib import Path

def parse_result_from_content(content: str, col: str) -> str:
    """
    Parse a cell value from a ```python ...``` block like:
    ```python
    ColumnName = "some value"
    ```
    Returns the string value assigned to `col`.
    """
    try:
        # extract code from fenced block
        match = re.search(r"```python\s+(.*?)```", content, re.DOTALL)
        code = match.group(1).strip() if match else content.strip()

        local_env = {}
        exec(code, {}, local_env)
        if col in local_env and (isinstance(local_env[col], dict) or isinstance(local_env[col], int)):
            return local_env[col]
    except Exception as e:
        print(f"[parse error] {e}")

    return ""

def parse_result_from_content_list(content: str, col: str) -> list:
    """
    Parse a cell value from a ```python ...``` block like:
    ```python
    ColumnName = "some value"
    ```
    Returns the string value assigned to `col`.
    """
    try:
        # extract code from fenced block
        match = re.search(r"```python\s+(.*?)```", content, re.DOTALL)
        code = match.group(1).strip() if match else content.strip()

        local_env = {}
        exec(code, {}, local_env)
        if col in local_env and isinstance(local_env[col], list):
            return local_env[col]
    except Exception as e:
        print(f"[parse error] {e}")

    return []

def image_to_data_url(image_path) -> str:
    """
    Convert local image to data URL suitable for Responses image_url.
    """
    image_path = Path(image_path)
    suffix = image_path.suffix.lower().lstrip(".")
    if suffix == "jpg":
        suffix = "jpeg"
    mime = f"image/{suffix}"

    b64 = base64.b64encode(image_path.read_bytes()).decode("utf-8")
    return f"data:{mime};base64,{b64}"

def url_to_hash(url: str, ext=".png"):
    h = hashlib.sha256(url.encode()).hexdigest()[:16]
    return f"{h}{ext}"

def _normalize_url_variants(url: str):
    variants = [url]
    if url.startswith("https://www."):
        variants.append(url.replace("https://www.", "https://", 1))
    elif url.startswith("https://"):
        # add www if missing
        rest = url[len("https://"):]
        if not rest.startswith("www."):
            variants.append("https://www." + rest)
    # de-dup preserving order
    out = []
    for u in variants:
        if u not in out:
            out.append(u)
    return out
