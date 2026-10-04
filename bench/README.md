# Benchmark

Seeded-bug benchmark (docs/EVALUATION.md). Planned layout, built in phase 0 / design step 3:

```
bench/
├── app/            # target app: Conduit + seed + reset (see app/README.md)
├── bugs/<id>.yaml  # id, category, toggle, expected report, held_out
├── reference/      # hand-written reference spec suite (filters mutants)
├── replay/<id>/    # recorded evidence + result JSON + expected label
└── results/        # scores, 3 runs each, mean and min–max
```
