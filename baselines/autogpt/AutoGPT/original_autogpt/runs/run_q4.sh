#!/usr/bin/env bash

index=q4

mkdir -p ./environment/$index

query="What is the dollars, impressions, and industry for the top 3 national and local TV parent companies?"
primary_key_vals=("ABBVIE INC" "PROCTER & GAMBLE CO" "PROGRESSIVE CORP" "GENERAL MOTORS CO" "TOYOTA MOTOR CORP" "FORD MOTOR CO")
primary_key="PARENT_COMPANY"
base_url="https://www.nielsen.com/"
cols=("TV TYPE" "RANK" "DOLLARS (MM)" "IMPRESSIONS (B)" "INDUSTRY")

for primary_key_val in "${primary_key_vals[@]}"; do
    for col in "${cols[@]}"; do
        task_prompt="
        You should provide the \"$col\" information for answering the query \"$query\" with $primary_key being \"$primary_key_val\".
        The data is publicly available at $base_url.
        Strictly finish with the exact value of $col. YOU HAVE TO PROVIDE AN OUTPUT WITH KNOWN INFORMATION - DO NOT ASK FOR ADDITIONAL INFO.
        "

        primary_key_val_no_space=$(echo $primary_key_val | sed 's/ /_/g' | cut -c1-20)
        col_no_space=$(echo $col | sed 's/ /_/g')
        
        workspace_id="$index/$primary_key_val_no_space/$col_no_space"
        echo "Workspace ID:"
        echo "$workspace_id"
        mkdir -p ./environment/$workspace_id

        echo "Task Prompt:"
        echo "$task_prompt"

        . autogpt.sh run \
            --ai-task "$task_prompt" \
            --skip-reprompt \
            --workspace-id "$workspace_id" \
            --skip-news \
            --ai-role "You are a seasoned digital assistant that is an expert in searching the web for information related to clinical trials." \
            --continuous \
            --log-level INFO \
            --fast_llm "gpt-5-2025-08-07" --smart_llm "gpt-5-2025-08-07" --openai_cost_budget 100 2>&1 | tee ./environment/$workspace_id/output.txt &
    done
done