import os
import json
import argparse
import pandas as pd
import re
from datetime import datetime
import asyncio

from autogen_agentchat.teams import MagenticOneGroupChat
from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_ext.agents.web_surfer import MultimodalWebSurfer
 
AUTOGEN_PROMPT = '''
You are completing a table that answers the following query: "{query}", starting from this base domain: "{base_domain}".
You should provide the "{col}" information with "{primary_key}" being "{primary_key_val}".
Here's the collection of information you already have {given_cols}.
You should strictly wrap the value you found for "{col}" in "\\boxed{{ANSWER HERE}}". For example, "\\boxed{{123}}".
'''

async def run_autogen(query, col, primary_key, pk_val, row, base_domain):
    prompt = AUTOGEN_PROMPT.format(
        query=query,
        col=col,
        primary_key=primary_key,
        primary_key_val=pk_val,
        given_cols=row,
        base_domain=base_domain
    )

    web_surfer_agent = MultimodalWebSurfer(
        name="MultimodalWebSurfer",
        model_client=OpenAIChatCompletionClient(model="gpt-5-2025-08-07"),
    )

    team = MagenticOneGroupChat([web_surfer_agent], model_client=OpenAIChatCompletionClient(model="gpt-5-2025-08-07"), max_turns=3)

    stream = team.run_stream(task=prompt)
    
    # Capture the output instead of just displaying it
    output_lines = []
    async for message in stream:
        if hasattr(message, 'content') and message.content:
            output_lines.append(str(message.content))
        print(message)
    
    await web_surfer_agent.close()
    
    full_output = '\n'.join(output_lines)
    return full_output

async def run_autogen_pipeline(query, schema, primary_key, primary_key_vals, output_folder, base_domain):
    os.makedirs(output_folder, exist_ok=True)

    rows = []

    for pk_val in primary_key_vals:
        row = {primary_key: pk_val}

        for col in schema:
            if col == primary_key:
                continue
            log_file = os.path.join(output_folder, f"{pk_val}-{col}.log")
            content = await run_autogen(query, col, primary_key, pk_val, row, base_domain)

            # --- Parse output ---
            boxed_pattern = r'\\boxed\{([^}]+)\}'
            matches = re.findall(boxed_pattern, content)
    
            if matches:
                value = matches[-1]
            else:
                value = "Not Specified"

            with open(log_file, "a") as f:
                f.write(content)

            row[col] = value

        rows.append(row)

    # --- Save output ---
    pd.DataFrame(rows, columns=schema).to_csv(os.path.join(output_folder, "output.csv"), index=False)

def run_experiment(id):

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_root = f"logs/sodium_{id}_{timestamp}"
    os.makedirs(output_root, exist_ok=True)

    schema = pd.read_csv(f"../../sodium-bench/schema/{id}.csv").columns.tolist()

    with open("../../sodium-bench/queries.json", "r") as f:
        query_dict = json.load(f)

    query = query_dict[str(id)]["query"]
    primary_key = query_dict[str(id)]["primary_key"]
    primary_key_vals = query_dict[str(id)]["primary_key_vals"]
    base_domain = query_dict[str(id)].get("base_url", None)

    print(f"[Start] Running AutoGen on ID {id}")
    asyncio.run(run_autogen_pipeline(
        query, schema, primary_key, primary_key_vals,
        output_root, base_domain
    ))

    print(f"[Done] Finished AutoGen on ID {id}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--id",
        type=int,
        required=True,
        help="Query ID to run (e.g., 1)"
    )
    args = parser.parse_args()
    run_experiment(args.id)
