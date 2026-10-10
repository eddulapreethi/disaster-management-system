from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.models.user import User
from app.services.assistant_service import answer_question
from app.utils.authentication import get_current_user

router = APIRouter(prefix="/assistant", tags=["assistant"])


class AssistantChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    history: list[dict[str, Any]] | None = None

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
        history = data.history or []
        return answer_question(data.question, db, user, history=history)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
