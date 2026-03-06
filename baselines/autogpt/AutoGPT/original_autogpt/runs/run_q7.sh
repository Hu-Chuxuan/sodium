#!/usr/bin/env bash

index=q7

mkdir -p ./environment/$index

query="What is the highest rated movie directed by Christopher Nolan between 2010 and 2015?"
primary_key_vals=("Inception" "The Dark Knight Rises" "Man of Steel" "Transcendence" "Interstellar")
primary_key="movie_name"
base_url="https://www.imdb.com/"
cols=("Director" "Genres" "Motion Picture Rating (MPA)" "Release Date" "Budget" "Gross profit" "Runtime" "Rating")

# Function to extract cell value from autogpt output
extract_cell_value() {
    local output_file="$1"
    local cell_value=""
    
    # Look for the pattern 36m{'reason': '<cell value>'} in the output file
    if [ -f "$output_file" ]; then
        cell_value=$(grep -o "36m{'reason': '[^']*'}" "$output_file" | head -1 | sed "s/36m{'reason': '//" | sed "s/'}//")
    fi
    
    # If no match found, return None
    if [ -z "$cell_value" ]; then
        echo "None"
    else
        echo "$cell_value"
    fi
}

# Function to process a single row
process_row() {
    local primary_key_val="$1"
    local previous_info=""
    
    echo "Processing row for $primary_key: $primary_key_val"
    
    for col in "${cols[@]}"; do
        task_prompt="You should provide the \"$col\" information for answering the query \"$query\" with $primary_key being \"$primary_key_val\". The data is publicly available at $base_url. Strictly finish with the exact value of $col. YOU HAVE TO PROVIDE AN OUTPUT WITH KNOWN INFORMATION - DO NOT ASK FOR ADDITIONAL INFO. You have previously found the following information: $previous_info"

        primary_key_val_no_space=$(echo $primary_key_val | sed 's/ /_/g' | cut -c1-20)
        col_no_space=$(echo $col | sed 's/ /_/g')
        
        workspace_id="$index/$primary_key_val_no_space/$col_no_space"
        echo "Workspace ID: $workspace_id"
        mkdir -p ./environment/$workspace_id

        echo "Task Prompt: $task_prompt"

        # Write task prompt to output file first
        echo "=== TASK PROMPT ===" > ./environment/$workspace_id/output.txt
        echo "$task_prompt" >> ./environment/$workspace_id/output.txt
        echo "===================" >> ./environment/$workspace_id/output.txt
        echo "" >> ./environment/$workspace_id/output.txt

        # Run autogpt synchronously for this cell
        . autogpt.sh run \
            --ai-task "$task_prompt" \
            --skip-reprompt \
            --workspace-id "$workspace_id" \
            --skip-news \
            --ai-role "You are a seasoned digital assistant that is an expert in searching the web for information related to clinical trials." \
            --continuous \
            --log-level INFO \
            --fast_llm "gpt-5-2025-08-07" --smart_llm "gpt-5-2025-08-07" --openai_cost_budget 100 >> ./environment/$workspace_id/output.txt 2>&1
        
        # Extract cell value from output
        cell_value=$(extract_cell_value "./environment/$workspace_id/output.txt")
        
        # Add to previous_info in the required format
        if [ -z "$previous_info" ]; then
            previous_info="$col: $cell_value"
        else
            previous_info="$previous_info, $col: $cell_value"
        fi
        
        echo "Extracted cell value for $col: $cell_value"
        echo "Updated previous_info: $previous_info"
    done
}

# Process all rows in parallel
for primary_key_val in "${primary_key_vals[@]}"; do
    process_row "$primary_key_val" &
done

# Wait for all background processes to complete
wait
echo "All rows processed"

