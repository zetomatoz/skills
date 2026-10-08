---
description: Run the bounded stress-observe-tune-evaluate loop across fixed profiles
argument-hint: Ray system, profile suite, objective, SLOs and experiment budget
---

Load the installed inference-optimization skill and its experiment/role references.
User inputs: $ARGUMENTS. Coordinate benchmark, observer, tuner and evaluator roles.
Where supported and authorized, delegate focused work; otherwise execute sequentially.
Use one writer, one load test at a time, private artifacts and fixed profile gates.
Stop on plateau/budget/failure; report the best verified tested configuration,
remaining uncertainty and exact final deployed state. Never run an unbounded loop.
