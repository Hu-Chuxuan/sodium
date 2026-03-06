@echo off
FOR /F "usebackq tokens=1,* delims==" %%A IN (`findstr /V "^#" .env`) DO set "%%A=%%B"
call .venv\Scripts\activate
call uv pip install -r requirements.txt

python -u run.py ^
    --test_file data/input/queries.json ^
    --api_key "%OPENAI_API_KEY%" ^
    --headless ^
    --model_type "openai" ^
    --api_model "gpt-5" ^
    --max_iter 3 ^
    --max_workers 10 ^
    --max_attached_imgs 3 ^
    --temperature 1 ^
    --fix_box_color ^
    --output_dir results/gpt5_final ^
    --seed 42 > test_tasks.log 2>&1