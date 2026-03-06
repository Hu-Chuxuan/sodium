import pandas as pd
import os
import json
from collections import defaultdict

def result_to_csv(result_dir, gt_path):
    gt = pd.read_csv(gt_path)
    pk_column = gt.columns[0]
    pk_values = gt[pk_column].tolist()

    results = defaultdict(dict)
    columns = set()
    for filename in os.listdir(result_dir):
        if not filename.endswith('.json'):
            continue
        filepath = os.path.join(result_dir, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            continue
        
        # Check if this is the old format (primary_key, column, result)
        # or new format (primary_key: val, col1: val1, col2: val2, ...)
        if 'column' in data and 'result' in data:
            # Old format
            pk = data.get('primary_key')
            col = data.get('column')
            val = data.get('result', 'N/A')
            if pk is not None and col is not None:
                results[str(pk)][str(col)] = val
                columns.add(str(col))
        else:
            # New format: extract primary key and all other fields as columns
            pk = data.get(pk_column)
            if pk is not None:
                for key, value in data.items():
                    if key != pk_column:  # Skip the primary key itself
                        results[str(pk)][str(key)] = value
                        columns.add(str(key))

    columns = sorted(columns)
    df_rows = []
    for pk in pk_values:
        row = [pk]
        for col in columns:
            row.append(results.get(str(pk), {}).get(col, 'N/A'))
        df_rows.append(row)
    df = pd.DataFrame(df_rows, columns=[pk_column] + columns)
    df.to_csv(os.path.join(result_dir, 'output.csv'), index=False)