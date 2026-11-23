# DevOps notes: Docker, CI/CD, security and quality

## 1. The pipeline (`.github/workflows/ci.yml`)

```
push / pull request
   |
   +--> backend   ruff lint -> 30 tests (real PostgreSQL) -> coverage gate 85% -> pip-audit
   +--> frontend  type-check + production build -> npm audit
                      |
                      v  (both must pass)
                  docker   hadolint -> build images -> start the whole stack -> smoke tests -> Trivy scan
                      |
                      v  (only on push to main)
                  publish  push API and web images to ghcr.io, tagged with the commit SHA and "latest"
```

| Stage | Why it exists |
|---|---|
| ruff | Catches bugs and sloppy code before review |
| Tests + coverage gate | Proves behaviour, and stops coverage from quietly dropping below 85% |
| pip-audit / npm audit | Flags dependencies with known vulnerabilities |
| hadolint | Checks the Dockerfiles against best practice |
| Start the real stack + smoke tests | Proves the *containers* work together, not just the code: health, admin login with a token, 401 without a token, website deep links, security headers, API not running as root |
| Trivy | Scans the built images for known vulnerabilities (HIGH and CRITICAL that have a fix) |
| publish (CD) | Every merge to `main` produces versioned, ready-to-deploy images |

CI uses throwaway random secrets generated during the run, so nothing sensitive is stored in the repository.

## 2. What the pipeline found, and what was changed

| Finding | Where | Fix |
|---|---|---|
| 4 npm vulnerabilities (1 high: vite, 2 moderate: react-router, 1 moderate: esbuild) | `npm audit` | Upgraded vite 5 to 8, plugin-react to 6, react-router-dom 6 to 7. Audit now reports 0. Type-check and build still pass |
| Exceptions raised inside `except` without chaining (B904, 2 places) | `main.py` lines 100 and 332 | `raise ... from None`, so the 401/409 is not buried under an internal error |
| Unused imports (F401, 2) and missing end-of-file newline (W292, 2) | tests, `main.py`, `security.py` | Removed / added |
| ruff B008 on `Depends(...)` (34 hits) | everywhere | False positive: it is FastAPI's normal pattern. Configured in `ruff.toml` instead of changing code |
| Python dependencies | `pip-audit` | No known vulnerabilities (the check stays on as a guard) |
| Coverage | pytest-cov | 92% of the app code; the pipeline fails below 85% |
| 3 operating-system vulnerabilities in the web image (pcre2, tiff, zlib: HIGH/CRITICAL, fixes available) | Trivy | Moved to nginx-unprivileged 1.31-alpine and added `apk upgrade` in the final stage. Trivy now passes |

## 3. Docker hardening: before and after

| Before | After | Benefit |
|---|---|---|
| Container ran as root | Dedicated non-root user (uid 10001) | An attacker who gets into the container has far fewer rights |
| Website container ran the Vite dev server (including the esbuild issue above) | Multi-stage build: Node builds the site, a small unprivileged nginx serves static files. No Node, no source code, no dev server in the final image | Smaller image, much smaller attack surface |
| Passwords and secret key written in `docker-compose.yml` | Required from a git-ignored `.env`; compose refuses to start if they are missing | No secrets in the repository |
| Database port published on the host | No published port; only the API can reach it | Database is not exposed |
| No health checks | Health checks on db, api and web; services start only when their dependency is healthy | No race at startup, and a broken container is visible |
| `COPY . .` | `COPY *.py` plus a `.dockerignore` that excludes tests, `.env`, `.git`, frontend | Smaller images, no secrets or tests inside |
| Unpinned tags | Pinned versions (`python:3.12-slim-bookworm`, `node:22-alpine`, `nginx-unprivileged:1.27-alpine`, `postgres:16-alpine`) | Reproducible builds; Dependabot proposes updates |
| No browser security headers | nginx sends `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, a Content-Security-Policy, and hides its version | Blocks clickjacking, MIME sniffing and unknown script sources |
| Containers could gain privileges | `no-new-privileges` on every service | Blocks privilege escalation |

Dependabot (`.github/dependabot.yml`) opens weekly pull requests for pip, npm, Docker and GitHub Actions updates.

## 4. Running it

```bash
cp .env.example .env     # set your own values
docker compose up --build
```

## 5. CD (continuous delivery)

- On every push to `main`, after all checks pass, the API and web images are published to GitHub Container Registry (`ghcr.io/<owner>/<repo>-api` and `-web`), tagged with the commit SHA and `latest`.
- Deploying the images to a server is out of scope for this project.
- Known limitation: the website image has the API address baked in at build time (`VITE_API_URL`). For several environments it should read it at runtime, or be built per environment.

## 6. Status

- The full pipeline has run on GitHub: lint, tests, coverage, dependency scans, Dockerfile lint, image builds, full-stack smoke tests, the Trivy scan, and publishing the images.
- The first Trivy run failed on real findings in the web image (pcre2, tiff, zlib). They were fixed by moving to a newer base image and applying OS patches.
- Dependabot opens update pull requests. Major version jumps are checked by this pipeline before anything is merged.
- Deployment is intentionally out of scope.

## 7. SAST and DAST (reading notes, not implemented)

- **SAST** reads the source code without running it and flags risky patterns (hard-coded secrets, unsafe queries). Tools: Bandit, Semgrep, CodeQL. It would go right after the lint step.
- **DAST** attacks the *running* application like an outsider and reports weak headers, authentication problems and exposed paths. Tool: OWASP ZAP. It would go in the `docker` job, after the stack is up, targeting `http://localhost:8000`.
