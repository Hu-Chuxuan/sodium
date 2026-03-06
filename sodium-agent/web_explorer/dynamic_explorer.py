from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional

from playwright.sync_api import Page
from urllib.parse import urljoin

from utils.prompt import DYNAMIC_SYSTEM_PROMPT
from utils.log import document_func_call
import utils.dynamic_explorer_tools as dx

def inspect_dynamic(
    url: str,
    query: str,
    primary_key: str,
    primary_key_val: str,
    col: str,
    given_info,
    client,
    log_file,
    max_webpage_retries: int = 3,
    max_retries: int = 12,
    headless: bool = True
) -> Dict[str, Any]:
    task = {"query": query, "primary_key": primary_key, "primary_key_val": primary_key_val, "col": col, "given_info": given_info}

    history: List[Dict[str, Any]] = []
    virtual_accessibility: Optional[Dict[str, Any]] = None
    links = []
    path_record = {}

    sess = dx.load_page(url, headless, max_webpage_retries)
    page = sess.page

    for r in range(max_retries):
        observation = collect_page_observation(page)
        decision = determine_step(
            client=client,
            task=task,
            observation=observation,
            virtual_accessibility=virtual_accessibility,
            history=history,
            model="gpt-5",
            log_file=log_file
        )

        st = decision["step_type"]

        if st == -1:
            history.append({
                "round": r,
                "error": decision["error"],
                "rationale": decision["rationale"]
            })
            continue
        
        if st == 1:
            js_code = decision["accessibility_update_js"]
            exec_out = execute_accessibility_update_js(page, js_code)
            if exec_out.get("ok"):
                virtual_accessibility = exec_out.get("result")
            else:
                virtual_accessibility = {"_error": exec_out.get("error")}

            history.append({
                "round": r,
                "step_type": 1,
                "rationale": decision.get("rationale"),
                "js_hash": hashlib.sha256(js_code.encode("utf-8", errors="ignore")).hexdigest()[:16],
                "exec_ok": exec_out.get("ok"),
                "exec_error": exec_out.get("error"),
                "state_signature": observation["state_signature"],
            })
            continue

        if st == 3:
            result = decision["answer"]
            for key in result:
                if key == col or key in given_info:
                    given_info[key] = result[key]
            sess.close()
            return given_info, links, True, observation["state_signature"]["url"], path_record

        if st == 4:
            links = extract_links_from_page(page)
            sess.close()
            return given_info, links, True, observation["state_signature"]["url"], path_record
        
        if st == 5:
            sess.close()
            return given_info, links, False, observation["state_signature"]["url"], path_record

        # ---- Step 2: click one or multiple selectors
        selectors: List[str] = decision.get("selectors") or []
        selectors = [s for s in selectors if isinstance(s, str) and s.strip()][:8]

        click_results = []

        for sel in selectors:
            before_sig = dx._get_state_signature(page)
            log = click(page, sel)
            page.wait_for_timeout(1200)
            after_sig = dx._get_state_signature(page)
            changed = dx._state_changed(before_sig, after_sig)
            log["changed"] = changed
            click_results.append(log)
            if after_sig['url'] != before_sig['url']:
                path_record[after_sig['url']] = before_sig['url']

        page.wait_for_timeout(1000)
        observation = collect_page_observation(page)

        history.append({
            "round": r,
            "step_type": 2,
            "rationale": decision.get("rationale"),
            "selectors": selectors,
            "click_results": click_results
        })
    links = extract_links_from_page(page)
    sess.close()
    return given_info, links, True, observation["state_signature"]["url"], path_record

def determine_step(
    client,
    log_file,
    task: Dict[str, Any],
    observation: Dict[str, Any],
    virtual_accessibility: Optional[Dict[str, Any]],
    history: List[Dict[str, Any]]
) -> Dict[str, Any]:
    payload = {
        "observation": {
            "page_meta": observation["page_meta"],
            "state_signature": observation["state_signature"],
            "visible_text_excerpt": observation["page_text"]["visible_text"][:8000],
            "a11y_nodes": observation["a11y"]["nodes"][:1400],
            "dom_interactives": observation["dom_interactives"]["items"][:1000],
        },
        "virtual_accessibility": virtual_accessibility,
        "history": history[-10:],
        "output_schema": {
            "step_type": "1|2|3|4|5",
            "if_1": {"accessibility_update_js": "string (required, ends with return {...};)"},
            "if_2": {"selectors": "list[str] length 1..8"},
            "if_3": {"answer": "string"},
            "if_4": {},
            "if_5": {},
        },
    }
    task_desc = f'''
        You are helping complete a table for the following query:
        {task['query']}

        We are searching for information for column "{task['col']}" for the record where "{task['primary_key']}" = "{task['primary_key_val']}". Here's the collection of information you already have: {task['given_info']}.
        
        Here are your current observations:

        '''
    if observation["screenshot_data_url"] is not None:
        resp = client.responses.create(
            model="gpt-5",
            input=[
                {"role": "system", "content": DYNAMIC_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": task_desc+json.dumps(payload, ensure_ascii=False)},
                        {"type": "input_image", "image_url": observation["screenshot_data_url"], "detail": "high"},
                    ],
                },
            ],
        )
    else:
        resp = client.responses.create(
            model="gpt-5",
            input=[
                {"role": "system", "content": DYNAMIC_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": task_desc+json.dumps(payload, ensure_ascii=False)}
                    ],
                },
            ],
        )
    
    def loads_first_json(s: str):
        s = (s or "").strip()
        if s.startswith("```"):
            s = s.strip("`")
            s = s.replace("json\n", "", 1).strip()

        dec = json.JSONDecoder()
        obj, idx = dec.raw_decode(s) 

        return obj, s[idx:].strip()
    document_func_call(log_file, "determine_step", resp, task_desc+json.dumps(payload, ensure_ascii=False))
    try:
        data, leftover = loads_first_json(resp.output_text)
    except:
        return {"step_type": -1, "error": "return {note:'invalid output'};", "rationale": "Invalid answer"}
    print(data)

    st = data.get("step_type")
    if st not in (1, 2, 3, 4, 5):
        return {"step_type": -1, "error": "return {note:'invalid step_type'};", "rationale": "Invalid output"}

    if st == 1:
        js_code = data.get("accessibility_update_js")
        if not isinstance(js_code, str) or "return" not in js_code:
            return {"step_type": -1, "error": "return {note:'missing js'};", "rationale": "Missing JS"}
        return data

    if st == 2:
        sels = data.get("selectors")
        if isinstance(sels, str):
            sels = [sels]
        if not isinstance(sels, list) or not sels:
            return {"step_type": -1, "error": "return {note:'invalid selectors'};", "rationale": "Invalid selectors"}
        data["selectors"] = [s.strip() for s in sels if isinstance(s, str) and s.strip()][:8]
        if not data["selectors"]:
            return {"step_type": -1, "error": "return {note:'empty selectors'};", "rationale": "Empty selectors"}
        return data

    if st == 3:
        ans = data.get("answer")
        if not isinstance(ans, dict) or task['col'] not in ans or not isinstance(ans[task['col']], str) or not ans[task['col']].strip():
            return {"step_type": -1, "error": "return {note:'invalid answer dict'};", "rationale": "Invalid answer"}
        return data
    
    if st == 4:
        return data

    return data

def collect_page_observation(
    page,
    a11y_interesting_only: bool = False,
    max_a11y_nodes: int = 8000,
    max_dom_interactives: int = 160,
) -> Dict[str, Any]:
    """
    Loads `url` and returns a single observation payload suitable to show an agent:
      - metadata (title, lang)
      - state signature (url/title/main_text_hash/ax_digest)
      - flattened a11y nodes (role/name/states + path)
      - curated DOM interactives with selector candidates + bbox
      - screenshot as data URL (PNG)

    This avoids dumping full raw HTML while still providing rich UI info.
    """
    # screenshot
    try:
        png_bytes = page.screenshot(full_page=True)
        screenshot_data_url = dx._data_url_from_png_bytes(png_bytes)
    except:
        try:
            page.evaluate("""
                () => {
                    if (document.fonts && document.fonts.ready) {
                        // detach waiting chain; do not block
                        document.fonts.ready.catch(() => null);
                    }
                }
            """)
            png_bytes = page.screenshot(full_page=True)
            screenshot_data_url = dx._data_url_from_png_bytes(png_bytes)
        except:
            screenshot_data_url = None

    snap = page.accessibility.snapshot(interesting_only=a11y_interesting_only)
    a11y_flat: List[Dict[str, Any]] = []
    if snap:
        dx._walk_a11y(snap, a11y_flat, max_nodes=max_a11y_nodes)

    dom_interactives = dx._get_dom_interactives(page, max_elems=max_dom_interactives)

    print("page.url:", page.url)
    print("num anchors:", page.evaluate("() => document.querySelectorAll('a').length"))
    print("sample href attr:", page.evaluate("() => Array.from(document.querySelectorAll('a')).slice(0,10).map(a=>a.getAttribute('href'))"))
    print("sample href prop:", page.evaluate("() => Array.from(document.querySelectorAll('a')).slice(0,10).map(a=>a.href)"))


    obs = {
        "page_meta": dx._get_page_meta(page),
        "state_signature": dx._get_state_signature(page),
        "screenshot_data_url": screenshot_data_url,
        "page_text": {"visible_text": dx._get_visible_text(page)},
        "a11y": {
            "interesting_only": a11y_interesting_only,
            "node_count": len(a11y_flat),
            "nodes": a11y_flat,
        },
        "dom_interactives": {
            "count": len(dom_interactives),
            "items": dom_interactives,
        },
    }
    return obs

def execute_accessibility_update_js(
    page: Page,
    js_code: str,
    max_out_bytes: int = 300_000
) -> Dict[str, Any]:
    """
    Execute model-provided JS in the page context to discover structure (virtual accessibility).

    js_code should be either:
      - JS that RETURNS an object (e.g., `return {...}`), or
      - JS that evaluates to an object (e.g., `({foo: 1})`), or
      - JS that defines helpers and ends with returning an object.

    IMPORTANT (Playwright Python): page.evaluate accepts ONLY ONE argument object.
    """

    if not isinstance(js_code, str):
        return {"ok": False, "error": "js_code not a string", "result": None}
    if len(js_code) > 8000:
        return {"ok": False, "error": "js_code too long (>8000 chars)", "result": None}

    # Pass a SINGLE JSON-serializable arg object to Playwright.
    wrapper = r"""
    ({ code, maxOutBytes }) => {
      const clamp = (obj) => {
        try {
          const s = JSON.stringify(obj);
          if (s.length > maxOutBytes) {
            return { _truncated: true, _bytes: s.length, preview: s.slice(0, maxOutBytes) };
          }
          return obj;
        } catch (e) {
          return { _error: "stringify_failed", message: String(e) };
        }
      };

      try {
        // Normalize: allow either a function body or an expression.
        // If the code contains 'return', treat as function body.
        // Otherwise treat as an expression and return it.
        let fn;
        if (/\\breturn\\b/.test(code)) {
          fn = new Function(code);              // body: "...; return {...};"
        } else {
          fn = new Function("return (" + code + ");"); // expr: "({...})" or "someVar"
        }

        const res = fn();
        return { ok: true, result: clamp(res), error: null };
      } catch (e) {
        return { ok: false, result: null, error: String(e) };
      }
    }
    """

    out = page.evaluate(
        wrapper,
        {
            "code": js_code,
            "maxOutBytes": int(max_out_bytes),
        },
    )
    return out

def click(page: Page, sel: str, timeout_ms: int = 8000) -> Dict[str, Any]:
    """
    Robust click:
      - wait visible + scroll
      - normal click
      - force click fallback
      - JS click fallback ONLY if sel is CSS (not text=, xpath=, etc.)
    Returns debug info about the click attempt.
    """
    loc = page.locator(sel).first
    info: Dict[str, Any] = {"selector": sel, "clicked": False, "method": None, "error": None}

    try:
        loc.wait_for(state="visible", timeout=timeout_ms)
        loc.scroll_into_view_if_needed(timeout=timeout_ms)
        loc.click(timeout=timeout_ms)
        dx._wait_for_data_load(page)
        info["clicked"] = True
        info["method"] = "locator.click"
        return info
    except Exception as e1:
        try:
            loc.scroll_into_view_if_needed(timeout=timeout_ms)
            loc.click(timeout=timeout_ms, force=True)
            dx._wait_for_data_load(page)
            info["clicked"] = True
            info["method"] = "locator.click(force=True)"
            return info
        except Exception as e2:
            try:
                if any(sel.lstrip().startswith(prefix) for prefix in ("text=", "xpath=", "role=", "internal:", "data-test")):
                    raise ValueError("JS click fallback skipped: selector is not CSS.")
                page.evaluate(
                    """(cssSel) => {
                      const el = document.querySelector(cssSel);
                      if (el) el.click();
                      else throw new Error("querySelector found no element");
                    }""",
                    sel,
                )
                dx._wait_for_data_load(page)
                info["clicked"] = True
                info["method"] = "page.evaluate(querySelector.click)"
                return info
            except Exception as e3:
                info["error"] = f"{repr(e1)} | {repr(e2)} | {repr(e3)}"
                return info

def extract_links_from_page(page: Page) -> List[Dict[str, str]]:
    """
    Extract visible links from the current page.
    Returns a list of {"text": ..., "url": ...}.
    """

    base_url = page.url

    links = page.evaluate(
        """
        () => {
          const isVisible = (el) => {
            const r = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            return r.width > 0 && r.height > 0 &&
                   style.display !== 'none' &&
                   style.visibility !== 'hidden';
          };

          const out = [];
          for (const a of document.querySelectorAll('a[href]')) {
            if (!isVisible(a)) continue;

            const href = a.getAttribute('href');
            if (!href) continue;

            const text = (a.innerText || a.textContent || '').replace(/\\s+/g, ' ').trim();

            out.push({
              text,
              href
            });
          }
          return out;
        }
        """
    )

    results = []
    for item in links:
        href = item["href"].strip()

        if href.startswith("#") and not href.startswith("#/"):
            continue
        if href.lower().startswith("javascript:"):
            continue
        if href.lower().startswith("mailto:"):
            continue
        if href.lower().startswith("tel:"):
            continue

        full_url = urljoin(base_url, href)
        results.append({
            "text": item["text"],
            "url": full_url,
        })

    return results