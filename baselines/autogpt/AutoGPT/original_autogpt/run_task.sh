#!/usr/bin/env bash
index=$1

mkdir ./environment/$index

query="What are the changes in blood glucose levels reported across all clinical trials of GLP-1-based medications for Type 2 Diabetes conducted in the past year (2024-09-15 to 2025-09-15)?"
primary_key="National Clinical Trial ID"
primary_key_val="NCT05706506"
col="Sample Size"
previous_info='''
Drug Name: "Tirzepatide"
Sponsor: "Eli Lilly and Company"
Trial Phase: "Phase 4"
Year Published / Completed: "2024"
'''

task_prompt="
You should provide the \"$col\" information for answering the query \"$query\" with $primary_key being \"$primary_key_val\".
Do not say that the study results are not publicly available. It is confirmed to be publicly available.
Strictly finish with the exact value of $col. YOU HAVE TO PROVIDE AN OUTPUT WITH KNOWN INFORMATION - DONOT ASK FOR ADDITIONAL INFO.
You have previously found the following information: $previous_info.
"
  
echo "Task Prompt:"
echo "$task_prompt"

. autogpt.sh run \
    --ai-task "$task_prompt" \
    --skip-reprompt \
    --workspace-id "$index" \
    --skip-news \
    --ai-role "You are a seasoned digital assistant that is an expert in searching the web for data." \
    --continuous \
    --log-level INFO \
    --fast_llm "gpt-5-2025-08-07" --smart_llm "gpt-5-2025-08-07" --openai_cost_budget 100 2>&1 | tee ./environment/$index/output.txt
