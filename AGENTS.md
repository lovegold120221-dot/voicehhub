# AGENTS.md

## MANDATORY: Kokoro TTS Voice Reports

**After EVERY task — no exceptions — you MUST generate a spoken TTS report and auto-play it.** This applies to code changes, bug fixes, file operations, answering questions, reading files, or any response to the user.

```
python3 ~/.opencode/skills/kokoro-tts/tts.py "Your natural, humanlike report text"
```

- Write the report in a conversational, humanlike style (contractions, varied sentences, like a colleague giving a quick update)
- Keep it brief: 1-3 sentences for small tasks, 3-5 for larger ones
- Default voice: `af_heart` (warm, friendly). Use `--voice af_nicole` for technical reports.
- **This is NOT optional. Do it after every single response.**

## Commands

```
npm run dev              # Frontend (Vite) on :3000, binds 0.0.0.0
npm run dev:api          # Backend (Express + tsx) on :4200, binds 0.0.0.0
npm run dev:full         # Both concurrently
npm run build            # Production build via Vite → dist/
npm run lint             # Typecheck only (tsc --noEmit) — NOT ESLint
npm run start            # Production: tsx server/index.ts
npm run clean            # rm -rf dist
npm run docker:whatsapp:build   # Build WhatsApp Docker image
npm run docker:whatsapp:up      # WhatsApp backend in Docker on :4200
npm run docker:whatsapp:down    # Stop WhatsApp Docker stack
npm run smoke:whatsapp          # BROKEN — scripts/smoke-whatsapp-server.mjs is missing
```

No test framework, no test scripts, no pre-commit hooks. One CI workflow: `.github/workflows/android-distribution.yml` builds APK + deploys to Firebase Hosting + Firebase App Distribution (Android TWA).

## Entrypoint & Architecture

```
index.html → src/main.tsx → src/App.tsx
```

Single-package Vite + React 19 + TypeScript. Optional Express backend in `server/`. Firebase Auth (hardcoded config in `src/firebase.ts`), Supabase (Postgres + Storage), Gemini Live API for voice.

`src/App.tsx` (194 lines) is the orchestrator: auth state, theme, user routing (EntryFlow → AuthPage or BeatriceAgent). Business logic is extracted to separate modules.

### Separate sub-projects (not part of npm workflow)

| Directory | Purpose |
|---|---|
| `functions/` | Firebase Cloud Functions (`apiProxy` — proxies `/api/**` to VPS backend). Own `package.json`. |
| `flutter/` | Flutter mobile app. Own `pubspec.yaml`. |
| `orchestrator/` | Python orchestrator + voice bridge (`voice_bridge.py`). |
| `web/` | Standalone EburonHub web app (`web/index.html`). |

## Critical Gotchas

- **`@` path alias maps to root (`.`), NOT `src/`.** `import { X } from '@/src/lib/foo'` is correct; `import { X } from '@/lib/foo'` will fail.
- **`process.env.*` in frontend code is injected by Vite `define`** (non-VITE_ vars like `GEMINI_API_KEY`, `SUPABASE_URL`), not standard `import.meta.env`. VITE_-prefixed vars use `import.meta.env`. See `vite.config.ts:10-17` for the mapping.
- **`npm run lint` is `tsc --noEmit` only.** ESLint exists (`eslint.config.mjs`) but only runs Firebase security rules checks — it is NOT part of the lint script.
- **`npm run smoke:whatsapp` references `scripts/smoke-whatsapp-server.mjs` which does not exist.** The command will fail.
- **Firebase service account JSONs** (`beatrice-os-*.json`) in the repo root are gitignored. Never commit them.
- **`Cross-Origin-Opener-Policy: same-origin-allow-popups`** is set in both Vite dev server (`vite.config.ts:25`) and Express (`server/index.ts:28`). Required for Firebase Auth popup flow. Do not remove.
- **`DISABLE_HMR` env var** disables Vite HMR (used in AI Studio to prevent flickering during agent edits). See `vite.config.ts:29`.
- **Two Supabase clients**: `src/lib/supabase.ts` (frontend, uses Vite-injected `process.env`) and `server/supabase.ts` (backend, uses `dotenv/config` directly). They are separate instances.
- **`functions/src/index.ts` hardcodes the VPS IP** `http://168.231.78.113:4200` as the backend target. If the VPS IP changes, this must be updated.
- **`.firebaserc` says project `beatrice-os`** but the CI workflow deploys to `eburon-ai-beatrice`. These are different Firebase projects.

## Key Source Files

| File | Purpose |
|---|---|
| `src/components/BeatriceAgent.tsx` | Main agent (4960 lines): Gemini Live session, audio pipeline, ~40 tool declarations, settings panel, camera, document generation, memory |
| `src/firebase.ts` | Firebase init + `getAuth` only — hardcoded config for project `beatrice-os` |
| `src/lib/supabase.ts` | Supabase client + `handleDbError()` — every DB op must use this for structured error logging |
| `src/lib/audio.ts` | `AudioStreamer` (PCM16 mono 24kHz TTS playback) and `AudioRecorder` (mic capture) |
| `src/lib/whatsappClient.ts` | Backend API client — auto-detects backend URL from `VITE_BACKEND_URL`, then `VITE_SANDBOX_URL`, then `localStorage` |
| `src/constants.ts` | Shared `LANGUAGES` array (147 entries) — single source of truth |
| `src/index.css` | Single `@import "tailwindcss"` line + full theme system (40+ custom properties, 70+ light-mode overrides) |
| `vite.config.ts` | Path alias `@` → `.`, Tailwind v4 plugin, env injection via `define`, COOP header, HMR toggle |
| `server/index.ts` | Express backend: WhatsApp routes, Belgian tools, sandbox runner, Cerebras browser, web glance, document gen, health |
| `server/whatsapp.ts` | `WhatsAppManager`: Baileys session lifecycle, SSE streaming, auto-sync |
| `server/whatsapp-tools.ts` | Permission-gated WhatsApp tool dispatch |
| `server/supabase.ts` | Server-side Supabase client (uses `dotenv/config`, separate from frontend client) |
| `functions/src/index.ts` | Firebase Cloud Function `apiProxy` — proxies `/api/**` to VPS backend |

## Gemini Live API

- **SDK**: `@google/genai` `^1.29.0` (frontend). Also `@google/generative-ai` `^0.24.1` (server-side sandbox).
- **Model**: `gemini-2.5-flash-native-audio-preview-12-2025` (stored as obfuscated constant `_M` via `String.fromCharCode`).
- **Brand obfuscation**: SDK class name built via `['Goo','gle','Gen','AI'].join('')` to avoid plaintext in bundle.
- ~40 tools declared in `functionDeclarations`. Execution is a switch/case inside the `onmessage` closure.
- `VOICE_PERSONALITY_PROMPT` (~460 lines) in `BeatriceAgent.tsx` defines the entire persona. Do not alter casually.
- Document generation uses a separate non-voice Gemini session (`gemini-2.5-flash`).
- Audio output: PCM16 mono 24kHz, streamed via `AudioStreamer` (decode → queue → schedule → play).
- Permissions (booleans, default `true`) are injected into the system instruction at session start. Changes require reconnect.
- 10 most recent memories from Supabase `memories` table are pre-loaded into the system prompt.

## Firebase + Firestore

| File | Purpose |
|---|---|
| `src/firebase.ts` | Hardcoded Firebase config for `beatrice-os`, exports `auth` only |
| `firestore.rules` | Permissive (`allow read, write: if true`) — not enforced |
| `security_spec.md` | Describes desired state (user isolation, field validation, length limits), but actual rules don't implement it |
| `firebase-blueprint.json` | Defines `User` and `Message` schemas |
| `firebase.json` | Hosting config — rewrites `/api/**` to Cloud Function `apiProxy`, SPA fallback |
| `.firebaserc` | Default project: `beatrice-os` (note: CI deploys to `eburon-ai-beatrice`) |

## Server / Backend

- **Run**: `npm run dev:api` or `npx tsx server/index.ts`
- **Port**: `process.env.PORT || process.env.SANDBOX_PORT || '4200'`
- **Static files**: Serves `dist/` if built — acts as full web server (SPA fallback on `*` routes).
- **WhatsApp**: Baileys exclusively (Go WhatsApp removed). SSE streaming at `GET /api/whatsapp/stream/:userId`.
- **Housekeeping**: Every 30 min evicts stale WhatsApp sessions (`error`/`disconnected` state, not reconnecting).
- **CORS**: Wide open (`origin: '*'`). `Cross-Origin-Opener-Policy: same-origin-allow-popups`.
- `.env.example` documents all env var names (30 lines). Actual values live in `.env` (gitignored). See `README.md` (env section) and `vite.config.ts` (`define` block) for details.

## UI / Styling

- Tailwind CSS v4 via `@tailwindcss/vite` plugin (`@import "tailwindcss"`, no `tailwind.config.*`).
- Animations: `motion/react` (fka framer-motion).
- Icons: `lucide-react`.
- Markdown: `react-markdown`.
- Dark theme (`#050505` bg, `#d0a78b` accent) with light theme support via CSS custom properties.
- Theme persisted in `localStorage` key `beatrice_theme`.
- Document templates in `public/*-template.html` (11 types: contract, invoice, letter, proposal, etc.).

## VPS Deployment

- **URL**: `https://whatsapp.eburon.ai`
- **Process manager**: PM2 (`ecosystem.config.cjs`), manages 3 apps: `voxx-backend` (port 4200), `voix-backend` (port 3076), `api-eburon`
- **Reverse proxy**: Traefik with Let's Encrypt
- **Run**: `pm2 start node_modules/.bin/tsx -- server/index.ts --port=4200 --host=0.0.0.0`
- Hot-swap: `rsync` code to `/opt/voxx-zero/`, rebuild `dist/`, `pm2 restart voxx-backend --update-env`

## Docker

Two Dockerfiles for different purposes:
- `Dockerfile` — Full app (port 10000), uses Chromium for Puppeteer. Used for Render deployment.
- `Dockerfile.whatsapp` — WhatsApp-only backend (port 4200), slim image, no browser. Used via `docker-compose.whatsapp.yml`.

## Other Instruction Files

- `CLAUDE.md` — Claude Code instructions (somewhat stale, references "Voxx-Zero" naming)
- `GEMINI.md` — Gemini-specific overview
- `MEMORY.md` — Project memory: deployment details, VPS IP, Supabase URL, architecture decisions, bug fix log
- `TASK.md` — Historical task log with implementation context
- `WHITEPAPER.md` — Project whitepaper
- `docs/` — Architecture diagrams (Mermaid `.mmd` + SVG)
