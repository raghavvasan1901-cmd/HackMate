# HackMate

HackMate helps students discover hackathons and projects, form complementary teams, and organize their work together.

## Features

- Register, sign in, sign out, and manage student profiles. Passwords are stored using salted scrypt hashes; API access uses expiring signed bearer tokens.
- Browse and filter opportunities and teams, publish openings, create teams, and apply to join. Team leaders can accept or decline applications.
- Get transparent estimated teammate recommendations. Scores combine complementary skills (40%), shared interests (17%), required-role fit (14%), experience mix (8%), stated availability (8%), and relevant self-reported hackathon/project experience (13%). Team balance highlights missing and underrepresented skills.
- Use a member-only workspace with assigned tasks, priorities, due dates, progress, and team chat. Tasks and messages are only accessible to current team members.
- Submit collaborator reviews, view reputation ratings, receive application notifications, explore learning roadmaps, and practice with mock hackathon prompts.
- Maintain an extended developer portfolio with education, self-reported skill proficiency, projects, courses/achievements, and hackathon history; upload a private PDF resume and optionally fetch public repositories from GitHub's unauthenticated official API.
- Team leaders can send expiring invitations. Recipients can accept or decline; acceptance checks capacity and creates membership atomically, while the original application workflow remains available.
- Browse an interactive event calendar, create/update/delete events you control, and register on HackMate to track participation. Event records are user-entered; calendar markers never imply organizer-side registration.
- Compare teammates for a team or opportunity using estimated, explainable matching that includes skill proficiency and visible self-reported project/hackathon experience. Optional AI only rewrites fact-grounded explanations; deterministic recommendations remain available without AI credentials.
- Responsive Bootstrap 5 frontend and interactive API documentation at `/docs`.

The matching algorithm is deliberately rule-based and explainable. It does not require an ML model or third-party matching service.

## Requirements

- Python 3.10 or newer
- Visual Studio Code (recommended) or another editor

## Run locally (Windows PowerShell)

From the `HackMate` project directory:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Open `.env` and replace `HACKMATE_SECRET_KEY` with a long random value before using the app beyond local experimentation. Keep `.env` private; it is excluded from Git. Without a configured key, the app generates a temporary per-process key, so login tokens will stop working when the server restarts. `HACKMATE_DATABASE_URL` defaults to a SQLite database named `hackmate.db` in the project directory.

Start the application:

```powershell
uvicorn app.main:app --reload
```

Visit:

- App: <http://127.0.0.1:8000>
- Swagger UI: <http://127.0.0.1:8000/docs>
- Health check: <http://127.0.0.1:8000/api/health>

Tables are created automatically when the application starts. New portfolio, invitation, and calendar tables are additive. Startup also applies safe SQLite `ALTER TABLE` migrations for optional review dimensions and profile visibility fields; existing reviews and portfolio records are preserved, and migrated profile visibility uses the model's defined defaults. Starter learning roadmaps and mock challenges are seeded automatically; opportunities, events, and users are created through the app. The existing `hackmate.db` and its user/team records are not replaced.

### Database configuration

To use another SQLite file, set `HACKMATE_DATABASE_URL` in `.env`, for example:

```text
HACKMATE_DATABASE_URL=sqlite:///./data/hackmate.db
```

SQLite foreign-key checks are enabled for each database connection. Models and table definitions are in `app/models.py`.

## AI assistant setup

HackMate includes an authenticated, backend-only AI assistant at `/api/ai/chat`, powered by Google's official `google-genai` SDK and the Gemini API by default. The existing OpenAI provider remains available by setting `AI_PROVIDER=openai`.

1. Copy `.env.example` to `.env`.
2. Create a Gemini API key in [Google AI Studio](https://aistudio.google.com/app/apikey), then set these values in the project-root `.env` file:

```text
HACKMATE_SECRET_KEY=replace-this-with-a-long-random-secret
HACKMATE_DATABASE_URL=sqlite:///./hackmate.db
AI_PROVIDER=gemini
AI_API_KEY=your_google_gemini_api_key
AI_MODEL=gemini-2.5-flash
AI_TIMEOUT_SECONDS=20
AI_MAX_TOKENS=400
```

`AI_API_KEY` is your Google AI Studio Gemini API key. Keep it only in `.env`; `.env` is excluded from Git. `AI_MODEL` is configurable: `gemini-2.5-flash` is the suggested starting model and is currently listed as a stable Gemini API model, but access still depends on your Google account and region. Confirm the selected model in the [Gemini API model documentation](https://ai.google.dev/gemini-api/docs/models) and your AI Studio project. `AI_SYSTEM_INSTRUCTION` is optional and can override HackMate's built-in assistant guidance. Do not put the key in frontend code or share it in support requests.

3. Restart the FastAPI server (stop it with **Ctrl+C**, then start it again using the same command used to launch it, such as `uvicorn app.main:app --reload` from the project directory).
4. Sign in and open the floating HackMate AI panel to send a message and follow-up.

The project-root `.env` is loaded explicitly when the backend starts; existing environment variables take precedence over `.env`. The API key stays in the backend and is never returned to the browser or written to application logs. If configuration is missing, the assistant reports which variable names to set; it never returns a fake success response. AI requests require an authenticated user, are limited to 10 messages per minute per user, and have bounded message/output sizes and timeouts. Only relevant role, skills, interests, availability, and the user's own team requirements are included as chat context. For optional match explanations, candidate names and IDs are omitted; only relevant profile evidence is sent, and HackMate's algorithm supplies all scores. Conversation history is kept in memory, scoped to the signed-in user, and is cleared when the server process restarts. Users can start a new chat or delete their current conversation.

The same backend key enables optional **Explain with AI** matching text. Scores and candidate selection always come from the deterministic service. If credentials are missing or the provider fails, the API reports the explanation status and the UI retains the rule-based explanation.

### Portfolio, resume, invitations, and calendar

- `HACKMATE_PRIVATE_UPLOAD_DIR` optionally changes the private PDF storage directory. Relative paths are anchored to the project root; the default is `instance/private_uploads/`, excluded from version control and not mounted as static content. Uploads are capped at 5 MB, checked for a PDF signature, stored under a random server-generated name, and delivered only after an authorization/visibility check. Keep this storage backed up and access-controlled like other private user data.
- A portfolio section defaults to public for projects, history, education, and GitHub details, while resume visibility and location visibility default to private. Owners can change those settings. Resume content is never exposed through a public static URL. Email and authentication data are not part of the public portfolio.
- GitHub data is requested server-side from `api.github.com` without OAuth or an access token. Results are only public repositories returned by GitHub; API rate limiting is surfaced, and no contribution totals are fabricated.
- Team invitations are created by team leaders only, expire after 14 days, and appear in the authenticated invitation inbox and existing notifications. Acceptance checks the recipient, expiry, duplicate membership, and capacity before adding a member.
- Calendar event dates must include a timezone and are stored in UTC. Only explicit HackMate registrations appear as joined. Event owners control edits and deletion; registration deadlines within seven days are highlighted. No event details are invented.
- Calendar feeds can be synchronized by the separate worker described below. Feed records never create HackMate registrations, and missing source fields remain unknown.
- Review dimensions (communication, reliability, and teamwork) reuse the existing review table. Existing rows are preserved and their overall rating is used as the fallback for older records. Ratings summarize collaboration reports, not technical ability.

### Permitted hackathon event feeds

The event importer supports explicitly authorized HTTPS iCalendar (`text/calendar`) feeds. It parses structured calendar data only; it does not scrape event pages. No official public event API, RSS, or iCalendar endpoint with a documented access contract was verified for Unstop, Devfolio, Devpost, MLH, HackerEarth, or Hack2Skill. Devpost's often-mentioned `hackathons.rss` URL could not be verified from an official source, so it is not enabled. The similarly named Brabble project found during research is a local voice daemon, not a hackathon feed. Community scrapers and undocumented endpoints are not integrated. Ask each provider or organizer for an authorized feed/API and its reuse terms before configuring it.

Add only permitted, working feed URLs to `.env` as JSON, for example:

```text
HACKMATE_ICAL_FEEDS=[{"key":"approved-campus-feed","name":"Approved campus calendar","url":"https://REPLACE-WITH-AUTHORIZED-HOST/events.ics"}]
```

The example URL is a placeholder, not a live source. Feed URLs must use HTTPS and must not contain embedded credentials. Keep any private feed URL confidential. Up to 10 uniquely keyed feeds can be configured; a failed source does not stop other sources. Feed requests use a 12-second timeout, bounded retries, and no redirects. Invalid event records are skipped and counted.

Standard iCalendar fields map to event name (`SUMMARY`), description, organizer, start/end (with timezone), URL, location, categories, and cancellation status. Optional extra fields are read from `X-REGISTRATION-URL`, `X-REGISTRATION-START`, `X-REGISTRATION-DEADLINE`, `X-EVENT-FORMAT`, `X-HACKMATE-SCOPE`, `X-COUNTRY`, `X-REGION`, `X-ELIGIBILITY`, `X-MIN-TEAM-SIZE`, `X-MAX-TEAM-SIZE`, and `X-PRIZE-DETAILS`. Only explicit, supported source values are stored; scope is never inferred from a title or online format. Missing data stays blank, and dates are converted to UTC. Events are linked by source key/UID and conservative exact URL or exact title/organizer/day matching. Cancellation updates event status without removing registrations; events missing from a feed are not deleted.

Set `HACKMATE_SYNC_OWNER_USER_ID` to an existing HackMate user ID whose account will own scheduled imported events, and `HACKMATE_SYNC_INTERVAL_SECONDS` to at least `60` (default `3600`). Start exactly one separate worker process from the project directory:

```powershell
python -m app.sync_worker
```

The worker is intentionally not started by FastAPI, avoiding duplicate schedulers during `--reload` or multi-worker web deployments. Operate one worker instance for the configured database; a database lock and process lock prevent overlapping sync runs. Keep the worker running under a process manager/Task Scheduler for automatic polling. The interval is measured after each sync finishes.

Set `HACKMATE_SYNC_ADMIN_USER_IDS` to a comma-separated allowlist of existing user IDs to authorize manual sync and status access. The admin-only endpoints are `GET /api/admin/event-sync/sources`, `POST /api/admin/event-sync/run`, and `GET /api/admin/event-sync/runs`. Source URLs and request credentials are not returned. `/api/calendar/events` accepts search, scope, country, region, format, technology, eligibility, deadline, source, date-range, and pagination filters. The calendar shows imported/source freshness and organizer links separately from HackMate registration; recommendations use deterministic overlap with the user's saved skills/interests and continue to work without AI credentials.

**Provider status:** the generic authorized iCalendar adapter is implemented, but there is no preconfigured or independently verified live provider feed. Automatic population therefore starts only after an operator obtains permission, supplies a real feed URL, creates/chooses the sync-owner account, and starts the worker. No Unstop, Devfolio, Devpost, MLH, HackerEarth, Hack2Skill, or Brabble integration is claimed as active.

The assistant is read-only: it does not create or modify teams, profiles, tasks, or other application records. Do not place sensitive personal data, passwords, or access tokens in prompts.

## Run tests

With the virtual environment active:

```powershell
pytest -q
```

The workflow tests use a temporary SQLite database and cover registration/login, profile edits and privacy, secure resume upload and delivery, mocked GitHub API responses, invitations and membership, calendar events and explicit participation, team/opportunity matching with evidence, task and chat authorization, reviews, notification privacy, and authenticated AI behavior using mocked provider responses, including missing credentials, input validation, timeouts, and conversation ownership.

## Project layout

```text
app/
  main.py                 FastAPI application and static frontend
  database.py             SQLite engine, session dependency, ORM base
  models.py               Relational SQLAlchemy models
  schemas.py              Validated API request schemas
  security.py             Password hashing and bearer-token authentication
  routers/
    auth.py               Accounts and profiles
    marketplace.py        Opportunities, teams, applications, matching
    collaboration.py      Tasks, workspace, chat, reviews, notifications
    learning.py           Roadmaps and mock challenges
    ai.py                 Authenticated AI chat and conversation endpoints
    portfolio.py          Portfolio, secure resume, and GitHub public data
    invitations.py        User discovery and team invite lifecycle
    calendar.py           Hackathon events and explicit registrations
    event_sync.py         Admin event-feed sync and status APIs
  services/
    event_sync.py         Authorized iCalendar adapter, normalization, deduplication, and sync
  sync_worker.py          Separate configurable scheduled feed-sync process
  services/ai_service.py  Gemini/OpenAI integrations, user context, and rate limiting
  services/common.py      Shared profile and team-access helpers
  seed.py                 Idempotent starter content
  static/
    index.html            Responsive application shell
    css/styles.css        App styling
    js/app.js             Frontend navigation and API integration
tests/
  test_workflows.py
```

## API overview

All endpoints are under `/api`. Authenticated endpoints accept `Authorization: Bearer <access_token>`.

- `/auth/register`, `/auth/login`, `/auth/me`, `/auth/logout`
- `/users/{user_id}`, `/users/me/profile`, `/users/{user_id}/reviews`
- `/users/me/portfolio` and authenticated portfolio item management under `/users/me/portfolio/*`
- `/users/me/resume` plus protected `/users/{user_id}/resume`; public GitHub data at `/users/{user_id}/github`
- `/users/search`, `/teams/{team_id}/invitations`, and `/invitations`
- `/opportunities`, `/teams`, team applications, matching, and team balance
- `/opportunities/{opportunity_id}/matches` and team matches with optional `?explain_with_ai=true`
- `/calendar/events`, event management, `/calendar/events/{event_id}/register`, and `/calendar/recommendations`
- Admin-only `/admin/event-sync/sources`, `/admin/event-sync/run`, and `/admin/event-sync/runs` for permitted-feed synchronization
- Team tasks, workspace summary, and messages
- `/notifications`, `/roadmaps`, and `/challenges`
- `/ai/chat` plus authenticated list, retrieve, and delete operations under `/ai/conversations`

Logout removes the token from the browser; tokens expire after 24 hours. The demo token implementation is intentionally small and suitable for local learning, not a replacement for a production identity provider or token-revocation service. Use HTTPS and a strong secret for deployments.

## Notes

- The frontend loads Bootstrap, Bootstrap Icons, and fonts from public CDNs, so those visual assets require an internet connection. The API and core interactions are served by the local FastAPI app.
- Team chat uses a simple request/refresh model rather than a WebSocket.
- Mock hackathon drafts are saved in browser-local storage; they are not submitted to the server.
- Profile photo input accepts a URL; images are not uploaded to the server.
- Do not use real credentials in test data.
