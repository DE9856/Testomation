# Benchmark target app

[Conduit](conduit/UPSTREAM.md) (RealWorld: React + Express + Sequelize + Postgres), vendored so
seeded bugs can be planted in it. One container serves the API and the built frontend on
**http://localhost:4100** (`TESTO_TARGET_URL`). The frontend uses **hash routes**: `/#/login`,
`/#/register`, `/#/editor`, `/#/settings`, `/#/profile/<name>`, `/#/article/<slug>`.

```bash
bench/app/conduit.sh up      # build, start, seed once, snapshot template `conduit_seed`
bench/app/conduit.sh reset   # restore seeded state (template DB copy, ~1s) — before every run
bench/app/conduit.sh down    # stop (add -v to drop data)
```

## Seed data (`seed.mjs`)

| Users (password) | Content |
|---|---|
| alice (`alice-pass-1`), bob, carol, dave (`<name>-pass-1`) | 12 articles (3 each, 2 tags each), 1 comment per article, 4 favorites; alice follows bob and carol |

Emails are `<name>@conduit.test`. Tests that change data should create their own synthetic
user via `$faker` (D22); the seeded users are for read-only flows and login.
