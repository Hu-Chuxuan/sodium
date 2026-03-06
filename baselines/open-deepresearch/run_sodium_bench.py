import time
import os
import re
import json
import argparse
import traceback
import random
import shutil

import pandas as pd
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.options import Options
from result_to_csv import result_to_csv

BASE_URL = "http://localhost:3000"


def wait_for_report_or_error(driver, timeout=300):
    wait = WebDriverWait(driver, timeout)
    print("waiting")

    def check(driver):
        try:
            if driver.find_elements(By.XPATH, "//div[normalize-space()='Agent Error']"):
                return "error"
            if driver.find_elements(By.XPATH, "//*[contains(text(), 'No search results found')]"):
                return "error"
            start_button = driver.find_element(By.XPATH, "//button[normalize-space()='Start Deep Research']")
            if start_button:
                return start_button
            return False
        except Exception:
            return False

    return wait.until(check)


def get_latest_report_file(directory):
    try:
        files = os.listdir(directory)
    except FileNotFoundError:
        return None

    report_files = []
    pattern = re.compile(r'report-(\d+)\.json')
    for filename in files:
        match = pattern.match(filename)
        if match:
            report_files.append((int(match.group(1)), filename))

    if not report_files:
        return None

    return os.path.join(directory, max(report_files, key=lambda x: x[0])[1])


def postprocess(value):
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized == "true":
            return True
        elif normalized == "false":
            return False
        else:
            return re.sub(r'[$%]', '', value)
    return value



def resolve_primary_key_column(df_data, primary_key_col):
    for col in df_data.columns:
        if primary_key_col.lower() in col.lower() or col.lower() in primary_key_col.lower():
            return col
    return primary_key_col


def run_open_deepresearch(id, queries_data, data_dir):
    dataset_id = str(id)
    dataset_config = queries_data[dataset_id]

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = f"logs/sodium_{dataset_id}_{timestamp}"
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs("output", exist_ok=True)

    data_csv_path = os.path.join(data_dir, f"{dataset_id}.csv")
    if not os.path.exists(data_csv_path):
        print(f"Warning: CSV file not found: {data_csv_path}, skipping...")
        return

    df_data = pd.read_csv(data_csv_path)
    print(f"Loaded CSV data with shape: {df_data.shape}")
    print(f"Columns: {list(df_data.columns)}")

    primary_key = dataset_config["primary_key"]
    pk_vals = dataset_config["primary_key_vals"]
    input_query = dataset_config["query"]
    base_url = dataset_config.get("base_url", "")

    primary_key_column = resolve_primary_key_column(df_data, primary_key)
    columns = [c for c in df_data.columns if c != primary_key_column]

    # Setup driver
    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--ignore-certificate-errors")
    chrome_options.add_argument("--allow-insecure-localhost")
    chrome_options.add_argument("--disable-usb")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-plugins")
    chrome_options.add_argument("--disable-images")
    chrome_options.add_argument("--disable-javascript")
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebDriver/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    )
    temp_profile_dir = os.path.join(os.getcwd(), f"temp_profile_{dataset_id}")
    chrome_options.add_argument(f"--user-data-dir={temp_profile_dir}")

    driver = None
    success_count = 0
    error_count = 0

    try:
        driver = webdriver.Chrome(options=chrome_options)
        driver.set_page_load_timeout(30)
        print(f"Connecting to {BASE_URL}")
        driver.get(BASE_URL)
        time.sleep(2)

        base_url_hint = f'\nYou should search for information starting from this base URL: {base_url}\n' if base_url else ""

        for pk_val in pk_vals:
            print(f"Processing primary key value: {pk_val}")
            row_result = {}

            for column in columns:
                filename = os.path.join(output_dir, f"{pk_val}-{column}.json")
                if os.path.exists(filename):
                    print(f"Skipping existing file: {filename}")
                    try:
                        with open(filename, 'r', encoding='utf-8') as f:
                            saved = json.load(f)
                        if saved.get("status") == "success":
                            row_result[column] = saved.get("result", "")
                    except Exception:
                        pass
                    continue

                known = {k: v for k, v in row_result.items()}
                known_str = json.dumps(known, ensure_ascii=False) if known else "none"
                query = (
                    f'You should provide a cell value for the column "{column}". '
                    f'The primary key column is "{primary_key}" and its value for this row is "{pk_val}".\n'
                    f'Other columns already filled for this row: {known_str}\n'
                    f'Your answer should be a concise string. '
                    f'The overall task is: {input_query}\n'
                    'There is always an answer; keep trying unless you absolutely cannot find it, then respond with "No answer found".'
                    f'{base_url_hint}'
                )

                data = {"PK": pk_val, "column": column, "status": "pending"}

                max_retries = 2
                retry_count = 0
                success = False
                print(f"Trying for column: {column}")

                while retry_count < max_retries and not success:
                    try:
                        driver.refresh()

                        checkbox_button = driver.find_element(By.ID, "agent-mode")
                        if checkbox_button.get_attribute("aria-checked") == "false":
                            checkbox_button.click()

                        time.sleep(3)
                        search_box = driver.find_element(
                            By.XPATH,
                            "//input[@placeholder=\"What would you like to research? (e.g., 'Tesla Q4 2024 financial performance and market impact')\"]"
                        )
                        search_box.clear()
                        search_box.send_keys(query)

                        start_button = driver.find_element(By.XPATH, "//button[normalize-space()='Start Deep Research']")
                        start_button.click()
                        time.sleep(5)

                        result = wait_for_report_or_error(driver, timeout=300)
                        if result == "error":
                            retry_count += 1
                            print(f"Error encountered, attempt {retry_count}/{max_retries}")
                            if retry_count < max_retries:
                                driver.refresh()
                                time.sleep(5)
                                continue
                            else:
                                data["status"] = "error"
                                data["error_type"] = "report_generation_error"
                                data["error_details"] = f"Failed after {max_retries} attempts"
                                break
                        else:
                            data["status"] = "success"
                            report_file = get_latest_report_file("output")
                            if report_file:
                                with open(report_file, 'r', encoding='utf-8') as f:
                                    dir_data = json.load(f)
                                result_val = dir_data.get("result")
                                dir_data["result"] = postprocess(result_val) if result_val is not None else result_val
                                row_result[column] = dir_data["result"]
                                data.update(dir_data)
                            else:
                                data["status"] = "error"
                                data["error_type"] = "no_report_file"
                                data["error_details"] = "Report was generated but no report file found"
                            success = True

                        time.sleep(10)

                    except Exception as e:
                        retry_count += 1
                        error_type = type(e).__name__
                        print(f"Exception for column '{column}', attempt {retry_count}/{max_retries}")
                        print(f"Error Type: {error_type} — {str(e)}")
                        print(traceback.format_exc())

                        if retry_count < max_retries:
                            driver.refresh()
                            time.sleep(3)
                            continue
                        else:
                            data["status"] = "error"
                            data["error_type"] = error_type
                            data["error_details"] = str(e)
                            break

                # Log
                key = f"{pk_val}-{column}"
                log_file_path = os.path.join(output_dir, "log.json")
                if not os.path.exists(log_file_path):
                    with open(log_file_path, 'w') as f:
                        json.dump({}, f)
                with open(log_file_path, 'r+', encoding='utf-8') as log_file:
                    try:
                        log = json.load(log_file)
                    except json.JSONDecodeError:
                        log = {}
                    if key not in log:
                        log[key] = {"query": query, "results": [], "statuses": []}
                    log[key]["results"].append(data.get("result", "none"))
                    log[key]["statuses"].append(data["status"])
                    log_file.seek(0)
                    json.dump(log, log_file, indent=4)
                    log_file.truncate()

                # Save result
                try:
                    with open(filename, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=4)
                    print(f"Saved: {filename} (status: {data['status']})")
                    if data['status'] == 'success':
                        success_count += 1
                    else:
                        error_count += 1
                except Exception as file_error:
                    print(f"ERROR: Could not save file {filename}: {file_error}")
                    error_count += 1

    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        print(traceback.format_exc())
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
        try:
            if os.path.exists(temp_profile_dir):
                shutil.rmtree(temp_profile_dir, ignore_errors=True)
        except Exception:
            pass
        # Clean output dir
        try:
            with os.scandir("output") as entries:
                for entry in entries:
                    if entry.is_file() and entry.name != "cost.json":
                        os.unlink(entry.path)
        except Exception as cleanup_error:
            print(f"Warning: Could not clean output directory: {cleanup_error}")

    print(f"Completed dataset {dataset_id}. Success: {success_count}, Errors: {error_count}")

    print(f"Generating CSV from results...")
    result_to_csv(output_dir, data_csv_path)
    print(f"CSV created: {os.path.join(output_dir, 'output.csv')}")


def run_experiment(id):
    with open("../../sodium-bench/queries.json", "r", encoding="utf-8") as f:
        queries_data = json.load(f)

    run_open_deepresearch(id, queries_data, "../../sodium-bench/schema/")


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
