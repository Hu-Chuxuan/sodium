# 🌐 WebVoyager

This folder implements the [WebVoyager](https://github.com/MinorJerry/WebVoyager) baseline for SODIUM-Bench.
It uses Selenium to drive a Chrome browser, with `gpt-5` as the vision-language model.
WebVoyager fills each table cell sequentially, one at a time.

## 🛠️ Setup

Ensure Google Chrome is installed. On Linux (e.g., CentOS):

```bash
yum install chromium-browser
```

Install Python dependencies:

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
python run_sodiumbench.py --id <query_id>
```

Example:

```bash
python run_sodiumbench.py --id 1
```

## 📁 Output

```
logs/
  sodium_{id}_{timestamp}/
    pk_val-{pk_val}.json     # per-row result with all columns
    raw/                     # screenshots and raw agent traces per cell
    agent.log                # agent execution log
    output.csv               # aggregated output table
```
