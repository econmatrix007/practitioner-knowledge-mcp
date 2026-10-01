---
name: assumption-audit
title: Assumption Audit
category: stress-test
use_when: When a forecast, model, or recommendation rests on conditions nobody has written down
---
## Purpose

Every plan depends on conditions that must hold for it to work. Most of those
conditions stay implicit. An assumption audit makes them explicit, ranks them by
how much the conclusion depends on them, and assigns a way to test the weakest.

## Steps

1. Write the conclusion in one sentence.
2. List every condition that must be true for the conclusion to follow. Include
   conditions about markets, behavior, law, timing, and funding.
3. For each assumption, ask two questions:
   - How confident are we that it holds? (high, medium, low)
   - If it fails, does the conclusion change? (not at all, somewhat, completely)
4. Plot the assumptions on a two-by-two grid of confidence against impact.
5. Focus on low-confidence, high-impact assumptions. For each, name the cheapest
   evidence that would confirm or refute it, and who will gather it.
6. Add the surviving assumptions to the final document so readers can see them.

## Common failure modes

- Listing only the assumptions that are comfortable to question.
- Treating the base case as certain and the assumptions as decoration.
- Testing assumptions that are easy to check rather than those that matter.
- Dropping the assumption list from the final document, so later readers cannot
  tell when conditions have changed.

## Further reading

- Planning literature on assumption-based planning and "load-bearing" assumptions.
- Intelligence analysis guides on key assumptions checks.
