const API = "/api";
const state = {
  token: localStorage.getItem("hackmate_token"),
  user: null,
  page: "dashboard",
  teamId: Number(sessionStorage.getItem("hackmate_team_id")) || null,
  opportunityId: null,
  error: "",
  aiOpen: false,
  aiConversationId: null,
  aiBusy: false,
  profileId: null,
  calendarMonth: new Date(new Date().getFullYear(), new Date().getMonth(), 1),
  calendarFilters: {},
  calendarEventId: null,
  calendarEditingId: null,
  unreadNotificationCount: 0,
  pendingInvitationCount: 0,
  matchingExplainWithAi: false
};

const labels = {
  dashboard: "Overview", login: "Login", register: "Create account", profile: "My profile",
  "edit-profile": "Edit profile", opportunities: "Discover opportunities", "create-opportunity": "Post opportunity",
  "opportunity-detail": "Opportunity details", teams: "Find a team", "create-team": "Start a team",
  "team-detail": "Team details", applications: "Team applications", matching: "Smart teammate matching",
  balance: "Team balance analyzer", workspace: "Team workspace", tasks: "Task board",
  chat: "Team chat", reviews: "Reviews & ratings", reputation: "Reputation",
  roadmaps: "Learning roadmaps", challenges: "Mock hackathon", notifications: "Notifications",
  assistant: "HackMate AI", calendar: "Hackathon calendar", invitations: "Team invitations"
};

const esc = value => String(value ?? "").replace(/[&<>"']/g, char => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
}[char]));
const initials = name => (name || "HM").trim().split(/\s+/).slice(0, 2).map(part => part[0]).join("").toUpperCase();
const dateLabel = date => date ? new Date(date).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }) : "No deadline";
const commaValues = value => value.split(",").map(item => item.trim()).filter(Boolean);

function notify(message, error = false) {
  const region = document.getElementById("toast-region");
  const toast = document.createElement("div");
  toast.className = `app-toast${error ? " error" : ""}`;
  toast.textContent = message;
  region.append(toast);
  setTimeout(() => toast.remove(), 3600);
}

async function api(path, options = {}) {
  const isFormData = typeof FormData !== "undefined" && options.body instanceof FormData;
  const headers = { ...(options.body && !isFormData ? { "Content-Type": "application/json" } : {}), ...(options.headers || {}) };
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  let response;
  try {
    response = await fetch(`${API}${path}`, { ...options, headers });
  } catch (error) {
    console.error("HackMate network request failed", { path, error });
    throw new Error("Could not reach HackMate. Check that the server is running and try again.");
  }
  let payload = {};
  try { payload = await response.json(); } catch { /* Non-JSON error response */ }
  if (!response.ok) {
    console.warn("HackMate API request returned an error", {
      method: options.method || "GET",
      path: new URL(`${API}${path}`, location.origin).pathname,
      status: response.status
    });
    const responseDetail = payload?.detail;
    const validationDetails = Array.isArray(responseDetail)
      ? responseDetail.map(item => item?.msg).filter(Boolean).join("; ")
      : "";
    const detail = typeof responseDetail === "string"
      ? responseDetail
      : validationDetails || `HackMate request failed (HTTP ${response.status}). Please try again.`;
    if (response.status === 401 && state.token) {
      state.token = null;
      state.user = null;
      state.aiConversationId = null;
      localStorage.removeItem("hackmate_token");
      document.querySelector("#hackmate-ai-widget .hackmate-ai-messages")?.replaceChildren();
      updateAccount();
    }
    throw new Error(detail);
  }
  return payload;
}

function updateAccount() {
  const name = document.getElementById("nav-name");
  const status = document.getElementById("nav-status");
  const avatar = document.getElementById("nav-avatar");
  const logout = document.getElementById("logout-button");
  const assistantStatus = document.getElementById("ai-auth-state");
  const topbarAccount = document.getElementById("topbar-account");
  const topbarSignin = document.getElementById("topbar-signin");
  const topbarAvatar = document.getElementById("topbar-avatar");
  const topbarName = document.getElementById("topbar-name");
  if (name) name.textContent = state.user?.name || "Welcome!";
  if (status) status.textContent = state.user ? (state.user.preferred_role || "HackMate member") : "Sign in to get started";
  if (logout) logout.hidden = !state.user;
  if (assistantStatus) assistantStatus.textContent = state.user ? "Ready to brainstorm" : "Sign in to start a conversation";
  if (topbarAccount) topbarAccount.hidden = !state.user;
  if (topbarSignin) topbarSignin.hidden = Boolean(state.user);
  if (topbarName) topbarName.textContent = state.user?.name || "";
  if (topbarAvatar) {
    topbarAvatar.textContent = initials(state.user?.name);
    topbarAvatar.innerHTML = state.user?.photo_url ? `<img src="${esc(state.user.photo_url)}" alt="">` : esc(initials(state.user?.name));
  }
  if (avatar) {
    avatar.textContent = initials(state.user?.name);
    if (state.user?.photo_url) avatar.innerHTML = `<img src="${esc(state.user.photo_url)}" alt="">`;
  }
  updateNavigationBadges();
}

function updateNavigationBadges() {
  const notificationCount = document.getElementById("notification-count");
  const notificationDot = document.querySelector(".notification-dot");
  const navNotificationCount = document.getElementById("nav-notification-count");
  const invitationCount = document.getElementById("invitation-count");
  for (const [element, count] of [
    [notificationCount, state.unreadNotificationCount],
    [navNotificationCount, state.unreadNotificationCount],
    [invitationCount, state.pendingInvitationCount]
  ]) {
    if (!element) continue;
    element.hidden = !state.user || count < 1;
    element.textContent = count > 99 ? "99+" : String(count);
  }
  if (notificationDot) notificationDot.hidden = !state.user || state.unreadNotificationCount < 1;
  const notificationsButton = document.querySelector(".notification-button");
  if (notificationsButton) {
    notificationsButton.setAttribute(
      "aria-label",
      state.unreadNotificationCount
        ? `Notifications, ${state.unreadNotificationCount} unread`
        : "Notifications"
    );
  }
}

function heading(title, subtitle, action = "") {
  return `<div class="page-heading"><div><div class="eyebrow">HackMate community</div><h1>${esc(title)}</h1><p>${esc(subtitle)}</p></div>${action}</div>`;
}
function button(label, page, kind = "primary") {
  return `<button class="btn btn-${kind} btn-sm" data-page="${esc(page)}">${esc(label)}</button>`;
}
function tags(items = []) {
  return items.length ? `<div class="tag-row">${items.map(item => `<span class="skill-tag">${esc(item)}</span>`).join("")}</div>` : "";
}
function empty(icon, title, text, page, actionLabel) {
  return `<div class="empty-state"><i class="bi ${icon}"></i><h3>${esc(title)}</h3><p>${esc(text)}</p>${page ? `<div class="mt-3">${button(actionLabel || "Get started", page)}</div>` : ""}</div>`;
}
function errorMessage(error) {
  state.error = error?.message || "Something went wrong";
  console.warn("HackMate action failed", { page: state.page, message: state.error });
  notify(state.error, true);
}
function formatAiMarkdown(text = "") {
  const codeBlocks = [];
  const source = String(text).replace(/```([^\n]*)\n?([\s\S]*?)```/g, (_match, _language, code) => {
    const marker = `\uE000${codeBlocks.length}\uE001`;
    codeBlocks.push(`<pre><code>${esc(code.trimEnd())}</code></pre>`);
    return marker;
  });
  const inline = value => esc(value)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>");
  const lines = source.split(/\r?\n/);
  const output = [];
  let listType = null;
  const closeList = () => {
    if (listType) output.push(`</${listType}>`);
    listType = null;
  };
  for (const line of lines) {
    const unordered = line.match(/^\s*[-*]\s+(.+)$/);
    const ordered = line.match(/^\s*\d+[.)]\s+(.+)$/);
    const item = unordered || ordered;
    if (item) {
      const nextType = unordered ? "ul" : "ol";
      if (listType !== nextType) {
        closeList();
        listType = nextType;
        output.push(`<${listType}>`);
      }
      output.push(`<li>${inline(item[1])}</li>`);
      continue;
    }
    closeList();
    if (!line.trim()) continue;
    const marker = line.match(/^\uE000(\d+)\uE001$/);
    output.push(marker ? `__HACKMATE_CODE_${marker[1]}__` : `<p>${inline(line)}</p>`);
  }
  closeList();
  return output.join("").replace(/__HACKMATE_CODE_(\d+)__/g, (_match, index) => codeBlocks[Number(index)] || "");
}
function ensureAiWidget() {
  if (document.getElementById("hackmate-ai-widget")) return;
  const widget = document.createElement("div");
  widget.id = "hackmate-ai-widget";
  widget.className = "hackmate-ai-widget";
  widget.innerHTML = `
    <button class="hackmate-ai-fab" type="button" aria-label="Open HackMate AI" aria-expanded="false" aria-controls="hackmate-ai-panel">
      <i class="bi bi-stars"></i>
    </button>
    <section id="hackmate-ai-panel" class="hackmate-ai-panel" aria-label="HackMate AI chat" aria-hidden="true">
      <div class="hackmate-ai-header">
        <div class="ai-assistant-identity">
          <span class="ai-assistant-icon"><i class="bi bi-stars"></i></span>
          <div>
            <div class="eyebrow">HackMate AI</div>
            <h3>Project partner</h3>
            <small id="ai-auth-state">${state.user ? "Ready to brainstorm" : "Sign in to start a conversation"}</small>
          </div>
        </div>
        <div class="hackmate-ai-actions">
          <button type="button" class="chip-button" data-action="ai-new-chat" title="Start a new conversation"><i class="bi bi-plus-lg"></i><span>New</span></button>
          <button type="button" class="chip-button" data-action="ai-clear" title="Delete this conversation"><i class="bi bi-trash3"></i></button>
          <button type="button" class="icon-button ai-close" data-action="ai-close" aria-label="Close chat"><i class="bi bi-x-lg"></i></button>
        </div>
      </div>
      <div class="hackmate-ai-welcome">Hi! I'm HackMate AI. I can help you discover project ideas, plan hackathons, break your MVP into tasks, choose a tech stack, and identify the skills your team needs. What would you like to build?</div>
      <div class="hackmate-ai-suggestions">
        <button type="button" class="chip" data-ai-prompt="Generate a hackathon project idea">Project idea</button>
        <button type="button" class="chip" data-ai-prompt="Create a 24-hour hackathon roadmap">24-hour roadmap</button>
        <button type="button" class="chip" data-ai-prompt="Help me choose a tech stack">Tech stack</button>
        <button type="button" class="chip" data-ai-prompt="Break my project into tasks">Task breakdown</button>
        <button type="button" class="chip" data-ai-prompt="Identify missing skills in my team">Team skills</button>
        <button type="button" class="chip" data-ai-prompt="Help me prepare a pitch for judges">Pitch prep</button>
        <button type="button" class="chip" data-ai-prompt="Explain or help debug this programming problem">Debug help</button>
      </div>
      <div class="hackmate-ai-messages" role="log" aria-live="polite" aria-relevant="additions text"></div>
      <div class="hackmate-ai-input-row">
        <textarea rows="1" class="hackmate-ai-input" aria-label="Message HackMate AI" placeholder="Describe what you're building..." maxlength="2000"></textarea>
        <button type="button" class="hackmate-ai-send" data-action="ai-send" aria-label="Send message"><i class="bi bi-arrow-up"></i></button>
      </div>
      <div class="ai-privacy-note"><i class="bi bi-shield-check"></i> Your profile context is limited to relevant skills and team requirements.</div>
    </section>
  `;
  document.body.appendChild(widget);
  const input = widget.querySelector(".hackmate-ai-input");
  input.addEventListener("keydown", event => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendAiMessage(input.value);
    }
  });
  const fab = widget.querySelector(".hackmate-ai-fab");
  fab.addEventListener("click", () => {
    const panel = widget.querySelector(".hackmate-ai-panel");
    const isOpen = panel.classList.toggle("open");
    panel.setAttribute("aria-hidden", String(!isOpen));
    fab.setAttribute("aria-expanded", String(isOpen));
    if (isOpen) input.focus();
  });
  widget.querySelector("[data-action='ai-close']").addEventListener("click", () => {
    widget.querySelector(".hackmate-ai-panel").classList.remove("open");
    widget.querySelector(".hackmate-ai-panel").setAttribute("aria-hidden", "true");
    fab.setAttribute("aria-expanded", "false");
  });
  widget.querySelector("[data-action='ai-send']").addEventListener("click", async () => {
    await sendAiMessage(input.value);
  });
  widget.querySelector("[data-action='ai-new-chat']").addEventListener("click", () => {
    if (state.aiBusy) return;
    state.aiConversationId = null;
    widget.querySelector(".hackmate-ai-messages").replaceChildren();
    notify("Started a new HackMate AI conversation.");
    input.focus();
  });
}
function addAiMessage(role, content, typing = false) {
  const widget = document.getElementById("hackmate-ai-widget");
  if (!widget) return null;
  const messages = widget.querySelector(".hackmate-ai-messages");
  const row = document.createElement("div");
  row.className = `ai-message ${role}`;
  const bubble = document.createElement("div");
  bubble.className = "ai-bubble";
  bubble.innerHTML = typing
    ? '<span class="ai-typing" role="status" aria-label="HackMate AI is typing"><i></i><i></i><i></i></span>'
    : formatAiMarkdown(content);
  row.appendChild(bubble);
  messages.appendChild(row);
  messages.scrollTop = messages.scrollHeight;
  return bubble;
}
async function sendAiMessage(message, retry = false) {
  const widget = document.getElementById("hackmate-ai-widget");
  if (!widget || state.aiBusy) return;
  const input = widget.querySelector(".hackmate-ai-input");
  const prompt = String(message || "").trim();
  if (!prompt) return;
  if (!state.token) {
    input.value = "";
    widget.querySelector(".hackmate-ai-panel").classList.add("open");
    addAiMessage("assistant", "Please sign in to use HackMate AI. Your conversations are private to your account.");
    return;
  }
  state.aiBusy = true;
  input.value = "";
  const sendButton = widget.querySelector("[data-action='ai-send']");
  const newChatButton = widget.querySelector("[data-action='ai-new-chat']");
  const clearButton = widget.querySelector("[data-action='ai-clear']");
  sendButton.disabled = true;
  newChatButton.disabled = true;
  clearButton.disabled = true;
  widget.querySelector(".hackmate-ai-panel").classList.add("open");
  if (!retry) addAiMessage("user", prompt);
  const replyNode = addAiMessage("assistant", "", true);
  try {
    const response = await api("/ai/chat", {
      method: "POST",
      body: JSON.stringify({ message: prompt, conversation_id: state.aiConversationId })
    });
    state.aiConversationId = response.conversation_id;
    replyNode.innerHTML = formatAiMarkdown(response.reply);
  } catch (error) {
    replyNode.innerHTML = `<span class="ai-error">${esc(error.message)}</span><button type="button" class="ai-retry" data-action="ai-retry" data-prompt="${esc(prompt)}"><i class="bi bi-arrow-clockwise"></i> Try again</button>`;
  } finally {
    state.aiBusy = false;
    sendButton.disabled = false;
    newChatButton.disabled = false;
    clearButton.disabled = false;
    widget.querySelector(".hackmate-ai-messages").scrollTop = widget.querySelector(".hackmate-ai-messages").scrollHeight;
    input.focus();
  }
}
async function restoreAiConversation() {
  if (!state.token) return;
  state.aiConversationId = null;
  document.querySelector("#hackmate-ai-widget .hackmate-ai-messages")?.replaceChildren();
  try {
    const conversations = await api("/ai/conversations");
    const latest = conversations[0];
    if (!latest) return;
    const conversation = await api(`/ai/conversations/${encodeURIComponent(latest.id)}`);
    state.aiConversationId = latest.id;
    const messages = document.querySelector("#hackmate-ai-widget .hackmate-ai-messages");
    messages.replaceChildren();
    for (const message of conversation.messages || []) {
      if (message.role === "user" || message.role === "assistant") {
        addAiMessage(message.role, message.content);
      }
    }
  } catch (error) {
    if (error.message !== "Authentication required") notify(error.message, true);
  }
}
function openAiChat() {
  ensureAiWidget();
  const widget = document.getElementById("hackmate-ai-widget");
  const panel = widget.querySelector(".hackmate-ai-panel");
  panel.classList.add("open");
  panel.setAttribute("aria-hidden", "false");
  widget.querySelector(".hackmate-ai-fab").setAttribute("aria-expanded", "true");
  const input = widget.querySelector(".hackmate-ai-input");
  input.focus();
}
function memberLabel(team) {
  return `${team.member_count}/${team.max_size} members`;
}

async function getMyTeams() {
  const all = await api("/teams");
  const mine = state.user ? all.filter(team => team.members.some(member => member.id === state.user.id)) : [];
  if (!mine.length) {
    state.teamId = null;
    sessionStorage.removeItem("hackmate_team_id");
    return [];
  }
  if (!mine.some(team => team.id === state.teamId)) state.teamId = mine[0].id;
  sessionStorage.setItem("hackmate_team_id", state.teamId);
  return mine;
}
function selectTeam(teams) {
  return `<div class="mb-3"><label class="form-label" for="team-picker">Team workspace</label><select id="team-picker" class="form-select">${teams.map(team => `<option value="${team.id}" ${team.id === state.teamId ? "selected" : ""}>${esc(team.name)}</option>`).join("")}</select></div>`;
}
function closeMobileNavigation() {
  document.getElementById("sidebar").classList.remove("open");
  document.body.classList.remove("sidebar-open");
  document.getElementById("sidebar-backdrop").hidden = true;
  document.getElementById("mobile-menu").setAttribute("aria-expanded", "false");
}
function toggleMobileNavigation() {
  const sidebar = document.getElementById("sidebar");
  const isOpen = sidebar.classList.toggle("open");
  document.body.classList.toggle("sidebar-open", isOpen);
  document.getElementById("mobile-menu").setAttribute("aria-expanded", String(isOpen));
  document.getElementById("sidebar-backdrop").hidden = !isOpen;
}
function setSidebarCollapsed(collapsed) {
  document.getElementById("sidebar").classList.toggle("collapsed", collapsed);
  document.querySelector(".main-column").classList.toggle("sidebar-collapsed", collapsed);
  document.getElementById("sidebar-toggle").setAttribute("aria-expanded", String(!collapsed));
  document.getElementById("sidebar-toggle").setAttribute(
    "aria-label",
    collapsed ? "Expand sidebar" : "Collapse sidebar"
  );
  localStorage.setItem("hackmate_sidebar_collapsed", String(collapsed));
}

async function render() {
  const content = document.getElementById("content");
  const label = labels[state.page] || "Overview";
  document.getElementById("page-crumb").textContent = label;
  document.querySelectorAll(".app-nav [data-page]").forEach(node => {
    const active = node.dataset.page === state.page;
    node.classList.toggle("active", active);
    if (active) node.setAttribute("aria-current", "page");
    else node.removeAttribute("aria-current");
  });
  content.setAttribute("aria-busy", "true");
  content.innerHTML = state.page === "dashboard"
    ? `<div class="loading-skeleton" role="status" aria-label="Loading your workspace"><div class="skeleton-block skeleton-hero"></div><div class="skeleton-metrics"><span></span><span></span><span></span><span></span></div><div class="skeleton-panels"><span></span><span></span></div></div>`
    : `<div class="loading-state" role="status"><span class="spinner-border spinner-border-sm"></span> Loading ${esc(label.toLowerCase())}…</div>`;
  try {
    if (state.token && !state.user) state.user = await api("/auth/me");
    updateAccount();
    content.innerHTML = await renderPage();
    content.setAttribute("aria-busy", "false");
  } catch (error) {
    console.error("HackMate page failed to load", { page: state.page, error });
    content.setAttribute("aria-busy", "false");
    content.innerHTML = `<div class="page-error">${heading(label, "We couldn't load this section.")}<div class="alert alert-danger" role="alert"><strong>Something went wrong.</strong><span>${esc(error.message)}</span></div><button class="btn btn-outline-primary btn-sm" data-action="retry"><i class="bi bi-arrow-clockwise me-1"></i>Try again</button></div>`;
    errorMessage(error);
  }
}

async function renderPage() {
  switch (state.page) {
    case "login": return renderAuth(false);
    case "register": return renderAuth(true);
    case "profile": return renderProfile(false);
    case "edit-profile": return renderProfile(true);
    case "dashboard": return renderDashboard();
    case "opportunities": return renderOpportunities();
    case "create-opportunity": return renderOpportunityForm();
    case "opportunity-detail": return renderOpportunityDetail();
    case "teams": return renderTeams();
    case "create-team": return renderTeamForm();
    case "team-detail": return renderTeamDetail();
    case "applications": return renderApplications();
    case "matching": return renderMatches();
    case "balance": return renderBalance();
    case "workspace": case "tasks": return renderWorkspace();
    case "chat": return renderChat();
    case "reviews": return renderReviews();
    case "reputation": return renderReputation();
    case "roadmaps": return renderRoadmaps();
    case "challenges": return renderChallenges();
    case "notifications": return renderNotifications();
    case "assistant": return renderAssistantPage();
    case "calendar": return renderCalendar();
    case "invitations": return renderInvitations();
    default: return renderDashboard();
  }
}

function renderAuth(register) {
  const title = register ? "Create your account" : "Welcome back";
  return `<div class="auth-layout">
    <section class="auth-promo"><a class="auth-brand" href="#" data-page="dashboard"><span class="brand-mark"><i class="bi bi-lightning-charge-fill"></i></span> hackmate<span class="brand-dot">.</span></a>
      <span class="auth-kicker">THE NEXT BIG THING STARTS WITH A TEAM</span>
      <h2>Build your idea<br>with the right people.</h2>
      <p>Discover projects, find teammates who complement your skills, and bring your next hackathon idea to life.</p>
      <div class="auth-benefits"><span><i class="bi bi-check2-circle"></i> Find your perfect team fit</span><span><i class="bi bi-check2-circle"></i> Turn ideas into a real MVP</span><span><i class="bi bi-check2-circle"></i> Keep your team in sync</span></div>
      <div class="auth-promo-orbit"><i class="bi bi-stars"></i></div>
    </section>
    <section class="auth-card"><div class="auth-mobile-brand"><span class="brand-mark"><i class="bi bi-lightning-charge-fill"></i></span> hackmate<span class="brand-dot">.</span></div>
      <div class="eyebrow">${register ? "JOIN THE COMMUNITY" : "YOUR WORKSPACE IS WAITING"}</div><h1>${title}</h1><p>${register ? "Create an account and meet your next collaborators." : "Sign in to pick up where your team left off."}</p>
      <form data-form="${register ? "register" : "login"}">
        ${register ? `<div class="mb-3"><label class="form-label" for="auth-name">Full name</label><input id="auth-name" class="form-control" name="name" minlength="2" maxlength="100" required autocomplete="name" placeholder="e.g. Alex Morgan"></div>` : ""}
        <div class="mb-3"><label class="form-label" for="auth-email">Email address</label><input id="auth-email" class="form-control" type="email" name="email" required autocomplete="email" placeholder="you@college.edu"></div>
        <div class="mb-3"><label class="form-label" for="auth-password">Password</label><div class="password-field"><input id="auth-password" class="form-control" type="password" name="password" minlength="${register ? "8" : "1"}" required autocomplete="${register ? "new-password" : "current-password"}" placeholder="${register ? "At least 8 characters" : "Your password"}"><button type="button" class="password-toggle" data-action="password-toggle" aria-label="Show password" aria-pressed="false"><i class="bi bi-eye"></i></button></div></div>
        <button class="btn btn-primary w-100 auth-submit" type="submit">${register ? "Create account" : "Sign in"} <i class="bi bi-arrow-right ms-1"></i></button>
      </form><div class="auth-switch">${register ? "Already have an account?" : "New to HackMate?"} <button data-page="${register ? "login" : "register"}">${register ? "Sign in" : "Create an account"}</button></div>
      ${!state.user ? `<div class="auth-switch"><button data-page="opportunities">Explore opportunities without signing in <i class="bi bi-arrow-up-right ms-1"></i></button></div>` : ""}
    </section>
  </div>`;
}

async function renderDashboard() {
  const [opportunities, teams, roadmaps, notifications, invitations, calendarEvents, portfolio] = await Promise.all([
    api("/opportunities"), api("/teams"), api("/roadmaps"), state.user ? api("/notifications") : Promise.resolve([]),
    state.user ? api("/invitations") : Promise.resolve({ received: [], sent: [] }),
    state.user ? api(`/calendar/events?from_date=${monthDateKey(new Date())}&to_date=${monthDateKey(new Date(Date.now() + 30 * 86400000))}`) : Promise.resolve([]),
    state.user ? api("/users/me/portfolio") : Promise.resolve(null)
  ]);
  state.unreadNotificationCount = notifications.filter(item => !item.read).length;
  state.pendingInvitationCount = invitations.received.filter(item => item.status === "pending").length;
  updateNavigationBadges();
  const mine = state.user ? teams.filter(team => team.members.some(member => member.id === state.user.id)) : [];
  const pendingInvitations = invitations.received.filter(item => item.status === "pending");
  const joinedEvents = calendarEvents.filter(item => item.is_joined && !item.is_completed);
  const upcomingEvents = calendarEvents.filter(item => !item.is_completed && item.event_status !== "cancelled");
  const teamSummaries = await Promise.all(mine.map(async (team, index) => {
    try {
      const workspace = await api(`/teams/${team.id}/workspace`);
      const matches = index === 0 ? await api(`/teams/${team.id}/matches?limit=2`) : [];
      return { team, workspace, matches };
    } catch (error) {
      console.warn("Could not load dashboard workspace details", { teamId: team.id, error });
      return { team, workspace: null, matches: [], error: error.message };
    }
  }));
  const profileCompletion = state.user ? (() => {
    const fields = [
      state.user.name, state.user.preferred_role, state.user.college, state.user.department,
      state.user.bio, state.user.experience, state.user.availability,
      state.user.skills?.length, state.user.interests?.length, portfolio?.headline, portfolio?.degree,
      portfolio?.github_username, portfolio?.projects?.length, portfolio?.hackathon_history?.length
    ];
    const filled = fields.filter(value => value !== "" && value !== null && value !== undefined && value !== 0).length;
    return Math.min(100, Math.round((filled / fields.length) * 100));
  })() : 0;
  const cards = opportunities.slice(0, 2);
  const taskCount = teamSummaries.reduce((total, entry) => total + (entry.workspace ? entry.workspace.total_tasks : 0), 0);
  const pendingTasks = teamSummaries.reduce((total, entry) => total + (entry.workspace ? Math.max(0, entry.workspace.total_tasks - entry.workspace.completed_tasks) : 0), 0);
  const pendingTaskItems = teamSummaries.flatMap(entry => (entry.workspace?.tasks || [])
    .filter(task => task.status !== "Done")
    .map(task => ({ ...task, team_name: entry.team.name }))).slice(0, 3);
  return `<div class="hero-card"><div class="eyebrow text-white-50">${state.user ? "YOUR HACKMATE WORKSPACE" : "YOUR NEXT BIG IDEA STARTS HERE"}</div><h1>${state.user ? `Welcome back, ${esc(state.user.name)}.` : "Find your people.<br>Build what matters."}</h1><p>${state.user ? "Your next build starts with a team that complements your strengths. Pick up where you left off or explore something new." : "The right teammate can turn a good idea into a great one. Discover opportunities and build a team that brings every skill to the table."}</p><div class="hero-actions">${button("Find teammates", "teams", "light")}${button("Create a team", "create-team", "outline-light")}${button("Discover hackathons", "calendar", "outline-light")}<button class="btn btn-outline-light btn-sm" data-action="open-ai"><i class="bi bi-stars me-1"></i>Ask HackMate AI</button></div></div>
    <div class="stats-grid">
      <div class="stat-card"><span class="stat-icon"><i class="bi bi-compass"></i></span><div class="stat-value">${opportunities.length}</div><div class="stat-label">Open opportunities</div></div>
      <div class="stat-card"><span class="stat-icon"><i class="bi bi-people"></i></span><div class="stat-value">${teams.length}</div><div class="stat-label">Teams forming</div></div>
      <div class="stat-card"><span class="stat-icon"><i class="bi bi-person-check"></i></span><div class="stat-value">${mine.length}</div><div class="stat-label">Your teams</div></div>
      <div class="stat-card"><span class="stat-icon"><i class="bi bi-bell"></i></span><div class="stat-value">${state.unreadNotificationCount}</div><div class="stat-label">Unread notifications</div></div>
    </div>
    <div class="two-col mt-4">
      <div class="panel dashboard-panel">
        <div class="panel-heading"><h3>Profile completion</h3><span class="subtle">${profileCompletion}%</span></div>
        <div class="profile-meter"><span style="width:${profileCompletion}%"></span></div>
        <div class="mini-grid">
          <div class="mini-stat"><strong>${pendingTasks}</strong><span>Open tasks</span></div>
          <div class="mini-stat"><strong>${taskCount}</strong><span>Tracked tasks</span></div>
          <div class="mini-stat"><strong>${mine.length}</strong><span>Current teams</span></div>
          <div class="mini-stat"><strong>${pendingInvitations.length}</strong><span>Pending invites</span></div>
        </div>
        <div class="two-col mt-4"><div class="panel"><div class="panel-heading"><h3>Your registered hackathons</h3><button class="text-link" data-page="calendar">Open calendar</button></div>${joinedEvents.length ? joinedEvents.slice(0, 3).map(item => `<button class="event-list-row" data-action="calendar-event" data-id="${item.id}"><span class="event-list-date">${esc(dateLabel(item.starts_at))}</span><span class="event-list-info"><strong>${esc(item.name)}</strong><small>${esc(item.location || item.organizer || "Event details")}</small></span><span class="badge-soft badge-green">Joined</span></button>`).join("") : `<p class="text-secondary small mb-0">No upcoming registrations yet. Register for an event to see it here.</p>`}</div><div class="panel"><div class="panel-heading"><h3>Team invitations</h3><button class="text-link" data-page="invitations">Manage</button></div>${pendingInvitations.length ? pendingInvitations.slice(0, 3).map(item => `<div class="task-row"><div class="task-main"><strong>${esc(item.team_name)}</strong><small>From ${esc(item.inviter?.name || "team member")} · expires ${esc(dateLabel(item.expires_at))}</small></div><button class="btn btn-outline-primary btn-sm" data-page="invitations">Respond</button></div>`).join("") : `<p class="text-secondary small mb-0">No pending team invitations.</p>`}</div></div>
        <div class="dashboard-task-list"><div class="dashboard-task-heading"><strong>Pending tasks</strong><button class="text-link" data-page="tasks">View board</button></div>
          ${pendingTaskItems.length ? pendingTaskItems.map(task => `<div class="task-row"><div class="task-main"><strong>${esc(task.title)}</strong><small>${esc(task.team_name)} · ${esc(task.status)}${task.due_date ? ` · due ${esc(dateLabel(task.due_date))}` : ""}</small></div><span class="badge-soft ${task.priority === "High" ? "badge-red" : "badge-gray"}">${esc(task.priority)}</span></div>`).join("") : teamSummaries.some(entry => entry.error) ? `<div class="dashboard-inline-error" role="status">Some team workspace details couldn't be loaded. <button class="text-link" data-action="retry">Retry</button></div>` : `<p class="text-secondary small mb-0">${mine.length ? "No open tasks across your teams." : "Join a team to see its shared tasks here."}</p>`}
        </div>
      </div>
      <div class="panel dashboard-panel">
        <div class="panel-heading"><div><span class="eyebrow">Your next milestone</span><h3 class="mt-1">Upcoming hackathons</h3></div><button class="text-link" data-page="calendar">Open calendar</button></div>
        ${upcomingEvents.length ? upcomingEvents.slice(0, 3).map(item => `<button class="event-list-row" data-action="calendar-event" data-id="${item.id}"><span class="event-list-date">${esc(dateLabel(item.starts_at))}</span><span class="event-list-info"><strong>${esc(item.name)}</strong><small>${esc(item.organizer || item.location || "Event details")}</small></span>${item.is_joined ? '<span class="badge-soft badge-green">Joined</span>' : '<span class="badge-soft badge-gray">Explore</span>'}</button>`).join("") : `<p class="dashboard-empty-note">No events in the next 30 days. Browse the calendar for upcoming opportunities.</p>`}
        <div class="dashboard-ai-callout"><div><span class="eyebrow">Build with focus</span><p>Plan your next sprint or pressure-test an idea with your team-aware AI assistant.</p></div><button class="btn btn-outline-primary btn-sm" data-action="open-ai"><i class="bi bi-stars me-1"></i>Ask AI</button></div>
        <div class="suggested-prompt-list">
          <button class="chip" data-ai-prompt="Generate a hackathon project idea">Project idea</button>
          <button class="chip" data-ai-prompt="Create a 24-hour hackathon roadmap">24h roadmap</button>
          <button class="chip" data-ai-prompt="Recommend teammates and missing skills">Team gaps</button>
        </div>
      </div>
    </div>
    <div class="section-title"><h2>Opportunities to explore</h2><button data-page="opportunities">Browse all <i class="bi bi-arrow-right"></i></button></div>
    ${cards.length ? `<div class="item-grid">${cards.map(opportunityCard).join("")}</div>` : empty("bi-compass", "Your next opportunity is waiting", "Create the first opening for your campus community.", "create-opportunity", "Post an opportunity")}
    <div class="two-col mt-4"><div class="panel"><div class="panel-heading"><h3>Your team spaces</h3><span class="subtle">${mine.length} joined</span></div>${mine.length ? mine.slice(0, 3).map(team => teamListRow(team)).join("") : `<p class="text-secondary small mb-0">You haven't joined a team yet. Find a project that fits your skills.</p><div class="mt-3">${button("Find a team", "teams", "outline-primary")}</div>`}</div>
    <div class="panel"><div class="panel-heading"><h3>Top teammate matches</h3><span class="subtle">Live data</span></div>${teamSummaries.length && teamSummaries[0].matches.length ? teamSummaries[0].matches.map(match => `<div class="task-row"><div class="task-main"><strong>${esc(match.user.name)}</strong><small>${esc(match.complementary_skills.join(", ") || "Role fit")}</small></div><span class="badge-soft badge-green">${match.score}%</span></div>`).join("") : `<p class="text-secondary small mb-0">Create or join a team to see relevant teammate recommendations.</p>`}<button class="text-link mt-2" data-page="matching">Open matching center <i class="bi bi-arrow-right"></i></button></div></div>
    <div class="two-col mt-4"><div class="panel"><div class="panel-heading"><h3>Learning roadmaps</h3><span class="subtle">Available paths</span></div>${roadmaps.slice(0, 2).map(item => `<div class="task-row"><div class="task-main"><strong>${esc(item.title)}</strong><small>${esc(item.domain)}</small></div><i class="bi bi-arrow-up-right text-secondary"></i></div>`).join("")}<button class="text-link mt-2" data-page="roadmaps">Explore roadmaps <i class="bi bi-arrow-right"></i></button></div>
    <div class="panel"><div class="panel-heading"><h3>Recent notifications</h3><span class="subtle">${notifications.length} total</span></div>${notifications.slice(0, 3).map(item => `<div class="task-row"><div class="task-main"><strong>${esc(item.message)}</strong><small>${esc(dateLabel(item.created_at))}</small></div>${item.read ? '<span class="badge-soft badge-gray">Read</span>' : '<span class="badge-soft badge-green">New</span>'}</div>`).join("") || `<p class="text-secondary small mb-0">No notifications yet. Keep building momentum.</p>`}<button class="text-link mt-2" data-page="notifications">View all <i class="bi bi-arrow-right"></i></button></div></div>`;
}

async function renderAssistantPage() {
  if (!state.user) {
    return `${heading("HackMate AI", "Ask for ideas, plans, and team guidance.")}${empty("bi-person-lock", "Sign in required", "Log in to get personalized project ideas and teammate guidance.", "login", "Sign in")}`;
  }
  const myTeams = await getMyTeams();
  let teamContext = "No current team selected.";
  if (myTeams.length && state.teamId) {
    const team = myTeams.find(item => item.id === state.teamId) || myTeams[0];
    teamContext = `${team.name} · ${team.members.length} members · ${team.required_skills.join(", ") || "General project support"}`;
  }
  return `${heading("HackMate AI", "Brainstorm ideas, plan your sprint, and sharpen your pitch.")}
    <div class="assistant-shell panel">
      <div class="assistant-meta">
        <div>
          <div class="eyebrow">AI workspace</div>
          <h2>${esc(state.user.name)}</h2>
        </div>
        <span class="badge-soft badge-green">${esc(teamContext)}</span>
      </div>
      <div class="assistant-prompt-grid">
        <button class="chip" data-ai-prompt="Generate a hackathon project idea">Generate a hackathon project idea</button>
        <button class="chip" data-ai-prompt="Help me choose a tech stack">Help me choose a tech stack</button>
        <button class="chip" data-ai-prompt="Create a 24-hour hackathon roadmap">Create a 24-hour hackathon roadmap</button>
        <button class="chip" data-ai-prompt="Break my project into tasks">Break my project into tasks</button>
        <button class="chip" data-ai-prompt="Recommend teammates and missing skills">Recommend teammates and missing skills</button>
        <button class="chip" data-ai-prompt="Create a project pitch for judges">Create a project pitch for judges</button>
      </div>
      <div class="assistant-cta-row"><button class="btn btn-primary btn-sm" data-action="open-ai">Open AI chat</button></div>
    </div>`;
}

function opportunityCard(item) {
  return `<article class="item-card"><div class="card-topline"><span class="badge-soft">${esc(item.kind)}</span><span class="badge-soft badge-gray"><i class="bi bi-people me-1"></i>${item.team_size} team spots</span></div><h3>${esc(item.title)}</h3><p>${esc(item.description.slice(0, 135))}${item.description.length > 135 ? "…" : ""}</p>${tags(item.required_skills.slice(0, 4))}<div class="meta-line"><span><i class="bi bi-calendar3"></i>${esc(dateLabel(item.deadline))}</span><span><i class="bi bi-person"></i>${esc(item.creator)}</span></div><div class="card-actions"><button class="btn btn-outline-primary btn-sm" data-action="opportunity" data-id="${item.id}">View details</button><span class="ms-auto text-secondary small">${item.teams?.length || ""}</span></div></article>`;
}
function teamListRow(team) {
  return `<div class="task-row"><div class="task-main"><strong>${esc(team.name)}</strong><small>${memberLabel(team)}${team.opportunity_title ? ` · ${esc(team.opportunity_title)}` : ""}</small></div><button class="btn btn-outline-primary btn-sm" data-action="team" data-id="${team.id}">Open</button></div>`;
}

async function renderOpportunities() {
  const items = await api("/opportunities");
  return `${heading("Find the project that clicks", "Explore hackathons and project openings that match your interests.", button("Post an opportunity", "create-opportunity"))}
    <form class="filter-bar" data-form="opportunity-search"><input class="form-control" name="search" placeholder="Search title or description"><select class="form-select" name="kind"><option value="">All types</option><option>Hackathon</option><option>Project</option><option>Recruitment</option></select><input class="form-control" name="skill" placeholder="Filter by skill"><button class="btn btn-outline-primary btn-sm" type="submit"><i class="bi bi-search"></i> Search</button></form>
    <div id="opportunity-results" class="item-grid">${items.length ? items.map(opportunityCard).join("") : empty("bi-compass", "No opportunities yet", "Be the first to post one.", "create-opportunity", "Post opportunity")}</div>`;
}
function renderOpportunityForm() {
  if (!state.user) return `${heading("Post an opportunity", "Sign in to publish a new opening.")}${empty("bi-person-lock", "Sign in required", "Create an account or sign in to continue.", "login", "Sign in")}`;
  return `${heading("Put your idea out there", "Share an opportunity and invite great collaborators.")}<div class="form-card"><form data-form="create-opportunity">
    <div class="row g-3"><div class="col-md-8"><label class="form-label">Opportunity title</label><input name="title" class="form-control" required minlength="3" maxlength="160" placeholder="e.g. Build an AI-powered campus guide"></div>
    <div class="col-md-4"><label class="form-label">Type</label><select class="form-select" name="kind"><option>Hackathon</option><option>Project</option><option>Recruitment</option></select></div>
    <div class="col-12"><label class="form-label">Description</label><textarea name="description" class="form-control" required minlength="10" maxlength="5000" placeholder="What are you building? Who should join?"></textarea></div>
    <div class="col-md-6"><label class="form-label">Skills needed</label><input name="required_skills" class="form-control" placeholder="Python, UI/UX, React"><div class="form-text">Separate skills with commas.</div></div>
    <div class="col-md-3"><label class="form-label">Team size</label><input name="team_size" type="number" min="1" max="20" value="4" class="form-control"></div>
    <div class="col-md-3"><label class="form-label">Deadline</label><input name="deadline" type="date" class="form-control"></div>
    </div><div class="mt-4 d-flex gap-2"><button class="btn btn-primary btn-sm">Publish opportunity</button><button type="button" class="btn btn-light btn-sm" data-page="opportunities">Cancel</button></div>
  </form></div>`;
}
async function renderOpportunityDetail() {
  if (!state.opportunityId) return `${heading("Opportunity details", "Choose an opening to see more.")}${empty("bi-compass", "No opportunity selected", "Browse the open opportunities.", "opportunities", "Browse opportunities")}`;
  const item = await api(`/opportunities/${state.opportunityId}`);
  return `${heading(item.title, `${item.kind} · Posted by ${item.creator}`, button("Back to discover", "opportunities", "outline-primary"))}<div class="two-col"><div class="panel"><span class="badge-soft">${esc(item.kind)}</span><h2 class="mt-3 fs-5 fw-bold">${esc(item.title)}</h2><p class="text-secondary small" style="white-space:pre-wrap">${esc(item.description)}</p><div class="section-title"><h2>Skills that would help</h2></div>${tags(item.required_skills)}<div class="meta-line mt-3"><span><i class="bi bi-calendar3"></i>${esc(dateLabel(item.deadline))}</span><span><i class="bi bi-people"></i>Up to ${item.team_size} teammates</span></div><div class="mt-4"><button class="btn btn-primary btn-sm" data-action="start-team" data-id="${item.id}">Start a team for this</button></div></div><div class="panel"><div class="panel-heading"><h3>Teams forming</h3></div>${item.teams.length ? item.teams.map(teamListRow).join("") : `<p class="text-secondary small">No team has formed for this opportunity yet. Start one and invite collaborators.</p>`}</div></div>`;
}

async function renderTeams() {
  const teams = await api("/teams");
  return `${heading("Meet teams looking for you", "Find a group with a mission and skills that complement yours.", button("Create a team", "create-team"))}
    <form class="filter-bar" data-form="team-search"><input class="form-control" name="search" placeholder="Search team name"><input class="form-control" name="skill" placeholder="Filter by required skill"><button class="btn btn-outline-primary btn-sm">Search</button></form>
    <div id="team-results" class="item-grid">${teams.length ? teams.map(teamCard).join("") : empty("bi-people", "No teams are forming yet", "Create a team and be the first to bring an idea together.", "create-team", "Start a team")}</div>`;
}
function teamCard(team) {
  return `<article class="item-card"><div class="card-topline"><span class="badge-soft">${team.opportunity_title ? esc(team.opportunity_title) : "Open team"}</span><span class="badge-soft badge-gray">${memberLabel(team)}</span></div><h3>${esc(team.name)}</h3><p>${esc(team.description || "This team is ready for new collaborators.")}</p>${tags(team.required_skills.slice(0, 4))}<div class="meta-line"><span><i class="bi bi-person"></i>${esc(team.members.find(member => member.id === team.leader_id)?.name || "Team lead")}</span><span><i class="bi bi-person-workspace"></i>${team.required_roles.length ? esc(team.required_roles.slice(0, 2).join(", ")) : "All roles welcome"}</span></div><div class="card-actions"><button class="btn btn-outline-primary btn-sm" data-action="team" data-id="${team.id}">Team details</button>${state.user && !team.members.some(member => member.id === state.user.id) && team.member_count < team.max_size ? `<button class="btn btn-primary btn-sm" data-action="apply" data-id="${team.id}">Apply to join</button>` : ""}</div></article>`;
}
function renderTeamForm() {
  if (!state.user) return `${heading("Start a team", "Sign in to create your team.")}${empty("bi-person-lock", "Sign in required", "Create an account or sign in to continue.", "login", "Sign in")}`;
  return `${heading("Bring your team together", "Describe what you're building and the roles you still need.")}<div class="form-card"><form data-form="create-team"><div class="row g-3"><div class="col-md-8"><label class="form-label">Team name</label><input class="form-control" name="name" required minlength="2" maxlength="120" placeholder="e.g. Green Pixels"></div><div class="col-md-4"><label class="form-label">Maximum team size</label><input class="form-control" name="max_size" type="number" min="2" max="20" value="4"></div><div class="col-12"><label class="form-label">What are you building?</label><textarea class="form-control" name="description" maxlength="3000" placeholder="Tell teammates about your idea and goals"></textarea></div><div class="col-md-6"><label class="form-label">Skills you're looking for</label><input class="form-control" name="required_skills" placeholder="Python, Figma, data science"></div><div class="col-md-6"><label class="form-label">Roles to fill</label><input class="form-control" name="required_roles" placeholder="Frontend developer, designer"></div><div class="col-12"><label class="form-label">Opportunity (optional)</label><select name="opportunity_id" id="opportunity-picker" class="form-select"><option value="">Independent project</option></select></div></div><div class="mt-4"><button class="btn btn-primary btn-sm">Create team</button></div></form></div>`;
}
async function renderTeamDetail() {
  if (!state.teamId) return `${heading("Team details", "Find a team to see its shared workspace.")}${empty("bi-people", "No team selected", "Browse teams that are looking for collaborators.", "teams", "Find a team")}`;
  const team = await api(`/teams/${state.teamId}`);
  const isMember = state.user && team.members.some(member => member.id === state.user.id);
  const isLeader = state.user?.id === team.leader_id;
  return `${heading(team.name, team.opportunity_title || "A HackMate team", button("All teams", "teams", "outline-primary"))}<div class="two-col"><div class="panel"><div class="card-topline"><span class="badge-soft">${memberLabel(team)}</span>${team.opportunity_title ? `<span class="badge-soft badge-green">${esc(team.opportunity_title)}</span>` : ""}</div><p class="mt-3 text-secondary small">${esc(team.description || "This team is ready to build something great.")}</p><div class="section-title"><h2>What we're looking for</h2></div>${tags(team.required_skills)}<p class="small text-secondary">${team.required_roles.length ? `Roles: ${esc(team.required_roles.join(", "))}` : "Open to a range of roles"}</p>${!isMember && state.user && team.member_count < team.max_size ? `<button class="btn btn-primary btn-sm" data-action="apply" data-id="${team.id}">Apply to join</button>` : ""}${!state.user ? `<button class="btn btn-primary btn-sm" data-page="login">Sign in to apply</button>` : ""}</div><div class="panel"><div class="panel-heading"><h3>Teammates</h3></div>${team.members.map(member => `<div class="match-row"><div class="match-person"><span class="avatar">${esc(initials(member.name))}</span><div><strong>${esc(member.name)}</strong><small>${esc(member.role)}</small></div></div>${tags(member.skills.slice(0, 2))}</div>`).join("")}${isLeader ? `<button class="btn btn-outline-primary btn-sm mt-3" data-page="applications">Review applications</button>` : ""}</div></div>`;
}

async function renderApplications() {
  if (!state.user) return `${heading("Team applications", "Review people who want to join your team.")}${empty("bi-person-lock", "Sign in required", "Sign in to manage your team.", "login", "Sign in")}`;
  const teams = await api("/teams");
  const mine = teams.filter(team => team.leader_id === state.user.id);
  if (!mine.length) return `${heading("Team applications", "Review people who want to join your team.")}${empty("bi-inbox", "No team to manage yet", "Applications appear here when people apply to your team.", "create-team", "Create a team")}`;
  const selected = mine.find(team => team.id === state.teamId) || mine[0];
  state.teamId = selected.id;
  sessionStorage.setItem("hackmate_team_id", selected.id);
  const applications = await api(`/teams/${selected.id}/applications`);
  return `${heading("Team applications", "Get to know prospective teammates and make your decision.")}${selectTeam(mine)}<div class="panel">${applications.length ? applications.map(app => `<div class="application-row"><div class="match-person"><span class="avatar">${esc(initials(app.applicant.name))}</span><div><strong>${esc(app.applicant.name)} <span class="badge-soft badge-gray">${esc(app.status)}</span></strong><small>${esc(app.applicant.preferred_role || "Looking for a role")} · ${esc(app.applicant.experience)}</small><div class="tag-row mb-0">${app.applicant.skills.slice(0, 5).map(skill => `<span class="skill-tag">${esc(skill)}</span>`).join("")}</div><small>${esc(app.message || "No message added")}</small></div></div>${app.status === "pending" ? `<div class="d-flex gap-1"><button class="btn btn-primary btn-sm" data-action="decision" data-team="${selected.id}" data-id="${app.id}" data-status="accepted">Accept</button><button class="btn btn-outline-secondary btn-sm" data-action="decision" data-team="${selected.id}" data-id="${app.id}" data-status="rejected">Decline</button></div>` : ""}</div>`).join("") : empty("bi-inbox", "No applications yet", "When someone applies, their profile and message will appear here.")}</div>`;
}

async function renderMatches() {
  if (!state.user) return `${heading("Smart teammate matching", "Find collaborators that fill the gaps.")}${empty("bi-person-lock", "Sign in required", "Your team matches use your profile to rank candidates.", "login", "Sign in")}`;
  const teams = await getMyTeams();
  const opportunities = await api("/opportunities");
  if (!teams.length && !opportunities.length) return `${heading("Smart teammate matching", "Find collaborators that fill the gaps.")}${empty("bi-stars", "No team or opportunity to match yet", "Create a team or find an opportunity to start generating recommendations.", "create-team", "Create your team")}`;
  const targets = [
    ...teams.map(team => ({ key: `team:${team.id}`, name: `Team · ${team.name}`, type: "team", id: team.id, data: team })),
    ...opportunities.map(item => ({ key: `opportunity:${item.id}`, name: `Opportunity · ${item.title}`, type: "opportunity", id: item.id, data: item }))
  ];
  if (!targets.some(target => target.key === state.matchingTarget)) {
    state.matchingTarget = teams.length ? `team:${state.teamId || teams[0].id}` : targets[0].key;
  }
  const selected = targets.find(target => target.key === state.matchingTarget) || targets[0];
  const path = selected.type === "team"
    ? `/teams/${selected.id}/matches`
    : `/opportunities/${selected.id}/matches`;
  const matches = await api(`${path}?${state.matchingExplainWithAi ? "explain_with_ai=true" : ""}`);
  const required = selected.type === "team" ? selected.data.required_skills : selected.data.required_skills;
  const missing = selected.type === "team"
    ? (await api(`/teams/${selected.id}/balance`)).missing_skills
    : required;
  const aiStatus = matches.find(item => item.ai_explanation_status)?.ai_explanation_status;
  const statusNote = !state.matchingExplainWithAi ? "Rule-based estimates" :
    aiStatus === "available" ? "AI explanations enabled" :
      aiStatus === "missing_credentials" ? "AI explanations unavailable: configure AI_API_KEY; rule-based matching remains active." :
        `AI explanation service: ${String(aiStatus || "no recommendations").replaceAll("_", " ")}. Rule-based matching remains active.`;
  return `${heading("Your next great teammate", "Explainable estimated fit combines missing skills, role, availability, and self-reported hackathon experience.", `<button class="btn btn-outline-primary btn-sm" data-action="matching-explain">${state.matchingExplainWithAi ? "Use rule-based explanations" : "Explain with AI"}</button>`)}
    <div class="match-target-row"><label class="form-label mb-0" for="matching-target">Match for</label><select class="form-select" id="matching-target">${targets.map(target => `<option value="${esc(target.key)}" ${target.key === selected.key ? "selected" : ""}>${esc(target.name)}</option>`).join("")}</select></div>
    <div class="two-col align-items-start"><div class="panel"><div class="panel-heading"><h3>Project needs</h3><span class="subtle">${selected.type === "team" ? `${selected.data.member_count}/${selected.data.max_size} members` : "Opportunity requirements"}</span></div>
      ${tags(required)}<p class="form-text mt-2 mb-0">${missing.length ? `Current gaps: ${esc(missing.join(", "))}` : "No required skill gaps are recorded yet."}</p></div>
      <div class="panel"><div class="panel-heading"><h3>Recommendation method</h3></div><p class="small text-secondary mb-1">${esc(statusNote)}</p><p class="form-text mb-0">The score is a deterministic estimate, not a prediction of team success. AI only rewrites explanations from known facts; it never supplies scores or changes membership.</p></div></div>
    <div class="panel mt-3"><div class="panel-heading"><h3>Recommended teammates</h3><span class="subtle">Estimated fit · 0–100</span></div>
    ${matches.length ? matches.map(match => `<article class="match-card">
      <div class="match-card-head"><button class="profile-link" data-action="view-profile" data-id="${match.user.id}"><span class="avatar">${esc(initials(match.user.name))}</span><span><strong>${esc(match.user.name)}</strong><small>${esc(match.user.preferred_role || "Open to roles")} · ${esc(match.user.experience)}</small></span></button><div class="match-score"><span class="score-ring">${match.score}</span><small>estimate</small></div></div>
      <p class="match-explanation">${esc(match.ai_explanation || match.explanation)}</p>
      <div class="match-detail-grid"><div><strong>Can fill</strong>${tags(match.missing_skills_candidate_contributes)}</div><div><strong>Shared strengths</strong>${tags(match.strong_matching_skills)}</div></div>
      <div class="small text-secondary mt-2">Skills ${match.score_breakdown.complementary_skills}% · Interests ${match.score_breakdown.shared_interests}% · Role ${match.score_breakdown.required_role}% · Experience mix ${match.score_breakdown.experience_mix}% · Availability ${match.score_breakdown.availability}% · Hackathon evidence ${match.score_breakdown.relevant_hackathon_experience}%</div>
      ${match.relevant_hackathon_experience.length ? `<div class="match-history-note"><i class="bi bi-trophy"></i> Self-reported project experience: ${match.relevant_hackathon_experience.map(item => esc([item.project_title || item.event_name, item.team_role, item.technologies.join(", ")].filter(Boolean).join(" · "))).join("; ")}${match.relevant_hackathon_experience.some(item => item.verified) ? " · some verified" : " · unverified"}</div>` : ""}
      ${match.relevant_project_experience.length ? `<div class="match-history-note"><i class="bi bi-code-square"></i> Public self-reported projects: ${match.relevant_project_experience.map(item => esc(`${item.title} (${item.technologies.join(", ")})`)).join("; ")} · not independently verified</div>` : ""}
      <div class="match-history-note"><i class="bi bi-star"></i> Collaboration reputation: ${match.reputation.average_rating ?? "No rating"} from ${match.reputation.review_count} review${match.reputation.review_count === 1 ? "" : "s"}; not a measure of technical ability.</div>
      <div class="card-actions"><button class="btn btn-outline-primary btn-sm" data-action="view-profile" data-id="${match.user.id}">View portfolio</button>${teams.some(team => team.leader_id === state.user.id && team.member_count < team.max_size) ? `<button class="btn btn-primary btn-sm" data-action="invite-user" data-id="${match.user.id}">Invite to team</button>` : ""}</div>
    </article>`).join("") : empty("bi-stars", "No new matches just yet", "As more students complete profiles, we'll find collaborators whose skills complement this project.")}</div>`;
}

async function renderBalance() {
  if (!state.user) return `${heading("Team balance analyzer", "Spot skill gaps and make your team stronger.")}${empty("bi-person-lock", "Sign in required", "Team analysis is available to members.", "login", "Sign in")}`;
  const teams = await getMyTeams();
  if (!teams.length) return `${heading("Team balance analyzer", "Spot skill gaps and make your team stronger.")}${empty("bi-bar-chart-line", "Join or create a team first", "The analyzer compares member skills with the roles you need.", "create-team", "Create your team")}`;
  const team = teams.find(item => item.id === state.teamId);
  const result = await api(`/teams/${team.id}/balance`);
  return `${heading("A stronger, more balanced team", "See what your team already does well and the skills still missing.")}${selectTeam(teams)}<div class="two-col"><div class="panel"><div class="panel-heading"><h3>Skills on your team</h3></div>${Object.keys(result.skill_counts).length ? Object.entries(result.skill_counts).map(([skill, count]) => `<div class="task-row"><div class="task-main"><strong>${esc(skill)}</strong><small>${count} team member${count !== 1 ? "s" : ""}</small></div><span class="badge-soft ${count > 1 ? "badge-green" : "badge-gray"}">${count > 1 ? "Covered" : "Underrepresented"}</span></div>`).join("") : `<p class="text-secondary small">Your members haven't added skills to their profiles yet.</p>`}</div><div class="panel"><div class="panel-heading"><h3>Skills your project needs</h3></div>${result.required_skills.length ? result.required_skills.map(skill => `<div class="task-row"><div class="task-main"><strong>${esc(skill)}</strong><small>${result.missing_skills.some(item => item.toLowerCase() === skill.toLowerCase()) ? "No team member listed this skill yet" : "Already represented in your team"}</small></div>${result.missing_skills.some(item => item.toLowerCase() === skill.toLowerCase()) ? `<span class="badge-soft">Gap</span>` : `<span class="badge-soft badge-green">Covered</span>`}</div>`).join("") : `<p class="text-secondary small">Add required skills when editing your team to analyze coverage.</p>`}${result.suggested_roles.length ? `<div class="section-title"><h2>Roles to recruit</h2></div>${tags(result.suggested_roles)}` : ""}</div></div><div class="panel mt-3"><div class="panel-heading"><h3>Suggested collaborators</h3><button class="text-link" data-page="matching">See match details</button></div>${result.recommendations.slice(0, 3).map(match => `<div class="match-row"><div class="match-person"><span class="avatar">${esc(initials(match.user.name))}</span><div><strong>${esc(match.user.name)}</strong><small>Can add: ${esc(match.complementary_skills.join(", ") || "a fresh perspective")}</small></div></div><span class="score-ring">${match.score}</span></div>`).join("")}</div>`;
}

async function renderWorkspace() {
  if (!state.user) return `${heading("Team workspace", "Plan tasks, track momentum, and keep your work moving.")}${empty("bi-person-lock", "Sign in required", "Workspace content is private to team members.", "login", "Sign in")}`;
  const teams = await getMyTeams();
  if (!teams.length) return `${heading("Team workspace", "Plan tasks, track momentum, and keep your work moving.")}${empty("bi-kanban", "Create or join a team first", "Your team's task board will be available here.", "teams", "Find a team")}`;
  const team = teams.find(item => item.id === state.teamId);
  const data = await api(`/teams/${team.id}/workspace`);
  if (state.page === "tasks") {
    return `${heading("Team task board", `Turn the ${team.name} plan into clear next steps.`)}${selectTeam(teams)}<div class="two-col"><div class="panel"><div class="panel-heading"><h3>Tasks</h3><span class="subtle">${data.completed_tasks}/${data.total_tasks} complete</span></div><div class="progress mb-3"><div class="progress-bar" style="width:${data.progress_percent}%"></div></div>${data.tasks.length ? data.tasks.map(task => `<div class="task-row"><div class="task-main"><strong>${esc(task.title)} <span class="badge-soft ${task.status === "Done" ? "badge-green" : "badge-gray"}">${esc(task.status)}</span></strong><small>${esc(task.assignee_name || "Unassigned")} · ${esc(task.due_date || "No due date")} · ${esc(task.priority)} priority</small>${task.description ? `<small>${esc(task.description)}</small>` : ""}</div><button class="btn btn-outline-primary btn-sm" data-action="task-status" data-id="${task.id}" data-status="${esc(task.status)}">Move forward</button></div>`).join("") : `<p class="text-secondary small">No tasks yet. Add the first action item.</p>`}</div><div class="form-card"><h2 class="fs-6 fw-bold mb-3">Add a task</h2><form data-form="create-task"><div class="mb-3"><label class="form-label">Task title</label><input class="form-control" name="title" required minlength="2" maxlength="180" placeholder="e.g. Sketch the onboarding flow"></div><div class="mb-3"><label class="form-label">Description</label><textarea class="form-control" name="description" maxlength="3000" placeholder="What does done look like?"></textarea></div><div class="mb-3"><label class="form-label">Assign to</label><select class="form-select" name="assignee_id"><option value="">Unassigned</option>${team.members.map(member => `<option value="${member.id}">${esc(member.name)}</option>`).join("")}</select></div><div class="row g-2"><div class="col-6"><label class="form-label">Priority</label><select class="form-select" name="priority"><option>Medium</option><option>High</option><option>Low</option></select></div><div class="col-6"><label class="form-label">Due date</label><input class="form-control" type="date" name="due_date"></div></div><button class="btn btn-primary btn-sm mt-3">Add task</button></form></div></div>`;
  }
  return `${heading("Make the next move", "Keep ownership clear and progress visible for everyone.")}${selectTeam(teams)}<div class="panel mb-3"><div class="panel-heading"><h3>${esc(team.name)} progress</h3><span class="subtle">${data.completed_tasks} of ${data.total_tasks} tasks done</span></div><div class="progress"><div class="progress-bar" style="width:${data.progress_percent}%"></div></div><div class="small text-secondary mt-2">${data.progress_percent}% complete</div></div><div class="two-col"><div class="panel"><div class="panel-heading"><h3>Team tasks</h3><button class="text-link" data-page="tasks">Task board</button></div>${data.tasks.length ? data.tasks.map(task => `<div class="task-row"><div class="task-main"><strong>${esc(task.title)}</strong><small>${esc(task.assignee_name || "Unassigned")} · ${esc(task.due_date || "No due date")} · ${esc(task.priority)} priority</small></div><button class="btn btn-sm ${task.status === "Done" ? "btn-success" : "btn-outline-primary"}" data-action="task-status" data-id="${task.id}" data-status="${esc(task.status)}">${esc(task.status)}</button></div>`).join("") : `<p class="text-secondary small mb-0">No tasks yet. Create one and turn your plan into action.</p>`}</div><div class="panel"><div class="panel-heading"><h3>Quick links</h3></div><button class="btn btn-outline-primary btn-sm me-1 mb-2" data-page="chat"><i class="bi bi-chat-dots"></i> Open team chat</button><button class="btn btn-outline-primary btn-sm mb-2" data-page="balance"><i class="bi bi-bar-chart"></i> Team balance</button><p class="form-text mt-2">Only current team members can access this workspace, tasks, and team chat.</p></div></div>`;
}

async function renderChat() {
  if (!state.user) return `${heading("Team chat", "A private space for quick questions and shared decisions.")}${empty("bi-person-lock", "Sign in required", "Team messages can only be viewed by members.", "login", "Sign in")}`;
  const teams = await getMyTeams();
  if (!teams.length) return `${heading("Team chat", "A private space for quick questions and shared decisions.")}${empty("bi-chat-left-text", "Join or create a team first", "Your team conversation will show up here.", "teams", "Find a team")}`;
  const team = teams.find(item => item.id === state.teamId);
  const messages = await api(`/teams/${team.id}/messages`);
  return `${heading("Team chat", `Share updates and ideas with ${team.name}.`)}${selectTeam(teams)}<div class="panel"><div class="chat-box" id="chat-box">${messages.length ? messages.map(message => `<div class="chat-message ${message.sender_id === state.user.id ? "mine" : ""}"><strong>${esc(message.sender_name)}</strong><span>${esc(message.content)}</span><small>${esc(new Date(message.created_at).toLocaleString())}</small></div>`).join("") : `<div class="empty-state border-0"><i class="bi bi-chat-left-text"></i><h3>Say hello to your team</h3><p>Messages here are private to team members.</p></div>`}</div><form data-form="send-message" class="d-flex gap-2 mt-3"><input class="form-control" name="content" maxlength="2000" required placeholder="Write a message…"><button class="btn btn-primary btn-sm" aria-label="Send message"><i class="bi bi-send"></i></button></form><p class="form-text mt-2 mb-0">Messages refresh when you reopen this page. Team-only access is enforced by the API.</p></div>`;
}

async function renderReviews() {
  if (!state.user) return `${heading("Reviews & ratings", "Recognize great collaborators and build trust.")}${empty("bi-person-lock", "Sign in required", "Sign in to review your teammates.", "login", "Sign in")}`;
  const teams = await getMyTeams();
  if (!teams.length) return `${heading("Reviews & ratings", "Recognize great collaborators and build trust.")}${empty("bi-star", "Join a team first", "After collaborating, you can review another member.", "teams", "Find a team")}`;
  const team = teams.find(item => item.id === state.teamId);
  const members = team.members.filter(member => member.id !== state.user.id);
  return `${heading("Give credit where it's due", "A thoughtful review helps good collaborators find their next team.")}${selectTeam(teams)}<div class="two-col"><div class="form-card"><h2 class="fs-6 fw-bold mb-3">Review a collaborator</h2>${members.length ? `<form data-form="review"><div class="mb-3"><label class="form-label">Teammate</label><select class="form-select" name="reviewee_id" required>${members.map(member => `<option value="${member.id}">${esc(member.name)} · ${esc(member.role)}</option>`).join("")}</select></div><div class="mb-3"><label class="form-label">Overall collaboration rating</label><select class="form-select" name="rating"><option value="5">5 — Excellent</option><option value="4">4 — Great</option><option value="3">3 — Good</option><option value="2">2 — Fair</option><option value="1">1 — Needs improvement</option></select></div><div class="row g-2 mb-3">${["communication", "reliability", "teamwork"].map(category => `<div class="col-md-4"><label class="form-label text-capitalize">${category}</label><select class="form-select" name="${category}_rating">${[5,4,3,2,1].map(score => `<option value="${score}">${score}/5</option>`).join("")}</select></div>`).join("")}</div><div class="mb-3"><label class="form-label">Written feedback</label><textarea class="form-control" name="feedback" maxlength="2000" placeholder="What did they bring to the team?"></textarea></div><p class="form-text">Reviews are based on shared team participation and describe collaboration, not objective technical ability.</p><button class="btn btn-primary btn-sm">Submit review</button></form>` : `<p class="text-secondary small">There are no other team members to review yet.</p>`}</div><div class="panel"><div class="panel-heading"><h3>Team members</h3></div>${team.members.map(member => `<div class="match-row"><div class="match-person"><span class="avatar">${esc(initials(member.name))}</span><div><strong>${esc(member.name)}</strong><small>${esc(member.role)}</small></div></div><button class="btn btn-outline-primary btn-sm" data-action="reputation" data-id="${member.id}">View reputation</button></div>`).join("")}</div></div>`;
}
async function renderReputation() {
  if (!state.user) return `${heading("Your reputation", "Your profile and feedback from fellow builders.")}${empty("bi-person-lock", "Sign in to view your reputation", "Your collaborator profile is tied to your account.", "login", "Sign in")}`;
  const profile = await api(`/users/${state.user.id}`);
  const reviews = await api(`/users/${state.user.id}/reviews`);
  return `${heading("Your reputation", "Build a track record of thoughtful, reliable collaboration.", button("Edit profile", "edit-profile", "outline-primary"))}<div class="profile-header"><span class="avatar">${profile.photo_url ? `<img src="${esc(profile.photo_url)}" alt="">` : esc(initials(profile.name))}</span><div class="flex-grow-1"><h2>${esc(profile.name)}</h2><p>${esc([profile.preferred_role, profile.college].filter(Boolean).join(" · ") || "HackMate member")}</p></div><div class="text-center"><div class="score-ring mx-auto">${reviews.average_rating ?? "—"}</div><small class="text-secondary">${reviews.count} reviews</small></div></div><div class="panel">${reviews.reviews.length ? reviews.reviews.map(review => `<div class="task-row"><div class="task-main"><strong>${esc(review.reviewer)} <span class="text-warning">${"★".repeat(review.rating)}${"☆".repeat(5 - review.rating)}</span></strong><small>${esc(review.feedback || "No written feedback.")} · ${esc(dateLabel(review.created_at))}</small></div></div>`).join("") : empty("bi-star", "Your reputation starts with collaboration", "Complete a project together and invite your teammates to leave a review.")}</div>`;
}

async function renderProfile(edit) {
  if (!state.user) return `${heading("Developer portfolio", "Sign in to manage your profile or view public portfolios.")}${empty("bi-person-lock", "Sign in required", "Your portfolio and collaborator tools are linked to your account.", "login", "Sign in")}`;
  const viewingOther = Boolean(state.profileId && state.profileId !== state.user.id);
  const userId = viewingOther ? state.profileId : state.user.id;
  const [user, reviews] = await Promise.all([
    api(viewingOther ? `/users/${userId}/portfolio` : "/users/me/portfolio"),
    api(`/users/${userId}/reviews`)
  ]);
  if (edit && viewingOther) return `${heading("Developer portfolio", "You can only edit your own profile.")}${empty("bi-shield-lock", "Portfolio is read-only", "Return to your own portfolio to make changes.", "profile", "My profile")}`;
  if (edit) {
    const portfolio = user;
    return `${heading("Build your developer portfolio", "Education, technical skills, and clear collaboration preferences help teammates understand your fit.")}<div class="form-card mb-3"><form data-form="profile"><div class="section-title mt-0"><h2>Profile and collaboration</h2></div><div class="row g-3">
      ${profileInput("Full name", "name", user.name, true)}${profileInput("Preferred display name", "preferred_name", portfolio.preferred_name)}${profileInput("Professional headline", "headline", portfolio.headline, false, "text", "e.g. Backend developer building for the climate")}
      ${profileInput("College / university", "college", user.college)}${profileInput("Degree", "degree", portfolio.degree)}${profileInput("Course", "course", portfolio.course)}${profileInput("Department / branch", "department", user.department)}
      ${profileInput("Current year of study", "study_year", portfolio.study_year, false, "text", "e.g. 3rd year, recent graduate")}${profileInput("Graduation year", "graduation_year", portfolio.graduation_year ?? "", false, "number")}${profileInput("Location (optional)", "location", portfolio.location)}
      ${profileInput("Profile photo URL", "photo_url", user.photo_url, false, "url")}${profileInput("Preferred hackathon roles", "preferred_role", user.preferred_role, false, "text", "Frontend, UI/UX, project lead")}${profileInput("Experience level", "experience", user.experience)}
      ${profileInput("Availability", "availability", user.availability, false, "text", "e.g. evenings and weekends")}${profileInput("Collaboration mode", "collaboration_mode", portfolio.collaboration_mode, false, "text", "Remote, hybrid, in-person")}
      <div class="col-12"><label class="form-label" for="profile-languages">Languages spoken (optional)</label><input id="profile-languages" class="form-control" name="languages" value="${esc(portfolio.languages.join(", "))}" placeholder="English, Hindi"></div>
      <div class="col-md-8"><label class="form-label" for="profile-skills">Technical skills</label><input id="profile-skills" class="form-control" name="skills" value="${esc(user.skills.join(", "))}" placeholder="Python, API design, React"><div class="form-text">Comma-separated. These are self-reported; add proficiency detail below on your profile.</div></div>
      <div class="col-md-4"><label class="form-label" for="profile-interests">Interests and domains</label><input id="profile-interests" class="form-control" name="interests" value="${esc(user.interests.join(", "))}" placeholder="AI, IoT, civic tech"></div>
      <div class="col-12"><label class="form-label" for="profile-bio">Short biography</label><textarea id="profile-bio" class="form-control" name="bio" maxlength="1200">${esc(user.bio)}</textarea></div>
      <div class="col-12"><label class="form-label" for="profile-experience">Project experience summary</label><textarea id="profile-experience" class="form-control" name="project_experience" maxlength="2000">${esc(user.project_experience)}</textarea></div>
      </div><div class="mt-4"><button class="btn btn-primary btn-sm">Save profile and education</button></div></form></div>
      <div class="form-card"><form data-form="portfolio"><div class="section-title mt-0"><h2>Public profile privacy</h2></div><p class="form-text">Resume defaults to private. Email and authentication details are never shown on a public portfolio.</p>
        ${privacyCheck("resume_visible", "Allow invited/portfolio viewers to preview my resume", portfolio.privacy.resume_visible)}
        ${privacyCheck("projects_visible", "Show my featured projects", portfolio.privacy.projects_visible)}
        ${privacyCheck("history_visible", "Show my hackathon history", portfolio.privacy.history_visible)}
        ${privacyCheck("credentials_visible", "Show certifications, achievements, and GitHub details", portfolio.privacy.credentials_visible)}
        ${privacyCheck("education_visible", "Show my college and education details", portfolio.privacy.education_visible)}
        ${privacyCheck("location_visible", "Show my optional location", portfolio.privacy.location_visible)}
        <div class="row g-3 mt-1">${profileInput("GitHub username", "github_username", portfolio.github_username, false, "text", "Your public username only")}</div>
        <button class="btn btn-primary btn-sm mt-3">Save portfolio and privacy</button></form></div>`;
  }

  const own = !viewingOther;
  let githubPanel = "";
  if (user.github_username && user.privacy?.credentials_visible) {
    try {
      const github = await api(`/users/${userId}/github`);
      githubPanel = `<div class="panel mt-3"><div class="panel-heading"><h3>Public GitHub repositories</h3><a class="text-link" href="${esc(github.profile_url)}" target="_blank" rel="noopener noreferrer">View GitHub</a></div><div class="item-grid">${github.repositories.length ? github.repositories.map(repo => `<article class="repo-card"><a href="${esc(repo.url)}" target="_blank" rel="noopener noreferrer">${esc(repo.name)}</a><p>${esc(repo.description || "No repository description provided.")}</p><small>${esc(repo.language || "Language not specified")} · ${repo.stars} public stars</small></article>`).join("") : `<p class="text-secondary small">No public repositories were returned by GitHub.</p>`}</div><p class="form-text mt-2 mb-0">Live public data from GitHub's official API. Contribution totals are not available through this request.</p></div>`;
    } catch (error) {
      githubPanel = `<div class="panel mt-3"><div class="panel-heading"><h3>GitHub profile</h3><span class="subtle">${esc(error.message)}</span></div></div>`;
    }
  }
  const canInvite = own ? [] : (await api("/teams")).filter(team => team.leader_id === state.user.id && team.member_count < team.max_size);
  const resumeLink = user.resume_download_url;
  return `${heading(own ? "Developer portfolio" : `${user.display_name}'s portfolio`, user.headline || "A verified-data-aware portfolio of skills, projects, and collaboration experience.", own ? button("Edit profile", "edit-profile") : "")}
    <section class="profile-header portfolio-header"><span class="avatar">${user.photo_url ? `<img src="${esc(user.photo_url)}" alt="">` : esc(initials(user.display_name))}</span><div class="flex-grow-1"><div class="eyebrow">${own ? "YOUR PORTFOLIO" : "HACKMATE MEMBER"}</div><h2>${esc(user.display_name)}</h2><p>${esc([user.preferred_role, user.department, user.college].filter(Boolean).join(" · ") || "Add education and a preferred role")}</p><p class="small text-secondary mb-0">${esc([user.degree, user.course, user.study_year, user.graduation_year ? `Class of ${user.graduation_year}` : "", user.location].filter(Boolean).join(" · "))}</p></div><div class="text-center"><div class="score-ring mx-auto">${reviews.average_rating ?? "—"}</div><small class="text-secondary">${reviews.count} collaboration reviews</small></div>
    ${!own && canInvite.length ? `<button class="btn btn-primary btn-sm" data-action="invite-user" data-id="${user.id}"><i class="bi bi-envelope-plus me-1"></i>Invite to team</button>` : ""}
    ${!own && !canInvite.length ? `<span class="badge-soft badge-gray">Invitation requires team-lead access</span>` : ""}</section>
    <div class="two-col"><div class="panel"><div class="panel-heading"><h3>About</h3>${own ? `<button class="text-link" data-page="reputation">Reputation</button>` : ""}</div><p class="text-secondary small">${esc(user.bio || "No biography has been added.")}</p><div class="meta-line"><span><i class="bi bi-bar-chart"></i>${esc(user.experience || "Experience not specified")}</span><span><i class="bi bi-clock"></i>${esc(user.availability || "Availability not specified")}</span><span><i class="bi bi-people"></i>${esc(user.collaboration_mode || "Collaboration mode not specified")}</span></div><div class="section-title"><h2>Interests</h2></div>${tags(user.interests)}${user.languages.length ? `<div class="section-title"><h2>Languages</h2></div>${tags(user.languages)}` : ""}</div>
    <div class="panel"><div class="panel-heading"><h3>Skill set</h3><span class="subtle">Self-reported proficiency</span></div>${tags(user.skills)}${user.skills_detail.length ? user.skills_detail.map(skill => `<div class="skill-proficiency"><div><strong>${esc(skill.name)}</strong><small>${esc(skill.category)} · ${skill.verified ? "Independently verified" : "Self-reported — not independently verified"}</small></div><span class="proficiency-dots" aria-label="${skill.proficiency} out of 5">${"●".repeat(skill.proficiency)}${"○".repeat(5-skill.proficiency)}</span>${own ? `<button class="icon-button" data-action="delete-portfolio-skill" data-id="${skill.id}" aria-label="Remove ${esc(skill.name)}"><i class="bi bi-x"></i></button>` : ""}</div>`).join("") : `<p class="form-text">No proficiency details added yet.</p>`}${own ? `<form class="compact-form" data-form="add-portfolio-skill"><input class="form-control" name="name" required maxlength="80" placeholder="Skill"><select class="form-select" name="category"><option>Programming</option><option>Framework</option><option>Database</option><option>Cloud</option><option>Tool</option><option>Domain</option><option>Design</option></select><select class="form-select" name="proficiency" aria-label="Self-reported proficiency"><option value="1">1 · Learning</option><option value="2">2 · Basic</option><option value="3" selected>3 · Working</option><option value="4">4 · Confident</option><option value="5">5 · Advanced (self-reported)</option></select><button class="btn btn-outline-primary btn-sm">Add skill</button></form><p class="form-text mt-2 mb-0">Scale: 1 learning · 2 basic · 3 working · 4 confident · 5 advanced. Self-rated, not a verified assessment.</p>` : ""}</div></div>
    <div class="two-col mt-3"><div class="panel"><div class="panel-heading"><h3>Featured projects</h3><span class="subtle">${user.projects.length}</span></div>${user.projects.length ? user.projects.map(project => `<article class="portfolio-entry"><div class="d-flex justify-content-between gap-2"><strong>${esc(project.title)}</strong>${own ? `<button class="icon-button" data-action="delete-project" data-id="${project.id}" aria-label="Delete project"><i class="bi bi-trash"></i></button>` : ""}</div><p>${esc(project.description)}</p>${tags(project.technologies)}<div class="meta-line mt-2">${project.repository_url ? `<a href="${esc(project.repository_url)}" target="_blank" rel="noopener noreferrer">Repository</a>` : ""}${project.demo_url ? `<a href="${esc(project.demo_url)}" target="_blank" rel="noopener noreferrer">Live demo</a>` : ""}</div></article>`).join("") : `<p class="text-secondary small">No featured projects have been shared.</p>`}${own ? `<form class="entry-form" data-form="add-project"><strong>Add a featured project</strong><input class="form-control" name="title" required maxlength="160" placeholder="Project title"><textarea class="form-control" name="description" maxlength="3000" placeholder="What did you build?"></textarea><input class="form-control" name="technologies" placeholder="Technologies, comma-separated"><input class="form-control" name="repository_url" type="url" placeholder="https://github.com/…"><input class="form-control" name="demo_url" type="url" placeholder="https://demo.example"><button class="btn btn-primary btn-sm">Add project</button></form>` : ""}</div>
    <div class="panel"><div class="panel-heading"><h3>Resume</h3><span class="subtle">${user.resume_available ? (user.resume_visible ? "Visible to portfolio visitors" : "Private") : "Not uploaded"}</span></div>${user.resume_available ? `${own ? `<button class="btn btn-outline-primary btn-sm me-1" data-action="resume-preview" data-id="${user.id}">Preview PDF</button><button class="btn btn-outline-primary btn-sm me-1" data-action="resume-download" data-id="${user.id}">Download</button>` : resumeLink ? `<a class="btn btn-outline-primary btn-sm" href="${esc(resumeLink)}" target="_blank" rel="noopener noreferrer">View resume</a>` : `<p class="text-secondary small">Resume is private.</p>`}${own ? `<button class="btn btn-outline-danger btn-sm" data-action="delete-resume">Remove</button>` : ""}` : `<p class="text-secondary small">A resume is optional. Only upload a PDF you are comfortable storing privately on this server.</p>`}${own ? `<form class="entry-form" data-form="resume"><label class="form-label" for="resume-file">Upload or replace resume (PDF, max 5 MB)</label><input class="form-control" id="resume-file" type="file" name="file" accept="application/pdf,.pdf" required><button class="btn btn-primary btn-sm">Upload resume</button></form>` : ""}</div></div>
    ${githubPanel}
    <div class="two-col mt-3"><div class="panel"><div class="panel-heading"><h3>Hackathon history</h3><span class="subtle">Self-reported unless marked verified</span></div>${user.hackathon_history.length ? user.hackathon_history.map(item => `<article class="timeline-entry"><span class="timeline-dot"></span><div><strong>${esc(item.event_name)}</strong> ${item.verified ? `<span class="badge-soft badge-green">Verified by HackMate</span>` : `<span class="badge-soft badge-gray">Self-reported</span>`}<small>${esc([item.event_date, item.organizer, item.team_role].filter(Boolean).join(" · "))}</small>${item.project_title ? `<h4>${esc(item.project_title)}</h4>` : ""}<p>${esc(item.summary)}</p>${item.result ? `<span class="badge-soft">${esc(item.result)}</span>` : ""}${tags(item.technologies)}<div class="meta-line">${item.repository_url ? `<a href="${esc(item.repository_url)}" target="_blank" rel="noopener noreferrer">Repository</a>` : ""}${item.demo_url ? `<a href="${esc(item.demo_url)}" target="_blank" rel="noopener noreferrer">Demo</a>` : ""}${item.evidence_url ? `<a href="${esc(item.evidence_url)}" target="_blank" rel="noopener noreferrer">Evidence</a>` : ""}</div>${own ? `<button class="text-link" data-action="delete-history" data-id="${item.id}">Remove entry</button>` : ""}</div></article>`).join("") : `<p class="text-secondary small">No past events have been recorded.</p>`}${own ? `<form class="entry-form" data-form="add-history"><strong>Add a hackathon entry</strong><input class="form-control" name="event_name" required maxlength="160" placeholder="Event name"><input class="form-control" name="organizer" maxlength="160" placeholder="Organizer"><input class="form-control" name="event_date" type="date"><input class="form-control" name="project_title" maxlength="160" placeholder="Project title"><input class="form-control" name="team_role" maxlength="100" placeholder="Your team role"><input class="form-control" name="technologies" placeholder="Technologies, comma-separated"><input class="form-control" name="result" maxlength="160" placeholder="Result or placement (optional)"><textarea class="form-control" name="summary" maxlength="3000" placeholder="Short project summary"></textarea><input class="form-control" name="repository_url" type="url" placeholder="Repository URL"><input class="form-control" name="demo_url" type="url" placeholder="Demo URL"><input class="form-control" name="evidence_url" type="url" placeholder="Certificate or evidence URL"><p class="form-text mb-0">Entries are self-reported. HackMate does not independently verify these claims.</p><button class="btn btn-primary btn-sm">Add history</button></form>` : ""}</div>
    <div class="panel"><div class="panel-heading"><h3>Certifications and achievements</h3><span class="subtle">${user.credentials.length}</span></div>${user.credentials.length ? user.credentials.map(item => `<article class="portfolio-entry"><div class="d-flex justify-content-between gap-2"><div><strong>${esc(item.title)}</strong><small>${esc(item.kind)}${item.issuer ? ` · ${esc(item.issuer)}` : ""} · Self-reported</small>${item.evidence_url ? `<a class="small d-block" href="${esc(item.evidence_url)}" target="_blank" rel="noopener noreferrer">Evidence link</a>` : ""}</div>${own ? `<button class="icon-button" data-action="delete-credential" data-id="${item.id}" aria-label="Delete credential"><i class="bi bi-trash"></i></button>` : ""}</div></article>`).join("") : `<p class="text-secondary small">No certifications or achievements shared.</p>`}${own ? `<form class="entry-form" data-form="add-credential"><strong>Add certification, course, or achievement</strong><input class="form-control" name="title" required maxlength="160" placeholder="Title"><input class="form-control" name="issuer" maxlength="160" placeholder="Issuer or organizer"><select class="form-select" name="kind"><option>Certification</option><option>Course</option><option>Achievement</option></select><input class="form-control" type="url" name="evidence_url" placeholder="Optional public evidence URL"><button class="btn btn-primary btn-sm">Add item</button></form>` : ""}</div></div>
    <div class="panel mt-3"><div class="panel-heading"><h3>Collaboration reputation</h3><div class="score-ring">${reviews.average_rating ?? "—"}</div></div><p class="form-text">Ratings reflect teammates' collaboration experiences; they do not objectively measure technical ability. Review count: ${reviews.count}.</p><div class="rating-dimensions">${Object.entries(reviews.dimensions).map(([name, values]) => `<div><strong>${values.average ?? "—"}</strong><small>${esc(name)} · ${values.count} review${values.count === 1 ? "" : "s"}</small></div>`).join("")}</div>${reviews.reviews.length ? reviews.reviews.map(review => `<div class="review-summary"><strong>${"★".repeat(review.rating)}${"☆".repeat(5-review.rating)} · ${esc(review.reviewer)}</strong><small>Communication ${review.communication_rating}/5 · Reliability ${review.reliability_rating}/5 · Teamwork ${review.teamwork_rating}/5</small><p>${esc(review.feedback || "No written feedback.")}</p></div>`).join("") : `<p class="text-secondary small">No eligible collaborator reviews yet.</p>`}</div>`;
}
function privacyCheck(name, label, checked) {
  return `<label class="privacy-check"><input type="checkbox" name="${esc(name)}" ${checked ? "checked" : ""}><span>${esc(label)}</span></label>`;
}
function monthDateKey(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}
function calendarQuery(fromDate, toDate) {
  const params = new URLSearchParams({ from_date: fromDate, to_date: toDate, limit: "500" });
  for (const [key, value] of Object.entries(state.calendarFilters)) {
    if (value) params.set(key, value);
  }
  return `/calendar/events?${params}`;
}
function localDateTime(value) {
  if (!value) return "";
  const date = new Date(value);
  date.setMinutes(date.getMinutes() - date.getTimezoneOffset());
  return date.toISOString().slice(0, 16);
}
function eventForm(event = null, opportunities = []) {
  return `<div class="form-card calendar-create"><div class="panel-heading"><h3>${event ? "Edit event" : "Add a hackathon event"}</h3>${event ? `<button class="text-link" data-action="cancel-event-edit">Cancel edit</button>` : ""}</div>
    <form data-form="create-event"><div class="row g-3"><div class="col-md-8"><label class="form-label">Event name</label><input class="form-control" name="name" required maxlength="160" value="${esc(event?.name || "")}"></div><div class="col-md-4"><label class="form-label">Organizer</label><input class="form-control" name="organizer" maxlength="160" value="${esc(event?.organizer || "")}"></div>
    <div class="col-md-6"><label class="form-label">Starts</label><input class="form-control" name="starts_at" type="datetime-local" required value="${esc(localDateTime(event?.starts_at))}"></div><div class="col-md-6"><label class="form-label">Ends</label><input class="form-control" name="ends_at" type="datetime-local" required value="${esc(localDateTime(event?.ends_at))}"></div>
    <div class="col-md-6"><label class="form-label">Registration deadline</label><input class="form-control" name="registration_deadline" type="datetime-local" value="${esc(localDateTime(event?.registration_deadline))}"></div><div class="col-md-6"><label class="form-label">Location / online details</label><input class="form-control" name="location" maxlength="200" value="${esc(event?.location || "")}"></div>
    <div class="col-md-6"><label class="form-label">Event URL</label><input class="form-control" name="event_url" type="url" maxlength="500" value="${esc(event?.event_url || "")}" placeholder="https://…"></div><div class="col-md-6"><label class="form-label">Eligibility</label><input class="form-control" name="eligibility" maxlength="500" value="${esc(event?.eligibility || "")}"></div>
    <div class="col-md-6"><label class="form-label">Tags</label><input class="form-control" name="tags" value="${esc(event?.tags?.join(", ") || "")}" placeholder="AI, climate, student"></div><div class="col-md-6"><label class="form-label">Related opportunity (optional)</label><select class="form-select" name="opportunity_id"><option value="">None</option>${opportunities.map(item => `<option value="${item.id}" ${Number(event?.opportunity_id) === item.id ? "selected" : ""}>${esc(item.title)}</option>`).join("")}</select></div>
    <div class="col-12"><label class="form-label">Description</label><textarea class="form-control" name="description" maxlength="5000">${esc(event?.description || "")}</textarea></div></div><button class="btn btn-primary btn-sm mt-3">${event ? "Save event" : "Add event"}</button></form></div>`;
}

async function renderCalendar() {
  const month = state.calendarMonth;
  const lastDate = new Date(month.getFullYear(), month.getMonth() + 1, 0);
  const [monthEvents, upcoming, past, opportunities, recommendations] = await Promise.all([
    api(calendarQuery(monthDateKey(month), monthDateKey(lastDate))),
    api(calendarQuery(monthDateKey(new Date()), monthDateKey(new Date(Date.now() + 60 * 86400000)))),
    api(calendarQuery(monthDateKey(new Date(Date.now() - 365 * 86400000)), monthDateKey(new Date(Date.now() - 86400000)))),
    state.user ? api("/opportunities") : Promise.resolve([]),
    state.user ? api("/calendar/recommendations?limit=5") : Promise.resolve([])
  ]);
  let editing = null;
  if (state.calendarEditingId) editing = await api(`/calendar/events/${state.calendarEditingId}`);
  const offset = (month.getDay() + 6) % 7;
  const cells = Array.from({ length: 42 }, (_, index) => {
    const day = new Date(month.getFullYear(), month.getMonth(), index - offset + 1);
    const key = monthDateKey(day);
    const dailyEvents = monthEvents.filter(item => monthDateKey(new Date(item.starts_at)) === key);
    return `<div class="calendar-day${day.getMonth() === month.getMonth() ? "" : " outside"}${key === monthDateKey(new Date()) ? " today" : ""}">
      <span class="calendar-day-number">${day.getDate()}</span>${dailyEvents.slice(0, 2).map(item => `<button class="calendar-event-chip ${item.is_joined ? "joined" : ""} ${item.is_completed ? "completed" : ""} ${item.registration_deadline_pending ? "deadline" : ""}" data-action="calendar-event" data-id="${item.id}" title="${esc(item.name)}">${esc(item.name)}</button>`).join("")}${dailyEvents.length > 2 ? `<small class="calendar-more">+${dailyEvents.length - 2} more</small>` : ""}
    </div>`;
  }).join("");
  const listCard = item => `<button class="event-list-row" data-action="calendar-event" data-id="${item.id}"><span class="event-list-date">${esc(new Date(item.starts_at).toLocaleDateString(undefined, { month: "short", day: "numeric" }))}</span><span class="event-list-info"><strong>${esc(item.name)}</strong><small>${esc(item.organizer || "Organizer not listed")} · ${esc(item.location || item.country || "Location not listed")}${item.source_name ? ` · Source: ${esc(item.source_name)}` : ""}</small></span>${item.is_joined ? `<span class="badge-soft badge-green">Joined</span>` : item.registration_deadline_pending ? `<span class="badge-soft badge-red">Deadline soon</span>` : `<span class="badge-soft">${item.event_status === "cancelled" ? "Cancelled" : item.is_completed ? "Completed" : "Upcoming"}</span>`}</button>`;
  return `${heading("Hackathon calendar", "Discover events from permitted feeds and HackMate members. Check source details for completeness and freshness; only your explicit HackMate registration marks an event as joined.")}<form class="filter-bar" data-form="calendar-filters"><input class="form-control" name="search" value="${esc(state.calendarFilters.search || "")}" placeholder="Search hackathons"><select class="form-select" name="scope"><option value="">All scopes</option>${[["campus","College / campus"],["local","City / local"],["state","State-level"],["national","National"],["international","International"],["online_global","Online / global"]].map(([value,label]) => `<option value="${value}" ${state.calendarFilters.scope === value ? "selected" : ""}>${label}</option>`).join("")}</select><input class="form-control" name="country" value="${esc(state.calendarFilters.country || "")}" placeholder="Country"><input class="form-control" name="region" value="${esc(state.calendarFilters.region || "")}" placeholder="State / region"><select class="form-select" name="event_format"><option value="">Any format</option>${["online","offline","hybrid"].map(value => `<option value="${value}" ${state.calendarFilters.event_format === value ? "selected" : ""}>${value[0].toUpperCase()}${value.slice(1)}</option>`).join("")}</select><input class="form-control" name="technology" value="${esc(state.calendarFilters.technology || "")}" placeholder="Technology / topic"><input class="form-control" name="eligibility" value="${esc(state.calendarFilters.eligibility || "")}" placeholder="Eligibility"><input class="form-control" name="deadline_before" type="date" aria-label="Registration deadline on or before" value="${esc((state.calendarFilters.deadline_before || "").slice(0, 10))}" title="Registration deadline on or before"><button class="btn btn-primary btn-sm">Apply filters</button><button type="button" class="btn btn-light btn-sm" data-action="calendar-clear-filters">Clear</button></form><div class="calendar-layout"><section class="panel calendar-panel"><div class="calendar-toolbar"><button class="icon-button" data-action="calendar-prev" aria-label="Previous month"><i class="bi bi-chevron-left"></i></button><h2>${month.toLocaleDateString(undefined, { month: "long", year: "numeric" })}</h2><button class="icon-button" data-action="calendar-next" aria-label="Next month"><i class="bi bi-chevron-right"></i></button><button class="btn btn-outline-primary btn-sm ms-auto" data-action="calendar-today">Today</button></div><div class="calendar-grid calendar-weekdays">${["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map(day => `<span>${day}</span>`).join("")}</div><div class="calendar-grid">${cells}</div><div class="calendar-legend"><span><i class="legend-dot joined"></i>Registered / joined</span><span><i class="legend-dot"></i>Other event</span><span><i class="legend-dot completed"></i>Completed</span><span><i class="legend-dot deadline"></i>Deadline within 7 days</span></div></section>
    <aside class="panel calendar-upcoming"><div class="panel-heading"><h3>Coming up</h3><span class="subtle">Next 60 days</span></div>${upcoming.length ? upcoming.map(listCard).join("") : `<p class="text-secondary small">No scheduled events in this period. Add an event when you have confirmed details.</p>`}<div class="panel-heading mt-4"><h3>Recent event history</h3></div>${past.filter(item => item.is_completed).slice(-4).reverse().map(listCard).join("") || `<p class="text-secondary small">Completed events appear here.</p>`}</aside></div>
    ${state.user ? `<section class="panel mt-3"><div class="panel-heading"><h3>Recommended for your skills</h3><span class="subtle">Rule-based estimate</span></div>${recommendations.length ? recommendations.map(item => `<div class="task-row"><div class="task-main"><button class="text-link" data-action="calendar-event" data-id="${item.event.id}">${esc(item.event.name)}</button><small>${esc(item.reasons.join(" · "))}</small></div><span class="badge-soft badge-green">${item.estimated_match_score}% fit</span></div>`).join("") : `<p class="text-secondary small mb-0">Add skills or interests to your profile to see event matches.</p>`}</section>${eventForm(editing, opportunities)}` : `${empty("bi-person-lock", "Sign in to add or register for events", "Browsing the calendar is public; event creation and registration require an account.", "login", "Sign in")}`}`;
}

async function renderInvitations() {
  if (!state.user) return `${heading("Team invitations", "Invite collaborators or respond to an invitation.")}${empty("bi-person-lock", "Sign in required", "Your invitations are private to your account.", "login", "Sign in")}`;
  const [invitations, teams] = await Promise.all([api("/invitations"), api("/teams")]);
  state.pendingInvitationCount = invitations.received.filter(item => item.status === "pending").length;
  updateNavigationBadges();
  const ledTeams = teams.filter(team => team.leader_id === state.user.id && team.member_count < team.max_size);
  const receivedRows = invitations.received.map(item => `<article class="invitation-card"><div class="invitation-top"><div><span class="badge-soft ${item.status === "pending" ? "badge-green" : "badge-gray"}">${esc(item.status)}</span><h3>${esc(item.team_name)}</h3><p>Invited by <button class="text-link" data-action="view-profile" data-id="${item.inviter?.id}">${esc(item.inviter?.name || "Team member")}</button></p></div><small>Expires ${esc(dateLabel(item.expires_at))}</small></div>${item.message ? `<blockquote>${esc(item.message)}</blockquote>` : ""}<div class="card-actions"><button class="btn btn-outline-primary btn-sm" data-action="team" data-id="${item.team_id}">View team</button>${item.status === "pending" ? `<button class="btn btn-primary btn-sm" data-action="invitation-response" data-id="${item.id}" data-status="accepted">Accept and join</button><button class="btn btn-outline-secondary btn-sm" data-action="invitation-response" data-id="${item.id}" data-status="declined">Decline</button>` : ""}</div></article>`).join("");
  const sentRows = invitations.sent.map(item => `<article class="invitation-card"><div class="invitation-top"><div><span class="badge-soft ${item.status === "pending" ? "badge-green" : "badge-gray"}">${esc(item.status)}</span><h3>${esc(item.team_name)}</h3><p>To <button class="text-link" data-action="view-profile" data-id="${item.invitee?.id}">${esc(item.invitee?.name || "HackMate user")}</button></p></div><small>Expires ${esc(dateLabel(item.expires_at))}</small></div>${item.message ? `<blockquote>${esc(item.message)}</blockquote>` : ""}${item.status === "pending" ? `<button class="btn btn-outline-danger btn-sm" data-action="cancel-invitation" data-id="${item.id}">Cancel invitation</button>` : ""}</article>`).join("");
  return `${heading("Team invitations", "Coordinate membership through explicit invitations; accepting adds you to the team.")}<div class="two-col align-items-start"><section class="panel"><div class="panel-heading"><h3>Received</h3><span class="subtle">${invitations.received.filter(item => item.status === "pending").length} pending</span></div>${receivedRows || `<p class="text-secondary small">No invitations received.</p>`}</section><section class="panel"><div class="panel-heading"><h3>Sent</h3><span class="subtle">${invitations.sent.filter(item => item.status === "pending").length} pending</span></div>${sentRows || `<p class="text-secondary small">No invitations sent.</p>`}</section></div>
    <div class="panel mt-3"><div class="panel-heading"><h3>Find a HackMate user to invite</h3><span class="subtle">Only team leaders can invite.</span></div>${ledTeams.length ? `<form class="filter-bar" data-form="user-search"><input class="form-control" name="q" required minlength="2" maxlength="80" placeholder="Search a name, role, or skill"><button class="btn btn-outline-primary btn-sm">Search people</button></form><div id="invite-search-results"></div>` : `<p class="text-secondary small mb-0">You need to lead an open team with space before inviting someone.</p>`}</div>`;
}

async function renderUserSearch(query) {
  const target = document.getElementById("invite-search-results");
  if (!target) return;
  target.innerHTML = `<div class="loading-state"><span class="spinner-border spinner-border-sm"></span> Searching profiles…</div>`;
  const [users, teams] = await Promise.all([
    api(`/users/search?q=${encodeURIComponent(query)}`), api("/teams")
  ]);
  const availableTeams = teams.filter(team => team.leader_id === state.user.id && team.member_count < team.max_size);
  target.innerHTML = users.length ? users.map(user => `<article class="search-user-card"><button class="profile-link" data-action="view-profile" data-id="${user.id}"><span class="avatar">${esc(initials(user.name))}</span><span><strong>${esc(user.name)}</strong><small>${esc(user.preferred_role || user.experience)} · ${esc(user.skills.slice(0, 5).join(", ") || "Skills not listed")}</small><small>${user.hackathon_experience_count} self-reported hackathon entries</small></span></button>${availableTeams.length ? `<button class="btn btn-primary btn-sm" data-action="invite-user" data-id="${user.id}">Invite to team</button>` : ""}</article>`).join("") : empty("bi-search", "No users found", "Try searching for a different name, role, or skill.");
}

async function openInviteDialog(userId) {
  if (!state.user) {
    state.page = "login";
    await render();
    return;
  }
  const teams = (await api("/teams")).filter(team => team.leader_id === state.user.id && team.member_count < team.max_size);
  if (!teams.length) {
    notify("You need to lead an open team with capacity to send an invitation.", true);
    return;
  }
  document.getElementById("invite-modal")?.remove();
  const modal = document.createElement("div");
  modal.id = "invite-modal";
  modal.className = "modal fade";
  modal.tabIndex = -1;
  modal.innerHTML = `<div class="modal-dialog"><div class="modal-content"><div class="modal-header"><h2 class="modal-title fs-5">Invite to your team</h2><button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button></div><div class="modal-body"><form data-form="send-invitation"><input type="hidden" name="invitee_id" value="${userId}"><label class="form-label">Team</label><select class="form-select mb-3" name="team_id" required>${teams.map(team => `<option value="${team.id}">${esc(team.name)} · ${team.member_count}/${team.max_size}</option>`).join("")}</select><label class="form-label">Optional message</label><textarea class="form-control" name="message" maxlength="1000" placeholder="Tell them why you'd like to work together"></textarea><button class="btn btn-primary btn-sm mt-3">Send invitation</button></form></div></div></div>`;
  document.body.append(modal);
  modal.addEventListener("hidden.bs.modal", () => modal.remove(), { once: true });
  bootstrap.Modal.getOrCreateInstance(modal).show();
}

async function openResume(userId, download) {
  const response = await fetch(`/api/users/${userId}/resume${download ? "?download=true" : ""}`, {
    headers: state.token ? { Authorization: `Bearer ${state.token}` } : {}
  });
  if (!response.ok) {
    let payload = {};
    try { payload = await response.json(); } catch { /* Empty download error response */ }
    throw new Error(typeof payload.detail === "string" ? payload.detail : "Could not open the resume.");
  }
  const objectUrl = URL.createObjectURL(await response.blob());
  if (download) {
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = "resume.pdf";
    link.click();
    setTimeout(() => URL.revokeObjectURL(objectUrl), 30000);
    return;
  }
  document.getElementById("resume-preview-modal")?.remove();
  const modal = document.createElement("div");
  modal.id = "resume-preview-modal";
  modal.className = "modal fade";
  modal.tabIndex = -1;
  modal.innerHTML = `<div class="modal-dialog modal-xl modal-dialog-centered resume-dialog"><div class="modal-content"><div class="modal-header"><h2 class="modal-title fs-5">Resume preview</h2><button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button></div><div class="modal-body p-0"><iframe class="resume-preview-frame" title="Resume PDF preview" src="${objectUrl}"></iframe></div></div></div>`;
  modal.addEventListener("hidden.bs.modal", () => {
    URL.revokeObjectURL(objectUrl);
    modal.remove();
  }, { once: true });
  document.body.append(modal);
  bootstrap.Modal.getOrCreateInstance(modal).show();
}

async function showCalendarEvent(eventId) {
  const event = await api(`/calendar/events/${eventId}`);
  document.getElementById("calendar-event-modal")?.remove();
  const modal = document.createElement("div");
  modal.id = "calendar-event-modal";
  modal.className = "modal fade";
  modal.tabIndex = -1;
  const actions = `${event.event_url ? `<a class="btn btn-outline-primary btn-sm" href="${esc(event.event_url)}" target="_blank" rel="noopener noreferrer">Official event page</a>` : ""}${event.registration_url ? `<a class="btn btn-outline-primary btn-sm" href="${esc(event.registration_url)}" target="_blank" rel="noopener noreferrer">Organizer registration</a>` : ""}${state.user && !event.is_completed && event.event_status !== "cancelled" ? event.is_joined ? `<button class="btn btn-outline-secondary btn-sm" data-action="unregister-event" data-id="${event.id}">Remove HackMate registration</button>` : `<button class="btn btn-primary btn-sm" data-action="register-event" data-id="${event.id}">Mark attending on HackMate</button>` : ""}${event.can_edit ? `<button class="btn btn-outline-primary btn-sm" data-action="edit-event" data-id="${event.id}">Edit event</button><button class="btn btn-outline-danger btn-sm" data-action="delete-event" data-id="${event.id}">Delete event</button>` : ""}`;
  const staleAfter = event.last_fetched_at && Date.now() - new Date(event.last_fetched_at).getTime() > 30 * 86400000;
  modal.innerHTML = `<div class="modal-dialog modal-lg modal-dialog-centered"><div class="modal-content"><div class="modal-header"><div><span class="badge-soft ${event.is_joined ? "badge-green" : ""}">${event.is_joined ? "Registered / joined on HackMate" : event.event_status === "cancelled" ? "Cancelled by source" : event.is_completed ? "Completed" : "Upcoming"}</span><h2 class="modal-title fs-5 fw-bold mt-2">${esc(event.name)}</h2></div><button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button></div><div class="modal-body"><p>${esc(event.description || "No event description was added.")}</p><div class="meta-line"><span>${esc(new Date(event.starts_at).toLocaleString())} – ${esc(new Date(event.ends_at).toLocaleString())}</span><span>${esc(event.organizer || "Organizer not listed")}</span><span>${esc([event.location, event.region, event.country].filter(Boolean).join(", ") || "Location not listed")}</span></div>${event.registration_deadline ? `<p class="small mt-3 ${event.registration_deadline_pending ? "text-danger fw-bold" : "text-secondary"}">Registration deadline: ${esc(new Date(event.registration_deadline).toLocaleString())}</p>` : ""}${event.eligibility ? `<p class="small text-secondary">Eligibility: ${esc(event.eligibility)}</p>` : ""}${event.prize_details ? `<p class="small text-secondary">Prizes: ${esc(event.prize_details)}</p>` : ""}${event.scope ? `<p class="small text-secondary">Scope: ${esc(event.scope.replaceAll("_", " "))}${event.event_format ? ` · ${esc(event.event_format)}` : ""}</p>` : ""}${event.source_name ? `<div class="source-note"><strong>Source: ${esc(event.source_name)}</strong> · ${event.source_completeness ?? 0}% of supported fields are present${event.last_fetched_at ? ` · Last checked ${esc(new Date(event.last_fetched_at).toLocaleString())}` : ""}${staleAfter ? " · This source record may be stale; verify details with the organizer." : ""}</div>` : ""}${tags(event.tags)}${event.is_imported ? `<p class="form-text mt-2">HackMate registration only tracks your interest here. It does not register you with the event organizer.</p>` : ""}<div class="card-actions mt-3">${actions}</div></div></div></div>`;
  document.body.append(modal);
  modal.addEventListener("hidden.bs.modal", () => modal.remove(), { once: true });
  bootstrap.Modal.getOrCreateInstance(modal).show();
}
function profileInput(label, name, value, required = false, type = "text", placeholder = "") {
  const range = name === "graduation_year" ? 'min="1950" max="2150"' : "";
  return `<div class="col-md-6"><label class="form-label" for="profile-${esc(name)}">${esc(label)}</label><input id="profile-${esc(name)}" class="form-control" name="${esc(name)}" type="${type}" value="${esc(value)}" maxlength="${name === "photo_url" ? 500 : 180}" ${range} ${required ? "required" : ""} placeholder="${esc(placeholder)}"></div>`;
}

async function renderRoadmaps() {
  const items = await api("/roadmaps");
  return `${heading("A little learning goes a long way", "Explore practical roadmaps to add a new skill to your toolkit.")}<form class="filter-bar" data-form="roadmap-search"><input class="form-control" name="domain" placeholder="Filter by domain"><button class="btn btn-outline-primary btn-sm">Search</button></form><div id="roadmap-results" class="item-grid">${items.length ? items.map(item => `<article class="item-card"><span class="badge-soft">${esc(item.domain)}</span><h3>${esc(item.title)}</h3><p>${esc(item.description)}</p><ol class="small text-secondary ps-3">${item.steps.map(step => `<li class="mb-2">${esc(step)}</li>`).join("")}</ol></article>`).join("") : empty("bi-signpost-split", "No roadmaps found", "Try another domain.")}</div>`;
}
async function renderChallenges() {
  const items = await api("/challenges");
  return `${heading("Warm up with a mock hackathon", "Practice shaping an idea before the real event begins.")}<div class="item-grid">${items.length ? items.map(item => `<article class="item-card"><div class="card-topline"><span class="badge-soft">${esc(item.domain)}</span><span class="badge-soft badge-gray">${esc(item.difficulty)}</span></div><h3>${esc(item.title)}</h3><div class="challenge-prompt">${esc(item.prompt)}</div><div class="meta-line mt-3"><span><i class="bi bi-clock"></i>${item.duration_minutes} minute challenge</span></div><div class="card-actions"><button class="btn btn-primary btn-sm" data-action="challenge" data-id="${item.id}" data-title="${esc(item.title)}" data-prompt="${esc(item.prompt)}" data-duration="${item.duration_minutes}">Start practice</button></div></article>`).join("") : empty("bi-trophy", "No challenges available", "Please check back soon.")}</div>`;
}
async function renderNotifications() {
  if (!state.user) return `${heading("Notifications", "Stay up to date with your team activity.")}${empty("bi-person-lock", "Sign in required", "Notifications are linked to your account.", "login", "Sign in")}`;
  const items = await api("/notifications");
  state.unreadNotificationCount = items.filter(item => !item.read).length;
  updateNavigationBadges();
  return `${heading("Your updates", "Application and team activity, all in one place.")}<div class="panel">${items.length ? items.map(item => `<div class="notification-row"><div class="task-main"><strong>${esc(item.message)} ${!item.read ? `<span class="badge-soft">New</span>` : ""}</strong><small>${esc(dateLabel(item.created_at))}</small></div>${!item.read ? `<button class="btn btn-outline-primary btn-sm" data-action="read-notification" data-id="${item.id}">Mark read</button>` : ""}</div>`).join("") : empty("bi-bell", "You're all caught up", "When teammates apply or your membership changes, we'll let you know.")}</div>`;
}

async function refreshListForm(form, type) {
  const values = new FormData(form);
  const params = new URLSearchParams();
  for (const [key, value] of values.entries()) if (String(value).trim()) params.set(key, String(value).trim());
  const target = document.getElementById(type === "opportunity" ? "opportunity-results" : type === "team" ? "team-results" : "roadmap-results");
  if (!target) return;
  const rows = await api(`/${type === "opportunity" ? "opportunities" : type === "team" ? "teams" : "roadmaps"}?${params}`);
  target.innerHTML = type === "opportunity" ? (rows.length ? rows.map(opportunityCard).join("") : empty("bi-search", "Nothing matched that search", "Try a different keyword or filter.")) :
    type === "team" ? (rows.length ? rows.map(teamCard).join("") : empty("bi-search", "No teams matched", "Try another search.")) :
      (rows.length ? rows.map(item => `<article class="item-card"><span class="badge-soft">${esc(item.domain)}</span><h3>${esc(item.title)}</h3><p>${esc(item.description)}</p><ol class="small text-secondary ps-3">${item.steps.map(step => `<li class="mb-2">${esc(step)}</li>`).join("")}</ol></article>`).join("") : empty("bi-search", "No roadmaps matched", "Try another domain."));
}

async function handleForm(form) {
  const data = new FormData(form);
  const value = name => String(data.get(name) || "").trim();
  const submit = form.querySelector('[type="submit"],button:not([type])');
  const submitMarkup = submit?.innerHTML;
  if (submit) {
    submit.disabled = true;
    submit.setAttribute("aria-busy", "true");
    submit.innerHTML = `<span class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>Working…`;
  }
  try {
    switch (form.dataset.form) {
      case "calendar-filters":
        state.calendarFilters = Object.fromEntries(
          ["search", "scope", "country", "region", "event_format", "technology", "eligibility", "deadline_before"]
            .map(key => [key, value(key)])
            .filter(([, entry]) => entry)
        );
        if (state.calendarFilters.deadline_before) {
          state.calendarFilters.deadline_before = new Date(
            `${state.calendarFilters.deadline_before}T23:59:59`
          ).toISOString();
        }
        await render();
        break;
      case "login": case "register": {
        const registering = form.dataset.form === "register";
        const result = await api(`/auth/${registering ? "register" : "login"}`, {
          method: "POST",
          body: JSON.stringify(registering
            ? { name: value("name"), email: value("email"), password: value("password") }
            : { email: value("email"), password: value("password") })
        });
        state.token = result.access_token;
        state.user = result.user;
        localStorage.setItem("hackmate_token", state.token);
        state.page = "dashboard";
        notify(registering ? "Welcome to HackMate!" : "You're signed in.");
        await render();
        await restoreAiConversation();
        break;
      }
      case "profile":
        state.user = await api("/users/me/profile", { method: "PUT", body: JSON.stringify({
          name: value("name"), college: value("college"), department: value("department"),
          photo_url: value("photo_url"), experience: value("experience"), preferred_role: value("preferred_role"),
          availability: value("availability"), bio: value("bio"), project_experience: value("project_experience"),
          skills: commaValues(value("skills")), interests: commaValues(value("interests"))
        }) });
        await api("/users/me/portfolio", { method: "PUT", body: JSON.stringify({
          preferred_name: value("preferred_name"), headline: value("headline"),
          degree: value("degree"), course: value("course"), study_year: value("study_year"),
          graduation_year: value("graduation_year") ? Number(value("graduation_year")) : null,
          location: value("location"), collaboration_mode: value("collaboration_mode"),
          languages: commaValues(value("languages"))
        }) });
        state.page = "profile"; notify("Profile updated."); await render(); break;
      case "portfolio":
        await api("/users/me/portfolio", { method: "PUT", body: JSON.stringify({
          github_username: value("github_username"),
          resume_visible: data.has("resume_visible"),
          projects_visible: data.has("projects_visible"),
          history_visible: data.has("history_visible"),
          credentials_visible: data.has("credentials_visible"),
          education_visible: data.has("education_visible"),
          location_visible: data.has("location_visible")
        }) });
        notify("Portfolio and privacy settings updated."); await render(); break;
      case "add-portfolio-skill":
        await api("/users/me/portfolio/skills", { method: "POST", body: JSON.stringify({
          name: value("name"), category: value("category"), proficiency: Number(value("proficiency"))
        }) });
        notify("Self-reported skill added."); await render(); break;
      case "add-project":
        await api("/users/me/portfolio/projects", { method: "POST", body: JSON.stringify({
          title: value("title"), description: value("description"), technologies: commaValues(value("technologies")),
          repository_url: value("repository_url"), demo_url: value("demo_url")
        }) });
        notify("Featured project added."); await render(); break;
      case "add-credential":
        await api("/users/me/portfolio/credentials", { method: "POST", body: JSON.stringify({
          title: value("title"), issuer: value("issuer"), kind: value("kind"), evidence_url: value("evidence_url")
        }) });
        notify("Portfolio item added as self-reported."); await render(); break;
      case "add-history":
        await api("/users/me/portfolio/hackathons", { method: "POST", body: JSON.stringify({
          event_name: value("event_name"), organizer: value("organizer"), event_date: value("event_date"),
          project_title: value("project_title"), summary: value("summary"), team_role: value("team_role"),
          technologies: commaValues(value("technologies")), result: value("result"),
          repository_url: value("repository_url"), demo_url: value("demo_url"), evidence_url: value("evidence_url")
        }) });
        notify("Hackathon entry added as self-reported."); await render(); break;
      case "resume": {
        const file = data.get("file");
        if (!(file instanceof File) || !file.size) throw new Error("Choose a PDF resume to upload.");
        await api("/users/me/resume", { method: "POST", body: data });
        notify("Resume uploaded securely."); await render(); break;
      }
      case "user-search":
        await renderUserSearch(value("q"));
        break;
      case "send-invitation":
        await api(`/teams/${Number(value("team_id"))}/invitations`, {
          method: "POST", body: JSON.stringify({ invitee_id: Number(value("invitee_id")), message: value("message") })
        });
        bootstrap.Modal.getInstance(form.closest(".modal"))?.hide();
        notify("Team invitation sent."); await render(); break;
      case "create-event": {
        const payload = {
          name: value("name"), organizer: value("organizer"), description: value("description"),
          starts_at: new Date(value("starts_at")).toISOString(), ends_at: new Date(value("ends_at")).toISOString(),
          registration_deadline: value("registration_deadline") ? new Date(value("registration_deadline")).toISOString() : null,
          location: value("location"), event_url: value("event_url"), eligibility: value("eligibility"),
          tags: commaValues(value("tags")), opportunity_id: value("opportunity_id") ? Number(value("opportunity_id")) : null
        };
        if (state.calendarEditingId) {
          await api(`/calendar/events/${state.calendarEditingId}`, { method: "PUT", body: JSON.stringify(payload) });
          notify("Hackathon event updated.");
        } else {
          await api("/calendar/events", { method: "POST", body: JSON.stringify(payload) });
          notify("Hackathon event added to the calendar.");
        }
        state.calendarEditingId = null;
        await render(); break;
      }
      case "create-opportunity": {
        const result = await api("/opportunities", { method: "POST", body: JSON.stringify({
          title: value("title"), kind: value("kind"), description: value("description"),
          required_skills: commaValues(value("required_skills")), team_size: Number(value("team_size")),
          deadline: value("deadline")
        }) });
        state.opportunityId = result.id; state.page = "opportunity-detail";
        notify("Opportunity published."); await render(); break;
      }
      case "create-team": {
        const result = await api("/teams", { method: "POST", body: JSON.stringify({
          name: value("name"), description: value("description"),
          required_skills: commaValues(value("required_skills")), required_roles: commaValues(value("required_roles")),
          max_size: Number(value("max_size")), opportunity_id: value("opportunity_id") ? Number(value("opportunity_id")) : null
        }) });
        state.teamId = result.id; sessionStorage.setItem("hackmate_team_id", result.id);
        state.page = "team-detail"; notify("Your team is ready."); await render(); break;
      }
      case "create-task":
        await api(`/teams/${state.teamId}/tasks`, { method: "POST", body: JSON.stringify({
          title: value("title"), description: value("description"),
          assignee_id: value("assignee_id") ? Number(value("assignee_id")) : null,
          priority: value("priority"), due_date: value("due_date")
        }) });
        notify("Task added to your team board."); await render(); break;
      case "opportunity-search": await refreshListForm(form, "opportunity"); break;
      case "team-search": await refreshListForm(form, "team"); break;
      case "roadmap-search": await refreshListForm(form, "roadmap"); break;
      case "send-message":
        await api(`/teams/${state.teamId}/messages`, { method: "POST", body: JSON.stringify({ content: value("content") }) });
        await render(); break;
      case "review":
        await api(`/teams/${state.teamId}/reviews`, { method: "POST", body: JSON.stringify({
          reviewee_id: Number(value("reviewee_id")), rating: Number(value("rating")),
          communication_rating: Number(value("communication_rating")),
          reliability_rating: Number(value("reliability_rating")), teamwork_rating: Number(value("teamwork_rating")),
          feedback: value("feedback")
        }) });
        notify("Thanks for sharing thoughtful feedback."); await render(); break;
    }
  } catch (error) {
    errorMessage(error);
    if (form.isConnected && submit) {
      submit.disabled = false;
      submit.removeAttribute("aria-busy");
      submit.innerHTML = submitMarkup;
    }
  }
}

async function fillOpportunityPicker() {
  const select = document.getElementById("opportunity-picker");
  if (!select) return;
  const rows = await api("/opportunities");
  select.innerHTML = `<option value="">Independent project</option>${rows.map(item => `<option value="${item.id}" ${item.id === state.opportunityId ? "selected" : ""}>${esc(item.title)}</option>`).join("")}`;
}

document.addEventListener("click", async event => {
  const pageButton = event.target.closest("[data-page]");
  const action = event.target.closest("[data-action]");
  const promptElement = event.target.closest("[data-ai-prompt]");
  if (promptElement) {
    event.preventDefault();
    openAiChat();
    const widget = document.getElementById("hackmate-ai-widget");
    const input = widget.querySelector(".hackmate-ai-input");
    const prompt = promptElement.dataset.aiPrompt || "";
    if (promptElement.closest("#hackmate-ai-widget")) {
      await sendAiMessage(prompt);
    } else {
      input.value = prompt;
      input.focus();
    }
    return;
  }
  if (pageButton) {
    event.preventDefault();
    state.page = pageButton.dataset.page;
    if (state.page === "profile") state.profileId = null;
    if (state.page === "create-team") state.opportunityId = null;
    closeMobileNavigation();
    state.error = "";
    await render();
    if (state.page === "create-team") fillOpportunityPicker().catch(errorMessage);
    return;
  }
  if (!action) return;
  try {
    const id = Number(action.dataset.id);
    switch (action.dataset.action) {
      case "retry": await render(); break;
      case "password-toggle": {
        const input = action.closest(".password-field")?.querySelector("input");
        if (!input) break;
        const reveal = input.type === "password";
        input.type = reveal ? "text" : "password";
        action.setAttribute("aria-label", reveal ? "Hide password" : "Show password");
        action.setAttribute("aria-pressed", String(reveal));
        action.innerHTML = `<i class="bi ${reveal ? "bi-eye-slash" : "bi-eye"}" aria-hidden="true"></i>`;
        input.focus();
        break;
      }
      case "logout":
        try { if (state.token) await api("/auth/logout", { method: "POST" }); }
        finally {
          state.token = null;
          state.user = null;
          state.aiConversationId = null;
          document.querySelector("#hackmate-ai-widget .hackmate-ai-messages").replaceChildren();
          localStorage.removeItem("hackmate_token");
          state.page = "login";
          updateAccount();
          await render();
          notify("You have signed out.");
        }
        break;
      case "opportunity": state.opportunityId = id; state.page = "opportunity-detail"; await render(); break;
      case "start-team":
        state.opportunityId = id;
        state.page = "create-team";
        await render();
        await fillOpportunityPicker();
        break;
      case "team": state.teamId = id; sessionStorage.setItem("hackmate_team_id", id); state.page = "team-detail"; await render(); break;
      case "apply": {
        const message = window.prompt("Add a short note for the team lead (optional):") || "";
        await api(`/teams/${id}/applications`, { method: "POST", body: JSON.stringify({ message }) });
        notify("Application sent to the team lead."); state.page = "teams"; await render(); break;
      }
      case "decision":
        await api(`/teams/${action.dataset.team}/applications/${id}`, { method: "PATCH", body: JSON.stringify({ status: action.dataset.status }) });
        notify(`Application ${action.dataset.status}.`); await render(); break;
      case "task-status": {
        const next = action.dataset.status === "Todo" ? "In Progress" : action.dataset.status === "In Progress" ? "Done" : "Todo";
        await api(`/teams/${state.teamId}/tasks/${id}`, { method: "PATCH", body: JSON.stringify({ status: next }) });
        notify(`Task moved to ${next}.`); await render(); break;
      }
      case "read-notification":
        await api(`/notifications/${id}/read`, { method: "POST" }); await render(); break;
      case "reputation":
        state.profileId = id; state.page = "reputation";
        if (state.user && id !== state.user.id) await showPublicReputation(id);
        else await render();
        break;
      case "challenge":
        showChallenge(action.dataset);
        break;
      case "view-profile":
        state.profileId = id;
        state.page = "profile";
        await render();
        break;
      case "invite-user":
        await openInviteDialog(id);
        break;
      case "invitation-response":
        await api(`/invitations/${id}`, {
          method: "PATCH", body: JSON.stringify({ status: action.dataset.status })
        });
        notify(action.dataset.status === "accepted" ? "Invitation accepted; you joined the team." : "Invitation declined.");
        await render(); break;
      case "cancel-invitation":
        if (window.confirm("Cancel this pending invitation?")) {
          await api(`/invitations/${id}`, { method: "DELETE" });
          notify("Invitation cancelled."); await render();
        }
        break;
      case "calendar-prev":
        state.calendarMonth = new Date(state.calendarMonth.getFullYear(), state.calendarMonth.getMonth() - 1, 1);
        await render(); break;
      case "calendar-next":
        state.calendarMonth = new Date(state.calendarMonth.getFullYear(), state.calendarMonth.getMonth() + 1, 1);
        await render(); break;
      case "calendar-today":
        state.calendarMonth = new Date(new Date().getFullYear(), new Date().getMonth(), 1);
        await render(); break;
      case "calendar-clear-filters":
        state.calendarFilters = {};
        await render(); break;
      case "calendar-event":
        await showCalendarEvent(id);
        break;
      case "register-event":
        await api(`/calendar/events/${id}/register`, { method: "POST" });
        bootstrap.Modal.getInstance(document.getElementById("calendar-event-modal"))?.hide();
        notify("Event registration recorded."); await render(); break;
      case "unregister-event":
        await api(`/calendar/events/${id}/register`, { method: "DELETE" });
        bootstrap.Modal.getInstance(document.getElementById("calendar-event-modal"))?.hide();
        notify("Event registration removed."); await render(); break;
      case "edit-event":
        bootstrap.Modal.getInstance(document.getElementById("calendar-event-modal"))?.hide();
        state.calendarEditingId = id;
        state.page = "calendar";
        await render(); break;
      case "cancel-event-edit":
        state.calendarEditingId = null;
        await render(); break;
      case "delete-event":
        if (window.confirm("Delete this event and its registrations?")) {
          await api(`/calendar/events/${id}`, { method: "DELETE" });
          bootstrap.Modal.getInstance(document.getElementById("calendar-event-modal"))?.hide();
          state.calendarEditingId = null;
          notify("Event deleted."); await render();
        }
        break;
      case "delete-project":
        await api(`/users/me/portfolio/projects/${id}`, { method: "DELETE" });
        notify("Featured project removed."); await render(); break;
      case "delete-credential":
        await api(`/users/me/portfolio/credentials/${id}`, { method: "DELETE" });
        notify("Portfolio item removed."); await render(); break;
      case "delete-history":
        await api(`/users/me/portfolio/hackathons/${id}`, { method: "DELETE" });
        notify("Hackathon entry removed."); await render(); break;
      case "delete-portfolio-skill":
        await api(`/users/me/portfolio/skills/${id}`, { method: "DELETE" });
        notify("Portfolio skill removed."); await render(); break;
      case "delete-resume":
        if (window.confirm("Permanently remove your stored resume?")) {
          await api("/users/me/resume", { method: "DELETE" });
          notify("Resume removed."); await render();
        }
        break;
      case "resume-preview":
      case "resume-download":
        await openResume(id, action.dataset.action === "resume-download");
        break;
      case "matching-explain":
        state.matchingExplainWithAi = !state.matchingExplainWithAi;
        await render(); break;
      case "open-ai":
        openAiChat();
        break;
      case "ai-close":
        document.getElementById("hackmate-ai-widget")?.querySelector(".hackmate-ai-panel")?.classList.remove("open");
        document.getElementById("hackmate-ai-widget")?.querySelector(".hackmate-ai-panel")?.setAttribute("aria-hidden", "true");
        document.querySelector(".hackmate-ai-fab")?.setAttribute("aria-expanded", "false");
        break;
      case "ai-retry": {
        await sendAiMessage(action.dataset.prompt, true);
        break;
      }
      case "ai-clear": {
        if (state.aiBusy) break;
        if (state.aiConversationId && state.token) {
          await api(`/ai/conversations/${encodeURIComponent(state.aiConversationId)}`, { method: "DELETE" });
        }
        state.aiConversationId = null;
        document.querySelector("#hackmate-ai-widget .hackmate-ai-messages").replaceChildren();
        notify("Conversation cleared.");
        break;
      }
    }
  } catch (error) { errorMessage(error); }
});

async function showPublicReputation(userId) {
  const [profile, reviews] = await Promise.all([api(`/users/${userId}`), api(`/users/${userId}/reviews`)]);
  const content = document.getElementById("content");
  content.innerHTML = `${heading(`${esc(profile.name)}'s reputation`, "Collaborator profile and feedback.")}<div class="profile-header"><span class="avatar">${esc(initials(profile.name))}</span><div class="flex-grow-1"><h2>${esc(profile.name)}</h2><p>${esc([profile.preferred_role, profile.college].filter(Boolean).join(" · "))}</p></div><div class="text-center"><div class="score-ring mx-auto">${reviews.average_rating ?? "—"}</div><small class="text-secondary">${reviews.count} reviews</small></div></div><div class="panel">${reviews.reviews.length ? reviews.reviews.map(review => `<div class="task-row"><div class="task-main"><strong>${esc(review.reviewer)} <span class="text-warning">${"★".repeat(review.rating)}${"☆".repeat(5-review.rating)}</span></strong><small>${esc(review.feedback || "No written feedback.")}</small></div></div>`).join("") : empty("bi-star", "No reviews yet", "This collaborator's reputation is just getting started.")}</div>`;
}

function showChallenge(challenge) {
  document.getElementById("challenge-modal")?.remove();
  const draft = localStorage.getItem(`hackmate-challenge-${challenge.id}`) || "";
  const modal = document.createElement("div");
  modal.id = "challenge-modal";
  modal.className = "modal fade";
  modal.tabIndex = -1;
  modal.innerHTML = `<div class="modal-dialog modal-lg modal-dialog-scrollable"><div class="modal-content"><div class="modal-header"><div><span class="badge-soft">Mock hackathon · ${esc(challenge.duration)} min</span><h2 class="modal-title fs-5 fw-bold mt-2">${esc(challenge.title)}</h2></div><button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button></div><div class="modal-body"><div class="challenge-prompt">${esc(challenge.prompt)}</div><form data-form="challenge-answer" data-id="${esc(challenge.id)}"><label class="form-label mt-3">Your solution notes</label><textarea class="form-control" name="answer" maxlength="10000" rows="8" placeholder="Who is this for? What would you build first? How will you know it works?">${esc(draft)}</textarea><div class="form-text">Your draft is saved in this browser only. Try setting a timer for ${esc(challenge.duration)} minutes.</div><button class="btn btn-primary btn-sm mt-3">Save my draft</button></form></div></div></div>`;
  document.body.append(modal);
  modal.addEventListener("hidden.bs.modal", () => modal.remove(), { once: true });
  bootstrap.Modal.getOrCreateInstance(modal).show();
}

document.addEventListener("submit", event => {
  const form = event.target.closest("form[data-form]");
  if (!form) return;
  event.preventDefault();
  if (form.dataset.form === "challenge-answer") {
    localStorage.setItem(`hackmate-challenge-${form.dataset.id}`, String(new FormData(form).get("answer") || ""));
    bootstrap.Modal.getInstance(form.closest(".modal"))?.hide();
    notify("Practice draft saved in this browser.");
    return;
  }
  handleForm(form);
});

document.addEventListener("change", async event => {
  if (event.target.id === "matching-target") {
    state.matchingTarget = event.target.value;
    await render();
    return;
  }
  if (event.target.id === "team-picker") {
    state.teamId = Number(event.target.value);
    sessionStorage.setItem("hackmate_team_id", state.teamId);
    await render();
  }
});
document.getElementById("mobile-menu").addEventListener("click", () => {
  toggleMobileNavigation();
});
document.getElementById("sidebar-toggle").addEventListener("click", () => {
  setSidebarCollapsed(!document.getElementById("sidebar").classList.contains("collapsed"));
});
document.getElementById("sidebar-backdrop").addEventListener("click", () => {
  closeMobileNavigation();
});
document.addEventListener("keydown", event => {
  if (event.key === "Escape") closeMobileNavigation();
});

async function initialRender() {
  ensureAiWidget();
  if (localStorage.getItem("hackmate_sidebar_collapsed") === "true") setSidebarCollapsed(true);
  if (state.token) {
    try { state.user = await api("/auth/me"); }
    catch (error) {
      console.warn("Saved HackMate session could not be restored", error);
      state.token = null;
      localStorage.removeItem("hackmate_token");
    }
  }
  updateAccount();
  await render();
  await restoreAiConversation();
}
initialRender();
