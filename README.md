# Welfare Navigator

Multilingual civic-support discovery and application preparation demo. The deterministic rules engine labels **Potential match**, **Needs more information**, or **Appears unlikely**; it never makes an official eligibility decision.

## Run locally

Requirements: Node.js 20+ and Python 3.10+.

1. Start the API in one terminal: enter backend, create and activate a Python virtual environment, install requirements, then run uvicorn app.main:app --reload --port 8000.
2. Start the frontend in another terminal: enter frontend, run npm install and npm run dev.

Open http://localhost:3000. The UI has local fallback records if the API is unavailable.

## Environment

Copy `frontend/.env.example` to `frontend/.env.local` to change `NEXT_PUBLIC_API_URL`. Profile extraction uses the deterministic demo parser by default. To enable the optional single-call OpenAI-compatible profile extractor, set `OPENAI_API_KEY` and optionally `OPENAI_MODEL` for the backend process. Without a key, the local parser remains active.

## Demo mode and limitations

The supplied CSVs in `database/seed` are loaded in Demo Mode: 40 scheme entries, 15 categories, 64 rule rows, 92 scheme-document rows, 40 fictional demo profiles, and 110 sample user-document statuses. Select a sample profile from the Assessment screen. CSV document statuses are sample labels only and do not assert legal validity. The API exposes `GET /api/demo-users` and `POST /api/demo-users/{user_id}/load`.

Scheme records and source URLs are imported from the provided CSV. Rule rows marked as prototype/demo or containing verification notes are used only for explainable demo matching; the engine cannot establish official eligibility and rules may omit conditions. Check every scheme at its supplied source URL. Demo document upload accepts PDF/PNG/JPEG and returns “needs review”; OCR, persistent storage, authentication, and document verification are not configured. Demo API profiles/files are stored in process memory.

Recommendations now run controlled intent/concept extraction, target/category/state metadata filters, deterministic eligibility checks, and ranking over the filtered candidate set. Cached in-memory sparse-vector retrieval supplies source-attributed scheme chunks as a RAG fallback; this is not a dense embedding service. `database/migrations/002_scheme_metadata_and_rag.sql` adds scheme metadata and a pgvector chunk table for a PostgreSQL deployment, but the demo app does not connect to that database or populate embeddings. No RAG chunk claims an official source beyond the CSV-provided URL/date. If the in-memory retrieval is empty, metadata and rule matching still work.

Recommendation APIs include `POST /api/profile/extract`, `/api/intent/detect`, `/api/schemes/retrieve`, `/api/schemes/recommend`, `/api/eligibility/check`, `/api/rag/search`, and `/api/recommendations/refresh`. The chat and recommendation screens refresh after profile changes. Regression coverage is in `backend/tests` and can be run with `python -m unittest discover -s tests -v` from `backend`.

## Architecture

- frontend/: Next.js, React, strict TypeScript, Tailwind, Lucide; responsive single-page interface.
- backend/app/main.py: FastAPI routes, profile extraction, demo CSV loader, eligibility rules, upload metadata, and readiness.
- backend/app/taxonomy.py and backend/app/recommendations.py: controlled intent detection, scheme metadata, candidate filtering, sparse-vector chunk retrieval, and deterministic ranking.
- database/schema.sql and database/migrations: normalized PostgreSQL schema and additive scheme metadata/pgvector scaffold.

The rules engine handles comparisons, set membership, boolean equality, AND/OR, and unknown values. A required failed criterion yields APPEARS_UNLIKELY; otherwise any required unknown yields NEEDS_MORE_INFORMATION; all required criteria matched yields POTENTIAL_MATCH.
