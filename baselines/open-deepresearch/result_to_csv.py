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
        pk = data.get('PK')
        col = data.get('column')
        val = data.get('result', 'N/A')
        if pk is not None and col is not None:
            results[str(pk)][str(col)] = val
            columns.add(str(col))

    columns = sorted(columns)
    df_rows = []
    for pk in pk_values:
        row = [pk]
        for col in columns:
            row.append(results.get(str(pk), {}).get(col, 'N/A'))
        df_rows.append(row)
    df = pd.DataFrame(df_rows, columns=[pk_column] + columns)
    df.to_csv(os.path.join(result_dir, 'output.csv'), index=False)