# PrintReady AI Frontend

Designer-facing Web UI for the AI Print Production OS MVP.

```bash
cp .env.example .env.local
npm ci
npm run dev
```

The production build defaults to `https://ai-print-production-os-api.onrender.com` so a missing hosted environment variable can never silently route a visitor to their own localhost. Set `NEXT_PUBLIC_API_BASE_URL` only when intentionally overriding the API origin, such as local development. The UI supports upload, preset selection, diagnosis, fix confirmation, post-fix validation, download, feedback and immediate file deletion.

Validation:

```bash
npm run build
npm run lint
node --test tests/rendered-html.test.mjs
```

The frontend can be hosted independently, but the full product requires a reachable Python PDF worker/API. Do not present a frontend-only deployment as a functioning print-production service.
