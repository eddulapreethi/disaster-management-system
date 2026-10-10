import os
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.models.user import User
from app.services.assistant_provider import AssistantProviderNotConfigured, get_assistant_provider
from app.services.assistant_service import answer_question
from app.utils.authentication import get_current_user

router = APIRouter(prefix="/assistant", tags=["assistant"])


class AssistantHistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field(min_length=1, max_length=4000)

    @field_validator("text")
    @classmethod
    def validate_text(cls, text: str) -> str:
        text = text.strip()
        if not text:
            raise ValueError("Conversation messages cannot be empty.")
        return text


class AssistantChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    history: list[AssistantHistoryMessage] | None = Field(default=None, max_length=8)

    @field_validator("question")
    @classmethod
    def validate_question(cls, question: str) -> str:
        question = question.strip()
        if not question:
            raise ValueError("Enter a question.")
        return question


@router.post("/chat")
def chat(
    data: AssistantChatRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        history = [message.model_dump() for message in data.history or []]
        return answer_question(data.question, db, user, history=history)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/status")
def assistant_status(user: User = Depends(get_current_user)):
    _ = user
    try:
        return get_assistant_provider().status()
    except (AssistantProviderNotConfigured, ValueError) as error:
        return {
            "provider": os.getenv("DISASTERGUARD_ASSISTANT_PROVIDER", "ollama"),
            "model": os.getenv("DISASTERGUARD_ASSISTANT_MODEL", "qwen2.5:3b"),
            "reachable": False,
            "model_available": False,
            "status": "misconfigured",
            "message": str(error),
        }
