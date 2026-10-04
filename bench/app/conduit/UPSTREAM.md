# Upstream

Vendored from https://github.com/TonyMckes/conduit-realworld-example-app (MIT, see LICENSE)
at commit `5e127d8569b300e0a21dc2c20ea680da4967b1aa`, without `.git` and `node_modules`.

This copy is Testomation's benchmark target. Seeded bugs will be planted here behind toggles
(docs/EVALUATION.md), so it intentionally diverges from upstream.

## Patches (search for `[testomation patch]`)

| File | Change | Why |
|---|---|---|
| `backend/index.js` | SPA fallback: non-`/api` GETs serve `frontend/dist/index.html` in production | Upstream returns JSON 404 for non-API paths. **Turned out unnecessary:** the frontend uses hash routing (`/#/login`), so client routes never reach the server. Harmless; kept so a mistyped `/login` shows the app instead of JSON |
| `backend/controllers/articles.js` | `distinct: true` on both `findAndCountAll` calls | Upstream counted article×tag join rows: 12 articles reported as 24, so pagination showed an empty extra page. The clean benchmark app must be clean. Good candidate to re-plant as a seeded "pagination" bug |

## Known upstream quirks (not patched)

- `backend/seeders/*` insert plaintext passwords, but login compares bcrypt hashes, so seeded
  users can't log in. Testomation seeds through the API instead (`bench/app/seed.mjs`).
- Tables are created by `sequelize.sync({ alter: true })` on backend start; migrations are unused.
