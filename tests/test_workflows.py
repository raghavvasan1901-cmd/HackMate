import atexit
import json
import os
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ["HACKMATE_DATABASE_URL"] = f"sqlite:///{(Path(tempfile.gettempdir()) / f'hackmate-test-{os.getpid()}.db').as_posix()}"
os.environ["HACKMATE_SECRET_KEY"] = "test-only-secret-that-is-not-used-outside-tests"

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.database import Base, migrate_existing_sqlite_schema
from app.main import app


TEST_DATABASE = Path(tempfile.gettempdir()) / f"hackmate-test-{os.getpid()}.db"
def cleanup_test_database():
    from app.database import engine

    engine.dispose()
    TEST_DATABASE.unlink(missing_ok=True)


atexit.register(cleanup_test_database)


def test_migrate_legacy_sqlite_profile_visibility_columns_without_data_loss():
    legacy_engine = create_engine("sqlite://")
    try:
        with legacy_engine.begin() as connection:
            connection.execute(text("CREATE TABLE reviews (id INTEGER PRIMARY KEY)"))
            connection.execute(text(
                "CREATE TABLE developer_profiles "
                "(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, location TEXT NOT NULL DEFAULT '')"
            ))
            connection.execute(text(
                "INSERT INTO developer_profiles (id, user_id, location) VALUES (1, 42, 'Remote')"
            ))
            connection.execute(text(
                "CREATE TABLE hackathon_events ("
                "id INTEGER PRIMARY KEY, creator_id INTEGER NOT NULL, opportunity_id INTEGER, "
                "name VARCHAR(160) NOT NULL, organizer VARCHAR(160) NOT NULL DEFAULT '', "
                "description TEXT NOT NULL DEFAULT '', starts_at DATETIME NOT NULL, ends_at DATETIME NOT NULL, "
                "registration_deadline DATETIME, location VARCHAR(200) NOT NULL DEFAULT '', "
                "event_url VARCHAR(500) NOT NULL DEFAULT '', eligibility VARCHAR(500) NOT NULL DEFAULT '', "
                "tags VARCHAR(500) NOT NULL DEFAULT '', created_at DATETIME NOT NULL)"
            ))
            connection.execute(text(
                "INSERT INTO hackathon_events "
                "(id, creator_id, name, starts_at, ends_at, created_at) "
                "VALUES (7, 42, 'Existing event', '2026-11-01 10:00:00', "
                "'2026-11-02 10:00:00', '2026-10-01 10:00:00')"
            ))

        migrate_existing_sqlite_schema(legacy_engine)
        Base.metadata.create_all(bind=legacy_engine)

        with legacy_engine.connect() as connection:
            profile = connection.execute(text(
                "SELECT user_id, location, location_visible, education_visible "
                "FROM developer_profiles WHERE id = 1"
            )).one()
            review_columns = {
                row[1] for row in connection.exec_driver_sql("PRAGMA table_info(reviews)")
            }
            existing_event = connection.execute(text(
                "SELECT id, name, is_imported, event_status FROM hackathon_events WHERE id = 7"
            )).one()
        assert tuple(profile) == (42, "Remote", 0, 1)
        assert {"communication_rating", "reliability_rating", "teamwork_rating"} <= review_columns
        assert tuple(existing_event) == (7, "Existing event", 0, "scheduled")
    finally:
        legacy_engine.dispose()


def test_overview_data_endpoints_load_for_authenticated_user():
    with TestClient(app) as client:
        account, headers = register(client, "Overview Student")
        user_id = account["user"]["id"]
        team = client.post("/api/teams", headers=headers, json={
            "name": "Overview Team", "max_size": 4,
        })
        assert team.status_code == 201
        team_id = team.json()["id"]

        paths = [
            "/api/auth/me",
            "/api/opportunities",
            "/api/teams",
            "/api/roadmaps",
            "/api/notifications",
            "/api/invitations",
            "/api/calendar/events?from_date=2026-10-14&to_date=2026-11-13",
            "/api/users/me/portfolio",
            f"/api/teams/{team_id}/workspace",
            f"/api/teams/{team_id}/matches?limit=2",
        ]
        responses = {path: client.get(path, headers=headers) for path in paths}
        assert {path: response.status_code for path, response in responses.items()} == {
            path: 200 for path in paths
        }
        assert responses["/api/teams"].json()[0]["members"][0]["id"] == user_id
        assert isinstance(responses["/api/invitations"].json()["received"], list)
        assert isinstance(responses["/api/calendar/events?from_date=2026-10-14&to_date=2026-11-13"].json(), list)
        assert client.get("/api/users/me/portfolio").status_code == 401


def register(client: TestClient, name: str):
    result = client.post("/api/auth/register", json={
        "name": name, "email": f"{name.lower().replace(' ', '.')}+{uuid.uuid4().hex[:6]}@example.edu",
        "password": "safe-test-password-123",
    })
    assert result.status_code == 201, result.text
    payload = result.json()
    return payload, {"Authorization": f"Bearer {payload['access_token']}"}


def build_ical_event(
    uid: str,
    title: str,
    starts_at: datetime,
    ends_at: datetime,
    *,
    status: str = "CONFIRMED",
    event_url: str = "https://events.example.org/hackathon",
    categories: tuple[str, ...] = ("Python", "AI"),
) -> bytes:
    from icalendar import Calendar, Event, vDDDTypes

    calendar = Calendar()
    calendar.add("prodid", "-//HackMate tests//EN")
    calendar.add("version", "2.0")
    event = Event()
    event.add("uid", uid)
    event.add("summary", title)
    event.add("dtstart", starts_at)
    event.add("dtend", ends_at)
    event.add("url", event_url)
    event.add("organizer", "mailto:organizer@example.org")
    event.add("description", "A real event supplied by the configured feed.")
    event.add("categories", list(categories))
    event.add("x-hackmate-scope", "campus")
    event.add("x-event-format", "offline")
    event.add("x-country", "India")
    event.add("x-region", "Karnataka")
    event.add("x-eligibility", "University students")
    event.add("x-registration-deadline", vDDDTypes(starts_at - timedelta(days=2)))
    event.add("x-registration-url", "https://events.example.org/register")
    event.add("x-min-team-size", 2)
    event.add("x-max-team-size", 5)
    event.add("status", status)
    calendar.add_component(event)
    return calendar.to_ical()


def test_registration_login_and_profile_update():
    with TestClient(app) as client:
        assert client.get("/").status_code == 200
        assert client.get("/static/css/styles.css").status_code == 200
        assert client.get("/static/js/app.js").status_code == 200
        assert client.get("/docs").status_code == 200
        assert client.get("/api/health").json()["status"] == "ok"
        account, headers = register(client, "Taylor Student")
        assert account["user"]["name"] == "Taylor Student"
        assert client.get("/api/auth/me", headers=headers).status_code == 200
        updated = client.put("/api/users/me/profile", headers=headers, json={
            "name": "Taylor Student", "college": "Example University", "department": "Computing",
            "experience": "Intermediate", "preferred_role": "Backend Developer", "availability": "Weekends",
            "bio": "I like building useful tools.", "project_experience": "",
            "skills": ["Python", "SQL"], "interests": ["Civic tech"],
        })
        assert updated.status_code == 200
        assert updated.json()["skills"] == ["Python", "SQL"]
        assert "email" not in client.get("/api/users/1").json()
        login = client.post("/api/auth/login", json={
            "email": account["user"]["email"], "password": "safe-test-password-123"
        })
        assert login.status_code == 200
        assert client.post("/api/auth/login", json={
            "email": account["user"]["email"], "password": "incorrect-password"
        }).status_code == 401
        assert client.post("/api/auth/logout", headers=headers).status_code == 200


def test_team_application_tasks_chat_and_member_authorization():
    with TestClient(app) as client:
        _, leader_headers = register(client, "Team Lead")
        _, applicant_headers = register(client, "New Teammate")
        _, outsider_headers = register(client, "Outside Student")
        opportunity = client.post("/api/opportunities", headers=leader_headers, json={
            "title": "Accessible Campus Map", "kind": "Hackathon",
            "description": "Build a helpful map for students around campus.",
            "required_skills": ["Python", "Design"], "team_size": 3, "deadline": "",
        })
        assert opportunity.status_code == 201
        team = client.post("/api/teams", headers=leader_headers, json={
            "name": "Campus Builders", "description": "A small project team.",
            "required_skills": ["Python", "Design"], "required_roles": ["Designer"],
            "max_size": 3, "opportunity_id": opportunity.json()["id"],
        })
        assert team.status_code == 201
        team_id = team.json()["id"]
        application = client.post(f"/api/teams/{team_id}/applications", headers=applicant_headers, json={
            "message": "I can help with the interface."
        })
        assert application.status_code == 201
        assert client.post(f"/api/teams/{team_id}/applications", headers=applicant_headers, json={}).status_code == 409
        applications = client.get(f"/api/teams/{team_id}/applications", headers=leader_headers)
        assert applications.status_code == 200
        app_id = applications.json()[0]["id"]
        assert client.patch(
            f"/api/teams/{team_id}/applications/{app_id}", headers=leader_headers,
            json={"status": "accepted"},
        ).status_code == 200

        task = client.post(f"/api/teams/{team_id}/tasks", headers=applicant_headers, json={
            "title": "Draft the interface", "description": "Create the first layout",
            "assignee_id": None, "priority": "High", "due_date": "",
        })
        assert task.status_code == 201
        task_id = task.json()["id"]
        assert client.patch(
            f"/api/teams/{team_id}/tasks/{task_id}", headers=applicant_headers, json={"status": "Done"}
        ).json()["status"] == "Done"
        assert client.post(f"/api/teams/{team_id}/messages", headers=applicant_headers, json={
            "content": "I have a first draft."
        }).status_code == 201
        assert len(client.get(f"/api/teams/{team_id}/messages", headers=leader_headers).json()) == 1
        assert client.get(f"/api/teams/{team_id}/tasks", headers=outsider_headers).status_code == 403
        assert client.get(f"/api/teams/{team_id}/messages", headers=outsider_headers).status_code == 403
        balance = client.get(f"/api/teams/{team_id}/balance", headers=leader_headers)
        assert balance.status_code == 200
        assert "missing_skills" in balance.json()
        matches = client.get(f"/api/teams/{team_id}/matches", headers=leader_headers)
        assert matches.status_code == 200
        assert all(0 <= match["score"] <= 100 for match in matches.json())
        assert client.get(f"/api/teams/{team_id}/matches", headers=outsider_headers).status_code == 403


def test_reviews_and_notification_access():
    with TestClient(app) as client:
        leader, leader_headers = register(client, "Review Lead")
        member, member_headers = register(client, "Review Member")
        outsider, outsider_headers = register(client, "Review Outsider")
        team = client.post("/api/teams", headers=leader_headers, json={
            "name": "Review Crew", "max_size": 3,
        }).json()
        team_id = team["id"]
        application = client.post(f"/api/teams/{team_id}/applications", headers=member_headers, json={}).json()
        application_id = client.get(f"/api/teams/{team_id}/applications", headers=leader_headers).json()[0]["id"]
        assert application["status"] == "pending"
        client.patch(f"/api/teams/{team_id}/applications/{application_id}", headers=leader_headers, json={"status": "accepted"})
        review = client.post(f"/api/teams/{team_id}/reviews", headers=leader_headers, json={
            "reviewee_id": member["user"]["id"], "rating": 5, "feedback": "Great collaborator."
        })
        assert review.status_code == 201
        assert client.post(f"/api/teams/{team_id}/reviews", headers=leader_headers, json={
            "reviewee_id": member["user"]["id"], "rating": 4, "feedback": "Second review."
        }).status_code == 409
        reviews = client.get(f"/api/users/{member['user']['id']}/reviews")
        assert reviews.json()["average_rating"] == 5.0
        assert reviews.json()["reviews"][0]["communication_rating"] == 5
        notifications = client.get("/api/notifications", headers=member_headers).json()
        assert notifications
        notification_id = notifications[0]["id"]
        assert client.post(f"/api/notifications/{notification_id}/read", headers=outsider_headers).status_code == 404
        assert client.post(f"/api/notifications/{notification_id}/read", headers=member_headers).json()["read"]
        assert outsider["user"]["id"] != leader["user"]["id"]


def test_ai_requires_authentication_and_missing_credentials(monkeypatch):
    monkeypatch.delenv("AI_API_KEY", raising=False)
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    with TestClient(app) as client:
        response = client.post("/api/ai/chat", json={"message": "Hello"})
        assert response.status_code == 401

        _, headers = register(client, "AI User")
        missing_key = client.post("/api/ai/chat", headers=headers, json={"message": "Hi there"})
        assert missing_key.status_code == 503
        assert "AI_API_KEY" in missing_key.json()["detail"]


def test_ai_rejects_bad_input_and_handles_provider_failure(monkeypatch):
    with TestClient(app) as client:
        _, headers = register(client, "AI Tester")
        invalid = client.post("/api/ai/chat", headers=headers, json={"message": ""})
        assert invalid.status_code == 422
        invalid_conversation = client.post(
            "/api/ai/chat", headers=headers,
            json={"message": "hello", "conversation_id": "../other-user"},
        )
        assert invalid_conversation.status_code == 422

        monkeypatch.setenv("AI_API_KEY", "test-key")
        monkeypatch.setenv("AI_MODEL", "gpt-4o-mini")

        def fake_create(*args, **kwargs):
            raise TimeoutError("slow provider")

        import app.services.ai_service as ai_service
        from types import SimpleNamespace

        def fake_openai(**_kwargs):
            return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create)))

        monkeypatch.setattr(ai_service, "OpenAI", fake_openai)
        error = client.post("/api/ai/chat", headers=headers, json={"message": "Test AI timeout"})
        assert error.status_code == 504
        assert "too long" in error.json()["detail"].lower()

        def unavailable_create(*args, **kwargs):
            raise OSError("provider connection failed")

        def unavailable_openai(**_kwargs):
            return SimpleNamespace(chat=SimpleNamespace(
                completions=SimpleNamespace(create=unavailable_create)
            ))

        monkeypatch.setattr(ai_service, "OpenAI", unavailable_openai)
        provider_error = client.post("/api/ai/chat", headers=headers, json={"message": "Test provider failure"})
        assert provider_error.status_code == 502
        assert "unavailable" in provider_error.json()["detail"].lower()


def test_ai_successful_mocked_response_and_conversation_ownership(monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "test-key")
    monkeypatch.setenv("AI_MODEL", "gpt-4o-mini")
    import app.services.ai_service as ai_service
    from types import SimpleNamespace

    requests = []

    def fake_create(**kwargs):
        requests.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="Try a small, testable MVP."))]
        )

    def fake_openai(**_kwargs):
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create)))

    monkeypatch.setattr(ai_service, "OpenAI", fake_openai)
    with TestClient(app) as client:
        _, headers = register(client, "AI Owner")
        _, other_headers = register(client, "AI Visitor")
        first = client.post("/api/ai/chat", headers=headers, json={"message": "Plan my project"})
        assert first.status_code == 200
        assert first.json()["reply"] == "Try a small, testable MVP."
        conversation_id = first.json()["conversation_id"]

        followup = client.post("/api/ai/chat", headers=headers, json={
            "message": "What should I do first?", "conversation_id": conversation_id,
        })
        assert followup.status_code == 200
        assert followup.json()["conversation_id"] == conversation_id
        assert len(followup.json()["history"]) == 4
        assert len(requests) == 2
        assert "AI Owner" not in str(requests[0]["messages"])

        own_history = client.get(f"/api/ai/conversations/{conversation_id}", headers=headers)
        assert own_history.status_code == 200
        assert len(own_history.json()["messages"]) == 4
        assert client.get(
            f"/api/ai/conversations/{conversation_id}", headers=other_headers
        ).status_code == 404
        assert client.delete(
            f"/api/ai/conversations/{conversation_id}", headers=other_headers
        ).status_code == 404
        assert client.delete(
            f"/api/ai/conversations/{conversation_id}", headers=headers
        ).status_code == 200
        assert client.get(
            f"/api/ai/conversations/{conversation_id}", headers=headers
        ).status_code == 404


def test_ai_gemini_uses_configured_model_and_preserves_frontend_contract(monkeypatch):
    from types import SimpleNamespace

    import app.services.ai_service as ai_service

    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("AI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("AI_MODEL", "gemini-test-model")
    monkeypatch.setenv("AI_SYSTEM_INSTRUCTION", "Custom HackMate system guidance.")
    requests = []
    responses = iter(["Start with one core user journey.", "Then test it with a teammate."])

    class FakeGeminiClient:
        def __init__(self, **kwargs):
            self.options = kwargs

        class Models:
            @staticmethod
            def generate_content(**kwargs):
                requests.append(kwargs)
                return SimpleNamespace(text=next(responses))

        models = Models()

        def close(self):
            pass

    monkeypatch.setattr(ai_service.genai, "Client", FakeGeminiClient)
    with TestClient(app) as client:
        _, headers = register(client, "Gemini User")
        first = client.post("/api/ai/chat", headers=headers, json={"message": "Help plan my MVP"})
        assert first.status_code == 200
        assert first.json()["reply"] == "Start with one core user journey."
        assert first.json()["message"] == first.json()["reply"]
        conversation_id = first.json()["conversation_id"]

        followup = client.post("/api/ai/chat", headers=headers, json={
            "message": "What next?", "conversation_id": conversation_id,
        })
        assert followup.status_code == 200
        assert followup.json()["conversation_id"] == conversation_id
        assert len(followup.json()["history"]) == 4

    assert len(requests) == 2
    assert all(request["model"] == "gemini-test-model" for request in requests)
    assert requests[0]["config"].system_instruction == "Custom HackMate system guidance."
    assert [item.role for item in requests[1]["contents"]] == ["user", "model", "user"]
    assert "What next?" in requests[1]["contents"][-1].parts[0].text
    assert "Gemini User" not in str(requests)


def test_ai_gemini_maps_credentials_quota_network_and_empty_responses(monkeypatch):
    import httpx
    from google.genai.errors import APIError

    import app.services.ai_service as ai_service

    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("AI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("AI_MODEL", "gemini-test-model")
    failures = iter([
        APIError(code=401, response_json={"error": {"message": "private provider detail"}}),
        APIError(code=404, response_json={"error": {"message": "private provider detail"}}),
        APIError(code=429, response_json={"error": {"message": "private provider detail"}}),
        httpx.ConnectError("private network detail"),
        httpx.ReadTimeout("private timeout detail"),
        None,
    ])

    class FakeGeminiClient:
        def __init__(self, **_kwargs):
            pass

        class Models:
            @staticmethod
            def generate_content(**_kwargs):
                failure = next(failures)
                if failure is not None:
                    raise failure
                return SimpleNamespace(text="")

        models = Models()

        def close(self):
            pass

    from types import SimpleNamespace

    monkeypatch.setattr(ai_service.genai, "Client", FakeGeminiClient)
    with TestClient(app) as client:
        _, headers = register(client, "Gemini Error User")
        results = [
            client.post("/api/ai/chat", headers=headers, json={"message": "Please help"})
            for _ in range(6)
        ]

    assert [response.status_code for response in results] == [502, 502, 503, 502, 504, 502]
    assert "rejected its API key" in results[0].json()["detail"]
    assert "model is unavailable" in results[1].json()["detail"]
    assert "quota" in results[2].json()["detail"]
    assert "unavailable" in results[3].json()["detail"]
    assert "too long" in results[4].json()["detail"]
    assert "rephrasing" in results[5].json()["detail"]
    assert all("private" not in response.text for response in results)


def test_ai_team_guidance_uses_real_balance_and_match_results(monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "test-key")
    import app.services.ai_service as ai_service
    from types import SimpleNamespace

    requests = []

    def fake_openai(**_kwargs):
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
            create=lambda **params: (
                requests.append(params) or SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content="Use the team's real gaps as your guide."))]
                )
            )
        )))

    monkeypatch.setattr(ai_service, "OpenAI", fake_openai)
    with TestClient(app) as client:
        _, leader_headers = register(client, "Match Context Lead")
        _, candidate_headers = register(client, "Match Context Candidate")
        client.put("/api/users/me/profile", headers=candidate_headers, json={
            "name": "Match Context Candidate", "skills": ["Python", "Prototyping"],
            "interests": ["Education"], "preferred_role": "Developer",
        })
        team_response = client.post("/api/teams", headers=leader_headers, json={
            "name": "AI Context Team", "required_skills": ["Python", "Design"],
            "required_roles": ["Designer"], "max_size": 4,
        })
        assert team_response.status_code == 201
        team_id = team_response.json()["id"]
        balance = client.get(f"/api/teams/{team_id}/balance", headers=leader_headers)
        assert balance.status_code == 200
        assert "Design" in balance.json()["missing_skills"]

        response = client.post("/api/ai/chat", headers=leader_headers, json={
            "message": "Recommend teammates and identify missing skills in my team",
        })
        assert response.status_code == 200
        prompt = requests[0]["messages"][-1]["content"]
        assert "Matching context from HackMate's existing rule-based matching algorithm" in prompt
        assert "missing skills: Python, Design" in prompt
        assert "Match Context Candidate" not in prompt


def test_ai_conversation_list_requires_authentication_and_is_isolated(monkeypatch):
    monkeypatch.delenv("AI_API_KEY", raising=False)
    with TestClient(app) as client:
        _, headers = register(client, "Alice")
        _, other_headers = register(client, "Bob")

        response = client.post("/api/ai/chat", headers=headers, json={"message": "Plan my project"})
        assert response.status_code == 503
        conversations = client.get("/api/ai/conversations", headers=headers)
        assert conversations.status_code == 200
        other_conversations = client.get("/api/ai/conversations", headers=other_headers)
        assert other_conversations.status_code == 200
        assert len(other_conversations.json()) == 0
        assert client.get("/api/ai/conversations").status_code == 401


def test_ai_rate_limit(monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "test-key")
    import app.services.ai_service as ai_service
    from types import SimpleNamespace

    monkeypatch.setattr(ai_service.AIService, "_requests_per_minute", 1)

    def fake_openai(**_kwargs):
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
            create=lambda **_params: SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="Mocked response."))]
            )
        )))

    monkeypatch.setattr(ai_service, "OpenAI", fake_openai)
    with TestClient(app) as client:
        _, headers = register(client, "AI Rate Limit")
        first = client.post("/api/ai/chat", headers=headers, json={"message": "First request"})
        assert first.status_code == 200
        limited = client.post("/api/ai/chat", headers=headers, json={"message": "Second request"})
        assert limited.status_code == 429
        assert limited.headers["retry-after"] == "60"


def test_portfolio_privacy_projects_and_secure_resume(tmp_path, monkeypatch):
    monkeypatch.setenv("HACKMATE_PRIVATE_UPLOAD_DIR", str(tmp_path / "private"))
    with TestClient(app) as client:
        owner, owner_headers = register(client, "Portfolio Owner")
        viewer, viewer_headers = register(client, "Portfolio Viewer")
        owner_id = owner["user"]["id"]
        updated = client.put("/api/users/me/portfolio", headers=owner_headers, json={
            "preferred_name": "Builder", "headline": "Student engineer",
            "degree": "BSc", "course": "Computer Science", "study_year": "Year 2",
            "graduation_year": 2028, "location": "Remote", "languages": ["English", "Hindi"],
            "github_username": "octocat",
        })
        assert updated.status_code == 200
        assert updated.json()["display_name"] == "Builder"
        assert updated.json()["languages"] == ["English", "Hindi"]

        project = client.post("/api/users/me/portfolio/projects", headers=owner_headers, json={
            "title": "Study helper", "description": "A project.", "technologies": ["Python"],
            "repository_url": "https://github.com/example/project",
        })
        assert project.status_code == 201
        skill = client.post("/api/users/me/portfolio/skills", headers=owner_headers, json={
            "name": "Python", "category": "Programming", "proficiency": 3,
        })
        assert skill.status_code == 201
        assert skill.json()["verified"] is False

        history = client.post("/api/users/me/portfolio/hackathons", headers=owner_headers, json={
            "event_name": "Campus Build Day", "event_date": "2025-10-01",
            "project_title": "Study helper", "team_role": "Backend",
            "technologies": ["Python"], "result": "Finalist",
        })
        assert history.status_code == 201
        assert history.json()["verified"] is False
        assert client.get(f"/api/users/{owner_id}/portfolio").status_code == 200
        public = client.get(f"/api/users/{owner_id}/portfolio").json()
        assert public["projects"][0]["title"] == "Study helper"
        assert public["hackathon_history"][0]["verified"] is False
        assert public["resume_available"] is False

        invalid = client.post(
            "/api/users/me/resume", headers=owner_headers,
            files={"file": ("resume.pdf", b"not a PDF", "application/pdf")},
        )
        assert invalid.status_code == 415
        uploaded = client.post(
            "/api/users/me/resume", headers=owner_headers,
            files={"file": ("../../resume.pdf", b"%PDF-1.4\nsample\n%%EOF", "application/pdf")},
        )
        assert uploaded.status_code == 201
        assert client.get(f"/api/users/{owner_id}/resume").status_code == 404
        own_resume = client.get(f"/api/users/{owner_id}/resume", headers=owner_headers)
        assert own_resume.status_code == 200
        assert own_resume.content.startswith(b"%PDF-")

        visible = client.put("/api/users/me/portfolio", headers=owner_headers, json={
            "resume_visible": True, "projects_visible": False,
        })
        assert visible.status_code == 200
        public = client.get(f"/api/users/{owner_id}/portfolio", headers=viewer_headers).json()
        assert public["projects"] == []
        assert public["resume_available"] is True
        assert client.get(f"/api/users/{owner_id}/resume").status_code == 200
        assert client.get(f"/api/users/{owner_id}/resume?download=true").headers[
            "content-disposition"
        ].startswith("attachment")
        assert client.delete(
            f"/api/users/me/portfolio/projects/{project.json()['id']}", headers=viewer_headers
        ).status_code == 404
        assert client.delete("/api/users/me/resume", headers=owner_headers).status_code == 204
        assert client.get(f"/api/users/{owner_id}/resume", headers=owner_headers).status_code == 404


def test_github_profile_uses_official_public_api_with_mock(monkeypatch):
    class FakeResponse:
        status_code = 200

        def __init__(self, payload):
            self.payload = payload

        def json(self):
            return self.payload

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, **_kwargs):
            self.calls = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def get(self, url, **_kwargs):
            self.calls.append(url)
            if url.endswith("/repos"):
                return FakeResponse([{
                    "name": "public-project", "description": "Public data",
                    "html_url": "https://github.com/sample/public-project",
                    "language": "Python", "stargazers_count": 3, "private": False,
                }])
            return FakeResponse({
                "login": "sample", "html_url": "https://github.com/sample", "public_repos": 4,
            })

    monkeypatch.setattr("app.routers.portfolio.httpx.Client", FakeClient)
    with TestClient(app) as client:
        user, headers = register(client, "GitHub User")
        client.put("/api/users/me/portfolio", headers=headers, json={"github_username": "sample"})
        result = client.get(f"/api/users/{user['user']['id']}/github")
        assert result.status_code == 200
        assert result.json()["public_repositories"] == 4
        assert result.json()["repositories"][0]["stars"] == 3
        assert result.json()["source"] == "GitHub public API"


def test_team_invitations_accept_decline_cancel_expiration_and_capacity():
    with TestClient(app) as client:
        leader, leader_headers = register(client, "Invite Leader")
        first, first_headers = register(client, "Invite First")
        second, second_headers = register(client, "Invite Second")
        outsider, outsider_headers = register(client, "Invite Outsider")
        team = client.post("/api/teams", headers=leader_headers, json={
            "name": "Invitation Team", "max_size": 2,
        }).json()
        team_id = team["id"]
        invite_one = client.post(f"/api/teams/{team_id}/invitations", headers=leader_headers, json={
            "invitee_id": first["user"]["id"], "message": "Join our build.",
        })
        assert invite_one.status_code == 201
        invitation_id = invite_one.json()["id"]
        assert invite_one.json()["status"] == "pending"
        assert client.post(f"/api/teams/{team_id}/invitations", headers=leader_headers, json={
            "invitee_id": first["user"]["id"],
        }).status_code == 409
        assert client.post(f"/api/teams/{team_id}/invitations", headers=outsider_headers, json={
            "invitee_id": second["user"]["id"],
        }).status_code == 403
        assert client.post(f"/api/teams/{team_id}/invitations", headers=leader_headers, json={
            "invitee_id": leader["user"]["id"],
        }).status_code == 422
        assert client.get("/api/invitations").status_code == 401
        assert client.patch(
            f"/api/invitations/{invitation_id}", headers=outsider_headers, json={"status": "accepted"},
        ).status_code == 404
        accepted = client.patch(
            f"/api/invitations/{invitation_id}", headers=first_headers, json={"status": "accepted"},
        )
        assert accepted.status_code == 200
        assert accepted.json()["status"] == "accepted"
        assert client.patch(
            f"/api/invitations/{invitation_id}", headers=first_headers, json={"status": "accepted"},
        ).status_code == 409
        team_after = client.get(f"/api/teams/{team_id}").json()
        assert [member["id"] for member in team_after["members"]] == [leader["user"]["id"], first["user"]["id"]]
        assert any("accepted" in item["message"] for item in client.get("/api/notifications", headers=leader_headers).json())
        assert client.post(f"/api/teams/{team_id}/invitations", headers=leader_headers, json={
            "invitee_id": second["user"]["id"],
        }).status_code == 409

        other_team = client.post("/api/teams", headers=leader_headers, json={
            "name": "Decline Team", "max_size": 3,
        }).json()
        declined = client.post(f"/api/teams/{other_team['id']}/invitations", headers=leader_headers, json={
            "invitee_id": second["user"]["id"],
        }).json()
        response = client.patch(
            f"/api/invitations/{declined['id']}", headers=second_headers, json={"status": "declined"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "declined"
        assert client.get(f"/api/teams/{other_team['id']}").json()["member_count"] == 1

        cancel_team = client.post("/api/teams", headers=leader_headers, json={
            "name": "Cancel Team", "max_size": 3,
        }).json()
        cancellable = client.post(f"/api/teams/{cancel_team['id']}/invitations", headers=leader_headers, json={
            "invitee_id": outsider["user"]["id"],
        }).json()
        assert client.delete(
            f"/api/invitations/{cancellable['id']}", headers=outsider_headers,
        ).status_code == 404
        assert client.delete(
            f"/api/invitations/{cancellable['id']}", headers=leader_headers,
        ).status_code == 204

        expiration_team = client.post("/api/teams", headers=leader_headers, json={
            "name": "Expiration Team", "max_size": 3,
        }).json()
        expiring = client.post(
            f"/api/teams/{expiration_team['id']}/invitations", headers=leader_headers,
            json={"invitee_id": outsider["user"]["id"]},
        ).json()
        from app.database import SessionLocal
        from app.models import TeamInvitation

        with SessionLocal() as db:
            record = db.get(TeamInvitation, expiring["id"])
            record.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.commit()
        assert client.patch(
            f"/api/invitations/{expiring['id']}", headers=outsider_headers, json={"status": "accepted"},
        ).status_code == 409
        inbox = client.get("/api/invitations", headers=outsider_headers).json()
        assert next(item for item in inbox["received"] if item["id"] == expiring["id"])["status"] == "expired"


def test_calendar_events_timezone_filters_registration_and_permissions():
    with TestClient(app) as client:
        creator, creator_headers = register(client, "Calendar Creator")
        attendee, attendee_headers = register(client, "Calendar Attendee")
        other, other_headers = register(client, "Calendar Other")
        starts = datetime.now(timezone.utc) + timedelta(days=20)
        ends = starts + timedelta(days=2)
        deadline = starts - timedelta(days=3)
        payload = {
            "name": "Verified by user event", "organizer": "Organizer",
            "description": "A real event supplied by its creator.",
            "starts_at": starts.isoformat(), "ends_at": ends.isoformat(),
            "registration_deadline": deadline.isoformat(), "location": "Online",
            "event_url": "https://example.org/event", "eligibility": "Students",
            "tags": ["AI", "Web"],
        }
        assert client.get("/api/calendar/events").status_code == 200
        assert client.post("/api/calendar/events", json=payload).status_code == 401
        created = client.post("/api/calendar/events", headers=creator_headers, json=payload)
        assert created.status_code == 201, created.text
        event = created.json()
        event_id = event["id"]
        assert event["is_joined"] is False
        assert client.get(f"/api/calendar/events/{event_id}").json()["is_joined"] is False
        assert client.get(
            f"/api/calendar/events?from_date={starts.date().isoformat()}&to_date={starts.date().isoformat()}"
        ).json()[0]["id"] == event_id
        assert client.put(
            f"/api/calendar/events/{event_id}", headers=other_headers, json=payload,
        ).status_code == 403
        assert client.post(
            f"/api/calendar/events/{event_id}/register", headers=attendee_headers,
        ).status_code == 201
        joined = client.get(f"/api/calendar/events/{event_id}", headers=attendee_headers).json()
        assert joined["is_joined"] is True
        assert client.get(f"/api/calendar/events/{event_id}", headers=other_headers).json()["is_joined"] is False
        assert client.post(
            f"/api/calendar/events/{event_id}/register", headers=attendee_headers,
        ).status_code == 409
        assert client.delete(
            f"/api/calendar/events/{event_id}/register", headers=attendee_headers,
        ).status_code == 204
        assert client.get(f"/api/calendar/events/{event_id}", headers=attendee_headers).json()["is_joined"] is False
        assert client.delete(
            f"/api/calendar/events/{event_id}", headers=other_headers,
        ).status_code == 403
        invalid = dict(payload)
        invalid["ends_at"] = starts.isoformat()
        assert client.post(
            "/api/calendar/events", headers=creator_headers, json=invalid,
        ).status_code == 422
        assert client.delete(
            f"/api/calendar/events/{event_id}", headers=creator_headers,
        ).status_code == 204


def test_matching_uses_hackathon_history_and_optional_ai_fallback(monkeypatch):
    monkeypatch.delenv("AI_API_KEY", raising=False)
    with TestClient(app) as client:
        _, leader_headers = register(client, "Explain Match Lead")
        candidate, candidate_headers = register(client, "Explain Match Candidate")
        client.put("/api/users/me/profile", headers=candidate_headers, json={
            "name": "Explain Match Candidate", "skills": ["PyTorch"],
            "interests": ["AI"], "preferred_role": "AI Engineer", "availability": "Weekends",
        })
        client.post("/api/users/me/portfolio/hackathons", headers=candidate_headers, json={
            "event_name": "AI Sprint", "project_title": "Classifier",
            "team_role": "AI Engineer", "technologies": ["PyTorch"],
        })
        team = client.post("/api/teams", headers=leader_headers, json={
            "name": "AI Team", "required_skills": ["PyTorch"],
            "required_roles": ["AI Engineer"],
        }).json()
        results = client.get(
            f"/api/teams/{team['id']}/matches?explain_with_ai=true", headers=leader_headers,
        )
        assert results.status_code == 200
        match = next(item for item in results.json() if item["user"]["id"] == candidate["user"]["id"])
        assert match["score_is_estimate"] is True
        assert match["missing_skills_candidate_contributes"] == ["pytorch"]
        assert match["relevant_hackathon_experience"][0]["verified"] is False
        assert match["reputation"]["review_count"] == 0
        assert match["explanation_method"] == "rule_based"
        assert match["ai_explanation_status"] == "missing_credentials"

        import app.services.ai_service as ai_service
        from types import SimpleNamespace

        def fake_create(**_kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
                content='[{"index":0,"explanation":"Reports PyTorch project experience relevant to this team gap."}]'
            ))])

        monkeypatch.setenv("AI_API_KEY", "test-key")
        monkeypatch.setattr(ai_service, "OpenAI", lambda **_kwargs: SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))
        ))
        explained = client.get(
            f"/api/teams/{team['id']}/matches?explain_with_ai=true", headers=leader_headers,
        )
        ai_match = next(item for item in explained.json() if item["user"]["id"] == candidate["user"]["id"])
        assert ai_match["explanation_method"] == "ai"
        assert "PyTorch" in ai_match["ai_explanation"]


def test_icalendar_feed_parsing_validates_optional_data_and_dates():
    from icalendar import Calendar, Event

    from app.services.event_sync import parse_icalendar

    starts = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=30)
    valid = build_ical_event("uid-1", "Campus AI Sprint", starts, starts + timedelta(days=1))
    calendar = Calendar.from_ical(valid)
    invalid = Event()
    invalid.add("uid", "bad-date")
    invalid.add("summary", "Missing start")
    invalid.add("dtend", starts + timedelta(days=1))
    calendar.add_component(invalid)
    floating = Event()
    floating.add("uid", "floating-date")
    floating.add("summary", "Unzoned floating date")
    floating.add("dtstart", starts.replace(tzinfo=None))
    floating.add("dtend", (starts + timedelta(days=1)).replace(tzinfo=None))
    calendar.add_component(floating)
    parsed, invalid_count = parse_icalendar(calendar.to_ical())

    assert len(parsed) == 1
    assert invalid_count == 2
    assert parsed[0].starts_at == starts
    assert parsed[0].scope == "campus"
    assert parsed[0].event_format == "offline"
    assert parsed[0].team_size_min == 2
    assert parsed[0].team_size_max == 5
    assert parsed[0].registration_deadline == starts - timedelta(days=2)
    assert parsed[0].completeness > 50


def test_icalendar_sync_deduplicates_updates_and_preserves_registration(monkeypatch):
    import httpx

    import app.services.event_sync as event_sync
    from app.database import SessionLocal
    from app.models import HackathonEvent
    from app.models import EventSourceListing, HackathonEvent, HackathonRegistration

    starts = datetime.now(timezone.utc) + timedelta(days=30)
    current_payload = build_ical_event("shared-uid", "Campus AI Sprint", starts, starts + timedelta(days=1))
    monkeypatch.setenv("HACKMATE_ICAL_FEEDS", json.dumps([
        {"key": "organizer-feed", "name": "University Organizer", "url": "https://events.example.org/feed.ics"},
        {"key": "partner-feed", "name": "Partner Calendar", "url": "https://calendar.example.org/events.ics"},
    ]))

    def handler(request):
        return httpx.Response(
            200, headers={"content-type": "text/calendar; charset=utf-8"}, content=current_payload,
        )

    transport = httpx.Client(transport=httpx.MockTransport(handler))
    with TestClient(app) as client:
        owner, owner_headers = register(client, "Feed Sync Owner")
        with SessionLocal() as db:
            first = event_sync.sync_event_sources(db, owner["user"]["id"], transport)
        assert first["status"] == "success"
        assert first["events_created"] == 1
        assert first["events_updated"] == 1

        listing_response = client.get(
            "/api/calendar/events?scope=campus&country=India&region=Karnataka&event_format=offline&technology=AI&eligibility=students"
            f"&deadline_before={(starts - timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%S')}Z",
            headers=owner_headers,
        )
        assert listing_response.status_code == 200
        assert len(listing_response.json()) == 1
        event_payload = listing_response.json()[0]
        event_id = event_payload["id"]
        assert event_payload["is_imported"] is True
        assert event_payload["is_joined"] is False
        assert len(event_payload["source_listings"]) == 2
        assert event_payload["registration_url"] == "https://events.example.org/register"
        assert client.post(
            f"/api/calendar/events/{event_id}/register", headers=owner_headers,
        ).status_code == 201

        current_payload = build_ical_event(
            "shared-uid", "Campus AI Sprint Updated", starts, starts + timedelta(days=1), status="CANCELLED",
        )
        with SessionLocal() as db:
            second = event_sync.sync_event_sources(db, owner["user"]["id"], transport)
            assert db.query(HackathonEvent).count() == 1
            assert db.query(EventSourceListing).count() == 2
            assert db.query(HackathonRegistration).filter_by(event_id=event_id).count() == 1
        assert second["events_created"] == 0
        assert second["events_updated"] == 2
        cancelled = client.get(f"/api/calendar/events/{event_id}", headers=owner_headers).json()
        assert cancelled["event_status"] == "cancelled"
        assert cancelled["is_joined"] is True
        assert cancelled["is_imported"] is True
        assert cancelled["can_edit"] is False
        assert client.delete(f"/api/calendar/events/{event_id}", headers=owner_headers).status_code == 403
        _, another_headers = register(client, "Cancelled Event Student")
        assert client.post(
            f"/api/calendar/events/{event_id}/register", headers=another_headers,
        ).status_code == 409
        with SessionLocal() as db:
            assert db.query(HackathonRegistration).filter_by(event_id=event_id).count() == 1
    transport.close()


def test_event_sync_partial_failure_and_overlap(monkeypatch):
    import httpx

    import app.services.event_sync as event_sync
    from app.database import SessionLocal
    from app.models import HackathonEvent

    starts = datetime.now(timezone.utc) + timedelta(days=45)
    payload = build_ical_event(
        "success-uid", "Permitted feed event", starts, starts + timedelta(days=1),
        event_url="https://good.example.org/hackathon",
    )
    monkeypatch.setenv("HACKMATE_ICAL_FEEDS", json.dumps([
        {"key": "available", "name": "Available Calendar", "url": "https://good.example.org/feed.ics"},
        {"key": "unavailable", "name": "Unavailable Calendar", "url": "https://down.example.org/feed.ics"},
    ]))
    monkeypatch.setattr(event_sync.time, "sleep", lambda _delay: None)
    attempts = {"down": 0}

    def handler(request):
        if "down.example.org" in request.url.host:
            attempts["down"] += 1
            return httpx.Response(503, text="temporarily unavailable")
        return httpx.Response(200, headers={"content-type": "text/calendar"}, content=payload)

    transport = httpx.Client(transport=httpx.MockTransport(handler))
    with TestClient(app) as client:
        owner, _ = register(client, "Partial Sync Owner")
        with SessionLocal() as db:
            initial_event_count = db.query(HackathonEvent).count()
        event_sync._PROCESS_LOCK.acquire()
        try:
            with SessionLocal() as db:
                assert event_sync.sync_event_sources(db, owner["user"]["id"], transport)["status"] == "already_running"
        finally:
            event_sync._PROCESS_LOCK.release()
        with SessionLocal() as db:
            result = event_sync.sync_event_sources(db, owner["user"]["id"], transport)
        assert result["status"] == "partial_failure"
        assert result["events_created"] == 1, result
        assert attempts["down"] == 3
        assert [item["status"] for item in result["sources"]] == ["success", "failed"]
        assert "https://" not in result["sources"][1]["error"]
        with SessionLocal() as db:
            assert db.query(HackathonEvent).count() == initial_event_count + 1
    transport.close()


def test_event_sync_admin_authorization_and_manual_trigger(monkeypatch):
    import app.routers.event_sync as event_sync_router

    monkeypatch.setenv("HACKMATE_ICAL_FEEDS", json.dumps([
        {"key": "authorized-feed", "name": "Authorized Feed", "url": "https://feed.example.org/events.ics"},
    ]))
    with TestClient(app) as client:
        admin, admin_headers = register(client, "Sync Administrator")
        _, other_headers = register(client, "Other Account")
        monkeypatch.setenv("HACKMATE_SYNC_ADMIN_USER_IDS", str(admin["user"]["id"]))
        monkeypatch.setattr(event_sync_router, "sync_event_sources", lambda _db, _owner_id: {
            "status": "success", "sources": [], "events_found": 2, "events_created": 1, "events_updated": 1,
        })
        assert client.get("/api/admin/event-sync/sources").status_code == 401
        assert client.get("/api/admin/event-sync/sources", headers=other_headers).status_code == 403
        sources = client.get("/api/admin/event-sync/sources", headers=admin_headers)
        assert sources.status_code == 200
        assert sources.json()[0]["name"] == "Authorized Feed"
        assert "url" not in sources.json()[0]
        result = client.post("/api/admin/event-sync/run", headers=admin_headers)
        assert result.status_code == 200
        assert result.json()["events_created"] == 1
