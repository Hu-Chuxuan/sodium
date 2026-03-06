import os
import re
import json
import argparse
import pandas as pd
from datetime import datetime

from autogen import LLMConfig
from autogen.agents.experimental import WebSurferAgent
from result_to_csv import result_to_csv

BASE_SYSTEM_JSON_SPEC = """\
You are a research assistant that finds data from a given source.
You must extract the contents of the source to answer the query to the best of your ability.
Do not include any special characters in your answer.
When answering, always return a single JSON object with this exact schema:
{
  "result": <the best single value for the requested column>,
  "explanation": "<1-2 sentence justification referencing the sources>",
}
- For numeric answers, return raw numbers (e.g., 16.5 or 0.165 for 16.5%).
- If the source only shows a percentage, return it as a number in percent form (e.g., 16.5).
- If value is truly unknown, set "result": "N/A".
"""

def postprocess(value):
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized == "true":
            return True
        if normalized == "false":
            return False
        return re.sub(r'[$%]', '', value)
    return value

def parse_agent_json(content):
    if isinstance(content, dict):
        return content
    try:
        return json.loads(content)
    except Exception:
        if isinstance(content, str) and content.strip().startswith("```"):
            stripped = content.strip().strip("`")
            first_brace = stripped.find("{")
            last_brace = stripped.rfind("}")
            if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
                try:
                    return json.loads(stripped[first_brace:last_brace+1])
                except Exception:
                    pass
        return {"result": "N/A", "explanation": "Could not parse agent JSON", "evidence": []}

def build_agent(llm_config):
    agent = WebSurferAgent(
        name="search_agent",
        web_tool="browser_use",
        system_message=(
            BASE_SYSTEM_JSON_SPEC
        ),
        llm_config=llm_config,
    )
    return agent

def build_prior_knowledge(ordered_columns, results_so_far):
    parts = []
    for c in ordered_columns:
        if c in results_so_far:
            val = str(results_so_far[c])
            if val and val != "N/A":
                parts.append(f"{c}: {val}")
    pk_str = "; ".join(parts)
    if len(pk_str) > 2000:
        pk_str = pk_str[-2000:]
    return pk_str or "none"

def run_ag2(id, queries_data, data_dir):
    api_key = os.getenv("OPENAI_API_KEY")
    llm_config = LLMConfig(
        config_list=[
            {
                "api_type": "openai",
                "model": "gpt-5",
                "api_key": api_key,
                "base_url": "https://api.openai.com/v1",
            }
        ]
    )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_root = f"logs/sodium_{id}_{timestamp}"
    os.makedirs(output_root, exist_ok=True)

    csv_file_path = os.path.join(data_dir, f"{id}.csv")
    if not os.path.exists(csv_file_path):
        return
    df_data = pd.read_csv(csv_file_path)
    dataset_config = queries_data[str(id)]

    primary_key = dataset_config["primary_key"]
    pk_vals = dataset_config["primary_key_vals"]
    input_query = dataset_config["query"]
    base_url = dataset_config["base_url"]


    lower_map = {c.lower(): c for c in df_data.columns}
    primary_key_column = lower_map.get(primary_key.lower(), primary_key)
    columns = [c for c in df_data.columns if c != primary_key_column]

    tasks_by_pk = {pk: [] for pk in pk_vals}
    for pk_val in pk_vals:
        for column in columns:
            filename = os.path.join(output_root, f"{pk_val}-{column}.json")
            tasks_by_pk[pk_val].append((column, filename))

    ordered_columns = columns
    def worker(pk_val, column, filename, prior_knowledge):
        agent = build_agent(llm_config)
        query = f"Find the '{column}' with primary key '{primary_key}' that is '{pk_val}'. The result should answer the query: '{input_query}'. You have previous column information: {prior_knowledge}. Obtain your answer starting from this website: '{base_url}'."
        data = {"PK": pk_val, "column": column, "status": "pending"}
        try:
            chat_result = agent.run(message=query, tools=agent.tools, max_turns=3, user_input=False)
            chat_result.process()
            content = chat_result.messages[-1]["content"]
            parsed = parse_agent_json(content)
            parsed["result"] = postprocess(parsed.get("result", "N/A"))
            data["status"] = "success"
            data.update(parsed)
        except Exception as e:
            data["status"] = "error"
            data["error_type"] = type(e).__name__
            data["error_details"] = str(e)
        try:
            with open(filename, "w", encoding="utf-8") as outf:
                json.dump(data, outf, indent=4, ensure_ascii=False)
        except Exception as file_err:
            data["status"] = "error"
            data["error_type"] = type(file_err).__name__
            data["error_details"] = f"save_error: {file_err}"
        return data.get("result", "Not Specified")

    for pk_val in pk_vals:
        results_so_far = {}
        for column, filename in tasks_by_pk[pk_val]:
            prior_knowledge = build_prior_knowledge(ordered_columns, results_so_far)
            cell_result = worker(pk_val, column, filename, prior_knowledge)
            results_so_far[column] = cell_result

    result_to_csv(output_root, csv_file_path)

def run_experiment(id):
    with open("../../sodium-bench/queries.json", "r", encoding="utf-8") as f:
        queries_data = json.load(f)

    run_ag2(id, queries_data, "../../sodium-bench/schema/")

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