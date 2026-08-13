---
name: index_code_symbols
description: Map all classes, functions, and global variables in a target directory.
---

# Index Code Symbols

This skill enables the Codebase Explorer to build a mental map of the available code entities.

## When to use
- When first encountering a new subsystem or module.
- Before proposing changes, to ensure no naming conflicts.
- To understand inheritance (find all subclasses of `BaseRunner`).

## Step-by-Step Instructions
1. **Target Selection**: Identify the directory (e.g., `src/vision`).
2. **Execution**:
   - Use `grep` or `ast` parsing (via a script) to find definitions.
   - Example Command:
     ```bash
     grep -rE "^class |^def " src/vision
     ```
3. **Analysis**:
   - Note the file path, line number, and signature.
   - Identify dependencies (what does it import?).

## Verification Checklist
- [ ] List of symbols is complete for the requested scope.
- [ ] No syntax errors in the scanned files (if using AST).

## Rules & Constraints
- Read-Only: Do not modify files while indexing.
- Ignore `__pycache__` and hidden files.
