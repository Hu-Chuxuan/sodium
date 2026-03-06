#!/usr/bin/env bash

index=q2

mkdir -p ./environment/$index

# Read values from queries.json for key "2"
query="For all intervention reports that have been assigned a highest evidence tier, identify the outcome domain (selecting the alphabetically first if multiple domains share the same tier) corresponding to that tier. For each report, provide its effectiveness rating, grade level, and the percentage of male participants in the study sample?"
primary_key_vals=("723" "722" "719" "714")
primary_key="report_id"
base_url="https://ies.ed.gov/ncee/WWC/"
cols=("Study Title" "Release Year" "Highest Evidence Tier" "# Eligible Studies" "# Meeting Standards" "Highest Evidence Tier Outcome Domain" "Highest Evidence Tier Outcome Effectiveness Rating" "Highest Evidence Tier Outcome Effectiveness Grades" "Sample Composition Percentage - Gender (Male)")

for primary_key_val in ${primary_key_vals[@]}; do
    for col in "${cols[@]}"; do
        task_prompt="
        You should provide the \"$col\" information for answering the query \"$query\" with $primary_key being \"$primary_key_val\".
        The data is publicly available at $base_url.
        Strictly finish with the exact value of $col. YOU HAVE TO PROVIDE AN OUTPUT WITH KNOWN INFORMATION - DO NOT ASK FOR ADDITIONAL INFO.
        "
        
        col_no_space=$(echo $col | sed 's/ /_/g')
        workspace_id="$index/$primary_key_val/$col_no_space"
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