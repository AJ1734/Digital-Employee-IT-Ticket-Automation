"""
main.py – FastAPI application: REST API + static dashboard.
"""

import os
import asyncio
import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

from . import database as db
from .rag_setup import init_chroma
from .agent import process_ticket, approve_action, reject_action, activity_feed

# ── Startup ───────────────────────────────────────────────────────────────────

app = FastAPI(
    title="AI Digital Employee – IT Operations",
    description="Autonomous IT ticket resolution powered by LangChain + OpenRouter",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

TEMPLATES_DIR = Path(__file__).parent / "templates"


@app.on_event("startup")
async def startup_event():
    print("Initialising databases...")
    db.init_db()
    db.seed_db()
    init_chroma()
    print("AI Digital Employee is ready.")


# ── Static files & dashboard ─────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root():
    return FileResponse(TEMPLATES_DIR / "index.html")


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    return FileResponse(TEMPLATES_DIR / "index.html")


# ── API – Tickets ─────────────────────────────────────────────────────────────

@app.get("/api/tickets")
async def get_tickets():
    return {"tickets": db.get_all_tickets()}


@app.get("/api/tickets/{ticket_id}")
async def get_ticket(ticket_id: int):
    ticket = db.get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


class NewTicket(BaseModel):
    user_email: str
    subject: str
    system: str
    priority: Optional[str] = "medium"


@app.post("/api/tickets")
async def create_ticket(payload: NewTicket):
    conn = db.get_conn()
    user = conn.execute(
        "SELECT user_id FROM Users WHERE email=?", (payload.user_email,)
    ).fetchone()
    conn.close()

    user_id = user["user_id"] if user else None
    conn = db.get_conn()
    now = datetime.datetime.utcnow().isoformat()
    cur = conn.execute(
        "INSERT INTO Tickets(user_id,subject,system,priority,status,created_at) "
        "VALUES(?,?,?,?,?,?)",
        (user_id, payload.subject, payload.system, payload.priority, "queued", now),
    )
    ticket_id = cur.lastrowid
    conn.commit()
    conn.close()
    return {"ticket_id": ticket_id, "status": "queued"}


@app.post("/api/tickets/{ticket_id}/process")
async def trigger_processing(ticket_id: int, background_tasks: BackgroundTasks):
    ticket = db.get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if ticket["status"] == "in-progress":
        return {"message": "Already processing"}

    background_tasks.add_task(_run_agent, ticket_id)
    db.update_ticket_status(ticket_id, "in-progress")
    return {"ticket_id": ticket_id, "message": "Processing started"}


async def _run_agent(ticket_id: int):
    await process_ticket(ticket_id)


@app.post("/api/tickets/{ticket_id}/approve")
async def approve_ticket(ticket_id: int):
    result = await approve_action(ticket_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/api/tickets/{ticket_id}/reject")
async def reject_ticket(ticket_id: int):
    result = await reject_action(ticket_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ── API – Activity feed & stats ───────────────────────────────────────────────

@app.get("/api/activity")
async def get_activity(limit: int = 50):
    return {"activity": list(reversed(activity_feed[-limit:]))}


@app.get("/api/stats")
async def get_stats():
    return db.get_stats()


@app.get("/api/audit-logs")
async def get_audit_logs(limit: int = 50):
    return {"logs": db.get_audit_logs(limit)}


# ── Mock ServiceNow-style endpoints ──────────────────────────────────────────

@app.get("/api/servicenow/incidents")
async def sn_incidents():
    """Mock ServiceNow incident list endpoint."""
    tickets = db.get_all_tickets()
    return {
        "result": [
            {
                "number": f"INC{str(t['id']).zfill(7)}",
                "short_description": t["subject"],
                "state": t["status"],
                "priority": t["priority"],
                "sys_created_on": t["created_at"],
            }
            for t in tickets
        ]
    }


@app.get("/api/servicenow/cmdb/services")
async def sn_services():
    """Mock ServiceNow CMDB services endpoint."""
    conn = db.get_conn()
    svcs = conn.execute("SELECT * FROM Services").fetchall()
    conn.close()
    return {"result": [dict(s) for s in svcs]}


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    host = os.getenv("APP_HOST", "0.0.0.0")
    port = int(os.getenv("APP_PORT", 8000))
    uvicorn.run("main:app", host=host, port=port, reload=True)
