---
name: compile_technical_diagrams
description: Generate visual representations of the system.
---

# Compile Technical Diagrams

A picture is worth 1000 lines of code.

## When to use
- When explaining complex flows (e.g., Audio -> STT -> LLM -> TTS).
- Checking state machine logic.

## Step-by-Step Instructions
1. **Select Tool**: Mermaid.js (preferred for markdown) or Graphviz.
2. **Scan Logic**: Use `trace_execution_path` output.
3. **Generate Markdown**:
   - Wrap in ` mermaid` blocks.
   - Example:
     ```mermaid
     graph TD
     A[Mic] --> B[STT]
     B --> C[LLM]
     C --> D[TTS]
     ```
4. **Preview**: Render in a viewer to ensure syntax validity.

## Verification Checklist
- [ ] Diagram renders without syntax errors.
- [ ] Logic matches the code (no hallucinated connections).

## Rules & Constraints
- Keep diagrams simple; break large ones into sub-system views.
