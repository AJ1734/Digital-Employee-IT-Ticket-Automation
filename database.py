"""
database.py – SQLite setup, seed data, and all DB helper functions.
"""

import sqlite3
import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "mock_itsm.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create all tables."""
    conn = get_conn()
    c = conn.cursor()

    c.executescript("""
        CREATE TABLE IF NOT EXISTS Users (
            user_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            name      TEXT NOT NULL,
            email     TEXT UNIQUE NOT NULL,
            password_status TEXT DEFAULT 'active'
        );

        CREATE TABLE IF NOT EXISTS Services (
            service_name  TEXT PRIMARY KEY,
            status        TEXT DEFAULT 'running',
            last_restart  TEXT
        );

        CREATE TABLE IF NOT EXISTS Tickets (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER,
            subject     TEXT NOT NULL,
            system      TEXT,
            priority    TEXT DEFAULT 'medium',
            status      TEXT DEFAULT 'queued',
            created_at  TEXT,
            resolved_at TEXT,
            notes       TEXT,
            FOREIGN KEY(user_id) REFERENCES Users(user_id)
        );

        CREATE TABLE IF NOT EXISTS AuditLogs (
            log_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id   INTEGER,
            action      TEXT,
            timestamp   TEXT,
            result      TEXT,
            FOREIGN KEY(ticket_id) REFERENCES Tickets(id)
        );
    """)
    conn.commit()
    conn.close()


def seed_db():
    """Populate mock data (idempotent)."""
    conn = get_conn()
    c = conn.cursor()

    # Users
    users = [
        ("Alice Johnson",   "alice@corp.com",   "active"),
        ("Bob Martinez",    "bob@corp.com",     "locked"),
        ("Carol Singh",     "carol@corp.com",   "active"),
        ("David Lee",       "david@corp.com",   "expired"),
        ("Eve Williams",    "eve@corp.com",     "active"),
        ("Frank Brown",     "frank@corp.com",   "locked"),
        ("Grace Kim",       "grace@corp.com",   "active"),
        ("Hank Patel",      "hank@corp.com",    "active"),
        ("Iris Nguyen",     "iris@corp.com",    "expired"),
        ("Jack Thompson",   "jack@corp.com",    "active"),
    ]
    for name, email, status in users:
        c.execute(
            "INSERT OR IGNORE INTO Users(name,email,password_status) VALUES(?,?,?)",
            (name, email, status),
        )

    # Services
    services = [
        ("Active Directory",    "running",  "2024-06-01 08:00:00"),
        ("Email Server",        "running",  "2024-06-10 14:30:00"),
        ("VPN Gateway",         "degraded", "2024-06-12 09:15:00"),
        ("File Share Server",   "running",  "2024-06-05 11:00:00"),
        ("Database Server",     "running",  "2024-06-08 16:45:00"),
    ]
    for svc, st, lr in services:
        c.execute(
            "INSERT OR IGNORE INTO Services(service_name,status,last_restart) VALUES(?,?,?)",
            (svc, st, lr),
        )

    # Tickets (only if none exist)
    if c.execute("SELECT COUNT(*) FROM Tickets").fetchone()[0] == 0:
        now = datetime.datetime.utcnow().isoformat()
        tickets = [
            (2, "Cannot login – password expired",     "Active Directory", "high",   "queued"),
            (6, "Password locked after failed attempts","Active Directory", "high",   "queued"),
            (3, "VPN keeps disconnecting",             "VPN Gateway",       "medium", "queued"),
            (1, "Need logs for security audit",        "Email Server",      "low",    "queued"),
            (9, "Account password expired",            "Active Directory",  "medium", "queued"),
        ]
        for uid, subj, sys, pri, st in tickets:
            c.execute(
                "INSERT INTO Tickets(user_id,subject,system,priority,status,created_at) "
                "VALUES(?,?,?,?,?,?)",
                (uid, subj, sys, pri, st, now),
            )

    conn.commit()
    conn.close()


# ── Tool helpers ──────────────────────────────────────────────────────────────

def reset_password(email: str) -> dict:
    conn = get_conn()
    c = conn.cursor()
    row = c.execute("SELECT * FROM Users WHERE email=?", (email,)).fetchone()
    if not row:
        conn.close()
        return {"success": False, "message": f"User {email} not found."}
    c.execute("UPDATE Users SET password_status='active' WHERE email=?", (email,))
    conn.commit()
    conn.close()
    return {"success": True, "message": f"Password reset for {email}. Status set to active."}


def restart_service(service_name: str) -> dict:
    conn = get_conn()
    c = conn.cursor()
    row = c.execute(
        "SELECT * FROM Services WHERE service_name=?", (service_name,)
    ).fetchone()
    if not row:
        conn.close()
        return {"success": False, "message": f"Service '{service_name}' not found."}
    now = datetime.datetime.utcnow().isoformat()
    c.execute(
        "UPDATE Services SET status='running', last_restart=? WHERE service_name=?",
        (now, service_name),
    )
    conn.commit()
    conn.close()
    return {
        "success": True,
        "message": f"Service '{service_name}' restarted successfully at {now}.",
    }


def fetch_logs(system: str) -> dict:
    mock_logs = {
        "Active Directory": [
            "2024-06-14 08:12:01 [INFO]  Authentication request from alice@corp.com – SUCCESS",
            "2024-06-14 08:14:33 [WARN]  Failed login attempt for bob@corp.com (attempt 3/5)",
            "2024-06-14 08:15:01 [ERROR] Account locked: bob@corp.com – too many failures",
            "2024-06-14 08:30:22 [INFO]  Password reset initiated for iris@corp.com",
            "2024-06-14 09:00:00 [INFO]  AD replication sync completed successfully",
        ],
        "Email Server": [
            "2024-06-14 07:55:00 [INFO]  SMTP service started",
            "2024-06-14 08:00:01 [INFO]  2847 messages queued for delivery",
            "2024-06-14 08:22:15 [WARN]  Delivery delay detected – queue length 500+",
            "2024-06-14 08:45:00 [INFO]  Queue normalised – 12 messages pending",
            "2024-06-14 09:10:33 [INFO]  TLS handshake with external relay – OK",
        ],
        "VPN Gateway": [
            "2024-06-14 08:00:00 [INFO]  VPN service started",
            "2024-06-14 08:17:44 [WARN]  High packet loss detected (8.3%)",
            "2024-06-14 08:18:00 [ERROR] Tunnel to 10.0.0.5 dropped unexpectedly",
            "2024-06-14 08:20:30 [INFO]  Reconnection attempt 1/3 – FAILED",
            "2024-06-14 08:21:15 [INFO]  Reconnection attempt 2/3 – SUCCESS",
        ],
        "File Share Server": [
            "2024-06-14 08:05:00 [INFO]  NFS exports loaded",
            "2024-06-14 08:30:00 [INFO]  Disk usage: 72% on /vol/share1",
            "2024-06-14 08:55:00 [WARN]  Disk usage: 89% on /vol/archive – threshold exceeded",
            "2024-06-14 09:01:00 [INFO]  Backup job started for /vol/share1",
        ],
        "Database Server": [
            "2024-06-14 07:00:00 [INFO]  PostgreSQL 15.3 started",
            "2024-06-14 08:00:00 [INFO]  Checkpoint completed – WAL size 128 MB",
            "2024-06-14 08:45:00 [WARN]  Long query detected (12.4 s): SELECT * FROM audit_events",
            "2024-06-14 09:00:00 [INFO]  Autovacuum completed on 3 tables",
        ],
    }
    logs = mock_logs.get(
        system,
        [f"2024-06-14 09:00:00 [INFO]  No specific logs found for system: {system}"],
    )
    return {"system": system, "logs": logs}


def generate_report(ticket_id: int) -> dict:
    conn = get_conn()
    ticket = conn.execute(
        "SELECT * FROM Tickets WHERE id=?", (ticket_id,)
    ).fetchone()
    logs = conn.execute(
        "SELECT * FROM AuditLogs WHERE ticket_id=? ORDER BY timestamp",
        (ticket_id,),
    ).fetchall()
    conn.close()
    if not ticket:
        return {"error": f"Ticket {ticket_id} not found."}
    return {
        "report": {
            "ticket_id": ticket_id,
            "subject": ticket["subject"],
            "system": ticket["system"],
            "priority": ticket["priority"],
            "status": ticket["status"],
            "created_at": ticket["created_at"],
            "resolved_at": ticket["resolved_at"],
            "audit_trail": [dict(l) for l in logs],
        }
    }


def update_ticket_status(ticket_id: int, status: str, notes: str = ""):
    conn = get_conn()
    now = datetime.datetime.utcnow().isoformat()
    resolved_at = now if status == "resolved" else None
    conn.execute(
        "UPDATE Tickets SET status=?, notes=?, resolved_at=? WHERE id=?",
        (status, notes, resolved_at, ticket_id),
    )
    conn.commit()
    conn.close()


def add_audit_log(ticket_id: int, action: str, result: str):
    conn = get_conn()
    now = datetime.datetime.utcnow().isoformat()
    conn.execute(
        "INSERT INTO AuditLogs(ticket_id,action,timestamp,result) VALUES(?,?,?,?)",
        (ticket_id, action, now, result),
    )
    conn.commit()
    conn.close()


def get_all_tickets() -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT t.*, u.name as user_name, u.email as user_email "
        "FROM Tickets t LEFT JOIN Users u ON t.user_id=u.user_id "
        "ORDER BY t.id DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_ticket(ticket_id: int) -> dict | None:
    conn = get_conn()
    row = conn.execute(
        "SELECT t.*, u.name as user_name, u.email as user_email "
        "FROM Tickets t LEFT JOIN Users u ON t.user_id=u.user_id "
        "WHERE t.id=?",
        (ticket_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_stats() -> dict:
    conn = get_conn()
    today = datetime.date.today().isoformat()
    total = conn.execute("SELECT COUNT(*) FROM Tickets").fetchone()[0]
    resolved = conn.execute(
        "SELECT COUNT(*) FROM Tickets WHERE status='resolved'"
    ).fetchone()[0]
    today_count = conn.execute(
        "SELECT COUNT(*) FROM Tickets WHERE created_at LIKE ?", (f"{today}%",)
    ).fetchone()[0]
    pending = conn.execute(
        "SELECT COUNT(*) FROM Tickets WHERE status='pending_approval'"
    ).fetchone()[0]
    conn.close()
    resolve_rate = round((resolved / total * 100) if total else 0, 1)
    return {
        "total_tickets": total,
        "resolved": resolved,
        "auto_resolve_rate": resolve_rate,
        "tickets_today": today_count,
        "pending_approval": pending,
    }


def get_audit_logs(limit: int = 50) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT al.*, t.subject FROM AuditLogs al "
        "LEFT JOIN Tickets t ON al.ticket_id=t.id "
        "ORDER BY al.timestamp DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
