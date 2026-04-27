"""
rag_setup.py – Initialise ChromaDB with IT SOP/runbook documents.
"""

import chromadb
from chromadb.config import Settings

from pathlib import Path

CHROMA_PATH = str(Path(__file__).parent / "chroma_db")

SOPS = [
    {
        "id": "SOP-AD-001",
        "text": (
            "SOP-AD-001: Active Directory Password Reset Procedure. "
            "Verify the user identity by checking their email in the Users table. "
            "If the password_status is 'locked' or 'expired', update it to 'active' "
            "using the reset_password tool. Notify the user upon success. "
            "Do NOT reset passwords without verifying the user exists in the system."
        ),
    },
    {
        "id": "SOP-AD-002",
        "text": (
            "SOP-AD-002: Account Unlock Procedure. "
            "When a user account is locked due to failed login attempts, "
            "first fetch logs from Active Directory to confirm the lockout event. "
            "Then use reset_password to restore the account to active status. "
            "Log all actions in the audit trail."
        ),
    },
    {
        "id": "SOP-AD-003",
        "text": (
            "SOP-AD-003: Standard AD troubleshooting. "
            "To reset AD password, verify user email exists in the Users table, "
            "confirm password_status is not already active, then call reset_password "
            "with the user email. Update ticket status to resolved after success."
        ),
    },
    {
        "id": "SOP-SVC-001",
        "text": (
            "SOP-SVC-001: Service Restart Procedure. "
            "Before restarting any service, fetch and review recent logs to understand the failure. "
            "For non-critical services (VPN Gateway, Email Server, File Share Server): "
            "use restart_service tool directly. "
            "For CRITICAL services (Database Server, Active Directory): "
            "flag as pending_approval – do NOT restart without human approval. "
            "Always generate a report after a service restart."
        ),
    },
    {
        "id": "SOP-SVC-002",
        "text": (
            "SOP-SVC-002: VPN Troubleshooting Runbook. "
            "Step 1: Fetch VPN Gateway logs to identify error patterns. "
            "Step 2: Check for packet loss warnings or tunnel drops. "
            "Step 3: If tunnel drop detected, restart_service 'VPN Gateway'. "
            "Step 4: Confirm service status is 'running' after restart. "
            "Step 5: Update ticket to resolved and generate report."
        ),
    },
    {
        "id": "SOP-LOG-001",
        "text": (
            "SOP-LOG-001: Log Analysis Procedure. "
            "When a log analysis or audit is requested, use fetch_logs with the "
            "relevant system name. Summarise ERROR and WARN entries. "
            "Generate an incident report using generate_report. "
            "Escalate if critical errors are found (e.g., data corruption, security breach)."
        ),
    },
    {
        "id": "SOP-ESC-001",
        "text": (
            "SOP-ESC-001: Escalation Policy. "
            "Tickets must be escalated (status='escalated') when: "
            "1) The issue cannot be resolved with available tools. "
            "2) The system affected is classified as CRITICAL and requires physical intervention. "
            "3) Security incidents are suspected (brute-force, data exfiltration). "
            "Always write escalation reason in the ticket notes."
        ),
    },
    {
        "id": "SOP-RPT-001",
        "text": (
            "SOP-RPT-001: Incident Report Generation. "
            "After resolving any ticket, call generate_report with the ticket_id. "
            "The report includes the ticket subject, system, priority, resolution steps, "
            "and full audit trail. This report is automatically saved to the audit log."
        ),
    },
]


def init_chroma():
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    try:
        client.delete_collection("it_sops")
    except Exception:
        pass

    col = client.create_collection(
        name="it_sops",
        metadata={"hnsw:space": "cosine"},
    )
    col.add(
        documents=[s["text"] for s in SOPS],
        ids=[s["id"] for s in SOPS],
    )
    print(f"  ChromaDB initialised with {len(SOPS)} SOP documents.")
    return client


def get_chroma_retriever():
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    return client.get_or_create_collection("it_sops")


def query_sops(query: str, n_results: int = 3) -> list[str]:
    col = get_chroma_retriever()
    results = col.query(query_texts=[query], n_results=n_results)
    return results["documents"][0] if results["documents"] else []
