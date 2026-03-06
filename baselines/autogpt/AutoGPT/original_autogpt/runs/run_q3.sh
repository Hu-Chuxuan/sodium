#!/usr/bin/env bash

index=q3

mkdir -p ./environment/$index

query="For all STEM professional job related findings, what are their outcome effectiveness and findings?"
primary_key_vals=("Three essays on immigration policy and labor market outcomes in the U.S." "Encouraging evidence on a sector-focused advancement strategy" "The impact of career mentoring and psychosocial mentoring on affective organizational commitment, job involvement, and turnover intention" "Exploring women engineering faculty's mentoring networks" "When trying hard isn't natural: Women's belonging with and motivation for male-dominated STEM fields as a function of effort expenditure concerns" "Transformative graduate education programs: An analysis of impact on STEM and non-STEM Ph.D. completion")
primary_key="Title"
base_url="https://clear.dol.gov/"
cols=("Citation" "Topic_area" "Study_type" "Study_evidence_rating" "Outcome_effectiveness" "Findings" "Intervention_program" "Topics" "Target_population" "Firm_characteristics" "Geographic_setting" "Original_publication_date" "Original_publication_link" "Review Protocol")

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