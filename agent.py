"""
agent.py – LangChain agent with OpenRouter LLM, RAG, and IT tools.
"""

import os
import json
import asyncio
from typing import Any
from dotenv import load_dotenv

from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.tools import StructuredTool
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from . import database as db
from .rag_setup import query_sops

load_dotenv()

# ── Activity feed (in-memory ring buffer shared with FastAPI) ─────────────────
activity_feed: list[dict] = []

def _log_activity(ticket_id: int, step: str, detail: str):
    import datetime
    entry = {
        "ticket_id": ticket_id,
        "step": step,
        "detail": detail,
        "timestamp": datetime.datetime.utcnow().isoformat(),
    }
    activity_feed.append(entry)
    if len(activity_feed) > 200:
        activity_feed.pop(0)

# ── Critical services that require human approval ─────────────────────────────
CRITICAL_SERVICES = {"Database Server", "Active Directory"}

# ── Tool input schemas ────────────────────────────────────────────────────────

class ResetPasswordInput(BaseModel):
    email: str = Field(description="The user email to reset password for")

class RestartServiceInput(BaseModel):
    service_name: str = Field(description="Exact name of the service to restart")

class FetchLogsInput(BaseModel):
    system: str = Field(description="System/service name to fetch logs from")

class GenerateReportInput(BaseModel):
    ticket_id: int = Field(description="Ticket ID to generate report for")

# ── Tool factory (closures capture ticket_id) ─────────────────────────────────

def make_tools(ticket_id: int):

    def reset_password(email: str) -> str:
        _log_activity(ticket_id, "tool:reset_password", f"Resetting password for {email}")
        result = db.reset_password(email)
        db.add_audit_log(ticket_id, f"reset_password({email})", json.dumps(result))
        return json.dumps(result)

    def restart_service(service_name: str) -> str:
        if service_name in CRITICAL_SERVICES:
            msg = (
                f"APPROVAL_REQUIRED: '{service_name}' is a critical service. "
                "Flagging ticket for human approval before proceeding."
            )
            _log_activity(ticket_id, "approval_gate", msg)
            db.update_ticket_status(ticket_id, "pending_approval",
                                    f"Awaiting approval to restart {service_name}")
            db.add_audit_log(ticket_id, f"restart_service({service_name})",
                             "PENDING_APPROVAL – critical service")
            return msg
        _log_activity(ticket_id, "tool:restart_service", f"Restarting {service_name}")
        result = db.restart_service(service_name)
        db.add_audit_log(ticket_id, f"restart_service({service_name})", json.dumps(result))
        return json.dumps(result)

    def fetch_logs(system: str) -> str:
        _log_activity(ticket_id, "tool:fetch_logs", f"Fetching logs for {system}")
        result = db.fetch_logs(system)
        db.add_audit_log(ticket_id, f"fetch_logs({system})",
                         f"Retrieved {len(result.get('logs', []))} log lines")
        return json.dumps(result)

    def generate_report(ticket_id_arg: int) -> str:
        _log_activity(ticket_id, "tool:generate_report",
                      f"Generating report for ticket #{ticket_id_arg}")
        result = db.generate_report(ticket_id_arg)
        db.add_audit_log(ticket_id, f"generate_report({ticket_id_arg})", "Report generated")
        return json.dumps(result)

    return [
        StructuredTool(
            name="reset_password",
            func=reset_password,
            args_schema=ResetPasswordInput,
            description="Reset a user's Active Directory password by email. Use when password is locked or expired.",
        ),
        StructuredTool(
            name="restart_service",
            func=restart_service,
            args_schema=RestartServiceInput,
            description=(
                "Restart an IT service by its exact name. "
                "Critical services (Database Server, Active Directory) will require human approval."
            ),
        ),
        StructuredTool(
            name="fetch_logs",
            func=fetch_logs,
            args_schema=FetchLogsInput,
            description="Retrieve recent log lines for a given system or service.",
        ),
        StructuredTool(
            name="generate_report",
            func=generate_report,
            args_schema=GenerateReportInput,
            description="Generate an incident report for a given ticket ID.",
        ),
    ]


# ── LLM ───────────────────────────────────────────────────────────────────────

def get_llm():
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    model = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o")
    return ChatOpenAI(
        model=model,
        openai_api_key=api_key,
        openai_api_base="https://openrouter.ai/api/v1",
        temperature=0,
        default_headers={
            "HTTP-Referer": "http://localhost:8000",
            "X-Title": "AI Digital Employee",
        },
    )


SYSTEM_PROMPT = """You are an expert AI Digital Employee specialising in IT Operations and Level-1/Level-2 support.

Your job is to autonomously resolve IT support tickets by:
1. Classifying the issue (password reset, service restart, log analysis, etc.)
2. Following the most relevant Standard Operating Procedure (SOP)
3. Using the available tools to execute resolutions safely
4. Updating the ticket status when done

RELEVANT SOPs RETRIEVED FOR THIS TICKET:
{sop_context}

RULES:
- Always verify users exist before resetting passwords.
- Never restart critical services (Database Server, Active Directory) without flagging for approval.
- Fetch logs before restarting any service to understand root cause.
- Always generate a report after resolving a ticket.
- If you cannot resolve the issue, set status to 'escalated' and explain why.
- Be concise and professional in your final summary.
"""


def build_prompt():
    return ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("human", "{input}"),
        MessagesPlaceholder("agent_scratchpad"),
    ])


# ── Main pipeline ─────────────────────────────────────────────────────────────

async def process_ticket(ticket_id: int) -> dict:
    ticket = db.get_ticket(ticket_id)
    if not ticket:
        return {"error": f"Ticket {ticket_id} not found"}

    if ticket["status"] not in ("queued", "in-progress"):
        return {"message": f"Ticket {ticket_id} is already {ticket['status']}"}

    db.update_ticket_status(ticket_id, "in-progress")
    _log_activity(ticket_id, "intake", f"Processing ticket: {ticket['subject']}")

    # RAG retrieval
    query = f"{ticket['subject']} {ticket.get('system', '')}"
    sops = query_sops(query, n_results=3)
    sop_context = (
        "\n\n".join(sops)
        if sops
        else "No specific SOPs found – use general IT best practices."
    )
    _log_activity(ticket_id, "rag_retrieval",
                  f"Retrieved {len(sops)} relevant SOP(s) from knowledge base")

    task_prompt = (
        f"Ticket ID: {ticket_id}\n"
        f"Reported by: {ticket.get('user_name', 'Unknown')} <{ticket.get('user_email', '')}>\n"
        f"Subject: {ticket['subject']}\n"
        f"System: {ticket.get('system', 'Unknown')}\n"
        f"Priority: {ticket['priority']}\n\n"
        "Please diagnose and resolve this ticket using the available tools. "
        "After resolution, generate a report."
    )

    tools = make_tools(ticket_id)
    llm = get_llm()
    prompt = build_prompt().partial(sop_context=sop_context)
    agent = create_openai_functions_agent(llm=llm, tools=tools, prompt=prompt)
    executor = AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=True,
        max_iterations=8,
        return_intermediate_steps=True,
        handle_parsing_errors=True,
    )

    _log_activity(ticket_id, "agent_start", "LangChain agent invoked")

    try:
        result = await asyncio.to_thread(
            executor.invoke, {"input": task_prompt}
        )
        output = result.get("output", "Agent completed without output.")

        # Only mark resolved if not already pending_approval
        current = db.get_ticket(ticket_id)
        if current and current["status"] not in ("pending_approval", "escalated"):
            db.update_ticket_status(ticket_id, "resolved", output[:500])

        _log_activity(ticket_id, "agent_complete", output[:300])
        db.add_audit_log(ticket_id, "agent_complete", output[:500])

        return {
            "ticket_id": ticket_id,
            "status": db.get_ticket(ticket_id)["status"],
            "output": output,
            "steps": len(result.get("intermediate_steps", [])),
        }

    except Exception as e:
        err = str(e)
        db.update_ticket_status(ticket_id, "escalated", f"Agent error: {err[:300]}")
        db.add_audit_log(ticket_id, "agent_error", err[:500])
        _log_activity(ticket_id, "agent_error", err[:200])
        return {"ticket_id": ticket_id, "status": "escalated", "error": err}


async def approve_action(ticket_id: int) -> dict:
    """Human approves a pending_approval ticket – execute the deferred service restart."""
    ticket = db.get_ticket(ticket_id)
    if not ticket or ticket["status"] != "pending_approval":
        return {"error": "Ticket is not pending approval"}

    _log_activity(ticket_id, "approval_granted", f"Human approved action for ticket #{ticket_id}")
    db.add_audit_log(ticket_id, "human_approval", "APPROVED by operator")

    # Extract service name from notes
    notes = ticket.get("notes", "")
    service_name = None
    for svc in ("Database Server", "Active Directory"):
        if svc in notes:
            service_name = svc
            break

    if service_name:
        result = db.restart_service(service_name)
        db.add_audit_log(ticket_id, f"restart_service({service_name})", json.dumps(result))
        _log_activity(ticket_id, "tool:restart_service",
                      f"Post-approval restart of {service_name}: {result['message']}")
        db.update_ticket_status(ticket_id, "resolved",
                                f"Approved and restarted {service_name}: {result['message']}")
    else:
        db.update_ticket_status(ticket_id, "resolved", "Approved by operator")

    db.generate_report(ticket_id)
    return {"ticket_id": ticket_id, "status": "resolved", "message": "Action approved and executed"}


async def reject_action(ticket_id: int) -> dict:
    """Human rejects a pending_approval ticket."""
    ticket = db.get_ticket(ticket_id)
    if not ticket or ticket["status"] != "pending_approval":
        return {"error": "Ticket is not pending approval"}

    _log_activity(ticket_id, "approval_rejected", f"Human rejected action for ticket #{ticket_id}")
    db.add_audit_log(ticket_id, "human_rejection", "REJECTED by operator")
    db.update_ticket_status(ticket_id, "escalated", "Action rejected by operator – escalated for manual review")
    return {"ticket_id": ticket_id, "status": "escalated", "message": "Action rejected and escalated"}
