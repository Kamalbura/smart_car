---
name: trace_execution_path
description: Follow the flow of execution from entry point to handler.
---

# Trace Execution Path

This skill allows the Explorer to understand "what happens when X runs".

## When to use
- Debugging logic errors.
- Verifying the sequence of events in a pipeline (e.g., Audio Input -> Wake Word -> STT).

## Step-by-Step Instructions
1. **Identify Entry Point**: e.g., `if __name__ == "__main__":` in `src/vision/vision_runner.py`.
2. **Follow Calls**:
   - Read the main function.
   - Note instantiated classes.
   - Jump to those class definitions and read their `__init__` and `run` methods.
3. **Document Flow**:
   - Create a call graph (textual or diagrammatic).
   - Note asynchronous calls (Threads, Multiprocessing, AsyncIO).

## Verification Checklist
- [ ] Entry point is confirmed.
- [ ] All major branches (if/else) are considered.
- [ ] Async boundaries are identified.

## Rules & Constraints
- Do not guess what a function does by its name; read the code.
- Mark "Magic" (implicit behaviors) clearly.
