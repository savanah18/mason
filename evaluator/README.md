# Batch Evaluation
## Execute Batch Evaluation
```
DATE=20260409
TEST_ID=4585b0e1-e7df-4f05-a814-ad8016f55dd5
GOAL_FILE=../agent/personas/deployer/goal.yaml
EVALUATION_PROMPT_FILE=plan_evaluation_prompt.md
GEMINI_API_KEY=api-key python3 batch_evaluator.py  --date ${DATE}  --test-id ${TED_ID}  --goal-file $GOAL_FILE --evaluation-prompt-file $EVALUATION_PROMPT_FILE --create-cache --submit
```

## Monitor Batch Evaluation
```
GEMINI_API_KEY=xx python3 monitor_batch_results.py --download-results
```

## Aggregation
```
python3 evaluation_score_aggregation.py --batch-dir batch_results/deployer/ --pattern *.jsonl --persona deployer --output-csv deployer_score.csv
```