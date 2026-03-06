# 🤖 AutoGPT

This folder implements the [AutoGPT](https://github.com/Significant-Gravitas/AutoGPT) baseline for SODIUM-Bench.
It uses AutoGPT as a subprocess agent, with `gpt-5` as the language model.
AutoGPT fills each table cell sequentially, one at a time.

## 🛠️ Setup

Install AutoGPT using Poetry (requires Python ≤ 3.12):

```bash
cd AutoGPT/original_autogpt
poetry install
```

Install additional dependencies:

```bash
pip install openai pandas
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
    {pk_val}-{column}.log    # raw agent output and cost per cell
    output.csv               # aggregated output table
```
