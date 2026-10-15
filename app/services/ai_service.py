import os
import json
import logging
import threading
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import HTTPException
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types
from openai import APIError, APITimeoutError, OpenAI, RateLimitError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Team, TeamMember, User
from app.services.common import profile_data


logger = logging.getLogger(__name__)
DEFAULT_SYSTEM_INSTRUCTION = (
    "You are HackMate AI, an intelligent hackathon collaboration assistant. "
    "Help with team formation, complementary skills, hackathon discovery, project ideas, "
    "teamwork, technical planning, and learning roadmaps. Give clear, practical, "
    "beginner-friendly advice. Use only supplied app context for personal or current "
    "HackMate data. Never claim to create or change records, invent events or users, "
    "or produce shell commands or SQL."
)


class AIService:
    _conversations: dict[int, dict[str, dict[str, Any]]] = defaultdict(dict)
    _requests: dict[int, deque[float]] = defaultdict(deque)
    _rate_lock = threading.Lock()
    _requests_per_minute = 10
    _max_conversations_per_user = 20
    _max_messages_per_conversation = 40

    @staticmethod
    def _provider_config() -> tuple[str, str, str]:
        provider = (os.getenv("AI_PROVIDER") or "openai").strip().lower()
        api_key = (os.getenv("AI_API_KEY") or "").strip()
        default_model = "gemini-2.5-flash" if provider == "gemini" else "gpt-4o-mini"
        model = (os.getenv("AI_MODEL") or default_model).strip()
        if provider not in {"gemini", "openai"}:
            raise HTTPException(
                status_code=503,
                detail="HackMate AI has an unsupported provider configured. Set AI_PROVIDER to gemini or openai.",
            )
        if not api_key or not model:
            raise HTTPException(
                status_code=503,
                detail="HackMate AI is not configured. Set AI_PROVIDER, AI_API_KEY, and AI_MODEL in the project-root .env file.",
            )
        return provider, api_key, model

    @staticmethod
    def _system_instruction() -> str:
        return (os.getenv("AI_SYSTEM_INSTRUCTION") or DEFAULT_SYSTEM_INSTRUCTION).strip()

    @staticmethod
    def _raise_provider_error(provider: str, error: Exception) -> None:
        if isinstance(error, (APITimeoutError, TimeoutError, httpx.TimeoutException)):
            logger.warning("AI provider request timed out (provider=%s)", provider)
            raise HTTPException(
                status_code=504,
                detail="The AI provider took too long to respond. Please try again.",
            ) from error

        status = getattr(error, "code", None) or getattr(error, "status_code", None)
        try:
            status = int(status)
        except (TypeError, ValueError):
            status = None

        if status in {408, 504}:
            logger.warning("AI provider request timed out (provider=%s)", provider)
            raise HTTPException(
                status_code=504,
                detail="The AI provider took too long to respond. Please try again.",
            ) from error
        if status == 429 or isinstance(error, RateLimitError):
            logger.warning("AI provider rate limit reached (provider=%s)", provider)
            raise HTTPException(
                status_code=503,
                detail="The AI provider is busy or its quota is temporarily exhausted. Please try again shortly.",
                headers={"Retry-After": "30"},
            ) from error
        if status in {401, 403}:
            logger.error("AI provider rejected its configured credentials (provider=%s)", provider)
            raise HTTPException(
                status_code=502,
                detail="The AI provider rejected its API key. Check AI_API_KEY in the project-root .env file.",
            ) from error
        if status == 404:
            logger.error("AI provider could not find the configured model (provider=%s)", provider)
            raise HTTPException(
                status_code=502,
                detail="The configured AI model is unavailable. Check AI_MODEL and confirm it is enabled for your account.",
            ) from error

        logger.warning(
            "AI provider request failed (provider=%s, error_type=%s)",
            provider,
            type(error).__name__,
        )
        raise HTTPException(
            status_code=502,
            detail="The AI provider is unavailable right now. Please try again in a moment.",
        ) from error

    @staticmethod
    def _generate_text(
        provider: str,
        api_key: str,
        model: str,
        system_instruction: str,
        prompt: str,
        history: list[dict[str, str]],
        timeout: float,
        max_tokens: int,
        temperature: float,
        json_response: bool = False,
    ) -> str:
        try:
            if provider == "openai":
                client = OpenAI(api_key=api_key, timeout=timeout, max_retries=1)
                completion = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_instruction},
                        *[
                            {
                                "role": "assistant" if item["role"] == "assistant" else "user",
                                "content": item["content"],
                            }
                            for item in history
                        ],
                        {"role": "user", "content": prompt},
                    ],
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **({"response_format": {"type": "json_object"}} if json_response else {}),
                )
                answer = completion.choices[0].message.content
            else:
                contents = [
                    genai_types.Content(
                        role="model" if item["role"] == "assistant" else "user",
                        parts=[genai_types.Part.from_text(text=item["content"])],
                    )
                    for item in history
                ]
                contents.append(
                    genai_types.Content(
                        role="user",
                        parts=[genai_types.Part.from_text(text=prompt)],
                    )
                )
                client = genai.Client(
                    api_key=api_key,
                    http_options=genai_types.HttpOptions(timeout=int(timeout * 1000)),
                )
                try:
                    response = client.models.generate_content(
                        model=model,
                        contents=contents,
                        config=genai_types.GenerateContentConfig(
                            system_instruction=system_instruction,
                            temperature=temperature,
                            max_output_tokens=max_tokens,
                            response_mime_type="application/json" if json_response else None,
                        ),
                    )
                    answer = response.text
                finally:
                    client.close()
        except (APITimeoutError, TimeoutError, httpx.TimeoutException) as exc:
            AIService._raise_provider_error(provider, exc)
        except (APIError, genai_errors.APIError, OSError, httpx.HTTPError) as exc:
            AIService._raise_provider_error(provider, exc)
        except (AttributeError, IndexError, TypeError, ValueError) as exc:
            logger.warning("AI provider returned an invalid response (provider=%s)", provider)
            raise HTTPException(
                status_code=502,
                detail="The AI provider could not provide a usable response. Please try rephrasing your message.",
            ) from exc
        if not isinstance(answer, str) or not answer.strip():
            logger.warning("AI provider returned an empty response (provider=%s)", provider)
            raise HTTPException(
                status_code=502,
                detail="The AI provider could not provide a response to that message. Please try rephrasing it.",
            )
        return answer.strip()

    @staticmethod
    def _check_rate_limit(user_id: int) -> None:
        now = time.monotonic()
        with AIService._rate_lock:
            cutoff = now - 60
            expired_users = []
            for account_id, requests in AIService._requests.items():
                while requests and requests[0] <= cutoff:
                    requests.popleft()
                if not requests:
                    expired_users.append(account_id)
            for account_id in expired_users:
                del AIService._requests[account_id]
            requests = AIService._requests.setdefault(user_id, deque())
            if len(requests) >= AIService._requests_per_minute:
                raise HTTPException(
                    status_code=429,
                    detail="You've sent several messages recently. Please wait a minute and try again.",
                    headers={"Retry-After": "60"},
                )
            requests.append(now)

    @staticmethod
    def explain_matches(user: User, matches: list[dict[str, Any]]) -> dict[str, Any]:
        try:
            provider, api_key, model = AIService._provider_config()
        except HTTPException:
            return {"status": "missing_credentials", "explanations": []}
        if not matches:
            return {"status": "no_recommendations", "explanations": []}
        try:
            AIService._check_rate_limit(user.id)
        except HTTPException as exc:
            if exc.status_code == 429:
                return {"status": "rate_limited", "explanations": []}
            raise
        try:
            timeout = min(60.0, max(5.0, float(os.getenv("AI_TIMEOUT_SECONDS", "20"))))
            output_tokens = min(700, max(64, int(os.getenv("AI_MAX_TOKENS", "400"))))
        except ValueError:
            return {"status": "invalid_configuration", "explanations": []}

        candidates = [
            {
                "index": index,
                "skills_that_fill_team_gaps": match.get("missing_skills_candidate_contributes", []),
                "matching_skills": match.get("strong_matching_skills", []),
                "role_fit": match.get("role_compatibility", False),
                "availability_stated": match.get("availability_compatibility", False),
                "relevant_self_reported_experience": [
                    {
                        "project": history.get("project_title", ""),
                        "role": history.get("team_role", ""),
                        "technologies": history.get("technologies", []),
                    }
                    for history in match.get("relevant_hackathon_experience", [])
                ],
                "relevant_self_reported_projects": [
                    {
                        "title": project.get("title", ""),
                        "technologies": project.get("technologies", []),
                    }
                    for project in match.get("relevant_project_experience", [])
                ],
                "rating_sample": match.get("reputation", {}),
            }
            for index, match in enumerate(matches)
        ]
        prompt = (
            "Write one concise, evidence-grounded teammate fit explanation for each item. "
            "Use only the supplied fields; do not infer personality, success, skill mastery, or facts. "
            "Never create or alter a compatibility score. Mention that experience is self-reported where used. "
            "Return only JSON as an array of objects with integer index and explanation string. "
            f"Candidate facts: {json.dumps(candidates, ensure_ascii=True)}"
        )
        try:
            content = AIService._generate_text(
                provider=provider,
                api_key=api_key,
                model=model,
                system_instruction="Explain teammate recommendations from evidence only. Return valid JSON.",
                prompt=prompt,
                history=[],
                timeout=timeout,
                max_tokens=output_tokens,
                temperature=0.2,
                json_response=True,
            )
            parsed = json.loads(content)
            if not isinstance(parsed, list):
                return {"status": "invalid_provider_response", "explanations": []}
            explanation_map: dict[int, str] = {}
            for entry in parsed:
                if not isinstance(entry, dict) or not isinstance(entry.get("index"), int):
                    continue
                explanation = entry.get("explanation")
                index = entry["index"]
                if isinstance(explanation, str) and 0 <= index < len(matches):
                    explanation_map[index] = explanation.strip()[:500]
            return {
                "status": "available" if explanation_map else "invalid_provider_response",
                "explanations": [explanation_map.get(index) for index in range(len(matches))],
            }
        except HTTPException as exc:
            status = "provider_timeout" if exc.status_code == 504 else (
                "provider_rate_limited" if exc.status_code == 503 else "provider_unavailable"
            )
            return {"status": status, "explanations": []}
        except (ValueError, AttributeError, IndexError, TypeError):
            return {"status": "provider_unavailable", "explanations": []}

    @staticmethod
    def create_conversation(user_id: int, conversation_id: str | None = None) -> str:
        user_store = AIService._conversations.setdefault(user_id, {})
        if conversation_id:
            if conversation_id not in user_store:
                raise HTTPException(status_code=404, detail="Conversation not found")
            return conversation_id
        if len(user_store) >= AIService._max_conversations_per_user:
            oldest_id = min(user_store, key=lambda item: user_store[item]["created_at"])
            del user_store[oldest_id]
        new_id = uuid.uuid4().hex
        user_store[new_id] = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "messages": [],
        }
        return new_id

    @staticmethod
    def list_conversations(user_id: int) -> list[dict[str, Any]]:
        user_store = AIService._conversations.get(user_id, {})
        items: list[dict[str, Any]] = []
        for conversation_id, payload in user_store.items():
            messages = payload.get("messages", [])
            preview = messages[-1]["content"] if messages else "New conversation"
            items.append({
                "id": conversation_id,
                "preview": preview[:80],
                "updated_at": payload.get("updated_at"),
            })
        return sorted(items, key=lambda item: item["updated_at"] or "", reverse=True)

    @staticmethod
    def get_conversation(user_id: int, conversation_id: str) -> dict[str, Any]:
        conversation = AIService._conversations.get(user_id, {}).get(conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return conversation

    @staticmethod
    def delete_conversation(user_id: int, conversation_id: str) -> None:
        user_store = AIService._conversations.get(user_id, {})
        if conversation_id not in user_store:
            raise HTTPException(status_code=404, detail="Conversation not found")
        del user_store[conversation_id]

    @staticmethod
    def _user_prompt_context(user: User, db: Session) -> str:
        profile = profile_data(user, db)
        skills = ", ".join(profile.get("skills", [])[:8]) or "not specified"
        interests = ", ".join(profile.get("interests", [])[:8]) or "not specified"
        role = profile.get("preferred_role") or "not specified"
        availability = profile.get("availability") or "not specified"
        experience = profile.get("experience") or "not specified"
        team_memberships = db.scalars(
            select(Team)
            .join(TeamMember, TeamMember.team_id == Team.id)
            .where(TeamMember.user_id == user.id)
            .limit(3)
        ).all()
        team_context = [
            f"- Current team requirements: {team.required_skills or 'not specified'}; "
            f"roles: {team.required_roles or 'not specified'}."
            for team in team_memberships
        ]
        if not team_context:
            team_context.append("- User is not part of any team yet.")
        return (
            "User context:\n"
            f"- Preferred role: {role}\n"
            f"- Availability: {availability}\n"
            f"- Experience: {experience}\n"
            f"- Skills: {skills}\n"
            f"- Interests: {interests}\n"
            "- Team memberships:\n" + "\n".join(team_context) + "\n"
        )

    @staticmethod
    def generate_response(user: User, db: Session, message: str, conversation_id: str | None = None) -> dict[str, Any]:
        provider, api_key, model = AIService._provider_config()

        try:
            api_timeout = min(60.0, max(5.0, float(os.getenv("AI_TIMEOUT_SECONDS", "20"))))
            max_tokens = min(1200, max(64, int(os.getenv("AI_MAX_TOKENS", "400"))))
        except ValueError as exc:
            raise HTTPException(
                status_code=503,
                detail="HackMate AI has invalid server configuration. Check AI_TIMEOUT_SECONDS and AI_MAX_TOKENS.",
            ) from exc

        AIService._check_rate_limit(user.id)
        if conversation_id:
            room_id = AIService.create_conversation(user.id, conversation_id)
            conversation = AIService._conversations[user.id][room_id]
        else:
            room_id = uuid.uuid4().hex
            now = datetime.now(timezone.utc).isoformat()
            conversation = {"created_at": now, "updated_at": now, "messages": []}

        history = conversation["messages"][-10:]
        match_context = ""
        match_request = any(
            word in message.casefold()
            for word in ("match", "teammate", "team member", "skill gap", "missing skill")
        )
        if match_request:
            from app.routers.marketplace import team_balance

            teams = db.scalars(
                select(Team)
                .join(TeamMember, TeamMember.team_id == Team.id)
                .where(TeamMember.user_id == user.id)
                .limit(3)
            ).all()
            summaries = []
            if not teams:
                match_context = (
                    "Matching context: the user does not belong to a team, so the app cannot produce "
                    "team-specific match scores yet. Explain where they can create or join a team to see recommendations.\n"
                )
            for team in teams:
                balance = team_balance(team.id, user, db)
                matches = balance["recommendations"][:3]
                missing_skills = ", ".join(balance["missing_skills"]) or "none identified"
                underrepresented = ", ".join(balance["underrepresented_skills"]) or "none identified"
                if matches:
                    summaries.append(
                        f"- Team requirements currently have missing skills: {missing_skills}; "
                        f"underrepresented skills: {underrepresented}. Top candidate compatibility scores "
                        f"{', '.join(str(item['score']) for item in matches)} out of 100; "
                        f"complementary skill signals include "
                        f"{', '.join(dict.fromkeys(skill for item in matches for skill in item['complementary_skills'])) or 'no additional listed skills'}."
                    )
                else:
                    summaries.append(
                        f"- Team requirements currently have missing skills: {missing_skills}; "
                        f"underrepresented skills: {underrepresented}. This team currently has no other candidate profiles to score."
                    )
            if summaries and not match_context:
                match_context = (
                    "Matching context from HackMate's existing rule-based matching algorithm "
                    "(scores are real app results; candidate identities are intentionally omitted):\n"
                    + "\n".join(summaries)
                    + "\n"
                )

        prompt = (
            "You are HackMate AI, an expert assistant for student hackathon teams. "
            "Keep suggestions practical, safe, and beginner-friendly. Do not claim to have real-time access to private user data beyond the profile context provided. "
            "Never claim that you created or changed an application record. Do not invent users, opportunities, team details, "
            "matching scores, or available app features. Do not generate shell commands or SQL. Keep responses concise but useful.\n\n"
            f"{AIService._user_prompt_context(user, db)}\n\n"
            f"{match_context}"
            "User request: " + message
        )

        history = [
            {"role": item["role"], "content": item["content"]}
            for item in history if item.get("role") in {"user", "assistant"}
        ]
        answer = AIService._generate_text(
            provider=provider,
            api_key=api_key,
            model=model,
            system_instruction=AIService._system_instruction(),
            prompt=prompt,
            history=history,
            timeout=api_timeout,
            max_tokens=max_tokens,
            temperature=0.7,
        )

        user_message = {"role": "user", "content": message}
        assistant_message = {"role": "assistant", "content": answer}
        conversation["messages"].append(user_message)
        conversation["messages"].append(assistant_message)
        conversation["messages"] = conversation["messages"][-AIService._max_messages_per_conversation:]
        conversation["updated_at"] = datetime.now(timezone.utc).isoformat()
        user_conversations = AIService._conversations.setdefault(user.id, {})
        if not conversation_id and len(user_conversations) >= AIService._max_conversations_per_user:
            oldest_id = min(user_conversations, key=lambda item: user_conversations[item]["created_at"])
            del user_conversations[oldest_id]
        user_conversations[room_id] = conversation
        return {
            "conversation_id": room_id,
            "reply": answer,
            "history": conversation["messages"],
        }
