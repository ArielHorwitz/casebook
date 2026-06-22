"use strict";

// --- state ----------------------------------------------------------------
const state = {
  ws: null,
  activeCase: null,
  agents: new Map(), // agent_id -> {agent_id, case_id, label, backend, model, state, live}
  transcripts: new Map(), // agent_id -> [item]
  models: new Map(), // agent_id -> {available: [{model_id, name}], current}
  panes: new Map(), // agent_id -> {root, transcript, input, sendBtn, cancelBtn, stateEl}
  focusedAgent: null, // agent_id of the keyboard-focused session pane
  hotkeyByKey: new Map(), // KeyboardEvent.key -> action name
};

const el = (id) => document.getElementById(id);

// Render model output as markdown, sanitized — the agent's text is semi-trusted
// (it may quote files or web content), so we never inject raw HTML.
marked.setOptions({ gfm: true, breaks: true });
function renderMarkdown(text) {
  return DOMPurify.sanitize(marked.parse(text || ""));
}

// --- websocket ------------------------------------------------------------
function connect() {
  const ws = new WebSocket(`ws://${location.host}/ws`);
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

// --- toasts (transient feedback for things with no home in a transcript) ---
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

// --- event handling (single reducer for live + replayed events) -----------
function handleEvent(event) {
  switch (event.type) {
    case "snapshot":
      return applySnapshot(event);
    case "agent_added":
    case "agent_updated":
      return upsertAgent(event);
    case "agent_removed":
      return removeAgent(event.agent_id);
    case "models":
      state.models.set(event.agent_id, { available: event.available || [], current: event.current });
      return renderModel(event.agent_id);
    case "case_created":
      return loadCases();
    case "notice":
      // Notices tied to a live session go in its transcript; orphans (failed
      // starts, case-level messages) would otherwise vanish — surface as a toast.
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
  for (const [agentId, events] of Object.entries(snapshot.transcripts || {})) {
    for (const event of events) applyToTranscript(event);
  }
}

// Handles both agent_added and agent_updated (e.g. live <-> stored transitions).
function upsertAgent(agent) {
  state.agents.set(agent.agent_id, agent);
  if (!state.transcripts.has(agent.agent_id)) state.transcripts.set(agent.agent_id, []);
  buildPane(agent);
  updateHead(agent.agent_id);
}

function removeAgent(agentId) {
  const pane = state.panes.get(agentId);
  if (pane) pane.root.remove();
  state.panes.delete(agentId);
  state.agents.delete(agentId);
  state.transcripts.delete(agentId);
  state.models.delete(agentId);
}

// Mutate the transcript array, then re-render just that agent's transcript.
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
    const existing = items.find((i) => i.kind === "tool" && i.id === event.tool_call_id);
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
    const perm = items.find((i) => i.kind === "permission" && i.request_id === event.request_id);
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
      <span class="label"></span>
      <select class="model" title="model" hidden></select>
      <span class="state"></span>
      <button class="rename" title="rename session">✎</button>
      <button class="autoname" title="name session with the model">✨</button>
      <label class="allow" title="auto-allow this session's permission requests"><input type="checkbox" /> allow</label>
      <button class="resume" hidden>Resume</button>
      <button class="close" title="close session (keep history)">×</button>
      <button class="delete" title="delete session and history">🗑</button>
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
  input.onkeydown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
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
  root.addEventListener("mousedown", () => focusPane(agent.agent_id));

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
    stateEl: root.querySelector(".state"),
    labelEl: root.querySelector(".label"),
  };
  state.panes.set(agent.agent_id, pane);
  applyPaneVisibility();
  renderTranscript(agent.agent_id);
  renderModel(agent.agent_id);
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
  select.replaceChildren(...available.map((m) => {
    const option = document.createElement("option");
    option.value = m.model_id;
    option.textContent = m.name || m.model_id;
    if (m.description) option.title = m.description;
    return option;
  }));
  if (models.current) select.value = models.current;
  select.hidden = false;
}

function updateHead(agentId) {
  const pane = state.panes.get(agentId);
  const agent = state.agents.get(agentId);
  if (!pane || !agent) return;
  pane.labelEl.textContent = `${agent.label}  ·  ${agent.backend || ""}`;
  const live = !!agent.live;
  const working = agent.state === "working" || agent.state === "starting";
  pane.stateEl.textContent = agent.state || "";
  pane.stateEl.className = "state" + (working ? " working" : "");
  // A stored (non-live) session shows a Resume button instead of a composer.
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
    body.className = "content";
    // User text is shown verbatim; everything the model emits is markdown.
    if (item.role === "user") {
      body.textContent = item.text;
    } else {
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
    const q = document.createElement("div");
    q.className = "q";
    const tc = item.tool_call || {};
    q.textContent = `Permission: ${tc.title || "tool call"}${tc.kind ? ` (${tc.kind})` : ""}`;
    node.appendChild(q);
    const opts = document.createElement("div");
    opts.className = "options";
    for (const option of item.options) {
      const btn = document.createElement("button");
      btn.textContent = option.name;
      btn.onclick = () => send({ action: "permission", request_id: item.request_id, option_id: option.option_id });
      opts.appendChild(btn);
    }
    const deny = document.createElement("button");
    deny.textContent = "Deny";
    deny.onclick = () => send({ action: "permission", request_id: item.request_id, option_id: null });
    opts.appendChild(deny);
    node.appendChild(opts);
    return node;
  }
  return document.createElement("div");
}

function applyPaneVisibility() {
  for (const [agentId, pane] of state.panes) {
    const agent = state.agents.get(agentId);
    pane.root.hidden = !agent || agent.case_id !== state.activeCase;
    pane.root.classList.toggle("focused", agentId === state.focusedAgent);
  }
  const hasCase = state.activeCase !== null;
  el("add-agent").hidden = !hasCase;
  el("placeholder").hidden = hasCase;
  el("case-meta").hidden = !hasCase;
}

// --- keyboard focus + shortcuts -------------------------------------------
function visiblePaneIds() {
  return [...state.panes.keys()].filter((id) => {
    const agent = state.agents.get(id);
    return agent && agent.case_id === state.activeCase;
  });
}

function focusPane(agentId) {
  if (!state.panes.has(agentId)) return;
  state.focusedAgent = agentId;
  for (const [id, pane] of state.panes) pane.root.classList.toggle("focused", id === agentId);
}

function focusStep(delta) {
  const ids = visiblePaneIds();
  if (ids.length === 0) return;
  const current = ids.indexOf(state.focusedAgent);
  const next = current < 0 ? 0 : (current + delta + ids.length) % ids.length;
  focusPane(ids[next]);
  const pane = state.panes.get(ids[next]);
  if (pane) pane.root.scrollIntoView({ inline: "nearest", block: "nearest" });
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
  const summary = await fetch("/api/cases", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: title.trim() || "Unnamed case" }),
  }).then((r) => r.json());
  await loadCases();
  openCase(summary.case_id);
}

function runAction(action) {
  const id = state.focusedAgent;
  const agent = id && state.agents.get(id);
  switch (action) {
    case "new_case": return newCase();
    case "new_session": return newSession();
    case "focus_next": return focusStep(1);
    case "focus_prev": return focusStep(-1);
    case "help": return toggleHelp();
  }
  if (!agent) return; // session-targeted actions need a focused pane
  switch (action) {
    case "rename_session": return sessionRename(id);
    case "name_session": return send({ action: "name_agent", agent_id: id });
    case "resume_session": if (!agent.live) send({ action: "resume_agent", agent_id: id }); return;
    case "close_session": if (agent.live) send({ action: "close_agent", agent_id: id }); return;
    case "delete_session": return sessionDelete(id);
    case "toggle_allow": return sessionToggleAllow(id);
    case "cancel_turn": return send({ action: "cancel", agent_id: id });
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
  if (event.key === "Escape" && !el("hotkey-help").hidden) return toggleHelp();
  if (isTyping()) return;
  const action = state.hotkeyByKey.get(event.key);
  if (!action) return;
  event.preventDefault();
  runAction(action);
}

async function loadHotkeys() {
  const map = await fetch("/api/hotkeys").then((r) => r.json());
  state.hotkeyByKey = new Map(Object.entries(map).map(([action, key]) => [key, action]));
  const rows = Object.entries(map)
    .map(([action, key]) => `<tr><td>${key}</td><td>${action.replace(/_/g, " ")}</td></tr>`)
    .join("");
  el("hotkey-help-body").innerHTML = `<table>${rows}</table>`;
}

function toggleHelp() {
  el("hotkey-help").hidden = !el("hotkey-help").hidden;
}

// --- cases ----------------------------------------------------------------
async function loadCases() {
  const cases = await fetch("/api/cases").then((r) => r.json());
  const list = el("case-list");
  list.replaceChildren();
  for (const c of cases) {
    const li = document.createElement("li");
    li.dataset.caseId = c.case_id;
    li.innerHTML = `<div>${c.title}</div><div class="case-status">${c.status} · ${c.case_id}</div>`;
    li.onclick = () => openCase(c.case_id);
    list.appendChild(li);
  }
}

async function openCase(caseId) {
  state.activeCase = caseId;
  for (const li of document.querySelectorAll("#case-list li")) {
    li.classList.toggle("active", li.dataset.caseId === caseId);
  }
  const detail = await fetch(`/api/cases/${caseId}`).then((r) => r.json());
  el("case-title").textContent = detail.title || caseId;
  renderFiles(detail.files || []);
  const ids = visiblePaneIds();
  state.focusedAgent = ids.includes(state.focusedAgent) ? state.focusedAgent : (ids[0] || null);
  applyPaneVisibility();
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
  const text = await fetch(`/api/cases/${state.activeCase}/files/${encodeURIComponent(name)}`).then((r) => r.text());
  el("file-modal-name").textContent = name;
  el("file-modal-content").textContent = text;
  el("file-modal").hidden = false;
}

// --- backends -------------------------------------------------------------
async function loadBackends() {
  const info = await fetch("/api/backends").then((r) => r.json());
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

// --- wiring ---------------------------------------------------------------
el("add-agent").onclick = newSession;
el("new-case").onclick = newCase;
el("file-modal-close").onclick = () => (el("file-modal").hidden = true);
el("file-modal").onclick = (e) => {
  if (e.target.id === "file-modal") el("file-modal").hidden = true;
};
el("hotkey-help-close").onclick = toggleHelp;
el("hotkey-hint").onclick = toggleHelp;
document.addEventListener("keydown", onKeydown);

loadCases();
loadBackends();
loadHotkeys();
connect();
