# AI Digital Employee – IT Operations

Autonomous AI agent for Level-1/Level-2 IT support, powered by LangChain + OpenRouter + ChromaDB + FastAPI.

## Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure API key
```bash
cp .env.example .env
# Edit .env and paste your OpenRouter API key
```

### 3. Run the application
```bash
python main.py
# OR
uvicorn main:app --reload --port 8000
```

### 4. Open the dashboard
Visit: http://localhost:8000/dashboard

---

## Architecture

```
Ticket Submitted
      │
      ▼
FastAPI (/api/tickets/{id}/process)
      │
      ▼
LangChain Agent (OpenRouter LLM)
      │
      ├── ChromaDB (RAG – SOP/Runbook retrieval)
      │
      ├── Tools:
      │     reset_password   → SQLite Users table
      │     restart_service  → SQLite Services table (critical = pending_approval)
      │     fetch_logs       → Mock log generator
      │     generate_report  → AuditLogs + ticket summary
      │
      └── SQLite (tickets, audit logs, users, services)
```

## Project Structure

```
AI_Digital_Employee/
├── main.py          # FastAPI app
├── agent.py         # LangChain agent + tools
├── database.py      # SQLite helpers + seed data
├── rag_setup.py     # ChromaDB initialisation + SOP documents
├── seed.py          # Standalone DB seeder
├── requirements.txt
├── .env.example
├── mock_itsm.db     # Auto-created on first run
├── chroma_db/       # Auto-created on first run
└── templates/
    └── index.html   # Single-page dashboard
```

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET  | /api/tickets | List all tickets |
| POST | /api/tickets | Create new ticket |
| POST | /api/tickets/{id}/process | Trigger AI agent |
| POST | /api/tickets/{id}/approve | Approve pending action |
| POST | /api/tickets/{id}/reject  | Reject pending action |
| GET  | /api/activity | Agent activity feed |
| GET  | /api/stats    | Dashboard statistics |
| GET  | /api/audit-logs | Full audit trail |
| GET  | /api/servicenow/incidents | Mock ServiceNow incidents |
| GET  | /api/servicenow/cmdb/services | Mock CMDB services |

## Models (OpenRouter)

Change `OPENROUTER_MODEL` in `.env`:
- `openai/gpt-4o` (default – best results)
- `mistralai/mistral-7b-instruct` (fast, free tier)
- `anthropic/claude-3-haiku` (fast, capable)
- `meta-llama/llama-3-8b-instruct` (open source)
