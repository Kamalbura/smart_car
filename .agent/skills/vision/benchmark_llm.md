---
name: benchmark_llm
description: Test Large Language Model performance.
---

# Benchmark LLM

Ensures the brain is thinking at speed.

## When to use
- When switching models (e.g., TinyLlama -> Phi-2).
- Diagnosing "slow response" complaints.

## Step-by-Step Instructions
1. **Activate Environment**: `llme`.
2. **Run Benchmark**:
   ```bash
   ./scripts/test_llm_single.sh "Why is the sky blue?"
   ```
3. **Measure**:
   - Time to First Token (TTFT).
   - Tokens Per Second (TPS).

## Verification Checklist
- [ ] TTFT < 3s.
- [ ] TPS > 5 (usable for voice).

## Rules & Constraints
- WARNING: LLMs eat RAM. Ensure other services are idle if on 4GB Pi.
