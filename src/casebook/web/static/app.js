"use strict";

// --- state ----------------------------------------------------------------
const state = {
  ws: null,
  activeCase: null,
  agents: new Map(), // agent_id -> {agent_id, case_id, label, backend, state}
  transcripts: new Map(), // agent_id -> [item]
  panes: new Map(), // agent_id -> {root, transcript, input, sendBtn, cancelBtn, stateEl}
};

const el = (id) => document.getElementById(id);

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
  }
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
      return addAgent(event);
    case "agent_removed":
      return removeAgent(event.agent_id);
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
  for (const [agentId, pane] of state.panes) pane.root.remove();
  state.panes.clear();
  for (const agent of snapshot.agents) addAgent(agent);
  for (const [agentId, events] of Object.entries(snapshot.transcripts || {})) {
    for (const event of events) applyToTranscript(event);
  }
}

function addAgent(agent) {
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
      <span class="state"></span>
      <button class="remove" title="remove agent">×</button>
    </div>
    <div class="transcript"></div>
    <div class="composer">
      <textarea rows="1" placeholder="Message this agent…"></textarea>
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
  root.querySelector(".remove").onclick = () => send({ action: "remove_agent", agent_id: agent.agent_id });

  const pane = {
    root,
    transcript: root.querySelector(".transcript"),
    input,
    sendBtn,
    cancelBtn,
    stateEl: root.querySelector(".state"),
    labelEl: root.querySelector(".label"),
  };
  state.panes.set(agent.agent_id, pane);
  applyPaneVisibility();
  renderTranscript(agent.agent_id);
}

function updateHead(agentId) {
  const pane = state.panes.get(agentId);
  const agent = state.agents.get(agentId);
  if (!pane || !agent) return;
  pane.labelEl.textContent = `${agent.label}  ·  ${agent.backend || ""}`;
  const working = agent.state === "working" || agent.state === "starting";
  pane.stateEl.textContent = agent.state || "";
  pane.stateEl.className = "state" + (working ? " working" : "");
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
    node.appendChild(document.createTextNode(item.text));
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
  }
  const hasCase = state.activeCase !== null;
  el("add-agent").hidden = !hasCase;
  el("placeholder").hidden = hasCase;
  el("case-meta").hidden = !hasCase;
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

// --- wiring ---------------------------------------------------------------
el("add-agent").onclick = () => {
  if (state.activeCase) send({ action: "add_agent", case_id: state.activeCase });
};
el("file-modal-close").onclick = () => (el("file-modal").hidden = true);
el("file-modal").onclick = (e) => {
  if (e.target.id === "file-modal") el("file-modal").hidden = true;
};

loadCases();
connect();
