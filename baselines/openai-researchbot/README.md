# 🔍 OpenAI ResearchBot

This folder implements the [OpenAI ResearchBot](https://github.com/openai/openai-agents-python/tree/main/examples/research_bot) baseline for SODIUM-Bench, adapted from the `examples/research_bot/` example in the `openai-agents-python` repository.
It uses `ResearchManager` to orchestrate planner, search, and writer agents, with `gpt-5` as the language model.
OpenAI ResearchBot fills each table cell sequentially, one at a time.

## 🛠️ Setup

```bash
make sync
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
    {pk_val}-{column}.json   # per-cell result with status and result
    output.csv               # aggregated output table
```
