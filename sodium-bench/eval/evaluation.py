import json
from pathlib import Path
import pandas as pd

from utils.llm import compare as compare_llm
from utils.exact_match import compare as compare_exact_match


def evaluate_id(id, output_csv, queries_path, gt_root, out_root):
    output_csv = Path(output_csv)
    gt_root = Path(gt_root)
    out_dir = Path(out_root) / str(id)
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(queries_path, "r", encoding="utf-8") as f:
        queries = json.load(f)

    if str(id) not in queries:
        raise ValueError(f"id={id} not found in {queries_path}")

    pk = queries[str(id)]["primary_key"]
    gt_path = gt_root / f"{id}.csv"

    if not gt_path.exists():
        raise FileNotFoundError(f"Ground truth not found: {gt_path}")
    if not output_csv.exists():
        raise FileNotFoundError(f"Output CSV not found: {output_csv}")

    df_gt = pd.read_csv(gt_path).set_index(pk)
    df_pred = pd.read_csv(output_csv).set_index(pk)

    common_rows = df_gt.index.intersection(df_pred.index)
    common_cols = df_gt.columns.intersection(df_pred.columns)
    df_gt = df_gt.loc[common_rows, common_cols]
    df_pred = df_pred.loc[common_rows, common_cols]

    llm_match_df = pd.DataFrame(index=df_gt.index, columns=df_gt.columns, dtype="Int64")
    str_match_df = pd.DataFrame(index=df_gt.index, columns=df_gt.columns, dtype="Int64")

    llm_matched = str_matched = total = 0

    with open(out_dir / "llm_eval.log", "w", encoding="utf-8") as log_f:
        for r in df_gt.index:
            for c in df_gt.columns:
                v_gt = df_gt.at[r, c]
                v_pred = df_pred.at[r, c]
                total += 1

                s_ok = 1 if compare_exact_match(v_gt, v_pred) else 0
                str_match_df.at[r, c] = s_ok
                str_matched += s_ok

                ok, text = compare_llm(v_gt, v_pred, pk, r, c)
                ok = 1 if bool(ok) else 0
                llm_match_df.at[r, c] = ok
                llm_matched += ok

                log_f.write(f"[row_pk={r}][col={c}]\n")
                log_f.write(f"gt={v_gt}\n")
                log_f.write(f"pred={v_pred}\n")
                log_f.write(f"matched={ok}\n")
                if text is not None:
                    log_f.write(str(text).rstrip() + "\n")
                log_f.write("\n" + ("-" * 60) + "\n\n")

    str_match_df.to_csv(out_dir / "string_match.csv", index=True)
    llm_match_df.to_csv(out_dir / "llm_match.csv", index=True)

    llm_pct = llm_matched / total if total else 0.0
    str_pct = str_matched / total if total else 0.0

    print(
        f"[id={id}] LLM {llm_matched}/{total} ({llm_pct:.2%}) | "
        f"String {str_matched}/{total} ({str_pct:.2%})"
    )

    return llm_matched, total, llm_pct, str_matched, total, str_pct


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--id", type=int, required=True)
    parser.add_argument("--output_csv", type=str, required=True)
    parser.add_argument("--queries_path", type=str, default="./queries.json")
    parser.add_argument("--gt_root", type=str, default="./gt")
    parser.add_argument("--out_root", type=str, default="./eval_outputs")
    args = parser.parse_args()
    evaluate_id(args.id, args.output_csv, args.queries_path, args.gt_root, args.out_root)
