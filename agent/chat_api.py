"""Sal's chat brain over HTTP for the dashboard (D-010: same Sal everywhere).

Mount in ui/server:  from agent.chat_api import router as sal_chat_router; app.include_router(sal_chat_router)
Or standalone:       uv run uvicorn agent.chat_api:app --port 8103

POST /chat                 {"chat_id": "ui", "text": "...", "actor": "owner"} -> {reply, needs_owner, why[], actions[], orders[]}
POST /chat/decide          {"chat_id": "ui", "approved": true}  -> same shape (the owner's answer to the open ask)
GET  /chat/{chat_id}/history  last 20 turns       GET /chat/{chat_id}/waiting  actions waiting on the owner
"""
from __future__ import annotations

import asyncio
from dataclasses import asdict

from fastapi import APIRouter, FastAPI
from pydantic import BaseModel

from agent import chat

router = APIRouter(tags=["sal-chat"])


class ChatIn(BaseModel):
    chat_id: str = "ui"
    text: str
    actor: str = "owner"


class DecideIn(BaseModel):
    chat_id: str = "ui"
    approved: bool = True


def _out(r: chat.ChatReply) -> dict:
    d = asdict(r)
    return {"reply": d["text"], "needs_owner": d["needs_owner"], "why": d["why"], "persona_url": d["persona_url"],
            "actions": d["actions"], "orders": d["orders"], "error": d["error"]}


async def _run(chat_id: str, text: str, actor: str) -> dict:
    # run in a worker thread: the turn does sync event POSTs (possibly to this same server) and its own loop
    r = await asyncio.to_thread(chat.run_chat, chat_id, text, None, actor=actor, channel="ui")
    return _out(r)


@router.post("/chat")
async def post_chat(body: ChatIn) -> dict:
    return await _run(body.chat_id, body.text, body.actor)


@router.post("/chat/decide")
async def post_decide(body: DecideIn) -> dict:
    return await _run(body.chat_id, "Approved, go ahead." if body.approved else "Declined. Don't order it.", "owner")


@router.get("/chat/{chat_id}/history")
def get_history(chat_id: str) -> dict:
    return {"turns": chat.load_history(chat_id)}


@router.get("/chat/{chat_id}/waiting")
def get_waiting(chat_id: str) -> dict:
    return {"waiting": chat.waiting_items(chat_id)}


app = FastAPI(title="Sal chat")
app.include_router(router)
