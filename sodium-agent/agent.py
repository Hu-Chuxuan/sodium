from pathlib import Path
import os
import pandas as pd
from openai import OpenAI

from utils.log import cell_summary, document_func_call
from cache_manager import discover_path
from web_explorer.web_explorer import atp_bfs
from web_explorer.page_explorer import inspect_page

api_key = os.getenv("OPENAI_API_KEY")

def sodium_agent(query, schema, primary_key, primary_key_vals, output_folder, domain):
    os.makedirs(output_folder, exist_ok=True)
    client = OpenAI(api_key=api_key)

    rows = []
    source_rows = []
    source_static_rows = []
    path_rows = []

    for pk_idx, pk_val in enumerate(primary_key_vals):
        row = {primary_key: pk_val}
        source_row = {primary_key: pk_val}
        source_static_row = {primary_key: pk_val}
        path_row = {primary_key: pk_val}

        for col_idx, col in enumerate(schema):
            if col == primary_key:
                continue
            
            log_dir = Path(output_folder) / f"{pk_val}-{col}"
            log_dir.mkdir(parents=True, exist_ok=True)

            # Page Cache
            upper_source = None
            left_source = None

            if pk_idx > 0:
                upper_source = source_rows[pk_idx - 1].get(col)
                upper_source_static = source_static_rows[pk_idx - 1].get(col)
                log_file = log_dir / "cache_manager.jsonl"
                document_func_call(log_file, "upcache", None, None)

                if upper_source_static is not None and upper_source and len(str(upper_source)) > 0:
                    row, next_level_links, proceed, upper_source, path_record_level = inspect_page(upper_source, upper_source_static, log_file, query, primary_key, pk_val, col, row, client)
                    if col in row:
                        print(f"[Cache✓ up] ({pk_val}, {col}) -> using upper value")
                        source_row[col] = upper_source
                        source_static_row[col] = upper_source_static
                        path_row[col] = path_rows[pk_idx - 1].get(col)
                        cell_summary(log_dir, row[col], row, upper_source)
                        continue

            prev_cols = [c for c in schema if c != primary_key]
            if col_idx > 1:  # >1 since index 0 is primary key
                left_col = prev_cols[col_idx - 2]
                left_source = source_row.get(left_col)
                left_source_static = source_static_row.get(left_col)
                log_file = log_dir / "cache_manager.jsonl"
                document_func_call(log_file, "leftcache", None, None)
                if left_source_static is not None and left_source and len(str(left_source)) > 0:
                    row, next_level_links, proceed, left_source, path_record_level = inspect_page(
                        left_source, left_source_static, log_file, query, primary_key, pk_val, col, row, client
                    )
                    if col in row:
                        print(f"[Cache✓ left] ({pk_val}, {col}) -> using left value")
                        source_row[col] = left_source
                        source_static_row[col] = left_source_static
                        path_row[col] = path_row.get(left_col)
                        cell_summary(log_dir, row[col], row, left_source)
                        continue

            upper_primary_key_val = None
            upper_path = None
            left_col = None
            left_path = None
            if pk_idx > 0:
                upper_path = path_rows[pk_idx - 1].get(col)
                upper_primary_key_val = rows[pk_idx - 1].get(primary_key)
            if col_idx > 1:
                left_col = prev_cols[col_idx - 2]
                left_path = path_row.get(left_col)

            # Path Cache
            if upper_primary_key_val is not None or left_col is not None:
                log_file = log_dir / "cache_manager.jsonl"
                explore_ranks = discover_path(query, primary_key, pk_val, col, upper_primary_key_val, col, upper_path, pk_val, left_col, left_path, row, client, log_file)
            else:
                explore_ranks = []

            # Web Explorer
            explore_ranks.append(domain)
            for i, starting_page in enumerate(explore_ranks):
                log_file = log_dir / f"web_explorer_{i}.jsonl"
                row, source, source_static, path = atp_bfs(
                    client, log_file, starting_page, query, primary_key, pk_val, col, row
                )
                if col in row:
                    break

            source_row[col] = source
            source_static_row[col] = source_static
            path_row[col] = path
            if col not in row:
                row[col] = 'Not Specified'
            cell_summary(log_dir, row[col], row, source)

        rows.append(row)
        source_rows.append(source_row)
        source_static_rows.append(source_static_row)
        path_rows.append(path_row)

    pd.DataFrame(rows, columns=schema).to_csv(os.path.join(output_folder, "output.csv"), index=False)
    pd.DataFrame(source_rows, columns=schema).to_csv(os.path.join(output_folder, "sources.csv"), index=False)