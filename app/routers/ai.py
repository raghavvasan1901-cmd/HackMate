from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import AIChatIn
from app.security import current_user
from app.services.ai_service import AIService

router = APIRouter(tags=["AI assistant"])


@router.post("/ai/chat")
def chat_with_ai(data: AIChatIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not data.message.strip():
        raise HTTPException(status_code=400, detail="A message is required.")
    result = AIService.generate_response(user=user, db=db, message=data.message.strip(), conversation_id=data.conversation_id)
    return {
        "conversation_id": result["conversation_id"],
        "reply": result["reply"],
        "message": result["reply"],
        "history": result["history"],
    }


@router.get("/ai/conversations")
def list_conversations(user: User = Depends(current_user)):
    return AIService.list_conversations(user.id)


@router.get("/ai/conversations/{conversation_id}")
def get_conversation(conversation_id: str, user: User = Depends(current_user)):
    conversation = AIService.get_conversation(user.id, conversation_id)
    return {"id": conversation_id, "messages": conversation.get("messages", [])}


@router.delete("/ai/conversations/{conversation_id}")
def delete_conversation(conversation_id: str, user: User = Depends(current_user)):
    AIService.delete_conversation(user.id, conversation_id)
    return {"status": "deleted", "conversation_id": conversation_id}
