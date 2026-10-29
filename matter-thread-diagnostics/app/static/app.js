/**
 * Frontend logic for Matter & Thread AI Diagnostics
 * Handles Home Assistant Ingress base path, live telemetry, SVG topology, and AI streaming.
 */

// Determine Ingress base URL
const BASE_URL = window.location.pathname.endsWith('/')
  ? window.location.pathname.slice(0, -1)
  : window.location.pathname;

function apiPath(endpoint) {
  const cleanEndpoint = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
  return `${BASE_URL}${cleanEndpoint}`;
}

let currentTelemetry = null;

document.addEventListener("DOMContentLoaded", () => {
  initTabs();
  initSettingsForm();
  initPasswordToggles();
  fetchStatus();
  fetchLiveDiagnostics();
  initTopology();

  document.getElementById("btn-refresh").addEventListener("click", () => {
    fetchStatus();
    fetchLiveDiagnostics();
  });

  document.getElementById("btn-open-settings").addEventListener("click", () => {
    activateTab("tab-settings");
  });

  document.getElementById("btn-run-ai").addEventListener("click", () => {
    runAIDiagnosis(false);
  });

  document.getElementById("btn-run-sample").addEventListener("click", () => {
    runAIDiagnosis(true);
  });

  document.getElementById("btn-analyze-manual").addEventListener("click", () => {
    runManualLogAnalysis();
  });
});

/* Tabs Management */
function initTabs() {
  const tabButtons = document.querySelectorAll(".tab-btn");
  tabButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      const targetId = btn.getAttribute("data-tab");
      activateTab(targetId);
    });
  });
}

function activateTab(tabId) {
  document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
  document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));

  const targetBtn = document.querySelector(`.tab-btn[data-tab="${tabId}"]`);
  const targetContent = document.getElementById(tabId);
  if (targetBtn) targetBtn.classList.add("active");
  if (targetContent) targetContent.classList.add("active");

  if (tabId === "tab-topology") {
    fetchAndRenderTopology();
  }
}

/* API: Status & Configuration */
async function fetchStatus() {
  const badge = document.getElementById("ai-status-badge");
  try {
    const res = await fetch(apiPath("/api/status"));
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    const provider = data.ai_provider || "gemini";
    const hasKey = (provider === "gemini" && data.has_gemini_key) ||
                    (provider === "openai" && data.has_openai_key) ||
                    (provider === "anthropic" && data.has_anthropic_key);

    if (hasKey) {
      badge.className = "badge badge-success";
      badge.innerHTML = `<i class="fa-solid fa-check"></i> ${data.ai_model || provider} Active`;
    } else {
      badge.className = "badge badge-warning";
      badge.innerHTML = `<i class="fa-solid fa-key"></i> Key Required (${provider})`;
    }

    // Pre-populate settings form
    const providerSelect = document.getElementById("cfg-provider");
    if (providerSelect) {
      providerSelect.value = provider;
      toggleKeyInputs(provider);
    }
    const modelInput = document.getElementById("cfg-model");
    if (modelInput && data.ai_model) modelInput.value = data.ai_model;
  } catch (err) {
    badge.className = "badge badge-danger";
    badge.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> Server Error`;
    console.error("Status fetch error:", err);
  }
}

function initSettingsForm() {
  const providerSelect = document.getElementById("cfg-provider");
  if (providerSelect) {
    providerSelect.addEventListener("change", (e) => {
      toggleKeyInputs(e.target.value);
    });
  }

  const form = document.getElementById("settings-form");
  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const statusText = document.getElementById("settings-save-status");
      statusText.innerText = "Saving...";

      const payload = {
        ai_provider: document.getElementById("cfg-provider").value,
        ai_model: document.getElementById("cfg-model").value,
        gemini_api_key: document.getElementById("cfg-gemini-key").value || undefined,
        openai_api_key: document.getElementById("cfg-openai-key").value || undefined,
        anthropic_api_key: document.getElementById("cfg-anthropic-key").value || undefined,
        matter_server_url: document.getElementById("cfg-matter-url").value || undefined,
      };

      try {
        const res = await fetch(apiPath("/api/config"), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        if (res.ok) {
          statusText.innerText = "✓ Saved successfully!";
          setTimeout(() => { statusText.innerText = ""; }, 3000);
          fetchStatus();
        } else {
          statusText.innerText = "Failed to save.";
        }
      } catch (err) {
        statusText.innerText = "Error saving settings.";
        console.error(err);
      }
    });
  }
}

function toggleKeyInputs(provider) {
  document.getElementById("group-gemini-key").classList.toggle("hidden", provider !== "gemini");
  document.getElementById("group-openai-key").classList.toggle("hidden", provider !== "openai");
  document.getElementById("group-anthropic-key").classList.toggle("hidden", provider !== "anthropic");

  const modelSelect = document.getElementById("cfg-model");
  if (modelSelect) {
    if (provider === "gemini") {
      modelSelect.innerHTML = `
        <option value="gemini-2.0-flash">Gemini 2.0 Flash (Recommended - Fastest)</option>
        <option value="gemini-1.5-flash">Gemini 1.5 Flash</option>
        <option value="gemini-1.5-pro">Gemini 1.5 Pro</option>
      `;
    } else if (provider === "openai") {
      modelSelect.innerHTML = `
        <option value="gpt-4o">GPT-4o (Recommended)</option>
        <option value="gpt-4o-mini">GPT-4o-mini</option>
      `;
    } else if (provider === "anthropic") {
      modelSelect.innerHTML = `
        <option value="claude-3-5-sonnet-20241022">Claude 3.5 Sonnet (Recommended)</option>
        <option value="claude-3-5-haiku-20241022">Claude 3.5 Haiku</option>
      `;
    }
  }
}

function initPasswordToggles() {
  document.querySelectorAll(".btn-toggle-pw").forEach(btn => {
    btn.addEventListener("click", () => {
      const targetId = btn.getAttribute("data-target");
      const input = document.getElementById(targetId);
      if (input.type === "password") {
        input.type = "text";
        btn.innerHTML = `<i class="fa-solid fa-eye-slash"></i>`;
      } else {
        input.type = "password";
        btn.innerHTML = `<i class="fa-solid fa-eye"></i>`;
      }
    });
  });
}

/* API: Telemetry & Rules */
async function fetchLiveDiagnostics() {
  try {
    const res = await fetch(apiPath("/api/diagnostics/collect"));
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    currentTelemetry = data;
    renderKPIs(data);
    renderRulesTab(data);
  } catch (err) {
    console.error("Failed to load telemetry:", err);
  }
}

function renderKPIs(data) {
  const rules = data.rule_evaluations || {};

  // 1. Health Index
  const score = data.summary_score !== undefined ? data.summary_score : 100;
  const scoreElem = document.getElementById("health-score");
  const scoreDesc = document.getElementById("health-desc");
  scoreElem.innerText = score;
  if (score >= 80) {
    scoreElem.style.color = "var(--color-success)";
    scoreDesc.innerText = "Optimal mesh operation";
  } else if (score >= 50) {
    scoreElem.style.color = "var(--color-warning)";
    scoreDesc.innerText = "Degraded performance";
  } else {
    scoreElem.style.color = "var(--color-danger)";
    scoreDesc.innerText = "Action required (Packet loss/Split)";
  }

  // 2. Border Router Sync
  const splitRule = rules.split_network || {};
  const splitElem = document.getElementById("split-status");
  const splitDesc = document.getElementById("split-desc");
  if (splitRule.is_split_network) {
    splitElem.innerHTML = `<span class="badge badge-danger">Split Mesh</span>`;
    splitDesc.innerText = `${splitRule.distinct_network_count} independent PANs`;
  } else {
    splitElem.innerHTML = `<span class="badge badge-success">In Sync</span>`;
    splitDesc.innerText = "Single unified Extended PAN";
  }

  // 3. RF Coexistence
  const rfRule = rules.rf_coexistence || {};
  const rfElem = document.getElementById("rf-status");
  const rfDesc = document.getElementById("rf-desc");
  const ch = rfRule.thread_channel || "--";
  if (rfRule.severity === "HIGH") {
    rfElem.innerHTML = `<span class="badge badge-danger">Ch ${ch} (Conflict)</span>`;
    rfDesc.innerText = rfRule.overlapping_wifi_channel ? `Overlaps Wi-Fi Ch ${rfRule.overlapping_wifi_channel}` : "High RF overlap";
  } else if (rfRule.severity === "MINIMAL" || ch === 25) {
    rfElem.innerHTML = `<span class="badge badge-success">Ch ${ch} (Clean)</span>`;
    rfDesc.innerText = "Clear of 2.4GHz Wi-Fi";
  } else {
    rfElem.innerHTML = `<span class="badge badge-info">Ch ${ch}</span>`;
    rfDesc.innerText = rfRule.severity || "Standard";
  }

  // 4. IPv6
  const ipv6Rule = rules.ipv6_routing || {};
  const ipv6Elem = document.getElementById("ipv6-status");
  const ipv6Desc = document.getElementById("ipv6-desc");
  if (ipv6Rule.has_thread_ula_route) {
    ipv6Elem.innerHTML = `<span class="badge badge-success">Active ULA</span>`;
    ipv6Desc.innerText = "Kernel route present";
  } else {
    ipv6Elem.innerHTML = `<span class="badge badge-warning">Missing Route</span>`;
    ipv6Desc.innerText = "No ULA fd00::/8 found";
  }
}

function renderRulesTab(data) {
  const rules = data.rule_evaluations || {};

  // Rule 1: Split Mesh
  const split = rules.split_network || {};
  const splitBadge = document.getElementById("rule-badge-split");
  splitBadge.className = split.is_split_network ? "badge badge-danger" : "badge badge-success";
  splitBadge.innerText = split.is_split_network ? "CRITICAL: Split" : "PASS";
  document.getElementById("rule-text-split").innerText = split.summary || "";
  const splitDetail = document.getElementById("split-networks-detail");
  if (split.networks) {
    splitDetail.innerHTML = Object.entries(split.networks).map(([xpan, routers]) => `
      <div style="margin-bottom: 6px;">
        <strong>Ext PAN ID: ${xpan}</strong>
        ${routers.map(r => `<div>• ${r.name || 'Border Router'} (Channel: ${r.channel || 'N/A'})</div>`).join('')}
      </div>
    `).join('');
  }

  // Rule 2: RF Coexistence
  const rf = rules.rf_coexistence || {};
  const rfBadge = document.getElementById("rule-badge-rf");
  rfBadge.className = rf.severity === "HIGH" ? "badge badge-danger" : (rf.severity === "MINIMAL" ? "badge badge-success" : "badge badge-warning");
  rfBadge.innerText = rf.severity || "UNKNOWN";
  document.getElementById("rule-text-rf").innerText = rf.recommendation || rf.interference_description || "";

  // Rule 3: IPv6
  const ipv6 = rules.ipv6_routing || {};
  const ipv6Badge = document.getElementById("rule-badge-ipv6");
  ipv6Badge.className = ipv6.has_thread_ula_route ? "badge badge-success" : "badge badge-warning";
  ipv6Badge.innerText = ipv6.status || "UNKNOWN";
  document.getElementById("rule-text-ipv6").innerText = ipv6.summary || "";
  const routesBox = document.getElementById("ipv6-routes-detail");
  if (ipv6.sample_routes) {
    routesBox.innerHTML = ipv6.sample_routes.map(r => `<div>${r}</div>`).join('');
  }

  // Rule 4: Nodes
  const nq = rules.node_quality || {};
  const nqBadge = document.getElementById("rule-badge-nodes");
  nqBadge.className = nq.offline_count > 0 ? "badge badge-danger" : (nq.weak_count > 0 ? "badge badge-warning" : "badge badge-success");
  nqBadge.innerText = `${nq.healthy_count || 0}/${nq.total_nodes || 0} Online`;
  document.getElementById("rule-text-nodes").innerText = nq.summary || "";
  const nodesDetail = document.getElementById("nodes-detail-list");
  let nodeHtml = "";
  if (nq.offline_nodes && nq.offline_nodes.length > 0) {
    nodeHtml += nq.offline_nodes.map(n => `<div style="color:var(--color-danger)">🔴 Node ${n.node_id} (${n.name}) - ${n.reason}</div>`).join('');
  }
  if (nq.weak_nodes && nq.weak_nodes.length > 0) {
    nodeHtml += nq.weak_nodes.map(n => `<div style="color:var(--color-warning)">⚠️ Node ${n.node_id} (${n.name}) - ${n.reason}</div>`).join('');
  }
  if (!nodeHtml) {
    nodeHtml = `<div style="color:var(--color-success)">🟢 All commissioned nodes responding with healthy signal strength.</div>`;
  }
  nodesDetail.innerHTML = nodeHtml;
}

/* AI Diagnostics Execution */
async function runAIDiagnosis(useMock = false) {
  const loading = document.getElementById("ai-loading-indicator");
  const resultsCard = document.getElementById("ai-results-container");
  const reportBody = document.getElementById("ai-report-body");
  const userNotes = document.getElementById("user-symptoms").value;

  loading.classList.remove("hidden");
  resultsCard.classList.add("hidden");

  try {
    const res = await fetch(apiPath("/api/diagnostics/analyze"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_notes: userNotes,
        force_mock: useMock
      })
    });

    const data = await res.json();
    loading.classList.add("hidden");
    resultsCard.classList.remove("hidden");

    if (data.ai_result && data.ai_result.success) {
      document.getElementById("report-model-badge").innerText = `${data.ai_result.provider.toUpperCase()} (${data.ai_result.model})`;
      reportBody.innerHTML = marked.parse(data.ai_result.analysis);
      // Refresh KPIs if mock was used
      if (useMock && data.telemetry) {
        renderKPIs(data.telemetry);
        renderRulesTab(data.telemetry);
      }
    } else {
      const errMsg = (data.ai_result && data.ai_result.error) || "AI diagnosis could not be completed.";
      reportBody.innerHTML = `
        <div class="badge badge-danger" style="margin-bottom: 12px;"><i class="fa-solid fa-triangle-exclamation"></i> Error</div>
        <p>${errMsg}</p>
        <p style="margin-top: 10px;">Please open the <strong>Settings & API Keys</strong> tab and ensure your API key is correctly configured.</p>
      `;
    }
  } catch (err) {
    loading.classList.add("hidden");
    resultsCard.classList.remove("hidden");
    reportBody.innerHTML = `<p style="color:var(--color-danger)">Network error: ${err.message}</p>`;
  }
}

async function runManualLogAnalysis() {
  const logContent = document.getElementById("manual-log-input").value.trim();
  if (!logContent) {
    alert("Please paste some diagnostic logs or JSON first.");
    return;
  }

  activateTab("tab-ai");
  const loading = document.getElementById("ai-loading-indicator");
  const resultsCard = document.getElementById("ai-results-container");
  const reportBody = document.getElementById("ai-report-body");

  loading.classList.remove("hidden");
  resultsCard.classList.add("hidden");

  try {
    const res = await fetch(apiPath("/api/manual/analyze"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ log_content: logContent })
    });

    const data = await res.json();
    loading.classList.add("hidden");
    resultsCard.classList.remove("hidden");

    if (data.ai_result && data.ai_result.success) {
      document.getElementById("report-model-badge").innerText = "Manual Log Analysis";
      reportBody.innerHTML = marked.parse(data.ai_result.analysis);
    } else {
      reportBody.innerHTML = `<p style="color:var(--color-danger)">${data.ai_result?.error || 'Analysis failed'}</p>`;
    }
  } catch (err) {
    loading.classList.add("hidden");
    resultsCard.classList.remove("hidden");
    reportBody.innerHTML = `<p style="color:var(--color-danger)">Error: ${err.message}</p>`;
  }
}

/* Topology Graph (SVG Interactive Mesh) */
function initTopology() {
  // Container setup
}

async function fetchAndRenderTopology() {
  try {
    const res = await fetch(apiPath("/api/topology"));
    if (!res.ok) return;
    const data = await res.json();
    renderSvgTopology(data.nodes || [], data.edges || []);
  } catch (err) {
    console.error("Topology fetch failed:", err);
  }
}

function renderSvgTopology(nodes, edges) {
  const svg = document.getElementById("mesh-svg");
  svg.innerHTML = "";

  const width = svg.clientWidth || 800;
  const height = 450;
  const cx = width / 2;
  const cy = height / 2;

  // Position nodes radially
  const nodeMap = {};
  const total = nodes.length;
  nodes.forEach((n, idx) => {
    let x, y;
    if (n.type === "border_router") {
      x = idx === 0 ? cx - 120 : cx + 120;
      y = cy - 40;
    } else {
      const angle = (idx / (total - 1)) * 2 * Math.PI;
      const radius = 170;
      x = cx + radius * Math.cos(angle);
      y = cy + radius * Math.sin(angle);
    }
    nodeMap[n.id] = { ...n, x, y };
  });

  // Render edges
  edges.forEach(e => {
    const src = nodeMap[e.source];
    const tgt = nodeMap[e.target];
    if (!src || !tgt) return;

    const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
    line.setAttribute("x1", src.x);
    line.setAttribute("y1", src.y);
    line.setAttribute("x2", tgt.x);
    line.setAttribute("y2", tgt.y);

    let strokeColor = "#10b981";
    if (e.status === "warning") strokeColor = "#f59e0b";
    if (tgt.status === "offline") strokeColor = "#ef4444";

    line.setAttribute("stroke", strokeColor);
    line.setAttribute("stroke-width", "2");
    line.setAttribute("stroke-dasharray", tgt.status === "offline" ? "4,4" : "none");
    line.setAttribute("opacity", "0.7");
    svg.appendChild(line);

    // Label
    if (e.label) {
      const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
      text.setAttribute("x", (src.x + tgt.x) / 2);
      text.setAttribute("y", (src.y + tgt.y) / 2 - 4);
      text.setAttribute("fill", "#9ca3af");
      text.setAttribute("font-size", "10");
      text.setAttribute("text-anchor", "middle");
      text.textContent = e.label;
      svg.appendChild(text);
    }
  });

  // Render nodes
  Object.values(nodeMap).forEach(n => {
    const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
    g.style.cursor = "pointer";

    let fillColor = "#10b981"; // Router
    let r = 18;
    if (n.type === "border_router") {
      fillColor = "#3b82f6";
      r = 24;
    } else if (n.type === "end_device") {
      fillColor = "#8b5cf6";
      r = 16;
    }

    if (n.status === "weak") fillColor = "#f59e0b";
    if (n.status === "offline") fillColor = "#ef4444";

    const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    circle.setAttribute("cx", n.x);
    circle.setAttribute("cy", n.y);
    circle.setAttribute("r", r);
    circle.setAttribute("fill", fillColor);
    circle.setAttribute("stroke", "#ffffff");
    circle.setAttribute("stroke-width", "2");
    g.appendChild(circle);

    const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
    label.setAttribute("x", n.x);
    label.setAttribute("y", n.y + r + 14);
    label.setAttribute("fill", "#ffffff");
    label.setAttribute("font-size", "11");
    label.setAttribute("font-weight", "600");
    label.setAttribute("text-anchor", "middle");
    label.textContent = n.label.length > 20 ? n.label.slice(0, 18) + '...' : n.label;
    g.appendChild(label);

    g.addEventListener("click", () => {
      showNodeInspector(n);
    });

    svg.appendChild(g);
  });
}

function showNodeInspector(node) {
  const panel = document.getElementById("node-inspector");
  const title = document.getElementById("inspector-title");
  const content = document.getElementById("inspector-content");

  panel.classList.remove("hidden");
  title.innerText = `Node: ${node.label} (${node.type})`;
  content.innerHTML = `
    <div style="font-size: 13px; line-height: 1.6;">
      <div><strong>Status:</strong> <span class="badge badge-${node.status === 'online' ? 'success' : (node.status === 'weak' ? 'warning' : 'danger')}">${node.status.toUpperCase()}</span></div>
      <div><strong>Role:</strong> ${node.type === 'border_router' ? 'Thread Border Router' : (node.type === 'end_device' ? 'Battery Sleepy End Device (ICD)' : 'Mains-Powered Thread Router')}</div>
      <div><strong>Telemetry:</strong> ${node.details || 'N/A'}</div>
      <div style="margin-top: 8px; color: var(--text-muted); font-size: 12px;">Tip: For battery devices with weak signal (< -82 dBm), add an Eve Energy smart plug or mains-powered Thread bulb midway.</div>
    </div>
  `;
}
