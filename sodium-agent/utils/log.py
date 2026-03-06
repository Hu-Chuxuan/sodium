import json
from pathlib import Path
from utils.constant import COST_DICT

def document_func_call(
    log_file,
    function_name,
    response,
    input_info,
    additional_info=None,
):
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    usage = getattr(response, "usage", None)
    input_tokens = getattr(usage, "input_tokens", None) if usage else None
    output_tokens = getattr(usage, "output_tokens", None) if usage else None

    cost = None
    if input_tokens is not None and output_tokens is not None:
        cost = (
            input_tokens * COST_DICT["gpt-5"]["cost_per_input_token"]
            + output_tokens * COST_DICT["gpt-5"]["cost_per_output_token"]
        )

    record = {
        "name": function_name,
        "input": input_info,
        "output": getattr(response, "output_text", None),
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        } if usage else None,
        "cost": cost,
        "additional_info": additional_info,
    }

    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

def cell_summary(log_dir, value, row, source, summary_name="summary.json"):
    log_dir = Path(log_dir)
    total_cost = 0.0

    for jsonl_file in log_dir.glob("*.jsonl"):
        with jsonl_file.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except Exception:
                    continue

                cost = record.get("cost")
                if isinstance(cost, (int, float)):
                    total_cost += cost

    summary_path = log_dir / summary_name
    summary_path.write_text(
        json.dumps({"cost": total_cost, "value": value, "row": row, "source": source}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )