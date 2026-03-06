import os
import json
import argparse
import pandas as pd
from datetime import datetime

from agent import sodium_agent

def run_experiment(id):

    schema = pd.read_csv(f"../sodium-bench/schema/{id}.csv").columns.tolist()

    with open("../sodium-bench/queries.json", "r") as f:
        query_dict = json.load(f)

    query = query_dict[str(id)]["query"]
    primary_key = query_dict[str(id)]["primary_key"]
    primary_key_vals = query_dict[str(id)]["primary_key_vals"]
    domain = query_dict[str(id)].get("base_url", None)

    print(f"[Start] Running SODIUM-Agent on ID {id}")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_root = f"logs/sodium_{id}_{timestamp}"
    os.makedirs(output_root, exist_ok=True)
    os.makedirs(output_root, exist_ok=True)
    sodium_agent(query, schema, primary_key, primary_key_vals, output_root, domain)
    print(f"[Done] Finished find_url on ID {id}")

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
