import os
import json
import re
import pandas as pd
import argparse
import subprocess
from datetime import datetime

AUTOGPT_PROMPT = '''
You are completing a table that answers the following query: "{query}", starting from this base domain: "{base_domain}"
You should provide the "{col}" information with "{primary_key}" being "{primary_key_val}".
Here's the collection of information you already have {given_cols}.
You should strictly finish with the exact value you found for "{col}" with no additonal formatting. YOU HAVE TO PROVIDE AN OUTPUT WITH KNOWN INFORMATION - DONOT ASK FOR ADDITIONAL INFO.
'''

def run_autogpt(query, col, primary_key, pk_val, row, base_domain, query_id):
    prompt = AUTOGPT_PROMPT.format(
        query=query,
        base_domain=base_domain,
        col=col,
        primary_key=primary_key,
        primary_key_val=pk_val,
        given_cols=row
    )

    workspace_id = f"{query_id}_{primary_key}_{pk_val}_{col}"
    autogpt_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "AutoGPT", "original_autogpt"))
    autogpt_script = os.path.join(autogpt_dir, "autogpt.sh")

    cmd = [
        "bash",
        autogpt_script,
        "run",
        "--ai-task",
        prompt,
        "--skip-reprompt",
        "--workspace-id",
        workspace_id,
        "--skip-news",
        "--ai-role",
        "You are a seasoned digital assistant that is an expert in searching the web for data.",
        "--continuous",
        "--log-level",
        "INFO",
        "--fast_llm",
        "gpt-5-2025-08-07",
        "--smart_llm",
        "gpt-5-2025-08-07",
        "--openai_cost_budget",
        "100",
    ]

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=autogpt_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        stdout, _ = proc.communicate()
    except Exception as e:
        stdout = f"Failed to run AutoGPT: {e}"

    metadata_path = os.path.join(autogpt_dir, "environment", workspace_id, "metadata.json")
    metadata = {}
    cost = 0.0
    if os.path.exists(metadata_path):
        try:
            with open(metadata_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
                cost = float(metadata.get("cost", 0.0))
        except Exception:
            pass

    response = stdout
    return response, cost

def run_autogpt_pipeline(query, schema, primary_key, primary_key_vals, output_folder, base_domain, query_id):
    os.makedirs(output_folder, exist_ok=True)

    rows, total_cost = [], 0.0

    for pk_val in primary_key_vals:
        row = {primary_key: pk_val}

        for col in schema:
            if col == primary_key:
                continue
            log_file = os.path.join(output_folder, f"{pk_val}-{col}.log")
            content, cost = run_autogpt(query, col, primary_key, pk_val, row, base_domain, query_id)
            total_cost += cost

            pattern = r"\[36m\{'reason': '(.*?)'\}"
            matches = re.findall(pattern, content)

            if matches:
                value = matches[-1]
            else:
                value = "Not Specified"

            trace = (
                f"Total Cost: ${total_cost:.6f}\n"
                f"Current Cost: ${cost:.6f}\n"
                f"Message Content:\n{content}\n\n"
            )
            with open(log_file, "a") as f:
                f.write(trace)
            print(content)
            print(value)
            row[col] = value

        rows.append(row)

    pd.DataFrame(rows, columns=schema).to_csv(os.path.join(output_folder, "output.csv"), index=False)


def run_experiment(id):

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_root = f"logs/sodium_{id}_{timestamp}"
    os.makedirs(output_root, exist_ok=True)

    # --- Load data and metadata ---
    schema = pd.read_csv(f"../../sodium-bench/schema/{id}.csv").columns.tolist()

    with open("../../sodium-bench/queries.json", "r") as f:
        query_dict = json.load(f)

    query = query_dict[str(id)]["query"]
    primary_key = query_dict[str(id)]["primary_key"]
    primary_key_vals = query_dict[str(id)]["primary_key_vals"]

    base_domain = query_dict[str(id)].get("base_url", None)

    print(f"[Start] Running AutoGPT on ID {id}")
    run_autogpt_pipeline(
        query, schema, primary_key, primary_key_vals,
        output_root, base_domain, id
    )

    print(f"[Done] Finished AutoGPT on ID {id}")

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
