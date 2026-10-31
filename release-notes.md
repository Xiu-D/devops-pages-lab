---
title: Release notes
---

# Release notes

Every deploy of this site goes through the **Gated deploy to Pages** workflow:
`build -> validate -> deploy`. The deploy job only runs when validation passes.

| Commit | Change | Gate | Live site after |
|---|---|---|---|
| `d3f2771` | Added the gated deploy workflow (#1) | passed, deployed | `d3f2771` |
| `8a8277d` | Linked this page before it existed (deliberate failure demo) | **blocked**: `release-notes.html does not exist` | `d3f2771` (unchanged) |
| `e589ef7` | Added this page | **blocked**: validator bug, the page's own canonical URL was checked on the live site (404) | `d3f2771` (unchanged) |
| `8723c5d` | Validator reports failures as annotations | **blocked** (same bug) | `d3f2771` (unchanged) |
| `cb8ff42` | Fixed the validator: self links are checked inside the new build (#2) | passed, deployed | `cb8ff42` |

The deployed commit is always visible at [version.txt](version.txt).

[Back to home](./)
