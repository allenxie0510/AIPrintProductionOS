# Online demo deployment

- Status: Ready for deployment validation
- Target: one-user Alpha workflow evaluation
- Region: Singapore
- Backend: Render Docker web service
- Frontend: private OpenAI Sites deployment

## What this deployment proves

The demo exercises upload → analysis → rule report → confirmed repair → re-analysis → qpdf syntax validation → download → immediate deletion from a real browser over HTTPS.

It does not prove production scalability, independent PDF/X conformance, printer acceptance, malware isolation or durable job execution.

## License mode

This deployment uses the AGPL releases of PyMuPDF/MuPDF and Ghostscript. The application is therefore published under `AGPL-3.0-only`, retains a visible source link, and exposes the complete corresponding application source in the public GitHub repository.

Before changing the repository back to private or offering a proprietary service, obtain the applicable commercial licenses or replace the engines and record a new ADR. Legal counsel should review compliance before commercial launch.

## Backend deployment

1. Merge the validated implementation branch to the default branch.
2. In Render, choose **New → Blueprint** and connect `allenxie0510/AIPrintProductionOS`.
3. Render reads `render.yaml` and creates `ai-print-production-os-api` from the root `Dockerfile`.
4. Wait for `/health` to pass and record the generated `https://…onrender.com` URL.
5. Verify `GET /health`, `GET /v1/presets`, then run the scripted browser/API acceptance flow.

The free service has an ephemeral filesystem. A restart, sleep recovery or redeploy can remove the SQLite database and all artifacts before their nominal 24-hour TTL. This is acceptable only for evaluation.

### Demo engine safety limits

The Blueprint configures each PDF engine subprocess with:

- 320 MiB virtual-memory limit;
- 90 seconds CPU time;
- 120 seconds wall time;
- 20 pages, 100,000 PDF objects and 50 million pixels per image.

The API process does not import or execute the PDF parser directly. A limit breach marks the job `failed` with a stable resource error while the API remains healthy. These subprocess boundaries reduce blast radius on the free instance; they are not a replacement for a durable queue and isolated production worker container.

If the browser reports a CORS error together with `ERR_HTTP2_PROTOCOL_ERROR`, inspect Render Events first. A platform 502/instance restart does not contain FastAPI CORS headers and can therefore look like a CORS configuration problem. Verify `/health` and the OPTIONS preflight separately before changing CORS settings.

## Frontend deployment

1. The checked-in production fallback must be the exact Render HTTPS origin. `NEXT_PUBLIC_API_BASE_URL` may override it for local or alternate environments; the production bundle test must reject `localhost` and `127.0.0.1` API targets.
2. Run `npm ci`, `npm run lint`, and `npm test` in `frontend/`.
3. Package the validated `frontend/dist` artifact and deploy it privately with Sites.
4. Open the private URL and execute the complete workflow with a non-sensitive PDF.
5. Replace backend CORS `*` with the exact frontend origin before any broader Alpha access.

## Production migration gates

- Replace FastAPI in-process background work with a durable queue and isolated worker.
- Replace SQLite/local artifacts with durable metadata storage and lifecycle-managed object storage.
- Add malware scanning, decompression/resource limits, rate limits and authenticated users.
- Use print-provider-approved ICC profiles and presets.
- Integrate an independent PDF/X validator; until then every export remains a candidate.
- Add deletion audit and recovery testing before storing customer artwork.
