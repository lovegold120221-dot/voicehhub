# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 🏛️ High-Level Architecture & Structure

Voxx-Zero is a specialized, end-to-end AI agent designed to automate complex administrative and business tasks specific to the Belgian market. The system is composed of distinct, interacting layers:

**1. Frontend (Client Application)**
*   **Framework:** React 19, built with Vite, and styled using Tailwind CSS v4.
*   **Function:** Provides the user interface for interacting with the AI. It handles dynamic display of generated documents (invoices, NDAs, etc.) and manages the real-time audio streaming and recording for the Gemini Live API.
*   **Key Libraries:** Leverages Framer Motion for smooth animations and implements robust document generation using libraries like `jspdf` and `html2canvas`.

**2. Backend/API Layer**
*   **Framework:** Express.js, responsible for handling all external communications and business logic.
*   **Core Function:** Acts as a bridge between the client, the Gemini API, and third-party services. It manages the WhatsApp integration using `@whiskeysockets/baileys` and orchestrates the execution of the specialized Belgian tools.
*   **Location:** Primary entry point for backend logic is `server/index.ts`.

**3. Core Services & Data Persistence**
*   **Authentication:** Managed by Firebase Auth (using Google OAuth).
*   **Database/State:** Uses Supabase for persistent storage of user-specific data, including settings, custom knowledge bases, and document storage.
*   **AI Interaction:** Integrates deeply with the Gemini Live API for real-time audio and conversational AI capabilities.

**4. Specialized Belgian Tooling**
The core value of the system lies in its integration with 10 high-value, market-specific skills. These modules abstract complex local regulations into simple API calls, including:
*   KBO/CBE Company Intelligence (Company registration lookups).
*   VIES VAT Validation (EU VAT number checks).
*   Peppol E-Invoicing Generator (UBL/XML compliant invoice drafting).
*   Registration Tax Calculation (Regional tax law calculation).

## 🛠️ Development Commands

The following commands cover standard development workflows. All scripts are defined in `package.json`.

| Task | Command | Purpose | Notes |
| :--- | :--- | :--- | :--- |
| **Full Development** | `npm run dev:full` | Starts both the client and API side for local development. | Runs the frontend on `http://localhost:3000` and the backend API. |
| **Frontend Dev** | `npm run dev` | Runs the Vite development server for the React frontend. | Good for testing UI changes in isolation. |
| **Backend/API Dev** | `npm run dev:api` | Runs the Express/TypeScript backend logic. | Used primarily for developing or debugging the API endpoints and WhatsApp integration. |
| **Build** | `npm run build` | Compiles the entire client-side application. | Creates the optimized, production-ready assets in the `dist/` folder. |
| **Linting** | `npm run lint` | Runs TypeScript compilation check (`tsc --noEmit`). | Checks for type errors and syntax issues without generating output files. |
| **Testing** | *(No explicit `test` script provided)* | Run unit/integration tests. | **Action:** Check for `jest` or `vitest` setup in `src/` or `functions/` directories, or create a specific test script. |
| **Single Test** | *(N/A)* | Run a single test file. | **Action:** Follow the same pattern as the dedicated testing command (e.g., `npm run test:unit ./src/specific-file.test.ts`). |

## 📂 Codebase Organization Notes

*   **`src/`**: Contains the primary source code for the React frontend components and application logic.
*   **`server/`**: Hosts the main Express API server logic, handling routing and middleware.
*   **`functions/`**: Contains modularized, serverless functions (likely for Firebase/Cloud Functions) that execute specific, discrete backend tasks.
*   **`docs/`**: Contains architectural diagrams (`.mmd`, `.svg`) and high-level flowcharts, invaluable for understanding system invariants.
*   **`config`**: Environment variables and configuration files are crucial for connecting to external services (Supabase, Gemini, Firebase). Ensure all keys are loaded from the `.env` file.

## 🔑 Key Files & Directories

| Path | Purpose |
| --- | --- |
| `src/App.tsx` | Main application component with routing logic. |
| `src/components/BeatriceAgent.tsx` | Core AI agent interface and Gemini API integration. |
| `server/index.ts` | Express server entry point, defines all API routes. |
| `package.json` | Project dependencies and scripts. |
| `.env.example` | Template for environment variables (commit this). |
| `README.md` | Project overview and quick start guide. |

## 🚀 Deployment Notes

*   **Environment:** Production deployment uses Node.js 22+ with TypeScript compilation via Vite.
*   **Hosting:** Application is containerized using Docker (`Dockerfile`, `docker-compose.yml`).
*   **Configuration:** All sensitive keys (Gemini API, Supabase credentials) are managed through environment variables. Never hardcode secrets in source files.
