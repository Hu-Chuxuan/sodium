import asyncio
import argparse
import json
import os
import pandas as pd

from datetime import datetime

from examples.research_bot.manager import ResearchManager
from result_to_csv import result_to_csv

def resolve_primary_key_column_robust(df: pd.DataFrame, primary_key_col: str) -> str:
    lower_map = {c.lower(): c for c in df.columns}
    return lower_map.get(primary_key_col.lower(), primary_key_col)


async def run_researchbot(id: int, queries: dict, data_dir: str):
    q = queries[str(id)]
    primary_key = q["primary_key"]
    pk_vals = q["primary_key_vals"]
    input_query = q["query"]
    base_url = q["base_url"]

    csv_file_path = os.path.join(data_dir, f"{id}.csv")
    df = pd.read_csv(csv_file_path)
    pk_col = resolve_primary_key_column_robust(df, primary_key)
    columns = [c for c in df.columns if c != pk_col]

    manager = ResearchManager()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_root = f"logs/sodium_{id}_{timestamp}"
    os.makedirs(output_root, exist_ok=True)

    base_url_hint = f"\nObtain your answer starting from this website: '{base_url}'." if base_url else ""

    for pk_val in pk_vals:
        row_result = {}

        for column in columns:
            out_path = os.path.join(output_root, f"{pk_val}-{column}.json")

            if os.path.exists(out_path):
                try:
                    prev = json.loads(open(out_path, "r", encoding="utf-8").read())
                    if prev.get("status") == "success":
                        row_result[column] = prev.get("result", "")
                        continue
                except Exception:
                    pass

            known_str = json.dumps(row_result, ensure_ascii=False) if row_result else "none"
            prompt = (
                f"Find the '{column}' with primary key '{primary_key}' that is '{pk_val}'. "
                f"The result should answer the query: '{input_query}'. "
                f"Other columns already filled for this row: {known_str}."
                f"{base_url_hint}"
            )

            data = {"PK": pk_val, "column": column, "status": "pending"}
            try:
                res = await manager.run(query=prompt)
                data["status"] = "success"
                data["result"] = res
                row_result[column] = res
            except Exception as e:
                data["status"] = "error"
                data["error_type"] = type(e).__name__
                data["error_details"] = str(e)

            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

    result_to_csv(output_root, csv_file_path)


async def run_experiment(id: int):
    with open("../../sodium-bench/queries.json", "r") as f:
        queries = json.load(f)

    print(f"[Start] dataset {id}")
    await run_researchbot(id, queries, "../../sodium-bench/schema/")
    print(f"[Done] dataset {id}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", type=int, required=True, help="Query ID to run (e.g., 1)")
    args = parser.parse_args()
    asyncio.run(run_experiment(args.id))
