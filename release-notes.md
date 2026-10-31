---
title: Release notes
---

# Release notes

Every deploy of this site goes through the **Gated deploy to Pages** workflow:
`build -> validate -> deploy`. The deploy job only runs when validation passes.

| Commit | Change | Gate |
|---|---|---|
| `d3f2771` | Added the gated deploy workflow | passed, deployed |
| `8a8277d` | Linked this page before it existed (deliberate failure demo) | **blocked**: `release-notes.html does not exist` |
| this commit | Added this page, fixing the broken link | passed, deployed |

The deployed commit is always visible at [version.txt](version.txt).

[Back to home](./)
