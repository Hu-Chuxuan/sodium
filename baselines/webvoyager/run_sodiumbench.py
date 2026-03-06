import argparse
import json
import logging
import os
import platform
import re
import shutil
import time

from datetime import datetime

import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from prompts import SYSTEM_PROMPT
from openai import OpenAI

from utils import (
    get_web_element_rect,
    encode_image,
    extract_information,
    get_pdf_retrieval_ans_from_assistant,
    clip_message_and_obs,
    process_output,
)
from result_to_csv import result_to_csv


# =========================
# Logging
# =========================

def setup_logger(folder_path: str) -> None:
    os.makedirs(folder_path, exist_ok=True)
    log_file_path = os.path.join(folder_path, "agent.log")
    logger = logging.getLogger()
    for h in logger.handlers[:]:
        logger.removeHandler(h)
        try:
            h.close()
        except Exception:
            pass
    fh = logging.FileHandler(log_file_path)
    fh.setFormatter(logging.Formatter("%(levelname)s - %(message)s"))
    logger.addHandler(fh)
    logger.setLevel(logging.INFO)


# =========================
# Selenium config
# =========================

def driver_config(args: argparse.Namespace) -> webdriver.ChromeOptions:
    os.makedirs(args.download_dir, exist_ok=True)
    options = webdriver.ChromeOptions()
    options.add_argument("--disable-features=PushMessaging")
    options.add_argument("--no-sandbox")
    options.add_experimental_option("excludeSwitches", ["enable-logging"])
    if args.headless:
        options.add_argument("--headless=new")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument(
            "--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        )
    options.add_experimental_option(
        "prefs",
        {
            "download.default_directory": os.path.abspath(args.download_dir),
            "plugins.always_open_pdf_externally": True,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
        },
    )
    return options


# =========================
# Message formatting
# =========================

def format_msg(it, init_msg, pdf_obs, warn_obs, web_img_b64, web_text):
    if it == 1:
        init_msg += (
            "I've provided the tag name of each element and the text it contains (if text exists). "
            "Note that <textarea> or <input> may be textbox, but not exactly. "
            "Please focus more on the screenshot and then refer to the textual information.\n"
            f"{web_text}"
        )
        return {
            "role": "user",
            "content": [
                {"type": "text", "text": init_msg},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{web_img_b64}"}},
            ],
        }
    else:
        text = (
            f"Observation: {pdf_obs} " if pdf_obs else f"Observation:{warn_obs} "
        ) + (
            "please analyze the attached screenshot and give the Thought and Action. "
            "I've provided the tag name of each element and the text it contains (if text exists). "
            "Note that <textarea> or <input> may be textbox, but not exactly. "
            "Please focus more on the screenshot and then refer to the textual information.\n"
            f"{web_text}"
        )
        return {
            "role": "user",
            "content": [
                {"type": "text", "text": text},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{web_img_b64}"}},
            ],
        }


# =========================
# API call
# =========================

def call_api(args, client, messages):
    retry = 0
    while True:
        try:
            resp = client.chat.completions.create(
                model=args.api_model, messages=messages, temperature=args.temperature
            )
            return resp.usage.prompt_tokens, resp.usage.completion_tokens, False, resp
        except Exception as e:
            et = type(e).__name__
            logging.info(f"API error ({et}). {e}")
            if et == "RateLimitError":
                time.sleep(10)
            elif et == "APIError":
                time.sleep(15)
            else:
                return None, None, True, None
        retry += 1
        if retry >= 10:
            return None, None, True, None


# =========================
# Browser actions
# =========================

def exec_action_click(info, web_ele, driver):
    try:
        driver.execute_script("arguments[0].setAttribute('target','_self')", web_ele)
    except Exception:
        pass
    web_ele.click()
    time.sleep(2)

def exec_action_type(info, web_ele, driver):
    warn = ""
    val = info["content"]
    tag = web_ele.tag_name.lower()
    typ = web_ele.get_attribute("type")
    if (tag not in ("input", "textarea")) or (tag == "input" and typ not in ["text", "search", "password", "email", "tel"]):
        warn = f"note: target may not be a textbox (<{tag}>, type={typ})."
    try:
        web_ele.clear()
        if platform.system() == "Darwin":
            web_ele.send_keys(Keys.COMMAND, "a")
        else:
            web_ele.send_keys(Keys.CONTROL, "a")
        web_ele.send_keys(" ")
        web_ele.send_keys(Keys.BACKSPACE)
    except Exception:
        pass
    ActionChains(driver).click(web_ele).pause(0.3).send_keys(val).perform()
    time.sleep(1)
    return warn

def exec_action_scroll(info, web_eles, driver, args):
    num = info["number"]
    direction = info["content"]
    if num == "WINDOW":
        dy = args.window_height * 2 // 3
        driver.execute_script("window.scrollBy(0, arguments[0]);", dy if direction == "down" else -dy)
    else:
        ele = web_eles[int(num)]
        try:
            driver.execute_script("arguments[0].scrollBy(0, arguments[1]);", ele, args.window_height // 2 * (1 if direction == "down" else -1))
        except Exception:
            ActionChains(driver).key_down(Keys.ALT).send_keys(Keys.ARROW_DOWN if direction == "down" else Keys.ARROW_UP).key_up(Keys.ALT).perform()
    time.sleep(1)


# =========================
# Parsing helper: extract python fenced answer
# =========================

CELL_RE_TMPL = r"```python\s*{pk}\s*,\s*{col}\s*=\s*\"([^\"]*)\"\s*```"

def try_extract_cell(api_text: str, primary_key: str, col_name: str) -> str | None:
    pat = re.compile(CELL_RE_TMPL.format(pk=re.escape(primary_key), col=re.escape(col_name)))
    m = pat.search(api_text)
    if m:
        return m.group(1).strip()
    return None


# =========================
# Core run loop (per PK + per column)
# =========================

def run_single_column(task, pk_val: str, col_name: str, row_result: dict, raw_task_dir: str, args, client) -> str | None:
    setup_logger(raw_task_dir)
    logging.info(f"########## TASK pk={pk_val} col={col_name} ##########")

    options = driver_config(args)
    driver = webdriver.Chrome(options=options)
    extracted_value = None

    try:
        driver.set_window_size(args.window_width, args.window_height)
        driver.get("https://duckduckgo.com/")
        try:
            driver.find_element(By.TAG_NAME, "body").click()
        except Exception:
            pass
        driver.execute_script(
            """
            window.addEventListener('keydown', function(e){
              if(e.keyCode === 32 && e.target.type && !['text','textarea','search','email','password','tel'].includes(e.target.type)) {
                e.preventDefault();
              }
            }, {passive:false});
            """
        )
        time.sleep(1)

        download_files = sorted(os.listdir(args.download_dir))
        fail_obs = ""
        pdf_obs = ""
        warn_obs = ""
        pattern = re.compile(r"Thought:|Action:|Observation:")

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        obs_prompt = "Observation: please analyze the attached screenshot and give the Thought and Action. "

        os.makedirs("context", exist_ok=True)
        with open("context/existing_info.json", "w", encoding="utf-8") as f:
            json.dump({}, f)

        base_url_hint = f'\nYou should search for information starting from this base URL: {task["base_url"]}\n'

        known = {k: v for k, v in row_result.items() if k != task["primary_key"]}
        known_str = json.dumps(known, ensure_ascii=False) if known else "none"
        fill_cell_prompt = (
            f'You should provide a cell value for the column "{col_name}". '
            f'The primary key column is "{task["primary_key"]}" and its value for this row is "{pk_val}".\n'
            f'Other columns already filled for this row: {known_str}\n'
            f'Your answer should be a concise string loadable into a pandas dataframe cell.\n'
            'There is always an answer out there; keep trying unless you absolutely cannot find it, then respond with "No answer found".\n'
            f'Only provide the raw "{col_name}" information, strictly wrapped as ```python {task["primary_key"]}, {col_name} = "your answer here" ```.\n'
            f'{base_url_hint}'
        )
        init_msg = fill_cell_prompt + obs_prompt

        it = 0
        accum_pt = 0
        accum_ct = 0
        visited_urls = []

        while it < args.max_iter:
            it += 1
            logging.info(f"Iter: {it}")

            if not fail_obs:
                visited_urls.append(driver.current_url)
                try:
                    rects, web_eles, web_eles_text = get_web_element_rect(driver, fix_color=args.fix_box_color)
                except Exception as e:
                    logging.error("Page introspection failed.")
                    logging.error(e)
                    break

                img_path = os.path.join(raw_task_dir, f"screenshot{it}.png")
                driver.save_screenshot(img_path)
                b64_img = encode_image(img_path)
                curr = format_msg(it, init_msg, pdf_obs, warn_obs, b64_img, web_eles_text)
                messages.append(curr)
            else:
                messages.append({"role": "user", "content": fail_obs})

            messages = clip_message_and_obs(messages, args.max_attached_imgs)

            pt, ct, err, resp = call_api(args, client, messages)
            if err:
                break
            accum_pt += pt or 0
            accum_ct += ct or 0
            logging.info(f"PT:{accum_pt} CT:{accum_ct}")

            api_res_text = resp.choices[0].message.content
            messages.append({"role": "assistant", "content": api_res_text})
            process_output(api_res_text, task, visited_urls, raw_task_dir, col_name, accum_pt, accum_ct, args.api_model)

            if isinstance(api_res_text, str):
                maybe_val = try_extract_cell(api_res_text, task["primary_key"], col_name)
                if maybe_val is not None:
                    extracted_value = maybe_val

            # clear overlays
            if "rects" in locals() and rects:
                for r in rects:
                    try:
                        driver.execute_script("arguments[0].remove()", r)
                    except Exception:
                        pass
                rects = []

            # parse action
            text = api_res_text if isinstance(api_res_text, str) else str(api_res_text)
            if "Thought:" not in text or "Action:" not in text:
                fail_obs = "Format ERROR: Both 'Thought' and 'Action' should be included in your reply."
                continue
            parts = re.split(pattern, text)
            if len(parts) < 3:
                fail_obs = "Format ERROR: Could not parse 'Action: ...' section."
                continue
            chosen_action = parts[2].strip()
            action_key, info = extract_information(chosen_action)

            try:
                if action_key == "click":
                    idx = int(info[0])
                    rects, web_eles, web_eles_text = get_web_element_rect(driver, fix_color=args.fix_box_color)
                    ele = web_eles[idx]
                    exec_action_click(info, ele, driver)

                    # detect PDF download
                    current = sorted(os.listdir(args.download_dir))
                    if current != download_files:
                        time.sleep(2)
                        current = sorted(os.listdir(args.download_dir))
                        new_pdfs = [f for f in current if f not in download_files and f.endswith(".pdf")]
                        if new_pdfs:
                            src = os.path.join(args.download_dir, new_pdfs[0])
                            ans = get_pdf_retrieval_ans_from_assistant(client, src, col_name)
                            shutil.copy(src, raw_task_dir)
                            pdf_obs = "You downloaded a PDF file. Assistant answered: " + ans
                        download_files = current

                elif action_key == "wait":
                    time.sleep(1)

                elif action_key == "type":
                    idx = int(info["number"])
                    rects, web_eles, web_eles_text = get_web_element_rect(driver, fix_color=args.fix_box_color)
                    ele = web_eles[idx]
                    warn_obs = exec_action_type(info, ele, driver)

                elif action_key == "scroll":
                    rects, web_eles, web_eles_text = get_web_element_rect(driver, fix_color=args.fix_box_color)
                    exec_action_scroll(info, web_eles, driver, args)

                elif action_key == "goback":
                    driver.back()
                    time.sleep(1)

                elif action_key == "google":
                    driver.get("https://www.google.com/")
                    time.sleep(1)

                elif action_key == "answer":
                    logging.info("Answer action received; finishing column.")
                    break

                else:
                    raise NotImplementedError(f"Unknown action: {action_key}")

                fail_obs = ""
            except Exception as e:
                logging.error(f"Driver error: {e}")
                fail_obs = (
                    "The action you have chosen cannot be executed. Double-check numerical label / action / format, "
                    "then provide the revised Thought and Action."
                )

        try:
            est = (accum_pt or 0) / 1000 * 0.01 + (accum_ct or 0) / 1000 * 0.03
            logging.info(f"Estimated cost: {est}")
        except Exception:
            pass
    finally:
        driver.quit()

    return extracted_value


def is_row_complete(json_path: str) -> bool:
    if not os.path.exists(json_path):
        return False
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        for val in data.values():
            if val in ("No answer found", None, ""):
                return False
        return True
    except Exception:
        return False


def run_webvoyager(id, queries_data, data_dir, args, client) -> None:
    dataset_id = str(id)
    dataset_config = queries_data[dataset_id]

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dataset_final_dir = os.path.join(args.output_dir, f"sodium_{dataset_id}_{timestamp}")

    csv_file_path = os.path.join(data_dir, f"{dataset_id}.csv")
    if not os.path.exists(csv_file_path):
        print(f"Warning: CSV not found: {csv_file_path} (skipping)")
        return

    df = pd.read_csv(csv_file_path)
    print(f"Loaded CSV ({df.shape[0]} rows, {df.shape[1]} cols) -> {list(df.columns)}")

    if "primary_key" not in dataset_config:
        raise ValueError(f"Dataset '{dataset_id}' missing 'primary_key' in config.")
    primary_key = dataset_config["primary_key"]

    if "primary_key_vals" in dataset_config and dataset_config["primary_key_vals"]:
        pk_vals = list(dataset_config["primary_key_vals"])
    else:
        if primary_key not in df.columns:
            raise ValueError(f"Primary key '{primary_key}' not in CSV columns.")
        pk_vals = [str(x) for x in df[primary_key].dropna().astype(str).unique()]

    os.makedirs(dataset_final_dir, exist_ok=True)
    raw_base = os.path.join(dataset_final_dir, "raw")
    os.makedirs(raw_base, exist_ok=True)

    for i, pk_val in enumerate(pk_vals, start=1):
        print(f"[{i}/{len(pk_vals)}] PK={pk_val}")

        final_path = os.path.join(dataset_final_dir, f"pk_val-{pk_val}.json")
        if is_row_complete(final_path):
            print(f"PK={pk_val} already complete - SKIPPING")
            continue

        row_result = {primary_key: pk_val}
        if os.path.exists(final_path):
            try:
                with open(final_path, 'r', encoding='utf-8') as f:
                    row_result = json.load(f)
                print(f"Loaded partial data for PK={pk_val}")
            except Exception:
                row_result = {primary_key: pk_val}

        raw_pk_dir = os.path.join(raw_base, f"pk_{pk_val}")
        os.makedirs(raw_pk_dir, exist_ok=True)

        for col_name in df.columns:
            if col_name == primary_key:
                continue

            if col_name in row_result:
                existing_val = row_result[col_name]
                if existing_val and existing_val not in ("No answer found", None, ""):
                    print(f"Column '{col_name}' already filled - SKIPPING")
                    continue

            raw_task_dir = os.path.join(raw_pk_dir, f"task_{col_name}")
            os.makedirs(raw_task_dir, exist_ok=True)

            task = {
                "id": f"{dataset_id}:{pk_val}:{col_name}",
                "dataset_id": dataset_id,
                "primary_key": primary_key,
                "primary_key_val": pk_val,
                "col_name": col_name,
                "query": dataset_config.get(
                    "query",
                    f'Fill column "{col_name}" for {primary_key}={pk_val}'
                ),
                "base_url": dataset_config.get("base_url", ""),
            }

            val = run_single_column(task, pk_val, col_name, row_result, raw_task_dir, args, client)
            row_result[col_name] = val if val is not None else "No answer found"

        final_path = os.path.join(dataset_final_dir, f"pk_val-{pk_val}.json")
        with open(final_path, "w", encoding="utf-8") as f:
            json.dump(row_result, f, ensure_ascii=False, indent=2)
        print(f"     Saved: {final_path}")

    print(f"Converting results to CSV for dataset {dataset_id}...")
    try:
        result_to_csv(dataset_final_dir, csv_file_path)
        print(f"CSV created: {os.path.join(dataset_final_dir, 'output.csv')}")
    except Exception as e:
        print(f"Error creating CSV: {e}")


def run_experiment(id):
    args = argparse.Namespace(
        api_key=os.getenv("OPENAI_API_KEY", ""),
        api_model="gpt-5",
        max_iter=10,
        max_attached_imgs=3,
        temperature=1.0,
        output_dir="logs",
        download_dir="downloads",
        headless=True,
        window_width=1920,
        window_height=1080,
        fix_box_color=True,
    )

    client = OpenAI(api_key=args.api_key)

    os.makedirs(args.output_dir, exist_ok=True)

    with open("../../sodium-bench/queries.json", "r", encoding="utf-8") as f:
        queries_data = json.load(f)

    run_webvoyager(id, queries_data, "../../sodium-bench/schema/", args, client)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--id",
        type=int,
        required=True,
        help="Query ID to run (e.g., 1)"
    )
    args = parser.parse_args()
    run_experiment(args.id)
