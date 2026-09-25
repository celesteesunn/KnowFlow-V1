# KNOWFLOW — Enterprise Knowledge & Collaboration Platform

KnowFlow centralises organisational documents and provides simple AI-powered,
document-based question answering. Employees can log in, create and view their
own projects, upload PDF documents, search them, ask an AI assistant questions
grounded in the document content, see the source document and page used for
each answer, and detect potentially duplicate documents.

## Problem statement

Organisational information is scattered across documents, making it hard for
employees to find answers quickly. Searching is manual, answers are not
traceable to a source, and near-identical documents accumulate without anyone
noticing. KnowFlow solves this by centralising documents per project and
answering questions directly from the uploaded content, always citing the
source document and page.

## Objectives

- Provide a simple, secure place to upload and organise PDF documents per project.
- Answer employee questions from the documents using retrieval-augmented
  generation (RAG), with every answer citing its source.
- Keep data private: users only ever see their own projects and documents.
- Detect potential duplicate documents and surface unanswered questions so the
  knowledge base can be improved.
- Stay lightweight: SQLite, local embeddings, no external vector database.

## Features

- **Authentication** — register, log in, log out (session cookies, hashed
  passwords with werkzeug scrypt). Usernames are validated; passwords must be
  6-128 characters.
- **Projects** — create and view your own knowledge projects. Users never see
  other users' projects.
- **Dashboard** — real statistics: project and document counts, recently
  uploaded, recently updated (new versions), recent unanswered questions and
  potential duplicates, all computed live from the database.
- **Document management**
  - PDF upload with metadata (title, description, category)
  - PDF validation: extension check, readable content check, 20 MB size limit,
    rejection of invalid, corrupted, empty and text-less PDFs
  - Per-project document list: title, uploader, date, version, status
  - Document details with full metadata and version history
  - Open/download the stored PDF
  - Replace a document → new version created, previous version kept on disk
  - Archive (soft delete) and permanent delete (removes all versions, pages,
    chunks and files)
  - Text extraction per page with PyPDF, stored for search and RAG
- **Search** — keyword search within a project and global search across all of
  the user's documents, with document, project, page number and snippet.
- **AI question answering (RAG)** — a chat page where users pick a project and
  ask questions; answers are grounded in the project's documents with source
  citations. If the answer is not in the documents, the AI says so.
- **Duplicate detection** — TF-IDF cosine similarity flags near-identical
  documents on upload and lists duplicate pairs per project.
- **Related documents** — viewing a document shows semantically similar
  documents (≥ 10% similarity) from the user's own projects.
- **Knowledge gaps** — unanswered AI questions are recorded; admins see
  frequently unanswered questions with occurrence counts.
- **Admin (user management)** — admins see all users with project/document
  counts and can grant or remove admin roles (cannot change their own role).
- **Knowledge Insights (admin)** — frequently unanswered questions and
  potential duplicate pairs across all projects.

## Technology stack

| Layer                  | Technology                                    |
| ---------------------- | --------------------------------------------- |
| Frontend               | React (Vite) + CSS                            |
| Backend                | Python + Flask                                |
| Database               | SQLite                                        |
| Document processing    | Python + PyPDF (`pypdf`)                      |
| AI                     | Python + OpenAI-compatible LLM API (optional) |
| Semantic / duplicates  | Python + scikit-learn (TF-IDF / hashed vectors) |

## System architecture

```
Browser (React SPA on :5173)
        │  /api/*  (Vite dev proxy)
        ▼
Flask backend (:5000)
  ├── auth.py        register / login / logout / me (session cookies)
  ├── projects.py    project list + create (owner-scoped)
  ├── documents.py   upload, list, detail, download, replace, archive,
  │                  permanent delete, search, ask, duplicates (owner-scoped)
  ├── chat.py        POST /api/chat — RAG Q&A (owner check before retrieval)
  ├── knowledge.py   global search, related docs, knowledge gaps,
  │                  dashboard stats, admin users + insights
  └── ai.py          chunking, embeddings, retrieval, LLM generation
        │
        ▼
SQLite (data/knowflow.db)   +   uploads/ (stored PDFs)
```

The frontend talks to the backend through the Vite `/api` proxy, so requests
are same-origin. Session cookies are HTTP-only with SameSite=Lax. CORS is
restricted to the local dev servers.

## Workflow

1. A user registers or logs in (session cookie set).
2. The user creates a project.
3. The user uploads a PDF. The backend validates it, extracts text per page,
   chunks and embeds the text, stores everything in SQLite, and checks the new
   document against existing ones for potential duplicates.
4. The user can search the project, search globally, view related documents,
   and ask the AI assistant questions.
5. A question is answered from the project's own documents only; the answer
   cites the source document and page.
6. Questions the AI cannot answer are recorded as knowledge gaps, visible to
   admins.

## RAG workflow

```
Uploaded PDF → extracted text → sentence-aware chunks (≤600 chars, 100 overlap)
→ sparse embeddings (scikit-learn HashingVectorizer, 2^16 features, no vector DB)
→ stored in SQLite (document_chunks)
Question → embedded the same way → cosine similarity → top-3 chunks
→ chunks sent to the LLM (OpenAI-compatible) → answer + source citations
```

- Retrieval is permission-scoped: only the project owner's current,
  non-archived documents are ever searched, before any context reaches the LLM.
- With `OPENAI_API_KEY` set, answers are generated by the LLM using only the
  retrieved passages. Without a key, or if the LLM call fails, the system
  degrades to retrieval-only mode and returns the most relevant passages with
  citations, so the feature is fully usable offline.

## Database overview

| Table             | Purpose                                              |
| ----------------- | ---------------------------------------------------- |
| `users`           | Accounts: username, scrypt password hash, is_admin   |
| `projects`        | Knowledge projects, owned by a user                  |
| `documents`       | PDFs: metadata, version, status, file path, text     |
| `document_pages`  | Extracted text per page                              |
| `document_chunks` | RAG chunks with serialised embeddings                |
| `knowledge_gaps`  | Unanswered AI questions (user, project, timestamp)   |

The schema is created and migrated automatically on startup. The first
registered account is made an admin.

## Data Science features

- **Duplicate detection** — TF-IDF cosine similarity between documents
  (threshold 0.7). On upload, the response warns "Possible duplicate detected"
  with the similarity percentage. A per-project endpoint lists duplicate pairs.
  Similarity is a signal, never a claim of factual duplication.
- **Related documents** — TF-IDF cosine similarity between the viewed document
  and the user's other documents (threshold 0.1), top 3 shown.
- **Unanswered question tracking** — when a chat question has no retrieved
  chunks or the top score is below 0.05, the question is recorded in
  `knowledge_gaps`; admins see counts and last-asked times.

## Setup instructions

### Prerequisites

- Python 3.10+ (tested with 3.14)
- Node.js 18+ and npm

### 1. Backend (Flask)

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
python app.py                   # starts on http://localhost:5000
```

The database file, uploads folder and schema are created automatically on
first start.

### 2. Frontend (React)

```bash
cd frontend
npm install
npm run dev                     # starts on http://localhost:5173
```

Open http://localhost:5173, register an account, create a project, upload PDFs,
then search, ask questions and check for duplicates.

## Environment variables

Create `backend/.env` (gitignored) or set real environment variables. Real
environment variables always win over `.env` values.

| Variable              | Default                     | Purpose                              |
| --------------------- | --------------------------- | ------------------------------------ |
| `KNOWFLOW_SECRET_KEY` | `dev-secret-change-me`      | Flask session signing key            |
| `OPENAI_API_KEY`      | *(empty)*                   | Enables LLM-generated answers        |
| `OPENAI_BASE_URL`     | `https://api.openai.com/v1` | Any OpenAI-compatible endpoint       |
| `OPENAI_MODEL`        | `gpt-4o-mini`               | Model used for answers               |

Example:

```bash
set OPENAI_API_KEY=sk-...
set OPENAI_BASE_URL=https://api.openai.com/v1
set OPENAI_MODEL=gpt-4o-mini
set KNOWFLOW_SECRET_KEY=change-me
```

Without `OPENAI_API_KEY`, the app runs in retrieval-only mode (answers come
from the top matching passages with citations).

## How to run frontend

```bash
cd frontend
npm install
npm run dev
```

## How to run backend

```bash
cd backend
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

## API overview

| Method | Endpoint                              | Description                          |
| ------ | ------------------------------------- | ------------------------------------ |
| GET    | `/api/health`                         | Service status, version, DB check    |
| POST   | `/api/auth/register`                  | Create account (sets session)        |
| POST   | `/api/auth/login`                     | Sign in (sets session)               |
| POST   | `/api/auth/logout`                    | Sign out                             |
| GET    | `/api/auth/me`                        | Current user (or null)               |
| GET    | `/api/projects`                       | List own projects + document counts  |
| POST   | `/api/projects`                       | Create project                       |
| GET    | `/api/dashboard`                      | Dashboard stats for the signed-in user |
| GET    | `/api/documents`                      | All current documents across own projects |
| POST   | `/api/projects/<id>/documents`        | Upload PDF (multipart); response includes `potentially_similar` |
| GET    | `/api/projects/<id>/documents`        | List current documents in a project  |
| GET    | `/api/documents/<id>`                 | Document details + version history   |
| GET    | `/api/documents/<id>/download`        | Download the stored PDF              |
| POST   | `/api/documents/<id>/related`         | Related documents (own projects, ≥ 10% similar) |
| POST   | `/api/projects/<id>/documents/<doc>/replace` | Replace → new version, old kept |
| DELETE | `/api/documents/<id>`                 | Archive (soft delete)                |
| DELETE | `/api/documents/<id>/permanent`       | Permanently delete doc + all versions |
| GET    | `/api/projects/<id>/search?q=…`       | Keyword search with snippets         |
| GET    | `/api/search?q=…`                     | Global search across own projects    |
| POST   | `/api/projects/<id>/ask`              | AI Q&A → answer + source citations   |
| POST   | `/api/chat`                           | RAG chat: `{project_id, question}` → answer + sources (owner only) |
| GET    | `/api/projects/<id>/duplicates`       | Near-duplicate document pairs        |
| GET    | `/api/knowledge-gaps`                 | Frequently unanswered questions (admin only) |
| GET    | `/api/admin/users`                    | All users with counts (admin only)   |
| POST   | `/api/admin/users/<id>/admin`         | Grant/remove admin role (admin only, not self) |
| GET    | `/api/admin/insights`                 | Gaps + duplicate pairs across all projects (admin only) |

All endpoints except `/api/health` and `/api/auth/*` require an authenticated
session. Every project and document endpoint is owner-scoped: accessing another
user's project or document returns 404. Admin endpoints return 403 for
non-admins.

## Testing instructions

The application was verified end-to-end with live API tests covering:

- **Authentication** — valid login, invalid login (wrong password and unknown
  user both return 401), protected pages without a session return 401, logout
  clears the session.
- **Authorisation** — a fresh employee sees no projects, cannot list, view,
  download, upload to, delete, chat with or search another user's projects or
  documents (all 404), and is blocked from every admin endpoint (403). Admins
  can manage users but cannot change their own role.
- **Documents** — non-PDF files, corrupted PDFs, empty files and text-less
  PDFs are rejected with clear errors; valid PDFs upload, extract text, version
  on replace, archive, download, and permanently delete (including files on
  disk).
- **AI/RAG** — relevant questions return grounded answers with source
  document/page/score; irrelevant questions return an honest "not found"
  response; answers differ per question (no hardcoded answers); retrieval is
  permission-scoped; a failed LLM call degrades to retrieval-only mode.
- **Data Science** — duplicate detection warns on upload with similarity
  scores; related documents rank by similarity; unanswered questions are
  recorded and visible to admins.
- **Security** — passwords are hashed (scrypt), API keys live only in
  `backend/.env` (gitignored), uploads are validated, file paths are
  server-generated (no user-controlled paths), and session cookies are
  HTTP-only + SameSite=Lax.

## Known limitations

- **Owner-only access model** — projects and documents are private to their
  owner; there is no sharing or collaboration between users yet.
- **Local embeddings** — retrieval uses hashed bag-of-words vectors, not
  semantic embeddings; synonyms and paraphrases may be missed.
- **Keyword search** — project and global search use SQL `LIKE` matching, not
  full-text search; large corpora would benefit from FTS5.
- **Duplicate detection** — TF-IDF similarity is a signal, not proof of
  duplication; short or boilerplate-heavy documents can produce false
  positives.
- **PDF text extraction** — scanned/image-only PDFs yield no text and are
  rejected; OCR is not included.
- **Single-process backend** — the Flask development server is fine for local
  use; production would need a WSGI server and a real secret key.
- **No rate limiting** — login and chat endpoints have no throttling; fine for
  internal use, not for public exposure.
- **LLM dependency** — generated answers require an external API key; without
  it the app runs in retrieval-only mode.

## Future improvements

- Project sharing and team collaboration with per-member roles.
- Semantic embeddings (e.g. sentence-transformers) for better retrieval.
- SQLite FTS5 full-text search for faster, ranked keyword search.
- OCR for scanned documents.
- Rate limiting and brute-force protection on authentication.
- Automated test suite (pytest) covering the API endpoints.
- Deployment with a production WSGI server (gunicorn/waitress) and HTTPS.