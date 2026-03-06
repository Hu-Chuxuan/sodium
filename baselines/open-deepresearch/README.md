# 🔬 Open Deep Research

This folder implements the [Open Deep Research](https://github.com/btahir/open-deep-research) baseline for SODIUM-Bench.
It uses Selenium to drive the Open Deep Research Next.js app (running locally on `localhost:3000`), with `gpt-5` as the language model.
Open Deep Research fills each table cell sequentially, one at a time.

## 🛠️ Setup

Start the Next.js app in one terminal:

```bash
cd open-deep-research
npm install
npm run dev
```

Install Python dependencies in another terminal:

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
    {pk_val}-{column}.json   # per-cell result with status and result
    log.json                 # query and status log for all cells
    output.csv               # aggregated output table
```
