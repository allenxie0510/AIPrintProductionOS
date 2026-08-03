# PrintReady AI Frontend

Designer-facing Web UI for the AI Print Production OS MVP.

```bash
cp .env.example .env.local
npm ci
npm run dev
```

Set `NEXT_PUBLIC_API_BASE_URL` to the Python MVP API. The UI supports upload, preset selection, diagnosis, fix confirmation, post-fix validation, download, feedback and immediate file deletion.

Validation:

```bash
npm run build
npm run lint
node --test tests/rendered-html.test.mjs
```

The frontend can be hosted independently, but the full product requires a reachable Python PDF worker/API. Do not present a frontend-only deployment as a functioning print-production service.
