import requests
import re
import time

from urllib.parse import urljoin
from pathlib import Path
from playwright.sync_api import (
    sync_playwright,
    TimeoutError as PwTimeoutError,
    Error as PwError,
)

from utils.prompt import INSPECT_PAGE
from utils.lib import parse_result_from_content, _normalize_url_variants, url_to_hash, image_to_data_url
from utils.log import document_func_call

def inspect_static(url, query, primary_key, primary_key_val, col, client, given_info, log_file):
    proceed = True
    webpage_content = get_static_content(url)
    if webpage_content == -1:
        return given_info, [], False, url, {}
    
    log_dir = Path(log_file).parent
    screenshot_name = url_to_hash(url)
    screenshot_path = log_dir / screenshot_name

    viewpage(url, screenshot_path)

    image_url = image_to_data_url(screenshot_path)

    links = extract_links_from_markdown(webpage_content)
    prompt = INSPECT_PAGE.format(
        webpage_content=webpage_content,
        query=query,
        primary_key=primary_key, 
        primary_key_val=primary_key_val, 
        col=col,
        given_info=given_info
    )
    response = client.responses.create(
        model="gpt-5",
        reasoning={"effort": "high"},
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_image", "image_url": image_url, "detail": "high"},
                ],
            }
        ],
    )
    content = response.output_text

    result = parse_result_from_content(content, "res")
    if type(result) is dict:
        for key in result:
            if key == col or key in given_info:
                given_info[key] = result[key]
    elif result == -1:
        proceed = False

    document_func_call(log_file, "inspect_static", response, prompt, {"given_info": given_info, "links": links})

    return given_info, links, proceed, url, {}

def get_static_content(
    url: str,
    max_rate_limit_retries: int = 10,
    max_other_retries: int = 3,
    backoff_factor: int = 5,
):
    jina_link = f"https://r.jina.ai/{url}"
    rate_limit_attempts = 0
    other_attempts = 0

    while rate_limit_attempts < max_rate_limit_retries and other_attempts < max_other_retries:
        try:
            response = requests.get(jina_link, timeout=120)

            if response.status_code == 200:
                text = response.text
                text = re.sub(r'[^\x00-\x7F]+', ' ', text)
                return text

            if response.status_code == 429:
                rate_limit_attempts += 1
                wait_time = backoff_factor * (2 ** rate_limit_attempts)
                time.sleep(wait_time)
                continue

            # other non-200 errors
            other_attempts += 1
            wait_time = backoff_factor * (2 ** other_attempts)
            time.sleep(wait_time)

        except requests.exceptions.RequestException as e:
            other_attempts += 1
            wait_time = backoff_factor * (2 ** other_attempts)
            time.sleep(wait_time)

    return -1


def extract_links_from_markdown(markdown_text: str, base_url: str = ""):
    """
    Extracts Markdown-style links of the form [text](url) from markdown_text.
    Returns a list of {"text": ..., "url": ...} dictionaries.
    """
    results = []
    for match in re.finditer(r'\[([^\]]+)\]\(([^)]+)\)', markdown_text):
        text, link = match.groups()
        full_link = urljoin(base_url, link.strip())
        results.append({"text": text.strip(), "url": full_link})
    return results

def viewpage(url, save_path, timeout_ms=120_000):
    url_variants = _normalize_url_variants(url)

    with sync_playwright() as p:

        def attempt(browser_type: str, u: str, use_realistic_ctx: bool):
            browser = getattr(p, browser_type).launch(headless=True)

            kwargs = dict(
                viewport={"width": 1920, "height": 1080},
                device_scale_factor=2,   # 3 can be heavy; 2 is usually enough
            )
            if use_realistic_ctx:
                kwargs.update(
                    user_agent=(
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    locale="en-US",
                    timezone_id="America/Chicago",
                )

            context = browser.new_context(**kwargs)
            page = context.new_page()

            page.goto(u, wait_until="load", timeout=timeout_ms)
            page.wait_for_timeout(1500)
            page.screenshot(path=save_path, full_page=True)

            context.close()
            browser.close()

        errors = []

        strategies = [
            ("chromium", False, 1),
            ("chromium", True,  2),
            ("firefox",  True,  2),
            ("webkit",   True,  1),
        ]

        for u in url_variants:
            for browser_type, realistic, retries in strategies:
                for r in range(retries):
                    try:
                        attempt(browser_type, u, realistic)
                        return
                    except (PwTimeoutError, PwError) as e:
                        errors.append(f"{browser_type} realistic={realistic} url={u} try={r+1}: {e}")
                        time.sleep(0.8 * (r + 1))

        raise RuntimeError("viewpage failed after fallbacks:\n" + "\n".join(errors[-8:]))
