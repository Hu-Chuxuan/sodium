# 🤖 AutoGen

This folder implements the [AutoGen](https://github.com/microsoft/autogen) baseline for SODIUM-Bench.
It uses AutoGen's `MagenticOneGroupChat` with a `MultimodalWebSurfer` agent, with `gpt-5` as the language model.
AutoGen fills each table cell sequentially, one at a time.

## 🛠️ Setup

```bash
pip install -U "autogen-agentchat" "autogen-ext[openai]"
pip install "autogen-ext[web-surfer]"
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
    {pk_val}-{column}.log    # raw agent output per cell
    output.csv               # aggregated output table
```
