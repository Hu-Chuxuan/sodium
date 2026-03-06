from openai import OpenAI

import re
import os

api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key)

PROMPT_TEMPLATE = """
Your task is to decide if the following values are equivalent for expressing column "{col}" for the row where "{primary_key}" = "{primary_key_val}":

valA = {valA}
valB = {valB}

You should only care about their semantic meaning and disregard format differences,
including but not limited to:
- 0.1 vs 10%
- 1,000 vs 1000
- true vs yes
- abbreviations vs full expressions
(e.g., avg vs average, US vs United States)
- full name vs last/first name, as long as it indicates the same person

Output format (STRICT):
First line: reasoning (free text)
Second line: exactly one integer: 1 (matched) or 0 (unmatched)
"""

def compare(valA, valB, primary_key, primary_key_val, col, model="gpt-4o"):
    prompt = PROMPT_TEMPLATE.format(valA=valA, valB=valB, primary_key=primary_key, primary_key_val=primary_key_val, col=col)

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a careful semantic comparison assistant."},
            {"role": "user", "content": prompt},
        ]
    )

    text = resp.choices[0].message.content.strip()
    print("content: ", text)

    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if len(lines) < 2:
        return 0, text

    reasoning = lines[0]

    # find last standalone 0 or 1
    match = re.search(r"\b([01])\b", lines[-1])
    if not match:
        return 0, text

    matched = int(match.group(1))
    return matched, text