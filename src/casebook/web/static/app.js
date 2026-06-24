"use strict";

// --- routing ---------------------------------------------------------------
// Nested under /project/{id}/ — the project browser lives at /.
function parseRoute() {
  const projectCase = location.pathname.match(/^\/project\/([^/]+)\/case\/(.+)$/);
  if (projectCase) return { mode: "case", projectId: projectCase[1], caseId: decodeURIComponent(projectCase[2]) };
  const projectScratch = location.pathname.match(/^\/project\/([^/]+)\/scratch$/);
  if (projectScratch) return { mode: "scratch", projectId: projectScratch[1], caseId: "scratch" };
  const project = location.pathname.match(/^\/project\/([^/]+)\/?$/);
  if (project) return { mode: "home", projectId: project[1], caseId: null };
  return { mode: "projects", projectId: null, caseId: null };
}
const route = parseRoute();
function isSessionPage() {
  return route.mode === "case" || route.mode === "scratch";
}

// --- URL helpers -----------------------------------------------------------
function projectUrl(projectId) {
  return `/project/${encodeURIComponent(projectId)}/`;
}
function caseUrl(caseId) {
  return `/project/${encodeURIComponent(route.projectId)}/case/${encodeURIComponent(caseId)}`;
}
function scratchUrl() {
  return `/project/${encodeURIComponent(route.projectId)}/scratch`;
}
function apiBase() {
  return `/api/projects/${encodeURIComponent(route.projectId)}`;
}

// --- state ----------------------------------------------------------------
const state = {
  ws: null,
  activeCase: route.caseId,
  agents: new Map(),
  transcripts: new Map(),
  models: new Map(),
  usage: new Map(),
  panes: new Map(),
  focusedAgent: null,
  focusedCase: null,
  focusedProject: null,
  cases: [],
  projects: [],
  hotkeyByKey: new Map(),
  widths: [],
  widthIndex: -1,
};

const el = (id) => document.getElementById(id);

marked.setOptions({ gfm: true, breaks: true });
function renderMarkdown(text) {
  return DOMPurify.sanitize(marked.parse(text || ""));
}

// --- websocket (project-scoped) -------------------------------------------
function connect() {
  if (!route.projectId) return; // project browser has no websocket
  const ws = new WebSocket(`ws://${location.host}/ws/${encodeURIComponent(route.projectId)}`);
  state.ws = ws;
  ws.onopen = () => setConnection(true);
  ws.onclose = () => {
    setConnection(false);
    setTimeout(connect, 1000);
  };
  ws.onmessage = (msg) => handleEvent(JSON.parse(msg.data));
}

function send(action) {
  if (state.ws && state.ws.readyState === WebSocket.OPEN) {
    state.ws.send(JSON.stringify(action));
  } else {
    toast("Not connected — action ignored. Retrying the connection…");
  }
}

// --- toasts ----------------------------------------------------------------
function toast(message, kind = "info") {
  const node = document.createElement("div");
  node.className = `toast ${kind}`;
  node.textContent = message;
  node.onclick = () => node.remove();
  el("toasts").appendChild(node);
  setTimeout(() => node.remove(), 6000);
}

function setConnection(connected) {
  const node = el("connection");
  node.textContent = connected ? "connected" : "disconnected";
  node.className = connected ? "connected" : "disconnected";
}

// --- event handling --------------------------------------------------------
function handleEvent(event) {
  if (event.type === "snapshot") return applySnapshot(event);
  if (route.mode === "home") {
    if (event.type === "case_created" || event.type === "case_deleted") loadCases();
    return;
  }
  if (event.type === "case_deleted" && event.case_id === route.caseId) {
    location.href = projectUrl(route.projectId);
    return;
  }
  if (event.case_id && event.case_id !== route.caseId) return;
  switch (event.type) {
    case "agent_added":
    case "agent_updated":
      return upsertAgent(event);
    case "agent_removed":
      return removeAgent(event.agent_id);
    case "models":
      state.models.set(event.agent_id, { available: event.available || [], current: event.current });
      return renderModel(event.agent_id);
    case "usage": {
      const usage = state.usage.get(event.agent_id) || {};
      for (const key of ["used", "size", "input_tokens", "output_tokens", "total_tokens", "cost_amount", "cost_currency"]) {
        if (event[key] != null) usage[key] = event[key];
      }
      state.usage.set(event.agent_id, usage);
      return renderUsage(event.agent_id);
    }
    case "notice":
      if (event.agent_id && state.transcripts.has(event.agent_id)) {
        return applyToTranscript(event);
      }
      return toast(event.message);
    case "files_changed":
      if (event.case_id === state.activeCase) renderFiles(event.files);
      return;
    default:
      return applyToTranscript(event);
  }
}

function applySnapshot(snapshot) {
  state.agents.clear();
  state.transcripts.clear();
  state.models.clear();
  for (const [agentId, pane] of state.panes) pane.root.remove();
  state.panes.clear();
  for (const agent of snapshot.agents) upsertAgent(agent);
  for (const [agentId, models] of Object.entries(snapshot.models || {})) {
    state.models.set(agentId, { available: models, current: (state.agents.get(agentId) || {}).model });
    renderModel(agentId);
  }
  for (const [agentId, usage] of Object.entries(snapshot.usage || {})) {
    state.usage.set(agentId, usage);
    renderUsage(agentId);
  }
  for (const [agentId, events] of Object.entries(snapshot.transcripts || {})) {
    for (const event of events) applyToTranscript(event);
  }
  const ids = sessionIds();
  if (!ids.includes(state.focusedAgent)) state.focusedAgent = ids[0] || null;
  renderSessionList();
  applyPaneVisibility();
}

function upsertAgent(agent) {
  if (!isSessionPage() || agent.case_id !== route.caseId) return;
  state.agents.set(agent.agent_id, agent);
  if (!state.transcripts.has(agent.agent_id)) state.transcripts.set(agent.agent_id, []);
  if (agent.live) {
    buildPane(agent);
    updateHead(agent.agent_id);
  } else {
    removePaneOnly(agent.agent_id);
  }
  if (!state.focusedAgent) state.focusedAgent = agent.agent_id;
  renderSessionList();
  applyPaneVisibility();
}

function removePaneOnly(agentId) {
  const pane = state.panes.get(agentId);
  if (pane) pane.root.remove();
  state.panes.delete(agentId);
}

function removeAgent(agentId) {
  removePaneOnly(agentId);
  state.agents.delete(agentId);
  state.transcripts.delete(agentId);
  state.models.delete(agentId);
  state.usage.delete(agentId);
  if (state.focusedAgent === agentId) state.focusedAgent = sessionIds()[0] || null;
  renderSessionList();
  applyPaneVisibility();
}

function applyToTranscript(event) {
  const agentId = event.agent_id;
  if (event.type === "agent_state") {
    const agent = state.agents.get(agentId);
    if (agent) {
      agent.state = event.state;
      updateHead(agentId);
    }
    return;
  }
  const items = state.transcripts.get(agentId);
  if (!items) return;

  if (event.type === "message") {
    const last = items[items.length - 1];
    const streaming = event.role !== "user";
    if (streaming && last && last.kind === "message" && last.role === event.role && last.streaming) {
      last.text += event.text;
    } else {
      items.push({ kind: "message", role: event.role, text: event.text, streaming, system: event.system });
    }
  } else if (event.type === "tool_call") {
    const existing = items.find((item) => item.kind === "tool" && item.id === event.tool_call_id);
    if (existing) {
      if (event.title) existing.title = event.title;
      if (event.tool_kind) existing.tool_kind = event.tool_kind;
      existing.status = event.status || existing.status;
    } else {
      items.push({ kind: "tool", id: event.tool_call_id, title: event.title, tool_kind: event.tool_kind, status: event.status });
    }
  } else if (event.type === "notice") {
    items.push({ kind: "notice", message: event.message });
  } else if (event.type === "permission_request") {
    items.push({ kind: "permission", request_id: event.request_id, tool_call: event.tool_call, options: event.options, resolved: false });
  } else if (event.type === "permission_resolved") {
    const perm = items.find((item) => item.kind === "permission" && item.request_id === event.request_id);
    if (perm) perm.resolved = true;
  } else {
    return;
  }
  renderTranscript(agentId);
}

// --- panes / rendering ----------------------------------------------------
function buildPane(agent) {
  if (state.panes.get(agent.agent_id)) return;
  const root = document.createElement("div");
  root.className = "agent-pane";
  root.innerHTML = `
    <div class="agent-head">
      <div class="agent-head-title"><span class="label"></span></div>
      <div class="agent-head-controls">
        <span class="state"></span>
        <select class="model" title="model" hidden></select>
        <label class="allow" title="auto-allow this session's permission requests"><input type="checkbox" /> allow</label>
        <button class="rename" title="rename session">&#x270E;</button>
        <button class="autoname" title="autoname session">&#x2728;</button>
        <button class="promote" title="promote into a new case" hidden>&#x2191; case</button>
        <button class="resume" hidden>Resume</button>
        <button class="close" title="close session (keep history)">&#xd7;</button>
        <button class="delete" title="delete session and history">&#x1F5D1;</button>
      </div>
      <div class="agent-usage"></div>
    </div>
    <div class="transcript"></div>
    <div class="composer">
      <textarea rows="1" placeholder="Message this session…"></textarea>
      <button class="send">Send</button>
      <button class="cancel" hidden>Stop</button>
    </div>`;
  el("agent-panes").appendChild(root);

  const input = root.querySelector("textarea");
  const sendBtn = root.querySelector(".send");
  const cancelBtn = root.querySelector(".cancel");
  const doSend = () => {
    const text = input.value.trim();
    if (!text) return;
    send({ action: "send", agent_id: agent.agent_id, text });
    input.value = "";
  };
  sendBtn.onclick = doSend;
  input.onkeydown = (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      doSend();
    }
  };
  cancelBtn.onclick = () => send({ action: "cancel", agent_id: agent.agent_id });
  const allowInput = root.querySelector(".allow input");
  allowInput.onchange = () => send({ action: "set_always_allow", agent_id: agent.agent_id, value: allowInput.checked });
  root.querySelector(".rename").onclick = () => sessionRename(agent.agent_id);
  root.querySelector(".autoname").onclick = () => send({ action: "name_agent", agent_id: agent.agent_id });
  const modelSelect = root.querySelector(".model");
  modelSelect.onchange = () => send({ action: "set_model", agent_id: agent.agent_id, model_id: modelSelect.value });
  root.querySelector(".resume").onclick = () => send({ action: "resume_agent", agent_id: agent.agent_id });
  root.querySelector(".close").onclick = () => send({ action: "close_agent", agent_id: agent.agent_id });
  root.querySelector(".delete").onclick = () => sessionDelete(agent.agent_id);
  const promoteBtn = root.querySelector(".promote");
  promoteBtn.hidden = route.mode !== "scratch";
  promoteBtn.onclick = () => promoteSession(agent.agent_id);
  root.addEventListener("mousedown", () => focusSession(agent.agent_id));

  const pane = {
    root,
    transcript: root.querySelector(".transcript"),
    input,
    sendBtn,
    cancelBtn,
    composer: root.querySelector(".composer"),
    resumeBtn: root.querySelector(".resume"),
    modelSelect,
    allowInput,
    usageEl: root.querySelector(".agent-usage"),
    stateEl: root.querySelector(".state"),
    labelEl: root.querySelector(".label"),
  };
  state.panes.set(agent.agent_id, pane);
  applyPaneVisibility();
  renderTranscript(agent.agent_id);
  renderModel(agent.agent_id);
  renderUsage(agent.agent_id);
}

function fmtTokens(count) {
  if (count == null) return null;
  if (count >= 1e6) return (count / 1e6).toFixed(1) + "M";
  if (count >= 1e3) return (count / 1e3).toFixed(1) + "k";
  return String(count);
}

function renderUsage(agentId) {
  const pane = state.panes.get(agentId);
  if (!pane) return;
  const usage = state.usage.get(agentId);
  const parts = [];
  if (usage) {
    if (usage.used != null && usage.size != null) {
      const pct = usage.size ? Math.round((usage.used / usage.size) * 100) : 0;
      parts.push(`context ${fmtTokens(usage.used)}/${fmtTokens(usage.size)} (${pct}%)`);
    } else if (usage.used != null) {
      parts.push(`context ${fmtTokens(usage.used)}`);
    }
    if (usage.total_tokens != null) parts.push(`${fmtTokens(usage.total_tokens)} tokens`);
    if (usage.cost_amount != null) parts.push(`${usage.cost_currency || ""} ${usage.cost_amount.toFixed(2)}`.trim());
  }
  pane.usageEl.textContent = parts.join("  \u00b7  ");
  pane.usageEl.hidden = parts.length === 0;
}

function renderModel(agentId) {
  const pane = state.panes.get(agentId);
  if (!pane) return;
  const models = state.models.get(agentId);
  const select = pane.modelSelect;
  const available = (models && models.available) || [];
  if (available.length === 0) {
    select.hidden = true;
    return;
  }
  select.replaceChildren(...available.map((model) => {
    const option = document.createElement("option");
    option.value = model.model_id;
    option.textContent = model.name || model.model_id;
    if (model.description) option.title = model.description;
    return option;
  }));
  if (models.current) select.value = models.current;
  select.hidden = false;
}

function updateHead(agentId) {
  const pane = state.panes.get(agentId);
  const agent = state.agents.get(agentId);
  if (!pane || !agent) return;
  pane.labelEl.textContent = `${agent.label}  \u00b7  ${agent.backend || ""}`;
  const live = !!agent.live;
  const working = agent.state === "working" || agent.state === "starting";
  pane.stateEl.textContent = agent.state || "";
  pane.stateEl.className = "state" + (working ? " working" : "");
  pane.resumeBtn.hidden = live;
  pane.composer.hidden = !live;
  pane.allowInput.checked = !!agent.always_allow;
  pane.input.disabled = working;
  pane.sendBtn.disabled = working;
  pane.cancelBtn.hidden = agent.state !== "working";
}

function renderTranscript(agentId) {
  const pane = state.panes.get(agentId);
  if (!pane) return;
  const items = state.transcripts.get(agentId) || [];
  pane.transcript.replaceChildren(...items.map((item) => renderItem(agentId, item)));
  pane.transcript.scrollTop = pane.transcript.scrollHeight;
}

function renderItem(agentId, item) {
  if (item.kind === "message") {
    const node = document.createElement("div");
    node.className = `bubble ${item.role}` + (item.system ? " system" : "");
    const role = document.createElement("span");
    role.className = "role";
    role.textContent = item.system ? "system" : item.role;
    node.appendChild(role);
    const body = document.createElement("div");
    if (item.role === "user") {
      body.className = "content";
      body.textContent = item.text;
    } else {
      body.className = "content markdown";
      body.innerHTML = renderMarkdown(item.text);
    }
    node.appendChild(body);
    return node;
  }
  if (item.kind === "tool") {
    const node = document.createElement("div");
    node.className = "tool";
    node.innerHTML = `<span class="status ${item.status || ""}">${item.status || ""}</span>` +
      `<span class="tk">${item.tool_kind || "tool"}</span> ` +
      `<span class="title"></span>`;
    node.querySelector(".title").textContent = item.title || "";
    return node;
  }
  if (item.kind === "notice") {
    const node = document.createElement("div");
    node.className = "notice";
    node.textContent = item.message;
    return node;
  }
  if (item.kind === "permission") {
    const node = document.createElement("div");
    node.className = "permission" + (item.resolved ? " resolved" : "");
    const question = document.createElement("div");
    question.className = "q";
    const toolCall = item.tool_call || {};
    question.textContent = `Permission: ${toolCall.title || "tool call"}${toolCall.kind ? ` (${toolCall.kind})` : ""}`;
    node.appendChild(question);
    const opts = document.createElement("div");
    opts.className = "options";
    for (const option of item.options) {
      const btn = document.createElement("button");
      btn.textContent = option.name;
      btn.onclick = () => send({ action: "permission", request_id: item.request_id, option_id: option.option_id });
      opts.appendChild(btn);
    }
    const deny = document.createElement("button");
    deny.textContent = "Cancel";
    deny.onclick = () => send({ action: "permission", request_id: item.request_id, option_id: null });
    opts.appendChild(deny);
    node.appendChild(opts);
    return node;
  }
  return document.createElement("div");
}

function sessionIds() {
  return [...state.agents.keys()];
}

function renderSessionList() {
  const list = el("session-list");
  if (!list) return;
  list.replaceChildren();
  for (const agentId of sessionIds()) {
    const agent = state.agents.get(agentId);
    const li = document.createElement("li");
    li.dataset.agentId = agentId;
    li.className = "session-item" + (agentId === state.focusedAgent ? " focused" : "");
    const dot = `<span class="dot ${agent.state || ""}"></span>`;
    const meta = agent.live ? (agent.state || "live") : "closed";
    li.innerHTML =
      `<button class="open">${dot}<span class="name"></span>` +
      `<span class="session-meta">${meta}</span></button>` +
      `<button class="rename" title="rename">&#x270E;</button>` +
      `<button class="trash" title="delete session and history">&#x1F5D1;</button>`;
    li.querySelector(".name").textContent = agent.label;
    li.querySelector(".open").onclick = () => activateSession(agentId);
    li.querySelector(".rename").onclick = () => sessionRename(agentId);
    li.querySelector(".trash").onclick = () => sessionDelete(agentId);
    list.appendChild(li);
  }
}

function activateSession(agentId) {
  const agent = state.agents.get(agentId);
  if (!agent) return;
  state.focusedAgent = agentId;
  if (agent.live) {
    const pane = state.panes.get(agentId);
    if (pane) pane.root.scrollIntoView({ inline: "nearest", block: "nearest" });
  } else {
    send({ action: "resume_agent", agent_id: agentId });
  }
  applyPaneVisibility();
}

function applyPaneVisibility() {
  for (const [agentId, pane] of state.panes) {
    pane.root.classList.toggle("focused", agentId === state.focusedAgent);
  }
  for (const li of document.querySelectorAll("#session-list li")) {
    li.classList.toggle("focused", li.dataset.agentId === state.focusedAgent);
  }
  const hint = el("no-open-sessions");
  if (hint) hint.hidden = state.panes.size > 0;
}

// --- keyboard focus + shortcuts -------------------------------------------
function focusSession(agentId) {
  if (!state.agents.has(agentId)) return;
  state.focusedAgent = agentId;
  applyPaneVisibility();
  const pane = state.panes.get(agentId);
  if (pane) pane.root.scrollIntoView({ inline: "nearest", block: "nearest" });
  const li = document.querySelector(`#session-list li[data-agent-id="${CSS.escape(agentId)}"]`);
  if (li) li.scrollIntoView({ block: "nearest" });
}

function focusStep(delta) {
  if (route.mode === "home") return focusCaseStep(delta);
  if (route.mode === "projects") return focusProjectStep(delta);
  const ids = sessionIds();
  if (ids.length === 0) return;
  const current = ids.indexOf(state.focusedAgent);
  const next = current < 0 ? 0 : (current + delta + ids.length) % ids.length;
  focusSession(ids[next]);
}

function caseIds() {
  return [...document.querySelectorAll("#case-list li")].map((li) => li.dataset.caseId);
}

function focusCase(caseId) {
  state.focusedCase = caseId;
  for (const li of document.querySelectorAll("#case-list li")) {
    li.classList.toggle("focused", li.dataset.caseId === caseId);
  }
  if (caseId) renderCaseDetail(caseId);
  else {
    el("case-detail").hidden = true;
    el("placeholder").hidden = false;
  }
}

function focusCaseStep(delta) {
  const ids = caseIds();
  if (ids.length === 0) return;
  const current = ids.indexOf(state.focusedCase);
  const next = current < 0 ? 0 : (current + delta + ids.length) % ids.length;
  focusCase(ids[next]);
  const li = document.querySelector(`#case-list li[data-case-id="${CSS.escape(ids[next])}"]`);
  if (li) li.scrollIntoView({ block: "nearest" });
}

// --- project browser focus -------------------------------------------------
function projectIds() {
  return [...document.querySelectorAll("#project-list li")].map((li) => li.dataset.projectId);
}

function focusProject(projectId) {
  state.focusedProject = projectId;
  for (const li of document.querySelectorAll("#project-list li")) {
    li.classList.toggle("focused", li.dataset.projectId === projectId);
  }
  if (projectId) renderProjectDetail(projectId);
  else {
    el("project-detail").hidden = true;
    el("project-placeholder").hidden = false;
  }
}

function focusProjectStep(delta) {
  const ids = projectIds();
  if (ids.length === 0) return;
  const current = ids.indexOf(state.focusedProject);
  const next = current < 0 ? 0 : (current + delta + ids.length) % ids.length;
  focusProject(ids[next]);
  const li = document.querySelector(`#project-list li[data-project-id="${CSS.escape(ids[next])}"]`);
  if (li) li.scrollIntoView({ block: "nearest" });
}

function renderProjectDetail(projectId) {
  const project = state.projects.find((entry) => entry.id === projectId);
  if (!project) {
    el("project-detail").hidden = true;
    el("project-placeholder").hidden = false;
    return;
  }
  el("project-placeholder").hidden = true;
  el("init-prompt").hidden = true;
  el("project-detail").hidden = false;
  el("pd-name").textContent = project.name;
  el("pd-path").textContent = project.path;
  el("pd-meta").textContent = [
    `${project.cases || 0} case${project.cases === 1 ? "" : "s"}`,
    project.last_opened ? `opened ${new Date(project.last_opened).toLocaleString()}` : null,
  ].filter(Boolean).join("  \u00b7  ");
  el("pd-open").href = projectUrl(projectId);
}

// Session actions shared by buttons and hotkeys.
function sessionRename(agentId) {
  const current = (state.agents.get(agentId) || {}).label || "";
  const label = prompt("Session name:", current);
  if (label && label.trim()) send({ action: "rename_agent", agent_id: agentId, label: label.trim() });
}
function sessionDelete(agentId) {
  if (confirm("Delete this session and its history?")) send({ action: "delete_agent", agent_id: agentId });
}
function sessionToggleAllow(agentId) {
  const pane = state.panes.get(agentId);
  if (!pane) return;
  pane.allowInput.checked = !pane.allowInput.checked;
  send({ action: "set_always_allow", agent_id: agentId, value: pane.allowInput.checked });
}

function newSession() {
  if (state.activeCase) {
    send({ action: "add_agent", case_id: state.activeCase, backend: el("backend-select").value });
  }
}

async function newCase() {
  const title = prompt("New case title:", "Unnamed case");
  if (title === null) return;
  const summary = await fetch(`${apiBase()}/cases`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: title.trim() || "Unnamed case" }),
  }).then((response) => response.json());
  if (summary.case_id) location.href = caseUrl(summary.case_id);
}

async function deleteCase(caseId, title) {
  if (!caseId) return;
  if (!confirm(`Delete case "${title || caseId}" and all its sessions? This cannot be undone.`)) return;
  await fetch(`${apiBase()}/cases/${encodeURIComponent(caseId)}`, { method: "DELETE" });
  loadCases();
}

function deleteFocusedCase() {
  const li = document.querySelector(`#case-list li[data-case-id="${CSS.escape(state.focusedCase || "")}"]`);
  const title = li ? li.querySelector(".case-title-row").textContent : "";
  deleteCase(state.focusedCase, title);
}

function openFocused() {
  if (route.mode === "projects") {
    if (state.focusedProject) location.href = projectUrl(state.focusedProject);
    return;
  }
  if (route.mode === "home") {
    if (state.focusedCase) location.href = caseUrl(state.focusedCase);
    return;
  }
  const agent = state.focusedAgent && state.agents.get(state.focusedAgent);
  if (!agent) return;
  if (agent.live) {
    const pane = state.panes.get(state.focusedAgent);
    if (pane) pane.input.focus();
  } else {
    activateSession(state.focusedAgent);
  }
}

function runAction(action) {
  const agentId = state.focusedAgent;
  const agent = agentId && state.agents.get(agentId);
  switch (action) {
    case "new_case": return newCase();
    case "new_session": return isSessionPage() ? newSession() : newCase();
    case "delete_session": if (route.mode === "home") return deleteFocusedCase(); break;
    case "home":
      if (route.projectId) return location.href = projectUrl(route.projectId);
      return;
    case "scratch":
      if (route.projectId && route.mode !== "scratch") return location.href = scratchUrl();
      return;
    case "focus_next": return focusStep(1);
    case "focus_prev": return focusStep(-1);
    case "open_focused": return openFocused();
    case "cycle_width": return cycleWidth();
    case "cancel_turn": return cancelTurn();
    case "help": return toggleHelp();
  }
  if (!isSessionPage() || !agent) return;
  switch (action) {
    case "rename_session": return sessionRename(agentId);
    case "autoname_session": return send({ action: "name_agent", agent_id: agentId });
    case "close_session": if (agent.live) send({ action: "close_agent", agent_id: agentId }); return;
    case "delete_session": return sessionDelete(agentId);
    case "toggle_allow": return sessionToggleAllow(agentId);
  }
}

function cancelTurn() {
  if (isSessionPage() && state.focusedAgent) {
    send({ action: "cancel", agent_id: state.focusedAgent });
  }
}

function isTyping() {
  const node = document.activeElement;
  if (!node) return false;
  const tag = node.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || node.isContentEditable;
}

function onKeydown(event) {
  if (event.metaKey || event.ctrlKey || event.altKey) return;
  if (event.key === "Escape") {
    if (!el("file-modal").hidden) return (el("file-modal").hidden = true);
    if (!el("hotkey-help").hidden) return toggleHelp();
    if (isTyping()) return document.activeElement.blur();
  }
  if (isTyping()) return;
  const action = state.hotkeyByKey.get(event.key);
  if (!action) return;
  event.preventDefault();
  runAction(action);
}

async function loadHotkeys() {
  if (!route.projectId) return; // no hotkeys on project browser
  const map = await fetch(`${apiBase()}/hotkeys`).then((response) => response.json());
  state.hotkeyByKey = new Map();
  for (const [action, keys] of Object.entries(map)) {
    for (const key of Array.isArray(keys) ? keys : [keys]) state.hotkeyByKey.set(key, action);
  }
  const rows = Object.entries(map)
    .map(([action, keys]) => {
      const shown = (Array.isArray(keys) ? keys : [keys]).join(" / ");
      return `<tr><td>${shown}</td><td>${action.replace(/_/g, " ")}</td></tr>`;
    })
    .join("");
  el("hotkey-help-body").innerHTML = `<table>${rows}</table>`;
}

function toggleHelp() {
  el("hotkey-help").hidden = !el("hotkey-help").hidden;
}

async function loadUi() {
  if (!route.projectId) return;
  const ui = await fetch(`${apiBase()}/ui`).then((response) => response.json());
  const style = document.documentElement.style;
  if (ui.session_min_width) style.setProperty("--session-min-width", ui.session_min_width);
  if (ui.session_max_width) style.setProperty("--session-max-width", ui.session_max_width);
  state.widths = Array.isArray(ui.session_widths) ? ui.session_widths : [];
  const saved = localStorage.getItem("casebook.sessionWidth");
  const width = saved || ui.session_width;
  if (width) style.setProperty("--session-width", width);
  state.widthIndex = state.widths.indexOf(width);
}

function cycleWidth() {
  if (!state.widths || state.widths.length === 0) return;
  state.widthIndex = (state.widthIndex + 1 + state.widths.length) % state.widths.length;
  const width = state.widths[state.widthIndex];
  document.documentElement.style.setProperty("--session-width", width);
  localStorage.setItem("casebook.sessionWidth", width);
  toast(`Session width: ${width}`);
}

// --- projects (project browser) -------------------------------------------
async function loadProjects() {
  state.projects = await fetch("/api/projects").then((response) => response.json());
  const list = el("project-list");
  list.replaceChildren();
  for (const project of state.projects) {
    const li = document.createElement("li");
    li.dataset.projectId = project.id;
    li.className = "project-item";
    const link = document.createElement("a");
    link.className = "open";
    link.href = projectUrl(project.id);
    link.title = project.path;
    link.innerHTML = `<span class="project-name"></span><span class="project-path muted"></span>`;
    link.querySelector(".project-name").textContent = project.name;
    link.querySelector(".project-path").textContent = project.path;
    link.onclick = (event) => {
      if (event.metaKey || event.ctrlKey || event.shiftKey) return;
      event.preventDefault();
      focusProject(project.id);
    };
    li.appendChild(link);
    list.appendChild(li);
  }
  const ids = projectIds();
  state.focusedProject = ids.includes(state.focusedProject) ? state.focusedProject : (ids[0] || null);
  focusProject(state.focusedProject);
}

async function openProjectPath(path) {
  if (!path.trim()) return;
  const response = await fetch("/api/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path: path.trim(), action: "open" }),
  });
  const data = await response.json();
  if (response.ok) {
    location.href = projectUrl(data.id);
  } else if (data.error && data.error.includes("no casebook found")) {
    // Show init prompt
    el("project-detail").hidden = true;
    el("project-placeholder").hidden = true;
    el("init-prompt").hidden = false;
    el("init-prompt-path").textContent = path.trim();
    el("init-project").onclick = () => initProjectPath(path.trim());
  } else {
    toast(data.error || "Failed to open project", "error");
  }
}

async function initProjectPath(path) {
  const response = await fetch("/api/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, action: "init" }),
  });
  const data = await response.json();
  if (response.ok) {
    location.href = projectUrl(data.id);
  } else {
    toast(data.error || "Failed to initialize project", "error");
  }
}

// --- cases (project home page) --------------------------------------------
async function loadCases() {
  state.cases = await fetch(`${apiBase()}/cases`).then((response) => response.json());
  const list = el("case-list");
  list.replaceChildren();
  for (const caseEntry of state.cases) {
    const li = document.createElement("li");
    li.dataset.caseId = caseEntry.case_id;
    li.className = "case-item";
    const link = document.createElement("a");
    link.className = "open";
    link.href = caseUrl(caseEntry.case_id);
    link.title = caseEntry.title;
    link.textContent = caseEntry.title;
    link.onclick = (event) => {
      if (event.metaKey || event.ctrlKey || event.shiftKey) return;
      event.preventDefault();
      focusCase(caseEntry.case_id);
    };
    li.appendChild(link);
    list.appendChild(li);
  }
  const ids = caseIds();
  state.focusedCase = ids.includes(state.focusedCase) ? state.focusedCase : (ids[0] || null);
  focusCase(state.focusedCase);
}

let caseDetailToken = 0;
async function renderCaseDetail(caseId) {
  const summary = state.cases.find((caseEntry) => caseEntry.case_id === caseId);
  if (!summary) {
    el("case-detail").hidden = true;
    el("placeholder").hidden = false;
    return;
  }
  el("placeholder").hidden = true;
  el("case-detail").hidden = false;
  el("cd-title").textContent = summary.title;
  el("cd-open").href = caseUrl(caseId);
  el("cd-delete").onclick = () => deleteCase(caseId, summary.title);
  el("cd-meta").textContent = [
    summary.status,
    `${summary.sessions || 0} session${summary.sessions === 1 ? "" : "s"}`,
    summary.created ? new Date(summary.created).toLocaleString() : null,
  ].filter(Boolean).join("  \u00b7  ");
  el("cd-id").textContent = caseId;
  el("cd-keywords").innerHTML = (summary.keywords || []).map((keyword) => `<span class="kw">${keyword}</span>`).join("");
  el("cd-files").innerHTML = "";
  el("cd-sessions").innerHTML = "";
  const token = ++caseDetailToken;
  const detail = await fetch(`${apiBase()}/cases/${encodeURIComponent(caseId)}`).then((response) => response.json()).catch(() => null);
  if (token !== caseDetailToken || !detail) return;
  if ((detail.files || []).length) {
    el("cd-files").innerHTML = "<h4>Files</h4>" + detail.files.map((filename) => `<span class="file">${filename}</span>`).join("");
  }
  if ((detail.agents || []).length) {
    el("cd-sessions").innerHTML = "<h4>Sessions</h4>" +
      detail.agents.map((agent) => `<div class="cd-session">${agent.label} <span class="muted">(${agent.live ? agent.state : "closed"})</span></div>`).join("");
  }
}

// --- case page -------------------------------------------------------------
async function openCaseView(caseId) {
  const detail = await fetch(`${apiBase()}/cases/${caseId}`).then((response) => response.json()).catch(() => null);
  el("case-title").textContent = (detail && detail.title) || caseId;
  document.title = `${(detail && detail.title) || caseId} — casebook`;
  renderFiles((detail && detail.files) || []);
}

function renderFiles(files) {
  const list = el("file-list");
  list.replaceChildren();
  for (const name of files) {
    const li = document.createElement("li");
    li.textContent = name;
    li.onclick = () => openFile(name);
    list.appendChild(li);
  }
}

async function openFile(name) {
  const text = await fetch(`${apiBase()}/cases/${state.activeCase}/files/${encodeURIComponent(name)}`).then((response) => response.text());
  el("file-modal-name").textContent = name;
  const body = el("file-modal-content");
  if (/\.(md|markdown)$/i.test(name)) {
    body.className = "filebody markdown";
    body.innerHTML = renderMarkdown(text);
  } else {
    body.className = "filebody plain";
    body.textContent = text;
  }
  el("file-modal").hidden = false;
}

// --- backends --------------------------------------------------------------
async function loadBackends() {
  const info = await fetch(`${apiBase()}/backends`).then((response) => response.json());
  const select = el("backend-select");
  select.replaceChildren(...info.backends.map((name) => {
    const option = document.createElement("option");
    option.value = name;
    option.textContent = name;
    return option;
  }));
  if (info.default) select.value = info.default;
  select.hidden = info.backends.length <= 1;
}

async function promoteSession(agentId) {
  const title = prompt("Promote this session into a new case — title:", "Unnamed case");
  if (title === null) return;
  const response = await fetch(`${apiBase()}/promote`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ agent_id: agentId, title: title.trim() || "Unnamed case" }),
  }).then((response) => response.json()).catch(() => null);
  if (response && response.case_id) location.href = caseUrl(response.case_id);
}

function applyRoute() {
  const isProjects = route.mode === "projects";
  const isHome = route.mode === "home";
  const isScratch = route.mode === "scratch";
  const isCase = route.mode === "case";
  const hasProject = !!route.projectId;

  document.body.classList.toggle("projects", isProjects);
  document.body.classList.toggle("home", isHome);
  document.body.classList.toggle("case", isCase || isScratch);

  // Sidebar sections
  el("projects-nav").hidden = !isProjects;
  el("cases-nav").hidden = !isHome;
  el("case-nav").hidden = !(isCase || isScratch);
  el("files-section").hidden = !route.caseId || isScratch;

  // Main sections
  el("project-detail").hidden = true;
  el("project-placeholder").hidden = !isProjects;
  el("init-prompt").hidden = true;
  el("agents").hidden = !(isCase || isScratch);
  el("case-detail").hidden = true;
  el("placeholder").hidden = !isHome;

  // Top bar
  el("back-projects").hidden = !hasProject;
  el("back-cases").hidden = !(isCase || isScratch);
  if (hasProject) {
    el("back-cases").href = projectUrl(route.projectId);
  }
  el("case-title").hidden = isProjects || isHome;

  // Scratch link
  const scratchLink = el("scratch-link");
  if (scratchLink && hasProject) {
    scratchLink.href = scratchUrl();
  }

  // Connection indicator: hide on project browser (no websocket)
  el("connection").hidden = isProjects;
}

// --- wiring ---------------------------------------------------------------
el("add-agent").onclick = newSession;
el("new-case").onclick = newCase;
el("file-modal-close").onclick = () => (el("file-modal").hidden = true);
el("file-modal").onclick = (event) => {
  if (event.target.id === "file-modal") el("file-modal").hidden = true;
};
el("hotkey-help-close").onclick = toggleHelp;
el("hotkey-hint").onclick = toggleHelp;
el("open-project").onclick = () => openProjectPath(el("project-path-input").value);
el("project-path-input").onkeydown = (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    openProjectPath(el("project-path-input").value);
  }
};
document.addEventListener("keydown", onKeydown);

applyRoute();
if (route.mode === "projects") {
  loadProjects();
} else if (route.mode === "home") {
  loadHotkeys();
  loadUi();
  connect();
  loadCases();
} else if (route.mode === "scratch") {
  loadHotkeys();
  loadUi();
  connect();
  loadBackends();
  el("case-title").textContent = "Scratch sessions";
  document.title = "Scratch — casebook";
} else {
  loadHotkeys();
  loadUi();
  connect();
  loadBackends();
  openCaseView(route.caseId);
}
