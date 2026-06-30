# Batch Evaluation
## Execute Batch Evaluation
```
DATE=20260409
TEST_ID=4585b0e1-e7df-4f05-a814-ad8016f55dd5
GOAL_FILE=../agent/personas/deployer/goal.yaml
EVALUATION_PROMPT_FILE=plan_evaluation_prompt.md
AGENT_TOOL_FILES=deployer-tools-20260416.jsonl
GEMINI_API_KEY=api-key python3 batch_evaluator.py  --date ${DATE}  --test-id ${TEST_ID}  --goal-file $GOAL_FILE --agent-tool-files AGENT_TOOL_FILE --evaluation-prompt-file $EVALUATION_PROMPT_FILE --create-cache --submit
```

## Execute OpenAI Batch Evaluation
```
DATE=20260409
TEST_ID=4585b0e1-e7df-4f05-a814-ad8016f55dd5
GOAL_FILE=../agent/personas/deployer/goal.yaml
EVALUATION_PROMPT_FILE=plan_evaluation_prompt.md
AGENT_TOOL_FILES=deployer-tools-20260416.jsonl
OPENAI_API_KEY=api-key python3 openai_batch_evaluator.py --date ${DATE} --test-id ${TEST_ID} --goal-file $GOAL_FILE --agent-tool-files AGENT_TOOL_FILES --evaluation-prompt-file $EVALUATION_PROMPT_FILE --submit --poll --download-results
```

## Monitor Batch Evaluation
```
GEMINI_API_KEY=xx python3 monitor_batch_results.py --download-results
```

## Monitor OpenAI Batch Evaluation
```
OPENAI_API_KEY=xx python3 monitor_openai_batch_results.py --download-results
```

## Aggregation
```
python3 evaluation_score_aggregation.py --batch-dir batch_results/deployer/ --run-mode mock-plan --pattern *.jsonl --persona deployer --output-csv deployer_score.csv 
```

# Inject Evaluations for Prompt Optimization
```
python3 append_batch_evaluations_to_redis.py --persona deployer --batch-dir batch_results/deployer/e2e/ --pattern '*.jsonl' --redis-key-prefix 'workflow:dev:deployer:' --create-missing 
```

## Persisting Workflow Evaluations
```
PERSONA=deployer
PREFIX_KEY='workflow:dev:deployer:'
BATCH_DIR=batch_results/deployer/e2e
python3 append_batch_evaluations_to_redis.py --persona deployer --batch-dir $BATCH_DIR --pattern '*.jsonl' --redis-key-prefix $PREFIX_KEY --create-missing
``