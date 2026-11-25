# RepoPilot AI

> Production-ready semantic code search and grounded Q&A engine for GitHub repositories.

RepoPilot AI is a self-hosted, full-stack application that transforms any public GitHub repository into a searchable, interactive knowledge base. It indexes codebases using language-aware AST chunking, generates dense vector embeddings, and delivers evidence-backed answers with exact file and line citations via grounded LLM synthesis.

---

## Overview

Modern software repositories are dense and complex. Traditional lexical search (like `grep` or standard IDE search) fails when developers need conceptual answers ("Where is token refresh handled?", "How does the caching middleware work?"). Meanwhile, generic AI assistants frequently hallucinate file paths and function signatures when answering questions without repository-wide context.

RepoPilot AI solves this by coupling **code-aware parsing** with **vector similarity search (`pgvector`)** and **strict evidence grounding**:

- **No Hallucinations**: If retrieved code chunks do not clear a strict similarity threshold, the system explicitly reports insufficient evidence rather than guessing.
- **Accurate Line Citations**: Every code chunk preserves 1-based start and end line boundaries with syntax-highlighted previews.
- **Zero Embedding Costs by Default**: Runs fully local embeddings out-of-the-box with `sentence-transformers` (`all-MiniLM-L6-v2`), with zero required external embedding API keys. Optional cloud embeddings (OpenAI, Voyage AI) are supported.
- **Enterprise-Grade Ingestion**: Resilient background pipeline equipped with automated secret scanning, resource limiters, exponential backoff with jitter, and atomic database swaps.

---

## Demo & Preview

### Video Walkthrough

<video src="assets/Demo.mp4" controls width="100%">
  <p>Your browser does not support HTML5 video. You can <a href="assets/Demo.mp4">download or watch Demo.mp4 directly</a>.</p>
</video>

### Q&A Interface

![RepoPilot AI Q&A Interface](assets/qa-preview.png)

<p align="center">
  <em>Grounded Q&A Interface: Natural-language query with exact file paths, line ranges, similarity metrics, and syntax-highlighted code evidence.</em>
</p>

---

## Key Features

### 1. Code-Aware AST Chunking
Unlike naive token-splitting chunkers that cut functions in half, RepoPilot AI uses language-aware parsing:
- Preserves functions, methods, and classes as contiguous units.
- Intelligently splits oversized classes by member methods and oversized functions across logical line boundaries.
- Uses heading- and paragraph-aware chunking for Markdown, RST, and documentation files.
- Preserves exact 1-based `start_line` and `end_line` coordinates for all chunks.

### 2. Flexible Embedding Architecture
- **Local (Default)**: Embedded `sentence-transformers` (`all-MiniLM-L6-v2`, 384 dimensions). Runs locally with zero API billing.
- **Cloud Providers**: Seamless drop-in support for OpenAI (`text-embedding-3-small`, `text-embedding-3-large`) and Voyage AI (`voyage-code-3`, `voyage-3`).
- **Mismatch Protection**: Built-in dimension guards prevent querying a vector store indexed with a mismatched embedding dimension.

### 3. Strict Evidence Grounding
- Retrieves top-$k$ code chunks using cosine similarity search in `pgvector`.
- Evaluates chunk relevance against a configurable similarity threshold (default `0.25` for local embeddings).
- Rejects ungrounded queries upfront: if no retrieved chunk satisfies the threshold, RepoPilot AI reports insufficient evidence and halts execution before calling the LLM.

### 4. Robust Background Pipeline
- Background worker implements PostgreSQL-native row claiming via `SELECT ... FOR UPDATE SKIP LOCKED` to prevent duplicate processing.
- Handles transient network or subprocess failures with exponential backoff and randomized jitter.
- Immediately halts permanent failures (e.g. 404 repositories, authentication failures, missing git binaries) to preserve compute resources.
- Employs an **atomic swap strategy**: new chunks, files, and commit hashes are written in a staging transaction and swapped atomically, ensuring existing indexes remain untouched if an ingestion run fails.

### 5. Automated Security & Secret Scanning
- **Secret Filtering**: Excludes files containing sensitive keys (`.env*`, `id_rsa*`, `.pem`, `*.key`, `credentials.json`, `*.tfvars`, `.pypirc`, `.npmrc`, etc.) during discovery before contents are read.
- **Credential Redaction**: Sanitizes URLs, GitHub PATs, and Bearer tokens from all logs and error summaries.
- **Tenant Isolation**: Strict per-user repository isolation with JWT-authenticated endpoints.

---

## How It Works

```mermaid
flowchart TD
    A["Public GitHub Repository URL"] --> B["Git Clone (Ephemeral Local Disk)"]
    B --> C["File Discovery & Secret Filter"]
    C -->|Ignored Secrets & Binaries| D["Logged to repository_file_skips"]
    C -->|Eligible Source Files| E["AST Code Parser & Chunker"]
    E --> F["Vector Embeddings (Local or Remote)"]
    F --> G[("PostgreSQL + pgvector (Atomic DB Swap)")]
    
    H["User Natural-Language Question"] --> I["Query Embedding Generation"]
    I --> J["pgvector Cosine Similarity Search"]
    J --> K{"Passes Similarity Threshold?"}
    K -->|No| L["Return Insufficient Evidence Warning"]
    K -->|Yes| M["Construct Grounded Prompt with Citations"]
    M --> N["OpenRouter LLM Synthesis"]
    N --> O["Deliver Answer with Code Evidence & Line Ranges"]
```

1. **Ingestion**: The user submits a public GitHub repository URL. The backend clones the repository, checks resource limits, scans for secrets, and discovers source files.
2. **Chunking & Embedding**: Eligible code files are parsed into semantic chunks and embedded using dense vector representations.
3. **Storage**: Vectors and chunk metadata are committed atomically into PostgreSQL using `pgvector`. Local clone directories are pruned immediately.
4. **Retrieval**: When a query arrives, the system embeds the question and queries the vector index for nearest neighbors.
5. **Grounded Generation**: If relevant chunks meet the similarity threshold, they are formatted into an evidence block and passed to an OpenRouter LLM to construct a precise, cited answer.

---

## Tech Stack

| Layer | Technology | Details |
| :--- | :--- | :--- |
| **Backend** | [FastAPI](https://fastapi.tiangolo.com/) | Asynchronous Python REST API with Pydantic validation |
| **Database** | [PostgreSQL](https://www.postgresql.org/) + [pgvector](https://github.com/pgvector/pgvector) | Relational storage and vector similarity indexing |
| **ORM & Migrations**| [SQLAlchemy 2.0](https://www.sqlalchemy.org/) & [Alembic](https://alembic.sqlalchemy.org/) | Type-safe declarative models with versioned migrations |
| **Authentication** | Argon2 ([pwdlib](https://github.com/frankie567/pwdlib)) & [PyJWT](https://pyjwt.readthedocs.io/) | Argon2 password hashing and HS256 JWT bearer token auth |
| **Frontend** | [React 18](https://react.dev/), [TypeScript](https://www.typescriptlang.org/), [Vite](https://vitejs.dev/) | Client-side SPA with React Router v6 |
| **Styling & UI** | [Tailwind CSS](https://tailwindcss.com/) & [Lucide Icons](https://lucide.dev/) | Clean, accessible design system with responsive layouts |
| **Code Highlighting**| [React Syntax Highlighter](https://github.com/react-syntax-highlighter/react-syntax-highlighter) | Syntax highlighting for Python, JS, TS, Bash, and SQL |
| **Embeddings** | [sentence-transformers](https://www.sbert.net/) (`all-MiniLM-L6-v2`) | Default 384-dimensional local dense embeddings |
| **LLM Provider** | [OpenRouter](https://openrouter.ai/) | Configurable cloud LLM interface (`particle-ai/particle-1:free`, etc.) |

---

## Prerequisites

Before setting up RepoPilot AI, ensure you have the following installed:

- **Python**: `3.11` or `3.12`
- **Node.js**: `18.x` or `20.x` (with `npm`)
- **PostgreSQL**: Version 15+ with the [pgvector extension](https://github.com/pgvector/pgvector#installation) installed
- **Git**: Installed and accessible on your system `PATH`

---

## Installation & Setup

### 1. Database Setup

Ensure PostgreSQL is running, create the database, and enable the `pgvector` extension:

```sql
CREATE DATABASE repopilot;
\c repopilot
CREATE EXTENSION IF NOT EXISTS vector;
```

---

### 2. Backend Setup

1. **Create and activate a virtual environment**:

   ```bash
   # Linux / macOS
   python3 -m venv .venv
   source .venv/bin/activate

   # Windows (PowerShell)
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

2. **Install Python dependencies**:

   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment variables**:

   Copy the example environment configuration:

   ```bash
   cp .env.example .env
   ```

   Edit `.env` to supply your database credentials, JWT secret key, and optional API keys (see [Environment Variables](#environment-variables)).

4. **Apply database migrations**:

   ```bash
   alembic upgrade head
   ```

5. **Start the backend API server**:

   ```bash
   uvicorn app.main:app --reload
   ```

   The backend will be available at `http://127.0.0.1:8000`. You can inspect interactive API documentation at `http://127.0.0.1:8000/docs`.

---

### 3. Frontend Setup

1. **Navigate to the frontend directory**:

   ```bash
   cd frontend
   ```

2. **Install dependencies**:

   ```bash
   npm install
   ```

3. **Configure frontend environment**:

   Create or verify `frontend/.env`:

   ```env
   VITE_API_BASE_URL=http://localhost:8000
   ```

   *(Leave empty or omit if using Vite's development proxy).*

4. **Start the development server**:

   ```bash
   npm run dev
   ```

   The web interface will open at `http://localhost:5173`.

---

## Environment Variables

### Backend Configuration (`.env`)

| Variable | Required | Default | Description |
| :--- | :---: | :---: | :--- |
| `APP_NAME` | No | `RepoPilot AI` | Application title reported in health check and metadata |
| `DEBUG` | No | `true` | Enables FastAPI debug logging |
| `DATABASE_URL` | **Yes** | — | PostgreSQL connection string (`postgresql+psycopg://user:pass@host:5432/dbname`) |
| `JWT_SECRET_KEY` | **Yes** | — | Secret key for signing HS256 access tokens (minimum 32 characters) |
| `CLONE_BASE_DIR` | No | `clones` | Temporary directory on disk where Git clones are stored during discovery |
| `MAX_FILE_SIZE_BYTES` | No | `1048576` | Maximum file size for indexing (1 MB default; larger files are skipped) |
| `MAX_FILE_COUNT` | No | `10000` | Discovery safety ceiling; stops discovery when count is exceeded |
| `MAX_REPO_SIZE_BYTES` | No | `524288000` | Discovery safety ceiling for aggregate repository size (500 MB default) |
| `MAX_DISCOVERY_SECONDS` | No | `300.0` | Maximum timeout in seconds allowed for a single discovery run |
| `EMBEDDING_BATCH_SIZE` | No | `32` | Number of chunks vectorized per provider batch call |
| `EMBEDDING_PROVIDER` | No | `local` | Embedding backend: `local`, `openai`, `voyage`, or `openrouter` |
| `EMBEDDING_MODEL` | No | `all-MiniLM-L6-v2` | Name of the embedding model |
| `EMBEDDING_DIMENSION` | No | `384` | Vector dimension matching the embedding model (`384` for all-MiniLM-L6-v2) |
| `OPENAI_API_KEY` | Optional | — | Required only when `EMBEDDING_PROVIDER=openai` |
| `VOYAGE_API_KEY` | Optional | — | Required only when `EMBEDDING_PROVIDER=voyage` |
| `RETRIEVAL_TOP_K` | No | `5` | Maximum number of relevant code chunks returned per query |
| `RETRIEVAL_SIMILARITY_THRESHOLD` | No | `0.25` | Minimum cosine similarity score below which chunks are discarded |
| `LLM_PROVIDER` | No | `openrouter` | Chat LLM provider service |
| `LLM_MODEL` | No | `particle-ai/particle-1:free` | Model identifier used for grounded generation |
| `OPENROUTER_API_KEY` | **Yes** | — | OpenRouter API key used to synthesize answers |

### Frontend Configuration (`frontend/.env`)

| Variable | Required | Default | Description |
| :--- | :---: | :---: | :--- |
| `VITE_API_BASE_URL` | No | `""` | Base URL for the FastAPI backend (e.g. `http://localhost:8000`) |

---

## Usage Guide

### Web Application Workflow

1. **Sign Up**: Navigate to `/auth` and register a developer account with your email and password.
2. **Register a Repository**: On the **Dashboard**, paste any public GitHub repository URL (e.g., `https://github.com/pallets/click`) and click **Index**.
3. **Monitor Ingestion**: Watch real-time progress indicators as the background worker runs cloning, file discovery, AST chunking, vector embedding, and database storage.
4. **Ask Questions**: Navigate to the **Q&A** tab:
   - Select a specific indexed repository or search across all registered repositories.
   - Enter a natural language query (e.g., *"How does the CLI group command nesting work?"*).
   - Review the generated explanation alongside the exact code files, line numbers, and similarity metrics.

### Core REST API Endpoints

All protected endpoints require an `Authorization: Bearer <token>` header obtained from `/api/auth/login`.

#### Authentication
- `POST /api/auth/register` — Register a new account (`email`, `password`, `role`).
- `POST /api/auth/login` — Authenticate and receive a JWT access token.
- `GET /api/auth/me` — Inspect profile details of the current authenticated user.

#### Repositories & Ingestion
- `POST /api/repositories` — Register a repository and dispatch an indexing job.
- `GET /api/repositories` — List all repositories belonging to the authenticated user.
- `DELETE /api/repositories/{id}` — Delete a repository, purging all files, chunks, embeddings, and jobs.
- `GET /api/repositories/{id}/status` — Fetch repository health and active indexing job state.
- `POST /api/repositories/{id}/jobs` — Trigger a repository re-indexing job.
- `GET /api/repositories/{id}/skips` — List files skipped during discovery and the reason (e.g. secret, binary, oversized).

#### Retrieval & Grounded Q&A
- `POST /api/retrieval/query` — Retrieve top-$k$ raw vector chunks with similarity scores without invoking the LLM.
- `POST /api/chat/ask` — End-to-end grounded Q&A. Retrieves vector chunks and invokes the LLM to generate an evidence-backed answer.

---

## Important Implementation Details

### Atomic Database Swaps
Indexing is completely idempotent and safe against mid-pipeline failures. The background worker generates chunks and file records in memory and performs deletions and insertions within an atomic database transaction. If an error occurs during parsing or embedding, the transaction rolls back, leaving any previously indexed commit intact and functional.

### Worker Concurrency & Idempotency
Background workers utilize PostgreSQL row locks (`SELECT ... FOR UPDATE SKIP LOCKED`). Multiple worker instances or concurrent background threads can run simultaneously without duplicate job execution. Retries for transient issues follow exponential backoff with random jitter, capped at 3 attempts.

### Model Mismatch Protection
Before running semantic retrieval or chat requests, the API compares the configured model dimensions with the database index. If a mismatch is detected (e.g. attempting to query 384-dimensional embeddings using a 1536-dimensional provider), the service returns an explicit `409 Conflict` error prompting a re-index, rather than producing cryptic vector calculation failures.

---

## Current Scope & Limitations

- **Public Repositories**: Indexing currently supports public GitHub repositories over HTTPS.
- **Single-Branch Indexing**: Indexing processes the repository's default branch (`main` or `master`) or the specified branch at registration time.
- **File Exclusions**: Binary files, minified bundles (`*.min.js`), and files exceeding `MAX_FILE_SIZE_BYTES` are skipped to conserve embedding tokens and memory.

---

## Running Tests

RepoPilot AI includes a comprehensive automated test suite covering authentication, security scanning, language parsing, chunk persistence, and vector retrieval.

Execute the test suite with `pytest`:

```bash
# Run all unit and integration tests
pytest

# Run tests with verbose output
pytest -v

# Run a specific test module
pytest tests/test_retrieval_service.py
```

---

## Contributing

Contributions to RepoPilot AI are welcome! Please follow these steps:

1. Fork the repository.
2. Create a feature branch: `git checkout -b feature/your-feature-name`.
3. Commit your changes with clear, descriptive commit messages.
4. Ensure all automated tests pass: `pytest`.
5. Push to your branch and open a Pull Request.

---

## License

This project is licensed under the [MIT License](LICENSE).
