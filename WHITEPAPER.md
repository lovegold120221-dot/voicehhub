# Beatrice — EburonHub Voice Intelligence Platform

## Whitepaper v1.0

---

## Executive Summary

Beatrice is a premium, authenticated voice intelligence agent built by Eburon AI. It provides real-time, bidirectional voice conversation powered by Google's Gemini Live API, deeply integrated with the user's Google Workspace (Gmail, Calendar, Drive, Tasks, YouTube, Contacts), WhatsApp messaging, document generation, a persistent memory system, Belgian administrative tools, and a browser automation sandbox. The platform is designed as a single-page React application with a companion Express backend, deployed on Vercel and Render respectively.

Beatrice is not a chatbot. It is a voice-native executive assistant that speaks, listens, reads your email, manages your calendar, sends your WhatsApp messages, drafts your documents, remembers your preferences, and navigates Belgian bureaucracy — all through natural spoken conversation.

---

## System Architecture

### High-Level Topology

```
┌─────────────────────────────────────────────────────────┐
│                    Client (Browser)                      │
│  ┌───────────────────────────────────────────────────┐  │
│  │              React 19 SPA (Vite)                   │  │
│  │  ┌─────────┐  ┌──────────┐  ┌──────────────────┐  │  │
│  │  │ Auth    │  │ Voice    │  │ Tool Execution   │  │  │
│  │  │ (FB)    │  │ Pipeline │  │ (30+ tools)      │  │  │
│  │  └─────────┘  └──────────┘  └──────────────────┘  │  │
│  │  ┌──────────────────────────────────────────────┐  │  │
│  │  │        Gemini Live API Session                │  │  │
│  │  │   (gemini-2.5-flash-native-audio-preview)     │  │  │
│  │  └──────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────┘  │
│                         │                                │
│  ┌──────────────────────┼────────────────────────────┐  │
│  │   Local Storage      │        IndexedDB           │  │
│  │   (settings, tokens) │   (workspace outputs)      │  │
│  └──────────────────────┴────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
          │                    │                    │
          ▼                    ▼                    ▼
   ┌──────────┐     ┌──────────────┐      ┌──────────────┐
   │ Firebase │     │   Supabase   │      │   Express    │
   │   Auth   │     │  (messages,  │      │   Backend    │
   │          │     │   settings,  │      │   :4200      │
   │          │     │   memories)  │      │              │
   └──────────┘     └──────────────┘      └──────┬───────┘
                                          ┌──────┼──────┐
                                          ▼      ▼      ▼
                                    ┌────────┐┌──────┐┌────────┐
                                    │WhatsApp││Sand- ││Belgian │
                                    │(Baileys││box   ││Tools   │
                                    │+ Cloud)││      ││        │
                                    └────────┘└──────┘└────────┘
```

### Technology Stack

| Layer | Technology |
|---|---|
| Frontend Framework | React 19 with TypeScript |
| Build Tool | Vite 6 |
| Styling | Tailwind CSS v4 |
| Animation | Motion (formerly Framer Motion) |
| Icons | Lucide React |
| Markdown | react-markdown |
| AI SDK | `@google/genai` v1.29 |
| Voice Model | `gemini-2.5-flash-native-audio-preview-09-2025` |
| Document Model | `gemini-2.5-flash` (non-streaming) |
| Authentication | Firebase Auth (email/password + Google OAuth) |
| Database | Supabase (PostgreSQL) |
| Real-time Sync | Supabase Realtime Channels |
| Local Storage | IndexedDB (Dexie), OPFS, localStorage |
| Backend Runtime | Node.js + Express + TypeScript |
| WhatsApp | Baileys v7 (linked device) + Cloud API |
| PDF Generation | jsPDF + html2canvas |
| Browser Automation | Puppeteer + Cerebras |

---

## Core Capabilities

### 1. Real-Time Voice Interaction

Beatrice uses Google's Gemini Live API with native audio modalities for true bidirectional voice conversation. The audio pipeline operates as follows:

**Capture → Encode → Stream → Model → Decode → Playback**

- **AudioRecorder**: Captures microphone input via `getUserMedia`, downsamples from the browser's native sample rate to 16kHz mono, converts Float32 → PCM16 Int16, base64-encodes, and streams to the Live session via `sendRealtimeInput({ media })`.
- **AudioStreamer**: Receives PCM16 base64 chunks from the model, decodes to Float32, schedules playback through the Web Audio API with precise timing to avoid gaps or overlaps, and drives a real-time frequency analyzer for the orb visualization.
- **Voice Selection**: Five prebuilt voices available (Aoede, Fenrir, Kore, Puck, Charon), selectable in settings and applied at session start via `speechConfig.voiceConfig.prebuiltVoiceConfig.voiceName`.
- **Session Resilience**: Conversation buffer preserves the last N exchanges. On disconnect, exponential backoff reconnection (1s base, up to 5 attempts) restores the session with full context.

### 2. Google Workspace Integration

Beatrice connects to the user's Google account via OAuth 2.0 with offline access (refresh tokens). The following scopes are requested:

- `gmail` — read, send, draft, trash, modify labels
- `calendar` + `calendar.events` — list, create, update, delete events
- `tasks` — list, create, update, delete tasks
- `drive` + `drive.file` + `drive.metadata.readonly` + `drive.appdata` — list, search, read, create, update, delete files
- `youtube` + `youtube.force-ssl` — search videos
- `contacts` — list, create, update, delete contacts
- `spreadsheets` + `documents` — read/write Google Docs/Sheets
- `userinfo.profile` — display name and avatar

All Google API calls are proxied through a custom `gFetch` wrapper that handles automatic token refresh via `POST https://oauth2.googleapis.com/token` when 401/403 responses are detected. The refresh token is persisted in localStorage and synced to Supabase.

**Available Google Tools (declared as Gemini function declarations):**

| Tool | Description |
|---|---|
| `list_gmail_messages` | Search/read inbox with Gmail query syntax |
| `get_gmail_message` | Fetch full message by ID |
| `send_gmail_message` | Compose and send email |
| `create_gmail_draft` | Save draft |
| `trash_gmail_message` | Move to trash |
| `delete_gmail_message` | Permanently delete |
| `modify_gmail_message` | Add/remove labels |
| `list_calendar_events` | Upcoming events |
| `create_calendar_event` | Schedule with attendees, location, reminders |
| `update_calendar_event` | Modify existing event |
| `delete_calendar_event` | Remove event |
| `list_google_tasks` | Pending tasks |
| `create_google_task` | New task with notes |
| `update_google_task` | Modify or complete |
| `delete_google_task` | Remove task |
| `list_drive_files` | Browse Drive |
| `search_drive_files` | Query by name/type |
| `get_drive_file` | Fetch metadata |
| `create_drive_file` | Upload file or create folder |
| `update_drive_file_content` | Modify file contents |
| `delete_drive_file` | Remove file |
| `list_google_contacts` | Browse contacts |
| `create_google_contact` | Add contact |
| `update_google_contact` | Modify contact |
| `delete_google_contact` | Remove contact |
| `search_youtube` | Search videos |
| `get_user_location` | Browser geolocation |

### 3. WhatsApp Integration

The WhatsApp integration is the most architecturally sophisticated subsystem. It operates through a dual-provider model:

**Provider 1: Baileys (Linked Device)**
- Runs on the Express backend as a persistent WebSocket connection
- Uses `@whiskeysockets/baileys` v7 with multi-file auth state
- Supports QR code pairing and phone number pairing code
- Maintains up to 50,000 recent messages in memory with periodic persistence
- Desktop-style full history sync via `WA_SYNC_FULL_HISTORY`
- Session lifecycle: init → qr_ready → paired → (disconnected → reconnecting)

**Provider 2: Cloud API (Business)**
- Configured via admin portal with `phoneNumberId`, `accessToken`, `businessAccountId`
- Supports webhook configuration for incoming messages
- Used as fallback/alternative to Baileys

**Permission System:**
Ten boolean toggles gate all WhatsApp operations, injected into the system instruction at session start:

| Permission | Controls |
|---|---|
| `send_messages` | Outbound 1:1 messages |
| `read_chats` | Chat list and previews |
| `access_contacts` | Contact list |
| `manage_contacts` | Contact CRUD |
| `access_groups` | Group list |
| `send_group_messages` | Outbound group messages |
| `read_group_chats` | Group message history |
| `view_message_history` | Full chat history |
| `make_calls` | Call history |
| `make_whatsapp_calls` | Initiate calls |

**Delegated Send Rule:** Outbound WhatsApp tools require `requireUserApproval=true`, `approvedByUser=true`, and `mode="delegated_send"`. Beatrice must preview the message and wait for explicit approval before sending.

**Available WhatsApp Tools:**

| Tool | Description |
|---|---|
| `read_whatsapp_chats` | Recent conversations with unread counts |
| `get_whatsapp_contacts` | Contact list with names and numbers |
| `get_whatsapp_groups` | Group memberships |
| `get_whatsapp_message_history` | Full history for a chat (up to 2,000 messages) |
| `get_whatsapp_calls` | Call log |
| `send_whatsapp_message` | Send 1:1 text |
| `send_whatsapp_group_message` | Send group text |
| `send_whatsapp_text` | Send with auto contact resolution |
| `send_whatsapp_contact_card` | Share a contact |
| `resolve_contact` | Fuzzy name/alias → JID resolution |
| `request_whatsapp_send` | Preview confirmation UI |

### 4. Document Generation

Beatrice generates production-quality documents using a separate non-voice Gemini session (`gemini-2.5-flash`, non-streaming). The system supports 11 document templates:

| Template | Use Case |
|---|---|
| Contract | Executive employment agreement with signature canvas |
| Invoice | Line items, quantity, price, tax auto-calculation |
| Letter | Formal business letter with date/recipient/signature |
| Proposal | Executive summary, scope, pricing, timeline |
| Minutes | Meeting minutes with agenda, decisions, action items |
| Memo | Internal memorandum with To/From/Date/Subject |
| Purchase Order | Supplier info, line items, VAT, delivery terms |
| Receipt | Payment receipt with paid-in-full confirmation |
| Resignation | Formal resignation letter |
| NDA | Non-disclosure agreement |
| Certificate | Achievement or completion certificate |

Documents are rendered as self-contained HTML with embedded CSS, displayed in a sandboxed iframe viewer, and can be saved to IndexedDB workspace or uploaded to Google Drive.

### 5. Memory System

Beatrice maintains a persistent memory store in Supabase with two operations:

- **`add_to_memory`**: Stores facts, preferences, and personal details with optional tags (`['personal', 'preference', 'work', 'contact', 'fact']`). The model is instructed to proactively ask "should I remember that?" when the user shares personal information.
- **`search_memory`**: Semantic search across stored memories. Results are injected into the system instruction as `memoryContext` at session start.

### 6. Belgian Administrative & Business Tools

Ten specialized tools for the Belgian market, implemented server-side in `server/belgian-tools.ts`:

| Tool | Function |
|---|---|
| `belgian_company_lookup` | KBO/CBE company search with local high-fidelity records |
| `belgian_vies_vat_validate` | EU VAT number validation |
| `belgian_peppol_invoice` | Peppol-compliant e-invoice generation |
| `belgian_tax_calendar` | VAT, income tax, biztax, social security deadlines |
| `belgian_registration_tax_calc` | Property registration tax by region |
| `belgian_itsme_navigator` | Itsme authentication guidance |
| `belgian_language_bridge` | Dutch/French formal letter translation |
| `belgian_social_security_navigator` | Ziekenfonds/Mutualité refund guidance |
| `belgian_labor_law_simplifier` | Notice periods, indexation, 13th-month bonus |
| `belgian_mobility_planner` | NMBS/SNCB train travel planning |

### 7. Sandbox & Browser Automation

Two server-side execution environments for complex tasks:

- **Gemini Sandbox** (`/api/sandbox/run`): General-purpose task execution using `gemini-2.5-flash` for code review, analysis, research, and long-form writing. Results are presented in first person as if Beatrice did the work.
- **Cerebras Browser** (`/api/cerebras/browser`): Browser automation via Puppeteer + Cerebras LLM for web scraping, form filling, and live website interaction.

### 8. Camera & Screen Share

Beatrice can access the device camera and screen capture:
- Camera feed sent as video frames to the Live session via canvas capture at 1 FPS
- Front/back camera toggle (`facingMode: 'user' | 'environment'`)
- Screen share via `getDisplayMedia`
- Dedicated `VideoPage` component for full-screen camera view

---

## Data Model

### Supabase (PostgreSQL)

**`messages` table:**
| Column | Type | Constraints |
|---|---|---|
| `id` | uuid | PK, default gen_random_uuid() |
| `user_id` | text | FK → auth.users, NOT NULL |
| `session_id` | text | Groups messages into conversations |
| `role` | text | 'user' or 'model' only |
| `text` | text | Max 5,000 characters |
| `attachment_url` | text | Optional file attachment |
| `attachment_name` | text | Optional file name |
| `created_at` | timestamptz | default now() |

Messages are **immutable** — Firestore rules prohibit update and delete. This creates an audit trail of all agent interactions.

**`user_settings` table:**
| Column | Type | Description |
|---|---|---|
| `user_id` | text | PK, FK → auth.users |
| `persona_name` | text | Agent display name (max 50 chars) |
| `selected_voice` | text | TTS voice ID |
| `custom_prompt` | text | User-defined system prompt (max 2,000 chars) |
| `context_size` | int | Conversation history window |
| `user_title` | text | How Beatrice addresses the user |
| `language` | text | ISO language code |
| `whatsapp_permissions` | jsonb | Permission toggles |
| `whatsapp_phone` | text | Paired phone number |
| `theme` | text | 'dark' or 'light' |
| `ambient_enabled` | bool | Background sound toggle |
| `ambient_volume` | int | 0-20 volume level |
| `censorship_enabled` | bool | Content filter toggle |
| `updated_at` | timestamptz | Auto-updated |

**`memories` table:**
| Column | Type | Description |
|---|---|---|
| `id` | uuid | PK |
| `user_id` | text | FK → auth.users |
| `content` | text | The remembered information |
| `tags` | text[] | Categorization tags |
| `created_at` | timestamptz | |

### Local Storage

| Key | Purpose |
|---|---|
| `beatrice_theme` | Dark/light preference |
| `beatrice_language` | UI language |
| `beatrice_userTitle` | How Beatrice addresses user |
| `beatrice_censorship` | Content filter |
| `beatrice_ambient_enabled` | Background sound |
| `beatrice_ambient_volume` | Volume level |
| `beatrice_onboarding_done` | Onboarding completion flag |
| `beatrice_google_token` | Google access token |
| `beatrice_google_refresh_token` | Google refresh token |
| `beatrice_google_uid` | Associated Firebase UID |
| `beatrice_backend_url` | Backend server URL |
| `beatrice_knowledge_domains` | User's knowledge domains |

### IndexedDB (Dexie)

**`BeatriceDB`** — local-first database with four tables:
- `messages`: Offline message cache
- `settings`: Local settings mirror
- `sessions`: Conversation session metadata
- `knowledgeFiles`: Uploaded knowledge file metadata

**`beatrice_workspace`** — document/image output store with indexes on `userId`, `type`, and `createdAt`.

---

## Security Model

### Authentication
- Firebase Auth with email/password and Google OAuth
- Google OAuth uses offline access (`access_type: 'offline'`, `prompt: 'consent'`) to obtain refresh tokens
- Token refresh handled client-side via `https://oauth2.googleapis.com/token`

### Data Isolation
- All Supabase queries are scoped to `user_id = auth.uid()`
- Row-Level Security (RLS) enforced at the database level
- Firestore security rules validate: user identity, timestamp authenticity (`== request.time`), role constraints (`user`/`model` only), field whitelists, and length limits

### Security Invariants (from `security_spec.md`)
1. Users can only read/write their own data
2. Timestamps must equal server request time (prevents backdating)
3. Message roles restricted to `user` or `model`
4. Field validation by whitelist (prevents shadow field injection)
5. Length limits: `personaName` ≤ 50, `customPrompt` ≤ 2,000, `message.text` ≤ 5,000
6. Document IDs must match `^[a-zA-Z0-9_\-]+$` and be ≤ 128 characters
7. Messages are immutable (no update/delete)

### API Security
- CORS configured for cross-origin access
- `Cross-Origin-Opener-Policy: same-origin-allow-popups` for Google OAuth popup compatibility
- Permissions-Policy header restricts camera, microphone, display-capture, geolocation to self
- WhatsApp tools are permission-gated with 10 independent boolean toggles
- Outbound WhatsApp messages require delegated send approval

---

## Voice Personality

Beatrice's persona is defined by a ~350-line system instruction (`VOICE_PERSONALITY_PROMPT`) that governs her tone, speech patterns, emotional intelligence, and interaction style. Key characteristics:

- **Professional but warm**: Addresses the user by their chosen title (default: "Boss"), maintains a lightly warm base tone that adapts to context
- **Emotionally intelligent**: Recognizes anger, frustration, and distress. Responds with validation and empathy, never with robotic customer-service language
- **Natural speech**: Uses short spoken chunks, normal pauses, sparse human fillers, and occasional vocal expressions (laughter, sighs, hums) — but balanced at ~80% clean speech to 20% expression
- **Multilingual**: Adapts vocal expressions to the user's language (Filipino "hay nako", French "oh la la", Spanish "ay", Dutch "ooh", Arabic "uff")
- **Proactive memory**: Asks "should I remember that?" when users share personal information
- **Document-aware**: Never mentions HTML or technical details to the user — says "document", "preview", "draft", or "workspace"

---

## User Flow

```
Splash Page → Onboarding → Auth (Sign In / Register)
                                │
                                ▼
                          Entry Flow
                                │
                                ▼
                        WhatsApp Onboarding
                        (pair device or skip)
                                │
                                ▼
                        ┌───────────────┐
                        │  Main Agent   │
                        │  Interface    │
                        │               │
                        │  • Orb visual │
                        │  • Transcript │
                        │  • Tool tasks │
                        │  • Bottom nav │
                        └───────┬───────┘
                                │
          ┌─────────────┬───────┼───────┬─────────────┐
          ▼             ▼       ▼       ▼             ▼
      Chat Page    Video     Settings  Profile    WhatsApp
      (history)    Page      Panel     Page       Portal
                            (Google,  (persona,   (standalone
                             ambient,  voice,     chat UI)
                             WA perms) language)
```

---

## Deployment

### Production
| Component | Platform | URL |
|---|---|---|
| Frontend | Vercel | `https://voicehhub.vercel.app` |
| Backend | Render | `zero-backend` (Web Service) |
| Database | Supabase | `inypxifrayeafrlhkulz.supabase.co` |
| Auth | Firebase | `eburon-ai-beatrice` |

### Local Development
```
npm run dev        # Frontend on :3000 (or :3001 if :3000 occupied)
npm run dev:api    # Backend on :4200
npm run dev:full   # Both concurrently
```

### Environment Variables
Critical: `GEMINI_API_KEY`, `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`

---

## Known Limitations & Roadmap

### Current Limitations
- No test framework or CI pipeline
- BeatriceAgent.tsx is ~5,000 lines (needs decomposition into tool registry, session manager, UI components)
- No error boundary for React component tree
- WhatsApp backend uses in-memory message store (lost on restart unless persisted)
- Cerebras browser tasks use blocking `execSync`
- No rate limiting on backend endpoints
- Firebase config is hardcoded rather than environment-driven

### Recommended Next Steps
1. Extract tool execution into a registry pattern with individual handler modules
2. Add React error boundary at the App level
3. Implement test suite for audio pipeline, tool execution, and security rules
4. Add structured logging (e.g., Pino) throughout backend
5. Implement proper async subprocess management for browser automation
6. Add CI/CD pipeline (GitHub Actions) with lint, typecheck, and deploy stages
7. Extract voice personality prompt into a versioned, editable configuration file

---

## Conclusion

Beatrice represents a sophisticated integration of real-time voice AI, productivity tooling, and messaging — all wrapped in a carefully designed personality layer. The platform's architecture supports deep Google Workspace integration, a permission-gated WhatsApp system, document generation, persistent memory, and region-specific administrative tools. While the monolithic component structure creates maintenance challenges at its current scale, the core audio pipeline, AI integration, and WhatsApp subsystem are well-engineered and production-capable.

---

*Generated by Eburon AI — July 2026*
