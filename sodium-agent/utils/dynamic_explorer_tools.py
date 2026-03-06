from __future__ import annotations
from dataclasses import dataclass
from playwright.sync_api import sync_playwright, Page

import base64
import hashlib
import json
import re
from typing import Any, Dict, List, Optional

def _norm(s: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

def _walk_a11y(node: Dict[str, Any], out: List[Dict[str, Any]], path: str = "0", max_nodes: int = 8000) -> None:
    if not node or len(out) >= max_nodes:
        return
    out.append(
        {
            "path": path,
            "role": node.get("role"),
            "name": _norm(node.get("name")),
            "value": node.get("value"),
            "disabled": node.get("disabled"),
            "expanded": node.get("expanded"),
            "selected": node.get("selected"),
            "checked": node.get("checked"),
            "level": node.get("level"),
        }
    )
    children = node.get("children") or []
    for i, c in enumerate(children):
        _walk_a11y(c, out, path=f"{path}.{i}", max_nodes=max_nodes)

def _digest_obj(obj: Any, cap: int = 300_000) -> str:
    s = json.dumps(obj, sort_keys=True, ensure_ascii=False)
    s = s[:cap]
    return hashlib.sha256(s.encode("utf-8", errors="ignore")).hexdigest()

def _data_url_from_png_bytes(png_bytes: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png_bytes).decode("utf-8")

def _get_dom_interactives(page: Page, max_elems: int = 160) -> List[Dict[str, Any]]:
    """
    Curated interactives list with suggested selectors.
    Prefer stable attributes; fallback to text selector.
    """
    js = f"""
    () => {{
      const norm = (s) => (s || '').replace(/\\s+/g, ' ').trim();
      const isVisible = (el) => {{
        const r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0;
      }};

      const candidates = Array.from(document.querySelectorAll(
        'a, button, input, select, textarea, [role="button"], [role="tab"], [role="link"], [onclick], [tabindex]'
      ));

      const out = [];
      for (const el of candidates) {{
        if (out.length >= {max_elems}) break;
        if (!isVisible(el)) continue;

        const tag = el.tagName.toLowerCase();
        const role = el.getAttribute('role') || '';
        const id = el.id || '';
        const cls = (el.className && typeof el.className === 'string') ? el.className : '';
        const aria = el.getAttribute('aria-label') || '';
        const tid = el.getAttribute('data-testid') || '';
        const name =
          norm(el.innerText) ||
          norm(aria) ||
          norm(el.getAttribute('title')) ||
          norm(el.getAttribute('name'));

        // build selector candidates
        const selectors = [];
        if (id) selectors.push(`#${{CSS.escape(id)}}`);
        if (tid) selectors.push(`[data-testid="${{tid}}"]`);
        if (aria) selectors.push(`[aria-label="${{aria}}"]`);

        // role + name based (for Playwright get_by_role usage downstream)
        // keep as fields rather than a selector string
        let text_selector = '';
        if (name && (tag === 'button' || tag === 'a' || role === 'button' || role === 'tab')) {{
          text_selector = `text="${{name.slice(0, 60)}}"`;
          selectors.push(text_selector);
        }}

        // fallback: first class
        if (!id && cls) {{
          const c0 = cls.split(/\\s+/).filter(Boolean)[0];
          if (c0) selectors.push(`.${{CSS.escape(c0)}}`);
        }}

        // bounding box (helps debugging and optional "click by position")
        const r = el.getBoundingClientRect();

        out.push({{
          tag,
          role,
          name,
          id,
          class: cls.split(/\\s+/).filter(Boolean).slice(0, 3),
          aria_label: aria || null,
          data_testid: tid || null,
          selectors,
          bbox: {{
            x: Math.round(r.x), y: Math.round(r.y),
            w: Math.round(r.width), h: Math.round(r.height)
          }}
        }});
      }}
      return out;
    }}
    """
    return page.evaluate(js)

def _get_state_signature(page: Page) -> Dict[str, str]:
    url = page.url
    title = page.title()

    main_text = page.evaluate(
        """
        () => {
          const el = document.querySelector('main') || document.body;
          return (el && el.innerText) ? el.innerText : '';
        }
        """
    )
    main_text = (main_text or "")[:200_000]
    main_text_hash = hashlib.sha256(main_text.encode("utf-8", errors="ignore")).hexdigest()

    ax = page.accessibility.snapshot(interesting_only=True)
    ax_digest = _digest_obj(ax) if ax else "none"

    return {"url": url, "title": title, "main_text_hash": main_text_hash, "ax_digest": ax_digest}

def _get_page_meta(page: Page) -> Dict[str, Any]:
    lang = page.evaluate("() => document.documentElement.getAttribute('lang') || ''")
    return {"title": page.title(), "html_lang": lang}

def _get_visible_text(page: Page, limit: int = 250_000) -> str:
    return page.evaluate(
        """
        () => {
          const el = document.querySelector('main') || document.body;
          return (el && el.innerText) ? el.innerText : '';
        }
        """
    )[:limit]

def _state_changed(before: Dict[str, str], after: Dict[str, str]) -> bool:
    """
    Returns True if the page state changed in a meaningful way.
    Designed to be robust for SPA/tab-based navigation.

    Expected keys in before/after:
      - url
      - title
      - main_text_hash
      - ax_digest
    """

    if not before or not after:
        return True

    # 1) URL change (rare for tabs, but definitive)
    if before.get("url") != after.get("url"):
        return True

    # 2) Title change (sometimes used by SPAs)
    if before.get("title") != after.get("title"):
        return True

    # 3) Main visible text change (most important)
    if before.get("main_text_hash") != after.get("main_text_hash"):
        return True

    # 4) Accessibility tree changed (fallback signal)
    if before.get("ax_digest") != after.get("ax_digest"):
        return True

    return False

def _wait_for_data_load(
    page: Page,
    max_wait_time: int = 30000,
    network_idle_timeout: int = 2000,
    stability_check: bool = True,
    stability_duration: int = 2000,
    selectors_to_wait: Optional[List[str]] = None,
) -> None:
    """
    Wait for page data to finish loading by monitoring network activity and page stability.
    
    Args:
        page: The Playwright page object
        max_wait_time: Maximum total time to wait (milliseconds)
        network_idle_timeout: Time to wait with no network requests (milliseconds)
        stability_check: If True, wait for page content to stabilize
        stability_duration: Time to wait for content to remain unchanged (milliseconds)
        selectors_to_wait: Optional list of CSS selectors to wait for before considering page loaded
    """
    import time
    
    start_time = time.time() * 1000  # Convert to milliseconds
    
    # First, wait for any specified selectors to appear
    if selectors_to_wait:
        print(f"Waiting for selectors to appear: {selectors_to_wait}")
        for selector in selectors_to_wait:
            try:
                page.wait_for_selector(selector, timeout=max_wait_time, state="attached")
            except Exception as e:
                print(f"Warning: Selector '{selector}' not found: {e}")
    
    # Wait for network idle (no requests for network_idle_timeout ms)
    print(f"Waiting for network idle (no requests for {network_idle_timeout}ms)...")
    try:
        page.wait_for_load_state("networkidle", timeout=max_wait_time)
    except Exception as e:
        print(f"Warning: Network idle timeout: {e}")
    
    # Additional wait for network idle with custom timeout
    # This helps catch slow API calls that might not be caught by the initial wait
    print(f"Waiting additional {network_idle_timeout}ms for any remaining requests...")
    page.wait_for_timeout(network_idle_timeout)
    
    # Stability check: wait for page content to stabilize
    if stability_check:
        print(f"Checking page stability (waiting {stability_duration}ms for content to stabilize)...")
        previous_state = _get_state_signature(page)
        stable_count = 0
        check_interval = 500  # Check every 500ms
        
        while (time.time() * 1000 - start_time) < max_wait_time:
            page.wait_for_timeout(check_interval)
            current_state = _get_state_signature(page)
            
            if not _state_changed(previous_state, current_state):
                stable_count += check_interval
                if stable_count >= stability_duration:
                    print("Page content has stabilized.")
                    break
            else:
                stable_count = 0
                previous_state = current_state
                print("Page content still changing, continuing to wait...")
    
    elapsed = time.time() * 1000 - start_time
    print(f"Data loading wait completed in {elapsed:.0f}ms")

@dataclass
class PWSession:
    p: any
    browser: any
    context: any
    page: Page

    def close(self):
        # close in reverse order
        try:
            self.context.close()
        except Exception:
            pass
        try:
            self.browser.close()
        except Exception:
            pass
        try:
            self.p.stop()
        except Exception:
            pass

def load_page(
    url: str,
    headless: bool = True,
    max_retries: int = 3
):
    try:
        print("Attempting with Chromium (HTTP/2 disabled)...")
        return load_page_helper(url, headless, max_retries, False)
    except Exception as e:
        print(f"Chromium failed: {e}")
        print("\nTrying with Firefox as fallback...")
        # Fallback to Firefox if Chromium fails
        return load_page_helper(url, headless, max_retries, True)
    
def load_page_helper(
    url: str,
    headless: bool,
    max_retries: int,
    use_firefox: bool,
    wait_for_data: bool = True,
    max_wait_time: int = 30000,
    network_idle_timeout: int = 2000,
    stability_check: bool = True,
    stability_duration: int = 2000,
    selectors_to_wait: Optional[List[str]] = None,
):
    """
    Inspect a dynamic website and extract links.
    
    Args:
        url: The URL to inspect
        headless: Whether to run browser in headless mode
        use_firefox: If True, use Firefox instead of Chromium (useful for HTTP/2 issues)
        max_retries: Maximum number of retry attempts for navigation
    
    Returns:
        tuple: (context, browser, page)
    """
    import time
    
    p = sync_playwright().start()
    browser = None
    context = None
    page = None

    try:
        for attempt in range(max_retries):
            try:
                browser_args = [
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-gpu",
                    "--disable-web-security",
                    "--disable-features=IsolateOrigins,site-per-process",
                    "--disable-http2",  # Force HTTP/1.1 to avoid HTTP/2 protocol errors
                ]
                
                # Choose browser engine
                if use_firefox:
                    browser = p.firefox.launch(headless=headless)
                else:
                    browser = p.chromium.launch(
                        headless=headless,
                        args=browser_args
                    )
                
                # Create context with realistic settings
                context = browser.new_context(
                    viewport={"width": 1280, "height": 800},
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    locale="en-US",
                    timezone_id="America/New_York",
                    permissions=["geolocation"],
                    extra_http_headers={
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                        "Accept-Language": "en-US,en;q=0.9",
                        "Accept-Encoding": "gzip, deflate, br",
                        "DNT": "1",
                        "Connection": "keep-alive",
                        "Upgrade-Insecure-Requests": "1",
                        "Sec-Fetch-Dest": "document",
                        "Sec-Fetch-Mode": "navigate",
                        "Sec-Fetch-Site": "none",
                        "Sec-Fetch-User": "?1",
                        "Cache-Control": "max-age=0",
                    }
                )
                
                page = context.new_page()
                
                # Hide webdriver property
                page.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                    
                    // Override the plugins property to use a custom getter
                    Object.defineProperty(navigator, 'plugins', {
                        get: () => [1, 2, 3, 4, 5]
                    });
                    
                    // Override the languages property to use a custom getter
                    Object.defineProperty(navigator, 'languages', {
                        get: () => ['en-US', 'en']
                    });
                    
                    // Override permissions
                    const originalQuery = window.navigator.permissions.query;
                    window.navigator.permissions.query = (parameters) => (
                        parameters.name === 'notifications' ?
                            Promise.resolve({ state: Notification.permission }) :
                            originalQuery(parameters)
                    );
                """)
                
                # Navigate with realistic wait strategy
                # Try different wait strategies if domcontentloaded fails
                wait_strategies = ["domcontentloaded", "load", "networkidle"]
                wait_strategy = wait_strategies[min(attempt, len(wait_strategies) - 1)]
                
                try:
                    page.goto(url, wait_until=wait_strategy, timeout=30000)
                except Exception as e:
                    # If specific wait strategy fails, try networkidle as fallback
                    if wait_strategy != "networkidle":
                        print(f"Warning: {wait_strategy} failed, trying networkidle...")
                        page.goto(url, wait_until="networkidle", timeout=30000)
                    else:
                        raise
                
                if wait_for_data:
                    _wait_for_data_load(
                        page,
                        max_wait_time=max_wait_time,
                        network_idle_timeout=network_idle_timeout,
                        stability_check=stability_check,
                        stability_duration=stability_duration,
                        selectors_to_wait=selectors_to_wait,
                    )
                else:
                    page.wait_for_timeout(2000)
                
                return PWSession(p=p, browser=browser, context=context, page=page)
                    
            except Exception as e:
                try:
                    if context:
                        context.close()
                except Exception:
                    pass
                try:
                    if browser:
                        browser.close()
                except Exception:
                    pass

                context = None
                browser = None
                page = None

                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                else:
                    raise
    
    finally:
        if browser is None and context is None and page is None:
            try:
                p.stop()
            except Exception:
                pass