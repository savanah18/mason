---
name: clean-code-principles-and-best-practices
description: "Use when improving code quality, refactoring, reviewing style, or applying clean-code principles in this workspace; focus on readability, maintainability, and small safe changes."
---

# Clean Code Principles and Best Practices

Use this skill when the goal is to improve code quality without changing intended behavior.

## Core Principles

- Prefer small, focused functions and modules.
- Use descriptive names for files, functions, classes, and variables.
- Keep one responsibility per unit of code.
- Avoid duplication when a shared abstraction stays simple.
- Make control flow explicit and easy to follow.
- Handle errors with clear messages and predictable behavior.
- Keep comments rare and only use them for non-obvious intent.

## Best Practices

- Preserve public interfaces unless a change is intentional and documented.
- Refactor in small steps and validate each step.
- Keep changes local to the affected slice of code.
- Prefer straightforward code over clever abstractions.
- Remove dead code, unused imports, and stale paths.
- Align docs, tests, and implementation when behavior changes.

## Review Checklist

- Is the code easy to read on first pass?
- Does each function do one thing?
- Are names precise and consistent with the domain?
- Are error cases handled explicitly?
- Is the change the smallest viable improvement?
- Are docs or tests needed to keep behavior reproducible?

## Apply This When

- You are cleaning up existing code.
- You are reviewing a patch for maintainability.
- You want to make a change safer, clearer, or easier to extend.
