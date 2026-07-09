---
name: aiops-py312
description: "Use when running any Python code, installing Python packages, or executing notebooks in this workspace; always use the conda environment aiops-py312."
---

# aiops-py312 Python Execution Policy

Use the conda environment `aiops-py312` for every Python execution in this workspace.

## Required Behavior

- Always select or configure `aiops-py312` before running Python code.
- Use the conda environment `aiops-py312` for terminal Python commands, notebook kernels, snippet execution, and Python package installs.
- Do not use system Python, `base`, or any other interpreter for Python work in this repo.
- If a tool or workflow would otherwise use a different Python environment, switch it to `aiops-py312` first.
- When running Python from a terminal, prefer `conda activate aiops-py312` in interactive shells or `conda run -n aiops-py312` for one-off commands.

## Applies To

- `python`, `python3`, and direct interpreter calls
- Python notebook cells
- Python package installation and validation commands
- Short ad-hoc scripts used during debugging or testing

## Working Rule

Before any Python-related action, confirm the active environment is `aiops-py312` and proceed only with that environment.