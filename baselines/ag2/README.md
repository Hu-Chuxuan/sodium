# 🤖 AG2

This folder implements the [AG2](https://github.com/ag2ai/ag2) baseline for SODIUM-Bench.
It uses AG2's `WebSurferAgent` with `browser_use`, with `gpt-5` as the language model.
AG2 fills each table cell sequentially, one at a time.

## 🛠️ Setup

```bash
uv venv
uv pip install -r requirements.txt
```

Set your OpenAI API key:

```bash
export OPENAI_API_KEY=your_key_here
```

## 🚀 Run

```bash
python run_sodium_bench.py --id <query_id>
```

Example:

```bash
python run_sodium_bench.py --id 1
```

## 📁 Output

```
logs/
  sodium_{id}_{timestamp}/
    {pk_val}-{column}.json   # per-cell result with status, result, explanation
    output.csv               # aggregated output table
```
