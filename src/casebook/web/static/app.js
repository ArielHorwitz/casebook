"use strict";

// --- routing ---------------------------------------------------------------
// Each case is its own page (/case/<id>); the cases list is the home page (/).
// Browser tabs do the multiplexing — there are no in-app tabs.
function parseRoute() {
  const match = location.pathname.match(/^\/case\/(.+)$/);
  if (match) return { mode: "case", caseId: decodeURIComponent(match[1]) };
  return { mode: "home", caseId: null };
}
const route = parseRoute();

// --- state ----------------------------------------------------------------
const state = {
  ws: null,
  activeCase: route.caseId, // the case this page is scoped to (null on home)
  agents: new Map(), // agent_id -> {agent_id, case_id, label, backend, model, state, live}
  transcripts: new Map(), // agent_id -> [item]
  models: new Map(), // agent_id -> {available: [{model_id, name}], current}
  usage: new Map(), // agent_id -> {used, size, total_tokens, cost_amount, cost_currency}
  panes: new Map(), // agent_id -> {root, transcript, input, sendBtn, cancelBtn, stateEl}
  focusedAgent: null, // agent_id of the keyboard-focused session pane
  focusedCase: null, // case_id of the keyboard-focused case (home page)
  cases: [], // case summaries shown on the home page
  hotkeyByKey: new Map(), // KeyboardEvent.key -> action name
  widths: [], // configured session-column widths the resize hotkey cycles
  widthIndex: -1,
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
  if (event.type === "snapshot") return applySnapshot(event);
  if (route.mode === "home") {
    // The home page only tracks the case list; session events belong to pages.
    if (event.type === "case_created" || event.type === "case_deleted") loadCases();
    return;
  }
  // A case page whose case was deleted (elsewhere) returns to the home page.
  if (event.type === "case_deleted" && event.case_id === route.caseId) {
    location.href = "/";
    return;
  }
  // A case page ignores everything that isn't about its own case.
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
      const u = state.usage.get(event.agent_id) || {};
      for (const k of ["used", "size", "input_tokens", "output_tokens", "total_tokens", "cost_amount", "cost_currency"]) {
        if (event[k] != null) u[k] = event[k];
      }
      state.usage.set(event.agent_id, u);
      return renderUsage(event.agent_id);
    }
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

// Handles both agent_added and agent_updated (e.g. live <-> stored transitions).
// A pane is built only for an open (live) session; closed ones live in the
// sidebar list and take no pane space until reopened.
function upsertAgent(agent) {
  if (route.mode !== "case" || agent.case_id !== route.caseId) return;
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

// Drop a session's pane from the main area but keep its state and transcript so
// reopening it restores the history.
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
      <div class="agent-head-title"><span class="label"></span></div>
      <div class="agent-head-controls">
        <span class="state"></span>
        <select class="model" title="model" hidden></select>
        <label class="allow" title="auto-allow this session's permission requests"><input type="checkbox" /> allow</label>
        <button class="rename" title="rename session">✎</button>
        <button class="autoname" title="name session with the model">✨</button>
        <button class="resume" hidden>Resume</button>
        <button class="close" title="close session (keep history)">×</button>
        <button class="delete" title="delete session and history">🗑</button>
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

function fmtTokens(n) {
  if (n == null) return null;
  if (n >= 1e6) return (n / 1e6).toFixed(1) + "M";
  if (n >= 1e3) return (n / 1e3).toFixed(1) + "k";
  return String(n);
}

function renderUsage(agentId) {
  const pane = state.panes.get(agentId);
  if (!pane) return;
  const u = state.usage.get(agentId);
  const parts = [];
  if (u) {
    if (u.used != null && u.size != null) {
      const pct = u.size ? Math.round((u.used / u.size) * 100) : 0;
      parts.push(`context ${fmtTokens(u.used)}/${fmtTokens(u.size)} (${pct}%)`);
    } else if (u.used != null) {
      parts.push(`context ${fmtTokens(u.used)}`);
    }
    if (u.total_tokens != null) parts.push(`${fmtTokens(u.total_tokens)} tokens`);
    if (u.cost_amount != null) parts.push(`${u.cost_currency || ""} ${u.cost_amount.toFixed(2)}`.trim());
  }
  pane.usageEl.textContent = parts.join("  ·  ");
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
    // User text is shown verbatim; everything the model emits is markdown.
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

// All sessions of this case, in stable insertion order (live and closed alike).
function sessionIds() {
  return [...state.agents.keys()];
}

// The sidebar Sessions list is the source of truth for every session; the main
// area mirrors only the open (live) ones as panes.
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
      `<button class="rename" title="rename">✎</button>` +
      `<button class="trash" title="delete session and history">🗑</button>`;
    li.querySelector(".name").textContent = agent.label;
    li.querySelector(".open").onclick = () => activateSession(agentId);
    li.querySelector(".rename").onclick = () => sessionRename(agentId);
    li.querySelector(".trash").onclick = () => sessionDelete(agentId);
    list.appendChild(li);
  }
}

// Clicking a session focuses its pane (if open) or opens it (if closed).
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

// Mark the focused session in the sidebar and (if open) its pane, and show a
// hint when nothing is open in the main area.
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

// Focus moves between sessions on a case page, or between cases on home — the
// same hotkeys, scoped to whatever the page shows.
function focusStep(delta) {
  if (route.mode === "home") return focusCaseStep(delta);
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
  caseUrl(summary.case_id) && (location.href = caseUrl(summary.case_id));
}

function caseUrl(caseId) {
  return `/case/${encodeURIComponent(caseId)}`;
}

async function deleteCase(caseId, title) {
  if (!caseId) return;
  if (!confirm(`Delete case "${title || caseId}" and all its sessions? This cannot be undone.`)) return;
  await fetch(`/api/cases/${encodeURIComponent(caseId)}`, { method: "DELETE" });
  loadCases();
}

function deleteFocusedCase() {
  const li = document.querySelector(`#case-list li[data-case-id="${CSS.escape(state.focusedCase || "")}"]`);
  const title = li ? li.querySelector(".case-title-row").textContent : "";
  deleteCase(state.focusedCase, title);
}

// Enter: open the focused case (home), or — on a case page — focus the open
// session's composer, or open the focused session if it's closed.
function openFocused() {
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
  const id = state.focusedAgent;
  const agent = id && state.agents.get(id);
  switch (action) {
    case "new_case": return newCase();
    // "new" and "delete" reuse the same keys on both pages: on home they act on
    // cases, on a case page on sessions.
    case "new_session": return route.mode === "case" ? newSession() : newCase();
    case "delete_session": if (route.mode === "home") return deleteFocusedCase(); break;
    case "home": return route.mode === "case" ? (location.href = "/") : undefined;
    case "focus_next": return focusStep(1);
    case "focus_prev": return focusStep(-1);
    case "open_focused": return openFocused();
    case "cycle_width": return cycleWidth();
    case "cancel_turn": return cancelTurn();
    case "help": return toggleHelp();
  }
  if (route.mode !== "case" || !agent) return; // session actions need a focused session
  switch (action) {
    case "rename_session": return sessionRename(id);
    case "name_session": return send({ action: "name_agent", agent_id: id });
    case "resume_session": if (!agent.live) send({ action: "resume_agent", agent_id: id }); return;
    case "close_session": if (agent.live) send({ action: "close_agent", agent_id: id }); return;
    case "delete_session": return sessionDelete(id);
    case "toggle_allow": return sessionToggleAllow(id);
  }
}

// Stop a running turn — the focused session if it's working, otherwise whatever
// is running (so a long tool call can be stopped even if focus has moved).
function cancelTurn() {
  if (route.mode !== "case") return;
  const working = [...state.agents.values()]
    .filter((a) => a.live && (a.state === "working" || a.state === "starting"))
    .map((a) => a.agent_id);
  if (working.length === 0) return;
  const targets = working.includes(state.focusedAgent) ? [state.focusedAgent] : working;
  for (const id of targets) send({ action: "cancel", agent_id: id });
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
    // Leave the composer and return to keyboard navigation.
    if (isTyping()) return document.activeElement.blur();
  }
  if (isTyping()) return;
  const action = state.hotkeyByKey.get(event.key);
  if (!action) return;
  event.preventDefault();
  runAction(action);
}

async function loadHotkeys() {
  const map = await fetch("/api/hotkeys").then((r) => r.json());
  // A binding may be a single key or a list of keys.
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

// Apply configurable session-column sizing as CSS variables.
async function loadUi() {
  const ui = await fetch("/api/ui").then((r) => r.json());
  const style = document.documentElement.style;
  if (ui.session_min_width) style.setProperty("--session-min-width", ui.session_min_width);
  if (ui.session_max_width) style.setProperty("--session-max-width", ui.session_max_width);
  state.widths = Array.isArray(ui.session_widths) ? ui.session_widths : [];
  // A previously chosen width (this browser) wins over the configured default.
  const saved = localStorage.getItem("casebook.sessionWidth");
  const width = saved || ui.session_width;
  if (width) style.setProperty("--session-width", width);
  state.widthIndex = state.widths.indexOf(width);
}

// Cycle the session-column width through the configured list (resize hotkey).
function cycleWidth() {
  if (!state.widths || state.widths.length === 0) return;
  state.widthIndex = (state.widthIndex + 1 + state.widths.length) % state.widths.length;
  const width = state.widths[state.widthIndex];
  document.documentElement.style.setProperty("--session-width", width);
  localStorage.setItem("casebook.sessionWidth", width);
  toast(`Session width: ${width}`);
}

// --- cases (home page) ----------------------------------------------------
// The sidebar is a compact title-only list; focusing a case shows its details in
// the main view.
async function loadCases() {
  state.cases = await fetch("/api/cases").then((r) => r.json());
  const list = el("case-list");
  list.replaceChildren();
  for (const c of state.cases) {
    const li = document.createElement("li");
    li.dataset.caseId = c.case_id;
    li.className = "case-item";
    // A real link, so middle-/ctrl-click opens the case in a new browser tab; a
    // plain click just focuses it (details show in the main view).
    const link = document.createElement("a");
    link.className = "open";
    link.href = caseUrl(c.case_id);
    link.title = c.title;
    link.textContent = c.title;
    link.onclick = (e) => {
      if (e.metaKey || e.ctrlKey || e.shiftKey) return; // let the browser open a tab
      e.preventDefault();
      focusCase(c.case_id);
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
  const summary = state.cases.find((c) => c.case_id === caseId);
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
  ].filter(Boolean).join("  ·  ");
  el("cd-id").textContent = caseId;
  el("cd-keywords").innerHTML = (summary.keywords || []).map((k) => `<span class="kw">${k}</span>`).join("");
  el("cd-files").innerHTML = "";
  el("cd-sessions").innerHTML = "";
  // Enrich with files + sessions (drop the result if focus moved on).
  const token = ++caseDetailToken;
  const detail = await fetch(`/api/cases/${encodeURIComponent(caseId)}`).then((r) => r.json()).catch(() => null);
  if (token !== caseDetailToken || !detail) return;
  if ((detail.files || []).length) {
    el("cd-files").innerHTML = "<h4>Files</h4>" + detail.files.map((f) => `<span class="file">${f}</span>`).join("");
  }
  if ((detail.agents || []).length) {
    el("cd-sessions").innerHTML = "<h4>Sessions</h4>" +
      detail.agents.map((a) => `<div class="cd-session">${a.label} <span class="muted">(${a.live ? a.state : "closed"})</span></div>`).join("");
  }
}

// --- case page ------------------------------------------------------------
async function openCaseView(caseId) {
  const detail = await fetch(`/api/cases/${caseId}`).then((r) => r.json()).catch(() => null);
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
  const text = await fetch(`/api/cases/${state.activeCase}/files/${encodeURIComponent(name)}`).then((r) => r.text());
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

function applyRoute() {
  const home = route.mode === "home";
  document.body.classList.toggle("home", home);
  document.body.classList.toggle("case", !home);
  el("cases-nav").hidden = !home;
  el("case-nav").hidden = home;
  el("agents").hidden = home;
  el("case-detail").hidden = true; // shown on the home page when a case is focused
  el("placeholder").hidden = !home;
  el("back-cases").hidden = home;
  // The brand is the home heading; a case page leads with the back button + title.
  document.querySelector(".brand").hidden = !home;
  el("case-title").hidden = home;
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

applyRoute();
loadHotkeys();
loadUi();
connect();
if (route.mode === "home") {
  loadCases();
} else {
  loadBackends();
  openCaseView(route.caseId);
}
