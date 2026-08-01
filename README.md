# MASON

MASON (Multi-Agent Harness for Service Orchestration and Optimization) is a multi-agent system for cloud-native service orchestration, incident handling, and workflow optimization. The project is designed to reduce tool fragmentation, lower operator cognitive load, and provide a conversational, extensible, and autonomous interface for deployment and ad-hoc operational tasks.

## What MASON Does

- Routes tasks through specialized agents for orchestration, optimization, and reporting.
- Operates against cloud-native infrastructure with Kubernetes-aware tools and event-driven execution.
- Preserves context with Redis-backed memory for task state, observations, results, and reflections.
- Supports user-facing workflows through an IDE-based operational interface.
- Evaluates agent behavior with LLM-as-a-judge scoring and workflow telemetry.

[![Watch demo](docs/demo/Operation Demo.mp4)]

## System Overview

| Layer | Purpose | Key Pieces |
| --- | --- | --- |
| Interface | User interaction and operations | VS Code-based workflow, reports, notifications |
| Orchestration | Task routing and agent execution | Kafka queues, agent manager, personas, actions |
| Memory | Context and result persistence | Redis Agent Memory Server, Redis store |
| Inference | Local model serving | Qwen 3 Instruct 4B via TensorRT-LLM, Qwen 3.5 4B via vLLM |
| Environment | Cloud-native execution target | Kubernetes and related operational tooling |

## Evaluation Highlights

The project docs describe two main task families: deployment workflows and ad-hoc operational tasks. Evaluation used Gemini and GPT judge pipelines across two model setups.

| Task Type | Gemini Eval Setup A | Gemini Eval Setup B | GPT Eval Setup A | GPT Eval Setup B |
| --- | ---: | ---: | ---: | ---: |
| Deployment | 80% | 92% | 72% | 81% |
| Ad-Hoc | 78% | 88% | 72% | 88% |

Selected agent metrics from the GPT evaluation show the tradeoff between quality and operational efficiency:

| Metric | Setup A | Setup B |
| --- | ---: | ---: |
| Tool Accuracy | 0.70 / 0.74 | 0.80 / 0.81 |
| Step Efficiency | 0.71 / 0.69 | 0.79 / 0.82 |
| Plan Adherence | 0.71 / 0.63 | 0.81 / 0.78 |
| Faithfulness | 0.67 / 0.62 | 0.79 / 0.71 |
| Workflow Latency (s) | 31.4986 / 140.1829 | 93.6711 / 217.4672 |
| Function / Tool Calls | 4.88 / 7.88 | 6.72 / 13.60 |
| Generated Token Cost | 297.60 / 994.80 | 1540.16 / 2915.76 |
| TTFT (s) | 4.0248 / 2.8923 | 2.6683 / 1.6507 |

The docs also report that the prompt-optimization loop improved ad-hoc task pass rates from 52% to 76% across three optimization steps.

## Repository Layout

- `agent/` - agent entrypoints, tools, memory, actions, and serving code.
- `management/` - backend service for agent management and orchestration.
- `personas/` - persona-specific prompts and workflows.
- `templates/` - reusable templates for chat, core, memory, and LLM flows.
- `docs/` - capstone summary and poster presentation source material.
- `evaluator/` - batch evaluation, analysis, metrics, and reporting utilities.
- `tests/` - automated tests.

## Running The Stack

The repository is organized around Docker and Docker Compose.

Common service entrypoints from `docker-compose.yml` include:

- `agent-manager` on port `8010`
- `triton-server` on ports `8000`, `8001`, and `8002`
- `main-vllm-server` and `main-tensorrt-llm-server` for model serving profiles
- `deployer-agent` and other persona agents for operational workflows

The compose file also expects local environment files and secrets such as:

- `.env.*` files for model and deployment configuration
- `.secrets/oci-registry`
- `~/.kube/config`
- `~/.google-app-token`

Example commands:

```bash
docker compose --profile serving up --build
docker compose --profile standard up --build
```

Adjust the selected profiles to match the services you want to run.

## Source Documents

- [Capstone Project Executive Summary](docs/AI_299___Capstone_Project_Executive_Summary%20(1).pdf)
- [Poster Presentation Final](docs/Poster%20Presentation%20Final%20(1).pdf)

## Architecture Note

- [System Architecture](docs/system-architecture.md)

## Getting Started

- [Getting Started](docs/getting-started.md)

## Notes

- The project targets cloud-native operations and assumes access to GPU-backed model serving for the local inference stack.
- The docs emphasize conversational task handling, incident diagnosis, deployment workflows, and self-optimization through prompt refinement.
