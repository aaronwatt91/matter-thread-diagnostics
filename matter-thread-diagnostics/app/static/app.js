/**
 * Frontend logic for Matter & Thread AI Diagnostics v2.0.1
 * Handles Home Assistant Ingress base path, live multi-protocol network scanning
 * (mDNS _meshcop._udp, HA Thread TLV, Matter Cluster 0x0035, OTBR, IPv6 pings),
 * instant AI provider/model switching, interactive Cluster 0x0035 tables, and SVG topology.
 */

const BASE_URL = window.location.pathname.endsWith('/')
  ? window.location.pathname.slice(0, -1)
  : window.location.pathname;

function apiPath(endpoint) {
  const cleanEndpoint = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
  return `${BASE_URL}${cleanEndpoint}`;
}

let currentTelemetry = null;
let availableThreadNetworks = [];
let currentNodeSearchQuery = "";
let currentNodeRoleFilter = "all";
let topologyPhysicsState = {
  animFrameId: null,
  nodes: [],
  edges: [],
  zoom: 1.0,
  panX: 0,
  panY: 0,
  energy: 1.0,
  layoutMode: "force",
  colorMode: "role",
  filterMode: "all",
  showLinkLabels: true,
  affinityData: null,
};

const MODEL_OPTIONS_BY_PROVIDER = {
  gemini: [
    { value: "gemini-2.5-flash", label: "Gemini 2.5 Flash (Recommended / Fast)" },
    { value: "gemini-2.5-pro", label: "Gemini 2.5 Pro" },
    { value: "gemini-3-flash-preview", label: "Gemini 3 Flash Preview" },
    { value: "gemini-3.8-flash", label: "Gemini 3.8 Flash (Auto-resolves via ListModels)" },
  ],
  openai: [
    { value: "gpt-4o", label: "GPT-4o (Recommended)" },
    { value: "gpt-4o-mini", label: "GPT-4o-mini" },
    { value: "o3-mini", label: "OpenAI o3-mini" },
  ],
  anthropic: [
    { value: "claude-3-7-sonnet-latest", label: "Claude 3.7 Sonnet" },
    { value: "claude-3-5-sonnet-20241022", label: "Claude 3.5 Sonnet (Recommended)" },
    { value: "claude-3-5-haiku-20241022", label: "Claude 3.5 Haiku" },
  ],
};

document.addEventListener("DOMContentLoaded", () => {
  initTabs();
  initSettingsForm();
  initPasswordToggles();
  initTopScannerBar();
  initDeviceSearchAndTopologyControls();

  fetchStatus();
  fetchLiveDiagnostics();
  loadThreadNetworks();

  document.getElementById("btn-refresh").addEventListener("click", () => {
    scanSelectedNetwork();
  });

  document.getElementById("btn-open-settings").addEventListener("click", () => {
    activateTab("tab-settings");
  });

  document.getElementById("btn-run-ai").addEventListener("click", () => {
    runAIDiagnosis();
  });

  document.getElementById("btn-analyze-manual").addEventListener("click", () => {
    runManualLogAnalysis();
  });

  const btnLoadRaw = document.getElementById("btn-load-raw-scan");
  if (btnLoadRaw) {
    btnLoadRaw.addEventListener("click", async () => {
      const box = document.getElementById("manual-log-input");
      if (!box) return;
      box.value = "Loading full diagnostic log bundle...";
      try {
        const res = await fetch(apiPath("/api/diagnostics/logs"));
        if (res.ok) {
          const data = await res.json();
          box.value = data.bundle_text || JSON.stringify(currentTelemetry, null, 2);
          return;
        }
      } catch (_) {}
      if (currentTelemetry) {
        box.value = JSON.stringify(currentTelemetry, null, 2);
      } else {
        box.value = "No scan telemetry cached yet. Click '2. Scan Selected Network' first.";
      }
    });
  }

  ["btn-download-logs-top", "btn-download-logs-manual", "btn-download-ai-report"].forEach((btnId) => {
    const btn = document.getElementById(btnId);
    if (btn) {
      btn.addEventListener("click", () => downloadDiagnosticLogs(btn));
    }
  });

  const btnPurgeOffline = document.getElementById("btn-purge-offline-nodes");
  if (btnPurgeOffline) {
    btnPurgeOffline.addEventListener("click", () => triggerBulkPurgeOfflineNodes(btnPurgeOffline));
  }

  const btnRefreshChannel = document.getElementById("btn-refresh-channel-status");
  if (btnRefreshChannel) {
    btnRefreshChannel.addEventListener("click", () => fetchOtbrChannelInfo(true));
  }

  const btnApplyChannel = document.getElementById("btn-apply-channel-change");
  if (btnApplyChannel) {
    btnApplyChannel.addEventListener("click", () => triggerChannelChange());
  }

  const btnRefreshJoinable = document.getElementById("btn-refresh-joinable-networks");
  if (btnRefreshJoinable) {
    btnRefreshJoinable.addEventListener("click", () => fetchJoinableNetworks(true));
  }

  const selectTargetJoin = document.getElementById("select-target-join-network");
  if (selectTargetJoin) {
    selectTargetJoin.addEventListener("change", (e) => onJoinNetworkSelectChange(e.target.value));
  }

  const btnExecuteJoin = document.getElementById("btn-execute-join-network");
  if (btnExecuteJoin) {
    btnExecuteJoin.addEventListener("click", () => triggerJoinNetwork());
  }

  const btnRefreshTopo = document.getElementById("btn-refresh-topology");
  if (btnRefreshTopo) {
    btnRefreshTopo.addEventListener("click", async () => {
      btnRefreshTopo.disabled = true;
      btnRefreshTopo.innerHTML = `<i class="fa-solid fa-arrows-rotate fa-spin"></i> Scanning Mesh...`;
      await scanSelectedNetwork(false);
      btnRefreshTopo.innerHTML = `<i class="fa-solid fa-check"></i> Scanned!`;
      setTimeout(() => {
        btnRefreshTopo.disabled = false;
        btnRefreshTopo.innerHTML = `<i class="fa-solid fa-arrows-rotate"></i> Rescan Topology`;
      }, 1000);
    });
  }
});

/* Top Scanner Bar & Synced Network Selectors */
function initTopScannerBar() {
  const topSelect = document.getElementById("top-thread-network");
  const cfgSelect = document.getElementById("cfg-thread-network");

  if (topSelect) {
    topSelect.addEventListener("change", (e) => {
      const val = e.target.value;
      if (cfgSelect) cfgSelect.value = val;
      updateThreadNetworkDetails(val);
      updateSelectedNetworkStrip(val);
    });
  }

  if (cfgSelect) {
    cfgSelect.addEventListener("change", (e) => {
      const val = e.target.value;
      if (topSelect) topSelect.value = val;
      updateThreadNetworkDetails(val);
      updateSelectedNetworkStrip(val);
    });
  }

  const btnTopRefresh = document.getElementById("btn-top-refresh-nets");
  if (btnTopRefresh) {
    btnTopRefresh.addEventListener("click", () => loadThreadNetworks());
  }

  const btnCfgRefresh = document.getElementById("btn-refresh-thread-networks");
  if (btnCfgRefresh) {
    btnCfgRefresh.addEventListener("click", () => loadThreadNetworks());
  }

  const btnTopScan = document.getElementById("btn-top-scan");
  if (btnTopScan) {
    btnTopScan.addEventListener("click", () => scanSelectedNetwork(true));
  }

  const btnCfgScan = document.getElementById("btn-scan-selected-network");
  if (btnCfgScan) {
    btnCfgScan.addEventListener("click", () => scanSelectedNetwork(true));
  }

  const btnResetNetwork = document.getElementById("btn-reset-thread-network");
  if (btnResetNetwork) {
    btnResetNetwork.addEventListener("click", () => {
      if (topSelect) topSelect.value = "";
      if (cfgSelect) cfgSelect.value = "";
      updateThreadNetworkDetails("");
      updateSelectedNetworkStrip("");
      scanSelectedNetwork(true);
    });
  }

  const btnTopAi = document.getElementById("btn-top-ai");
  if (btnTopAi) {
    btnTopAi.addEventListener("click", () => {
      activateTab("tab-ai");
      runAIDiagnosis();
    });
  }
}

/* Device Search Box & Topology Physics Controls */
function initDeviceSearchAndTopologyControls() {
  const nodeSearch = document.getElementById("matter-node-search");
  const clearBtn = document.getElementById("btn-clear-node-search");
  const roleFilter = document.getElementById("matter-node-filter");
  const topoSearch = document.getElementById("topology-node-search");

  const applySearch = (val, sourceElem) => {
    currentNodeSearchQuery = (val || "").trim();
    if (nodeSearch && sourceElem !== nodeSearch) nodeSearch.value = val;
    if (topoSearch && sourceElem !== topoSearch) topoSearch.value = val;
    if (clearBtn) clearBtn.style.display = currentNodeSearchQuery ? "block" : "none";
    if (currentTelemetry) {
      renderRulesAndTables(currentTelemetry);
    }
    updateTopologySearchHighlight();
  };

  if (nodeSearch) {
    nodeSearch.addEventListener("input", (e) => applySearch(e.target.value, nodeSearch));
  }
  if (topoSearch) {
    topoSearch.addEventListener("input", (e) => applySearch(e.target.value, topoSearch));
  }
  if (clearBtn) {
    clearBtn.addEventListener("click", () => applySearch("", null));
  }
  if (roleFilter) {
    roleFilter.addEventListener("change", (e) => {
      currentNodeRoleFilter = e.target.value || "all";
      if (currentTelemetry) {
        renderRulesAndTables(currentTelemetry);
      }
    });
  }

  const btnShake = document.getElementById("btn-topology-shake");
  if (btnShake) {
    btnShake.addEventListener("click", () => {
      topologyPhysicsState.energy = 1.0;
      topologyPhysicsState.nodes.forEach((n) => {
        if (!n.dragging) {
          n.vx += (Math.random() - 0.5) * 14;
          n.vy += (Math.random() - 0.5) * 14;
        }
      });
    });
  }

  const btnResetZoom = document.getElementById("btn-topology-reset-zoom");
  if (btnResetZoom) {
    btnResetZoom.addEventListener("click", () => {
      topologyPhysicsState.zoom = 1.0;
      topologyPhysicsState.panX = 0;
      topologyPhysicsState.panY = 0;
      topologyPhysicsState.energy = Math.max(topologyPhysicsState.energy, 0.5);
    });
  }

  // Topology Layout Mode Switcher (Force, Transit, Matrix, Sankey, Radar, Sunburst, Chord)
  document.querySelectorAll(".btn-layout-mode").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".btn-layout-mode").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      const mode = btn.getAttribute("data-layout") || "force";
      topologyPhysicsState.layoutMode = mode;
      dispatchTopologyRender();
    });
  });

  // Topology Color By Selector
  const colorSelect = document.getElementById("topology-color-mode");
  if (colorSelect) {
    colorSelect.addEventListener("change", (e) => {
      topologyPhysicsState.colorMode = e.target.value || "role";
      updateTopologyNodeColors();
      updateTopologyLegend();
    });
  }

  // Topology Filter Selector
  const filterSelect = document.getElementById("topology-node-filter");
  if (filterSelect) {
    filterSelect.addEventListener("change", (e) => {
      topologyPhysicsState.filterMode = e.target.value || "all";
      applyTopologyVisibilityFilter();
    });
  }

  // Topology Show Link Signal Labels Checkbox
  const chkLabels = document.getElementById("chk-topo-show-labels");
  if (chkLabels) {
    chkLabels.addEventListener("change", (e) => {
      topologyPhysicsState.showLinkLabels = e.target.checked;
      applyTopologyVisibilityFilter();
    });
  }
}

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
    if (currentTelemetry && currentTelemetry.topology) {
      renderTopologyData(currentTelemetry.topology);
    } else {
      fetchAndRenderTopology();
    }
  } else if (tabId === "tab-channel") {
    fetchOtbrChannelInfo();
    fetchJoinableNetworks();
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
    const model = data.ai_model || "gemini-2.5-flash";
    const hasKey =
      (provider === "gemini" && data.has_gemini_key) ||
      (provider === "openai" && data.has_openai_key) ||
      (provider === "anthropic" && data.has_anthropic_key);

    if (hasKey) {
      badge.className = "badge badge-success";
      badge.innerHTML = `<i class="fa-solid fa-check"></i> ${model} Ready`;
    } else {
      badge.className = "badge badge-warning";
      badge.innerHTML = `<i class="fa-solid fa-key"></i> Key Needed (${model})`;
    }

    const reportBadge = document.getElementById("report-model-badge");
    if (reportBadge) {
      reportBadge.innerText = `${provider.toUpperCase()} (${model})`;
    }

    syncProviderAndModelSelects(provider, model);
    fetchLiveAIModels(provider, model);

    const matterUrlInput = document.getElementById("cfg-matter-url");
    if (matterUrlInput && data.matter_server_url) matterUrlInput.value = data.matter_server_url;

    const otbrUrlInput = document.getElementById("cfg-otbr-url");
    if (otbrUrlInput && data.otbr_url) otbrUrlInput.value = data.otbr_url;

    if (data.has_gemini_key) {
      document.getElementById("cfg-gemini-key").placeholder = `✓ Saved (${data.gemini_key_preview || 'Active'}) - enter new key to replace`;
    }
    if (data.has_openai_key) {
      document.getElementById("cfg-openai-key").placeholder = `✓ Saved (${data.openai_key_preview || 'Active'}) - enter new key to replace`;
    }
    if (data.has_anthropic_key) {
      document.getElementById("cfg-anthropic-key").placeholder = `✓ Saved (${data.anthropic_key_preview || 'Active'}) - enter new key to replace`;
    }
  } catch (err) {
    badge.className = "badge badge-danger";
    badge.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> Offline`;
    console.error("Status fetch error:", err);
  }
}

function populateModelSelectElement(selectElem, provider, selectedModel) {
  if (!selectElem) return;
  const opts = MODEL_OPTIONS_BY_PROVIDER[provider] || MODEL_OPTIONS_BY_PROVIDER.gemini;
  selectElem.innerHTML = "";
  let found = false;
  opts.forEach(o => {
    const opt = document.createElement("option");
    opt.value = o.value;
    opt.textContent = o.label;
    if (o.value === selectedModel) found = true;
    selectElem.appendChild(opt);
  });
  if (selectedModel && !found) {
    const customOpt = document.createElement("option");
    customOpt.value = selectedModel;
    customOpt.textContent = selectedModel;
    selectElem.appendChild(customOpt);
  }
  if (selectedModel && (found || selectElem.querySelector(`option[value="${selectedModel}"]`))) {
    selectElem.value = selectedModel;
  } else if (opts.length > 0) {
    selectElem.value = opts[0].value;
  }
}

function syncProviderAndModelSelects(provider, selectedModel) {
  const cfgProvider = document.getElementById("cfg-provider");
  const cfgModel = document.getElementById("cfg-model");
  const studioProvider = document.getElementById("studio-provider");
  const studioModel = document.getElementById("studio-model");

  if (cfgProvider) cfgProvider.value = provider;
  if (studioProvider) studioProvider.value = provider;

  document.getElementById("group-gemini-key")?.classList.toggle("hidden", provider !== "gemini");
  document.getElementById("group-openai-key")?.classList.toggle("hidden", provider !== "openai");
  document.getElementById("group-anthropic-key")?.classList.toggle("hidden", provider !== "anthropic");

  const defaultForProvider = (MODEL_OPTIONS_BY_PROVIDER[provider] || MODEL_OPTIONS_BY_PROVIDER.gemini)[0].value;
  const targetModel = selectedModel || defaultForProvider;

  populateModelSelectElement(cfgModel, provider, targetModel);
  populateModelSelectElement(studioModel, provider, targetModel);
}

async function fetchLiveAIModels(provider, selectedModel) {
  try {
    const res = await fetch(apiPath("/api/ai/models"));
    if (!res.ok) return;
    const data = await res.json();
    if (data.models && Array.isArray(data.models) && data.models.length > 0 && data.provider === provider) {
      const existing = MODEL_OPTIONS_BY_PROVIDER[provider] || [];
      const seen = new Set();
      const merged = [];
      data.models.forEach((m) => {
        if (m.value && !seen.has(m.value)) {
          seen.add(m.value);
          merged.push(m);
        }
      });
      existing.forEach((m) => {
        if (m.value && !seen.has(m.value)) {
          seen.add(m.value);
          merged.push(m);
        }
      });
      MODEL_OPTIONS_BY_PROVIDER[provider] = merged;
      const activeModel = selectedModel || data.selected_model;
      populateModelSelectElement(document.getElementById("cfg-model"), provider, activeModel);
      populateModelSelectElement(document.getElementById("studio-model"), provider, activeModel);
    }
  } catch (_) {}
}

async function saveProviderAndModelImmediate(provider, model) {
  const statusText = document.getElementById("settings-save-status");
  if (statusText) statusText.innerText = "Switching model...";
  try {
    const res = await fetch(apiPath("/api/config"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ai_provider: provider,
        ai_model: model,
      }),
    });
    if (res.ok) {
      if (statusText) {
        statusText.innerText = `✓ Active model: ${model}`;
        setTimeout(() => { statusText.innerText = ""; }, 2500);
      }
      await fetchStatus();
    }
  } catch (err) {
    console.error("Failed auto-saving model change:", err);
  }
}

function initSettingsForm() {
  const cfgProvider = document.getElementById("cfg-provider");
  const cfgModel = document.getElementById("cfg-model");
  const studioProvider = document.getElementById("studio-provider");
  const studioModel = document.getElementById("studio-model");

  // Settings Tab Provider Change -> update model list and auto-save immediately
  if (cfgProvider) {
    cfgProvider.addEventListener("change", (e) => {
      const newProv = e.target.value;
      const defaultModel = (MODEL_OPTIONS_BY_PROVIDER[newProv] || MODEL_OPTIONS_BY_PROVIDER.gemini)[0].value;
      syncProviderAndModelSelects(newProv, defaultModel);
      saveProviderAndModelImmediate(newProv, defaultModel);
    });
  }

  // Settings Tab Model Change -> sync and auto-save immediately
  if (cfgModel) {
    cfgModel.addEventListener("change", (e) => {
      const newModel = e.target.value;
      const prov = cfgProvider ? cfgProvider.value : "gemini";
      if (studioModel) studioModel.value = newModel;
      saveProviderAndModelImmediate(prov, newModel);
    });
  }

  // AI Studio Tab Provider Change -> update model list and auto-save immediately
  if (studioProvider) {
    studioProvider.addEventListener("change", (e) => {
      const newProv = e.target.value;
      const defaultModel = (MODEL_OPTIONS_BY_PROVIDER[newProv] || MODEL_OPTIONS_BY_PROVIDER.gemini)[0].value;
      syncProviderAndModelSelects(newProv, defaultModel);
      saveProviderAndModelImmediate(newProv, defaultModel);
    });
  }

  // AI Studio Tab Model Change -> sync and auto-save immediately
  if (studioModel) {
    studioModel.addEventListener("change", (e) => {
      const newModel = e.target.value;
      const prov = studioProvider ? studioProvider.value : "gemini";
      if (cfgModel) cfgModel.value = newModel;
      saveProviderAndModelImmediate(prov, newModel);
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
        otbr_url: document.getElementById("cfg-otbr-url") ? document.getElementById("cfg-otbr-url").value : undefined,
        target_thread_network: document.getElementById("top-thread-network") ? document.getElementById("top-thread-network").value : undefined,
      };

      try {
        const res = await fetch(apiPath("/api/config"), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
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

  const btnTest = document.getElementById("btn-test-ai");
  if (btnTest) {
    btnTest.addEventListener("click", async () => {
      const testResult = document.getElementById("ai-test-result");
      testResult.className = "";
      testResult.innerHTML = `<span style="color:var(--text-muted);"><i class="fa-solid fa-spinner fa-spin"></i> Saving current selection &amp; testing AI API connection...</span>`;

      const providerVal = document.getElementById("cfg-provider").value;
      const modelVal = document.getElementById("cfg-model").value;
      const geminiVal = document.getElementById("cfg-gemini-key").value;
      const openaiVal = document.getElementById("cfg-openai-key").value;
      const anthropicVal = document.getElementById("cfg-anthropic-key").value;

      // Always save provider & model (plus any non-empty key) before testing
      await fetch(apiPath("/api/config"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ai_provider: providerVal,
          ai_model: modelVal,
          gemini_api_key: geminiVal || undefined,
          openai_api_key: openaiVal || undefined,
          anthropic_api_key: anthropicVal || undefined,
        }),
      });

      try {
        const res = await fetch(apiPath("/api/test_ai"), { method: "POST" });
        const data = await res.json();
        if (data.success) {
          testResult.innerHTML = `<span class="badge badge-success"><i class="fa-solid fa-check"></i> ${escapeHtml(data.message)}</span>`;
          fetchStatus();
        } else {
          testResult.innerHTML = `<span class="badge badge-danger"><i class="fa-solid fa-triangle-exclamation"></i> Error:</span> <span style="color:var(--color-danger); margin-left:6px;">${escapeHtml(data.error)}</span>`;
        }
      } catch (err) {
        testResult.innerHTML = `<span style="color:var(--color-danger);">Network test error: ${escapeHtml(err.message)}</span>`;
      }
    });
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

/* Thread Networks Discovery & Selection */
async function loadThreadNetworks() {
  const topSelect = document.getElementById("top-thread-network");
  const cfgSelect = document.getElementById("cfg-thread-network");
  const btnTopRefresh = document.getElementById("btn-top-refresh-nets");
  const btnCfgRefresh = document.getElementById("btn-refresh-thread-networks");
  const countStatus = document.getElementById("thread-networks-count-status");
  const topFeedback = document.getElementById("top-scan-feedback");

  if (btnTopRefresh) {
    btnTopRefresh.disabled = true;
    btnTopRefresh.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Discovering...`;
  }
  if (btnCfgRefresh) {
    btnCfgRefresh.disabled = true;
    btnCfgRefresh.innerHTML = `<i class="fa-solid fa-arrows-rotate fa-spin"></i> Refreshing...`;
  }
  if (topFeedback) {
    topFeedback.style.color = "#38bdf8";
    topFeedback.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Querying HA datasets, mDNS (_meshcop._udp), OTBR &amp; Device Registry...`;
  }

  try {
    const res = await fetch(apiPath("/api/thread/networks"));
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    availableThreadNetworks = data.networks || [];
    const selectedId = data.selected_network !== undefined ? data.selected_network : (topSelect ? topSelect.value : "");

    populateNetworkDropdown(topSelect, availableThreadNetworks, selectedId);
    populateNetworkDropdown(cfgSelect, availableThreadNetworks, selectedId);

    updateThreadNetworkDetails(selectedId);
    updateSelectedNetworkStrip(selectedId);

    if (topFeedback) {
      topFeedback.style.color = availableThreadNetworks.length > 0 ? "var(--color-success)" : "var(--color-warning)";
      topFeedback.innerHTML = availableThreadNetworks.length > 0
        ? `✓ Found ${availableThreadNetworks.length} Thread network(s)`
        : `0 Thread networks returned — click '2. Scan Selected Network' to run full deep probe`;
    }

    if (countStatus) {
      if (availableThreadNetworks.length === 0) {
        countStatus.innerHTML = `<span style="color:var(--color-warning);"><i class="fa-solid fa-circle-info"></i> No Thread datasets found yet. Click "Scan Selected Network" to run a full probe.</span>`;
      } else {
        countStatus.innerHTML = `<span style="color:var(--color-success);"><i class="fa-solid fa-check"></i> Found ${availableThreadNetworks.length} Thread network(s) in Home Assistant.</span>`;
      }
    }
  } catch (err) {
    console.error("Failed to load thread networks:", err);
    if (topFeedback) {
      topFeedback.style.color = "var(--color-danger)";
      topFeedback.innerHTML = `Discovery error: ${err.message}`;
    }
    if (countStatus) {
      countStatus.innerHTML = `<span style="color:var(--color-danger);"><i class="fa-solid fa-triangle-exclamation"></i> Error querying networks: ${err.message}</span>`;
    }
  } finally {
    if (btnTopRefresh) {
      btnTopRefresh.disabled = false;
      btnTopRefresh.innerHTML = `<i class="fa-solid fa-magnifying-glass-chart"></i> Discover Networks`;
    }
    if (btnCfgRefresh) {
      btnCfgRefresh.disabled = false;
      btnCfgRefresh.innerHTML = `<i class="fa-solid fa-arrows-rotate"></i> Refresh Network List`;
    }
  }
}

function populateNetworkDropdown(selectElem, networks, selectedId) {
  if (!selectElem) return;
  selectElem.innerHTML = `<option value="">All Discovered Thread Networks (Full Mesh Scan)</option>`;
  networks.forEach(net => {
    const opt = document.createElement("option");
    opt.value = net.id;
    const xpanShort = net.extended_pan_id ? `XPAN: ${net.extended_pan_id}` : "";
    const chStr = net.channel ? `Ch ${net.channel}` : "";
    const prefStr = net.preferred ? "★ Preferred" : "";
    const rCount = net.routers && net.routers.length ? `[${net.routers.join(", ")}]` : "";
    const nCount = net.matter_node_count ? `${net.matter_node_count} Node(s)` : "";
    const metaParts = [chStr, prefStr, rCount, nCount, xpanShort].filter(Boolean).join(" • ");
    opt.textContent = metaParts ? `${net.name} (${metaParts})` : net.name;
    selectElem.appendChild(opt);
  });
  if (selectedId && networks.some(n => n.id === selectedId || n.extended_pan_id === selectedId)) {
    selectElem.value = selectedId;
  } else {
    selectElem.value = "";
  }
}

function updateSelectedNetworkStrip(selectedId) {
  const badgesContainer = document.getElementById("selected-network-badges");
  if (!badgesContainer) return;

  if (!selectedId) {
    const netCount = availableThreadNetworks.length;
    badgesContainer.innerHTML = `
      <span class="badge badge-info"><i class="fa-solid fa-globe"></i> Scope: All Networks (${netCount} discovered)</span>
      <span>Select a specific Thread network above and click <strong>2. Scan Selected Network</strong> to filter &amp; verify all nodes against its Extended PAN ID.</span>
    `;
    return;
  }

  const net = availableThreadNetworks.find(n => n.id === selectedId || n.extended_pan_id === selectedId);
  if (!net) {
    badgesContainer.innerHTML = `<span class="badge badge-info">Selected Target: ${escapeHtml(selectedId)}</span>`;
    return;
  }

  const routersText = net.routers && net.routers.length ? net.routers.join(", ") : "None via mDNS yet";
  badgesContainer.innerHTML = `
    <span class="badge badge-success"><i class="fa-solid fa-satellite-dish"></i> Target: ${escapeHtml(net.name)}</span>
    <span class="badge badge-info">Ext PAN ID: <code>${escapeHtml(net.extended_pan_id || 'UNKNOWN')}</code></span>
    ${net.channel ? `<span class="badge badge-ha">Channel ${net.channel}</span>` : ''}
    ${net.pan_id ? `<span class="badge" style="background:#374151;">PAN: ${escapeHtml(String(net.pan_id))}</span>` : ''}
    ${net.mesh_local_prefix ? `<span class="badge" style="background:#374151;">Prefix: <code>${escapeHtml(net.mesh_local_prefix)}</code></span>` : ''}
    <span style="color:var(--text-muted);">Border Routers: <strong>${escapeHtml(routersText)}</strong></span>
  `;
}

function updateThreadNetworkDetails(selectedId) {
  const detailsBox = document.getElementById("thread-network-details-box");
  if (!detailsBox) return;

  if (!selectedId) {
    detailsBox.style.display = "none";
    detailsBox.innerHTML = "";
    return;
  }

  const net = availableThreadNetworks.find(n => n.id === selectedId || n.extended_pan_id === selectedId);
  if (!net) {
    detailsBox.style.display = "none";
    return;
  }

  detailsBox.style.display = "block";
  const routersList = net.routers && net.routers.length ? net.routers.join(", ") : "None detected via mDNS yet";
  detailsBox.innerHTML = `
    <div style="font-size: 13px; line-height: 1.6;">
      <div><strong>Network Name:</strong> ${escapeHtml(net.name)}</div>
      <div><strong>Extended PAN ID:</strong> <code>${escapeHtml(net.extended_pan_id || 'UNKNOWN')}</code></div>
      <div><strong>PAN ID:</strong> <code>${escapeHtml(String(net.pan_id || 'UNKNOWN'))}</code></div>
      <div><strong>Channel:</strong> ${net.channel ? `Channel ${net.channel} (2.4 GHz 802.15.4)` : 'Auto / Unknown'}</div>
      <div><strong>Mesh-Local IPv6 Prefix:</strong> <code>${escapeHtml(net.mesh_local_prefix || 'Not decoded')}</code></div>
      <div><strong>Source:</strong> ${escapeHtml(net.source)}</div>
      <div><strong>Active Border Routers:</strong> ${escapeHtml(routersList)}</div>
    </div>
  `;
}

async function scanSelectedNetwork(switchToScanTab = false) {
  const topSelect = document.getElementById("top-thread-network");
  const cfgSelect = document.getElementById("cfg-thread-network");
  const topFeedback = document.getElementById("top-scan-feedback");
  const cfgFeedback = document.getElementById("scan-feedback");
  const btnTopScan = document.getElementById("btn-top-scan");

  const selectedId = topSelect ? topSelect.value : (cfgSelect ? cfgSelect.value : "");

  if (btnTopScan) {
    btnTopScan.disabled = true;
    btnTopScan.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Scanning mDNS, Cluster 0x0035 &amp; IPv6...`;
  }
  if (topFeedback) {
    topFeedback.style.color = "#38bdf8";
    topFeedback.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Running live mDNS (_meshcop._udp), HA TLV, Matter Cluster 0x0035 &amp; ICMPv6 ping scan...`;
  }
  if (cfgFeedback) {
    cfgFeedback.style.color = "var(--ha-primary-color)";
    cfgFeedback.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Scanning live network...`;
  }

  try {
    const res = await fetch(apiPath("/api/thread/select_and_scan"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ network_id: selectedId }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    if (data.telemetry) {
      currentTelemetry = data.telemetry;
      if (data.telemetry.available_thread_networks) {
        availableThreadNetworks = data.telemetry.available_thread_networks;
        populateNetworkDropdown(topSelect, availableThreadNetworks, selectedId);
        populateNetworkDropdown(cfgSelect, availableThreadNetworks, selectedId);
      }
      renderKPIs(currentTelemetry);
      renderRulesAndTables(currentTelemetry);
      if (data.topology || currentTelemetry.topology) {
        renderTopologyData(data.topology || currentTelemetry.topology);
      }
    }

    updateSelectedNetworkStrip(selectedId);
    updateThreadNetworkDetails(selectedId);

    const brCount = currentTelemetry?.telemetry?.border_routers_count || 0;
    const nodeCount = currentTelemetry?.telemetry?.matter_server?.nodes?.length || 0;
    const netCount = availableThreadNetworks.length;

    if (topFeedback) {
      topFeedback.style.color = "var(--color-success)";
      topFeedback.innerHTML = `✓ Scan complete: ${netCount} Network(s), ${brCount} Border Router(s), ${nodeCount} Matter Node(s)`;
    }
    if (cfgFeedback) {
      cfgFeedback.style.color = "var(--color-success)";
      cfgFeedback.innerHTML = `✓ Live scan complete!`;
      setTimeout(() => { cfgFeedback.innerHTML = ""; }, 4000);
    }

    if (switchToScanTab) {
      activateTab("tab-rules");
    }
  } catch (err) {
    if (topFeedback) {
      topFeedback.style.color = "var(--color-danger)";
      topFeedback.innerHTML = `Scan failed: ${err.message}`;
    }
    if (cfgFeedback) {
      cfgFeedback.style.color = "var(--color-danger)";
      cfgFeedback.innerHTML = `Scan failed: ${err.message}`;
    }
  } finally {
    if (btnTopScan) {
      btnTopScan.disabled = false;
      btnTopScan.innerHTML = `<i class="fa-solid fa-satellite-dish"></i> 2. Scan Selected Network`;
    }
  }
}

/* API: Initial Live Telemetry */
async function fetchLiveDiagnostics() {
  try {
    const res = await fetch(apiPath("/api/diagnostics/collect"));
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    currentTelemetry = data;

    // Also populate network dropdowns from the full telemetry payload if networks were found
    if (data.available_thread_networks && data.available_thread_networks.length > 0) {
      availableThreadNetworks = data.available_thread_networks;
      const topSelect = document.getElementById("top-thread-network");
      const cfgSelect = document.getElementById("cfg-thread-network");
      const selectedId = data.selected_target_network?.id || (topSelect ? topSelect.value : "");
      populateNetworkDropdown(topSelect, availableThreadNetworks, selectedId);
      populateNetworkDropdown(cfgSelect, availableThreadNetworks, selectedId);
      updateSelectedNetworkStrip(selectedId);
      updateThreadNetworkDetails(selectedId);
    }

    renderKPIs(data);
    renderRulesAndTables(data);
    if (data.topology) {
      renderTopologyData(data.topology);
    }
  } catch (err) {
    console.error("Failed to load telemetry:", err);
  }
}

function renderKPIs(data) {
  const rules = data.rule_evaluations || {};
  const telemetry = data.telemetry || {};

  // 1. Health Index
  const score = data.summary_score !== undefined ? data.summary_score : 100;
  const scoreElem = document.getElementById("health-score");
  const scoreDesc = document.getElementById("health-desc");
  scoreElem.innerText = score;
  if (score >= 80) {
    scoreElem.style.color = "var(--color-success)";
    scoreDesc.innerText = "Healthy mesh telemetry";
  } else if (score >= 50) {
    scoreElem.style.color = "var(--color-warning)";
    scoreDesc.innerText = "Warnings detected in scan";
  } else {
    scoreElem.style.color = "var(--color-danger)";
    scoreDesc.innerText = "Action required (Split/Offline)";
  }

  // 2. Border Router Sync
  const splitRule = rules.split_network || {};
  const splitElem = document.getElementById("split-status");
  const splitDesc = document.getElementById("split-desc");
  const brCount = telemetry.border_routers_count || 0;
  if (splitRule.is_split_network) {
    splitElem.innerHTML = `<span class="badge badge-danger">Split Mesh</span>`;
    splitDesc.innerText = `${splitRule.distinct_network_count} separate Extended PAN IDs`;
  } else if (brCount === 0) {
    splitElem.innerHTML = `<span class="badge badge-warning">0 Routers</span>`;
    splitDesc.innerText = "Click Scan to probe network";
  } else {
    splitElem.innerHTML = `<span class="badge badge-success">${brCount} TBR(s) Synced</span>`;
    splitDesc.innerText = "Unified Extended PAN ID";
  }

  // 3. RF Coexistence
  const rfRule = rules.rf_coexistence || {};
  const rfElem = document.getElementById("rf-status");
  const rfDesc = document.getElementById("rf-desc");
  const ch = rfRule.thread_channel || "--";
  if (rfRule.severity === "HIGH") {
    rfElem.innerHTML = `<span class="badge badge-danger">Ch ${ch} (Overlap)</span>`;
    rfDesc.innerText = rfRule.overlapping_wifi_channel ? `Overlaps 2.4GHz Wi-Fi Ch ${rfRule.overlapping_wifi_channel}` : "High RF overlap";
  } else if (rfRule.severity === "MINIMAL" || ch === 25 || ch === 26) {
    rfElem.innerHTML = `<span class="badge badge-success">Ch ${ch} (Clean)</span>`;
    rfDesc.innerText = "Clear of 2.4GHz Wi-Fi 1, 6, 11";
  } else if (ch !== "--") {
    rfElem.innerHTML = `<span class="badge badge-info">Channel ${ch}</span>`;
    rfDesc.innerText = rfRule.interference_description || "Guard band channel";
  } else {
    rfElem.innerHTML = `<span class="badge badge-warning">Ch Auto</span>`;
    rfDesc.innerText = "Channel determined by TBR";
  }

  // 4. IPv6 & Pings
  const ipv6Rule = rules.ipv6_routing || {};
  const pings = telemetry.reachability_probes || {};
  const ipv6Elem = document.getElementById("ipv6-status");
  const ipv6Desc = document.getElementById("ipv6-desc");
  if (ipv6Rule.has_thread_ula_route) {
    ipv6Elem.innerHTML = `<span class="badge badge-success">ULA Active</span>`;
    ipv6Desc.innerText = pings.probed_count
      ? `Pings: ${pings.reachable_count}/${pings.probed_count} reachable`
      : `${(ipv6Rule.detected_ula_prefixes || []).length} fd00::/8 route(s)`;
  } else {
    ipv6Elem.innerHTML = `<span class="badge badge-warning">No ULA Route</span>`;
    ipv6Desc.innerText = "No kernel fd00::/8 route found";
  }
}

function renderRulesAndTables(data) {
  const rules = data.rule_evaluations || {};
  const telemetry = data.telemetry || {};
  const targetNet = data.selected_target_network;
  const targetXpan = (targetNet?.extended_pan_id || "").toUpperCase();

  const pingMap = {};
  (telemetry.reachability_probes?.results || []).forEach(p => {
    if (p.ip) pingMap[p.ip] = p;
  });

  // --- TABLE 1: Discovered Border Routers ---
  const routers = telemetry.border_routers || [];
  const brCountBadge = document.getElementById("br-table-count");
  if (brCountBadge) brCountBadge.innerText = `${routers.length} Border Router(s)`;

  const tbodyBr = document.getElementById("tbody-border-routers");
  if (tbodyBr) {
    if (routers.length === 0) {
      tbodyBr.innerHTML = `
        <tr>
          <td colspan="7" style="padding: 18px; color: var(--text-muted); text-align: center;">
            No Thread Border Routers discovered yet. Click <strong>2. Scan Selected Network</strong> above to probe mDNS (<code>_meshcop._udp</code>), HA Thread, and Device Registry.
          </td>
        </tr>
      `;
    } else {
      tbodyBr.innerHTML = routers.map(r => {
        const xpan = (r.extended_pan_id || "UNKNOWN").toUpperCase();
        const isTarget = !targetXpan || xpan === targetXpan || xpan.includes(targetXpan);
        const addrs = r.addresses || [];
        const primaryIp = addrs[0] || "N/A";
        let pingCell = `<span style="color:var(--text-muted);">--</span>`;
        for (const a of addrs) {
          if (pingMap[a]) {
            const pr = pingMap[a];
            pingCell = pr.reachable
              ? `<span class="badge badge-success">${pr.rtt_ms ?? '<1'} ms</span>`
              : `<span class="badge badge-danger">Timeout</span>`;
            break;
          }
        }
        return `
          <tr style="border-bottom: 1px solid #37415166;">
            <td style="padding: 10px 8px;">
              <div style="display:flex; align-items:center; gap:6px; flex-wrap:wrap;">
                <strong>${escapeHtml(r.name || 'Border Router')}</strong>
                ${r.preferred ? `<span class="badge badge-success" style="font-size:10px; padding:1px 6px;" title="Preferred Border Router in Home Assistant">★ Preferred Router</span>` : ''}
              </div>
              <div style="font-size: 11px; color: var(--text-muted);">${escapeHtml(r.brand || '')} • ${escapeHtml(r.model || '')}${r.thread_version ? ` (Thread ${escapeHtml(r.thread_version)})` : ''}</div>
            </td>
            <td style="padding: 10px 8px;">
              <strong>${escapeHtml(r.network_name || '--')}</strong>
            </td>
            <td style="padding: 10px 8px;">
              <code style="color: ${isTarget ? '#38bdf8' : '#f87171'};">${escapeHtml(xpan)}</code>
              ${!isTarget ? `<span class="badge badge-danger" style="font-size:10px;">Different PAN</span>` : ''}
            </td>
            <td style="padding: 10px 8px;">
              ${r.channel ? `<span class="badge badge-ha">Ch ${r.channel}</span>` : '<span style="color:var(--text-muted)">Auto</span>'}
              ${r.pan_id ? `<div style="font-size:11px; color:var(--text-muted);">PAN: <code>${escapeHtml(String(r.pan_id))}</code></div>` : ''}
            </td>
            <td style="padding: 10px 8px; font-family: monospace; font-size: 12px;">
              ${escapeHtml(primaryIp)}
              ${r.mesh_local_prefix ? `<div style="font-size:11px; color:#38bdf8;">ULA: ${escapeHtml(r.mesh_local_prefix)}</div>` : ''}
            </td>
            <td style="padding: 10px 8px; font-size: 12px; color: var(--text-muted);">${escapeHtml(r.source || 'mDNS')}</td>
            <td style="padding: 10px 8px;">${pingCell}</td>
          </tr>
        `;
      }).join("");
    }
  }

  // --- TABLE 2: Commissioned Matter Nodes (Cluster 0x0035) ---
  const matterServer = telemetry.matter_server || {};
  const allNodes = matterServer.nodes || [];
  const qLower = (currentNodeSearchQuery || "").toLowerCase();

  const nodes = allNodes.filter(n => {
    // Role / State filter
    if (currentNodeRoleFilter === "online" && !n.available) return false;
    if (currentNodeRoleFilter === "issues") {
      const weakLqi = n.lqi !== null && n.lqi !== undefined && (
        n.lqi === 0 ||
        (n.lqi === 1 && (n.rssi === null || n.rssi === undefined || n.rssi < -82)) ||
        (n.lqi > 3 && n.lqi < 64)
      );
      const isWeak = (n.rssi !== null && n.rssi !== undefined && n.rssi < -82) || weakLqi;
      if (n.available && !isWeak) return false;
    } else if (currentNodeRoleFilter === "router") {
      const roleStr = (n.routing_role || "").toLowerCase();
      if (!roleStr.includes("router") && !roleStr.includes("leader") && !roleStr.includes("reed")) return false;
    } else if (currentNodeRoleFilter === "end_device") {
      const roleStr = (n.routing_role || "").toLowerCase();
      if (roleStr.includes("router") || roleStr.includes("leader")) return false;
    }

    // Search query filter
    if (!qLower) return true;
    const searchable = [
      `#${n.node_id}`,
      String(n.node_id || ""),
      n.ha_name || "",
      n.ha_area || "",
      n.ha_entity_id || "",
      n.hardware_model || "",
      n.product_name || "",
      n.vendor_name || "",
      n.node_label || "",
      n.routing_role || "",
      n.rloc16 || "",
      n.parent_rloc16 || "",
      n.extended_pan_id || "",
      n.ext_address || "",
      n.serial_number || "",
      n.available ? "online" : "offline",
      ...(n.ipv6_addresses || []),
    ].join(" ").toLowerCase();
    return searchable.includes(qLower);
  });

  const matterCountBadge = document.getElementById("matter-table-count");
  if (matterCountBadge) {
    if (!matterServer.connected) {
      matterCountBadge.innerText = `Matter Server Disconnected`;
      matterCountBadge.className = "badge badge-warning";
    } else if (qLower || currentNodeRoleFilter !== "all") {
      matterCountBadge.innerText = `${nodes.length} / ${allNodes.length} Node(s)`;
      matterCountBadge.className = "badge badge-info";
    } else {
      matterCountBadge.innerText = `${allNodes.length} Commissioned Node(s)`;
      matterCountBadge.className = "badge badge-info";
    }
  }

  const offlineNodesList = allNodes.filter(n => !n.available);
  const btnPurgeOffline = document.getElementById("btn-purge-offline-nodes");
  if (btnPurgeOffline) {
    if (matterServer.connected && offlineNodesList.length > 0) {
      btnPurgeOffline.style.display = "inline-flex";
      btnPurgeOffline.innerHTML = `<i class="fa-solid fa-trash-can"></i> Purge Offline (${offlineNodesList.length})`;
    } else {
      btnPurgeOffline.style.display = "none";
    }
  }

  const tbodyNodes = document.getElementById("tbody-matter-nodes");
  if (tbodyNodes) {
    if (!matterServer.connected) {
      tbodyNodes.innerHTML = `
        <tr>
          <td colspan="8" style="padding: 18px; color: var(--color-warning); text-align: center;">
            <i class="fa-solid fa-triangle-exclamation"></i> Could not connect to <code>python-matter-server</code> WebSocket (${escapeHtml(matterServer.error || 'Unreachable')}).<br>
            <small style="color:var(--text-muted);">Verify that the official <strong>Matter Server</strong> add-on is running in Home Assistant.</small>
          </td>
        </tr>
      `;
    } else if (allNodes.length === 0) {
      tbodyNodes.innerHTML = `
        <tr>
          <td colspan="8" style="padding: 18px; color: var(--text-muted); text-align: center;">
            Connected to Matter Server (Fabric ID: <code>${escapeHtml(String(matterServer.compressed_fabric_id || matterServer.fabric_id || 'OK'))}</code>), but 0 Matter nodes are currently commissioned.
          </td>
        </tr>
      `;
    } else if (nodes.length === 0) {
      tbodyNodes.innerHTML = `
        <tr>
          <td colspan="8" style="padding: 18px; color: var(--text-muted); text-align: center;">
            No devices match your search filter (<strong>${escapeHtml(currentNodeSearchQuery || currentNodeRoleFilter)}</strong>).
          </td>
        </tr>
      `;
    } else {
      tbodyNodes.innerHTML = nodes.map(n => {
        const nid = n.node_id;
        const avail = n.available;
        const xpan = (n.extended_pan_id || "").toUpperCase();
        const isTarget = !targetXpan || !xpan || xpan === targetXpan || xpan.includes(targetXpan);
        const rssi = n.rssi;
        const lqi = n.lqi;
        const v6List = n.ipv6_addresses || [];
        const ulaIp = v6List.find(ip => ip.toLowerCase().startsWith("fd")) || v6List[0] || "";
        const counters = n.telemetry_counters || {};
        const nbCount = (n.neighbor_table || []).length;

        let signalBadge = `<span style="color:var(--text-muted);">N/A</span>`;
        const lqiFmt = (lqi !== null && lqi !== undefined) ? (lqi <= 3 ? `${lqi}/3` : `${lqi}/255`) : "";
        if (rssi !== null && rssi !== undefined) {
          const sigClass = rssi < -82 ? "badge-danger" : (rssi < -72 ? "badge-warning" : "badge-success");
          signalBadge = `<span class="badge ${sigClass}">${rssi} dBm</span>`;
          if (lqiFmt) {
            signalBadge += ` <small style="color:var(--text-muted);">LQI ${lqiFmt}</small>`;
          }
        } else if (lqiFmt) {
          signalBadge = `<span class="badge badge-info">LQI ${lqiFmt}</span>`;
        }

        const displayName = n.ha_name || n.product_name || `Node ${nid}`;
        const hwModel = n.hardware_model && n.hardware_model !== displayName ? n.hardware_model : "";
        const areaBadge = n.ha_area
          ? ` <span class="badge badge-info" style="font-size:10px; padding:1px 6px;" title="Home Assistant Area">📍 ${escapeHtml(n.ha_area)}</span>`
          : "";

        return `
          <tr style="border-bottom: 1px solid #37415166;">
            <td style="padding: 10px 8px; font-weight: 700;">#${nid}</td>
            <td style="padding: 10px 8px;">
              <div style="display:flex; align-items:center; gap:5px; flex-wrap:wrap;">
                <span class="badge ${avail ? 'badge-success' : 'badge-danger'}" style="font-size:10px; padding:2px 6px;">${avail ? 'Online' : 'Offline'}</span>
                <strong>${escapeHtml(displayName)}</strong>${areaBadge}
              </div>
              <div style="font-size: 11px; color: var(--text-muted); margin-top: 2px;">
                ${escapeHtml(n.vendor_name || 'Unknown')}${hwModel ? ` • ${escapeHtml(hwModel)}` : ''}${n.ha_entity_id ? ` • <code style="color:#94a3b8;">${escapeHtml(n.ha_entity_id)}</code>` : ''} • Transport: <code>${escapeHtml(n.transport || 'thread')}</code>
                ${n.software_version ? ` • FW: ${escapeHtml(n.software_version)}` : ''}
              </div>
            </td>
            <td style="padding: 10px 8px;">
              <div>${escapeHtml(n.routing_role || 'Thread Node')}</div>
              ${n.rloc16 ? `<div style="font-size:11px; color:#38bdf8;">RLOC16: <code>${escapeHtml(n.rloc16)}</code>${n.parent_rloc16 ? ` → Parent <code>${escapeHtml(n.parent_rloc16)}</code>` : ''}</div>` : ''}
            </td>
            <td style="padding: 10px 8px;">
              ${xpan ? `<code style="color: ${isTarget ? '#38bdf8' : '#f87171'};">${escapeHtml(xpan)}</code>` : '<span style="color:var(--text-muted)">--</span>'}
              ${n.thread_channel ? `<div style="font-size:11px; color:var(--text-muted);">Ch ${n.thread_channel}</div>` : ''}
            </td>
            <td style="padding: 10px 8px;">${signalBadge}</td>
            <td style="padding: 10px 8px; font-size: 12px;">
              <div><strong>${nbCount}</strong> neighbor(s)</div>
              <div style="font-size:11px; color:var(--text-muted);">
                Parent switches: ${counters.parent_change_count || 0} | Detaches: ${counters.detached_role_count || 0}
              </div>
            </td>
            <td style="padding: 10px 8px; font-family: monospace; font-size: 11px;">
              ${ulaIp ? escapeHtml(ulaIp) : '<span style="color:var(--text-muted)">None reported</span>'}
            </td>
            <td style="padding: 10px 8px;">
              <div style="display: flex; gap: 6px; align-items: center; flex-wrap: wrap;">
                <button type="button" class="btn btn-outline btn-ping-node" data-node-id="${nid}" data-ipv6="${escapeHtml(ulaIp)}" style="font-size: 11px; padding: 4px 10px;">
                  <i class="fa-solid fa-bolt"></i> Ping
                </button>
                <button type="button" class="btn btn-outline btn-purge-node" data-node-id="${nid}" data-node-name="${escapeHtml(n.product_name || `Node ${nid}`)}" style="font-size: 11px; padding: 4px 10px; border-color: #ef444466; color: #f87171;" title="Decommission and purge this device from Matter Server &amp; Home Assistant">
                  <i class="fa-solid fa-trash-can"></i> Purge
                </button>
              </div>
              <div id="ping-res-${nid}" style="font-size: 11px; margin-top: 4px;"></div>
            </td>
          </tr>
        `;
      }).join("");

      document.querySelectorAll(".btn-ping-node").forEach(btn => {
        btn.addEventListener("click", () => {
          const nodeId = parseInt(btn.getAttribute("data-node-id"), 10);
          const ipv6 = btn.getAttribute("data-ipv6") || "";
          triggerLiveNodePing(nodeId, ipv6, btn);
        });
      });

      document.querySelectorAll(".btn-purge-node").forEach(btn => {
        btn.addEventListener("click", () => {
          const nodeId = parseInt(btn.getAttribute("data-node-id"), 10);
          const nodeName = btn.getAttribute("data-node-name") || `Node #${nodeId}`;
          triggerPurgeNode(nodeId, nodeName, btn);
        });
      });
    }
  }

  // --- Rule 1: Split Mesh ---
  const split = rules.split_network || {};
  const splitBadge = document.getElementById("rule-badge-split");
  splitBadge.className = split.is_split_network ? "badge badge-danger" : "badge badge-success";
  splitBadge.innerText = split.is_split_network ? "CRITICAL: Split" : "PASS";
  document.getElementById("rule-text-split").innerText = split.summary || "";
  const splitDetail = document.getElementById("split-networks-detail");
  if (split.networks && Object.keys(split.networks).length > 0) {
    splitDetail.innerHTML = Object.entries(split.networks).map(([xpan, rList]) => `
      <div style="margin-bottom: 10px; padding-bottom: 6px; border-bottom: 1px solid #374151;">
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <strong>Extended PAN ID: <code style="color:#38bdf8;">${escapeHtml(xpan)}</code></strong>
          <span class="badge badge-info" style="font-size:10px;">${rList.length} entry</span>
        </div>
        ${rList.map(r => `
          <div style="margin-left: 6px; margin-top: 4px; font-size: 12px; display:flex; align-items:center; gap:6px; flex-wrap:wrap;">
            <i class="fa-solid fa-circle-dot" style="font-size: 8px; color: ${r.type === 'nest' ? '#4285F4' : (r.type === 'ha' ? '#03A9F4' : '#10b981')};"></i>
            <span><strong>${escapeHtml(r.name || 'Thread Border Router')}</strong> ${r.model ? `<span style="color:var(--text-muted)">(${escapeHtml(r.model)})</span>` : ''}</span>
            ${r.channel ? `<span class="badge" style="font-size: 10px; padding: 2px 6px;">Ch ${r.channel}</span>` : ''}
            ${r.preferred ? `<span class="badge badge-success" style="font-size: 10px; padding: 2px 6px;">Preferred</span>` : ''}
          </div>
        `).join("")}
      </div>
    `).join("");
  } else {
    splitDetail.innerHTML = `<div style="color:var(--text-muted);">No active Extended PAN IDs discovered yet.</div>`;
  }

  // --- Rule 2: RF Coexistence ---
  const rf = rules.rf_coexistence || {};
  const rfBadge = document.getElementById("rule-badge-rf");
  rfBadge.className = rf.severity === "HIGH" ? "badge badge-danger" : (rf.severity === "MINIMAL" ? "badge badge-success" : "badge badge-warning");
  rfBadge.innerText = rf.severity || "UNKNOWN";
  document.getElementById("rule-text-rf").innerText = rf.recommendation || rf.interference_description || "";

  // --- Rule 3: IPv6 Routes & Active Pings ---
  const ipv6 = rules.ipv6_routing || {};
  const ipv6Badge = document.getElementById("rule-badge-ipv6");
  ipv6Badge.className = ipv6.has_thread_ula_route ? "badge badge-success" : "badge badge-warning";
  ipv6Badge.innerText = ipv6.status || "UNKNOWN";
  document.getElementById("rule-text-ipv6").innerText = ipv6.summary || "";
  const routesBox = document.getElementById("ipv6-routes-detail");
  let routesHtml = "";
  const probeResults = telemetry.reachability_probes?.results || [];
  if (probeResults.length > 0) {
    routesHtml += `<div style="margin-bottom:8px; color:#38bdf8; font-weight:700;">Active ICMPv6 / IP Reachability Probes:</div>`;
    routesHtml += probeResults.map(p => `
      <div style="margin-bottom:4px;">
        ${p.reachable ? '🟢' : '🔴'} <strong>${escapeHtml(p.name)}</strong> (<code>${escapeHtml(p.ip)}</code>):
        ${p.reachable ? `<span style="color:#34d399;">${p.rtt_ms ?? '<1'} ms (0% loss)</span>` : `<span style="color:#f87171;">Unreachable (${p.packet_loss_pct ?? 100}% loss)</span>`}
      </div>
    `).join("");
    routesHtml += `<hr style="border:none; border-top:1px solid #374151; margin:8px 0;">`;
  }
  if (ipv6.sample_routes && ipv6.sample_routes.length > 0) {
    routesHtml += `<div style="margin-bottom:4px; color:var(--text-muted); font-weight:700;">Kernel IPv6 Route Table (ip -6 route show):</div>`;
    routesHtml += ipv6.sample_routes.map(r => `<div>${escapeHtml(r)}</div>`).join("");
  } else {
    routesHtml += `<div style="color:var(--text-muted);">No IPv6 routes returned from kernel.</div>`;
  }
  routesBox.innerHTML = routesHtml;

  // --- Rule 4: Nodes & Logs ---
  const nq = rules.node_quality || {};
  const nqBadge = document.getElementById("rule-badge-nodes");
  nqBadge.className = nq.offline_count > 0 ? "badge badge-danger" : (nq.weak_count > 0 ? "badge badge-warning" : "badge badge-success");
  nqBadge.innerText = `${nq.healthy_count || 0}/${nq.total_nodes || 0} Healthy`;
  document.getElementById("rule-text-nodes").innerText = nq.summary || "";
  const nodesDetail = document.getElementById("nodes-detail-list");
  let nodeHtml = "";
  if (nq.offline_nodes && nq.offline_nodes.length > 0) {
    nodeHtml += nq.offline_nodes.map(n => `
      <div style="color:var(--color-danger); margin-bottom:6px; display:flex; justify-content:space-between; align-items:center; gap:8px;">
        <span>🔴 Node #${n.node_id} (${escapeHtml(n.name)}) — ${escapeHtml(n.reason)}</span>
        <button type="button" class="btn btn-outline btn-purge-inline" data-node-id="${n.node_id}" data-node-name="${escapeHtml(n.name)}" style="font-size:10px; padding:2px 8px; border-color:#ef444466; color:#f87171; flex-shrink:0;">
          <i class="fa-solid fa-trash-can"></i> Purge
        </button>
      </div>
    `).join("");
  }
  if (nq.weak_nodes && nq.weak_nodes.length > 0) {
    nodeHtml += nq.weak_nodes.map(n => `<div style="color:var(--color-warning); margin-bottom:4px;">⚠️ Node #${n.node_id} (${escapeHtml(n.name)}) — ${escapeHtml(n.reason)}</div>`).join("");
  }
  if (nq.wrong_network_nodes && nq.wrong_network_nodes.length > 0) {
    nodeHtml += nq.wrong_network_nodes.map(n => `
      <div style="color:#f87171; margin-bottom:6px; display:flex; justify-content:space-between; align-items:center; gap:8px;">
        <span>🔀 Node #${n.node_id} (${escapeHtml(n.name)}) — ${escapeHtml(n.reason)}</span>
        <button type="button" class="btn btn-outline btn-purge-inline" data-node-id="${n.node_id}" data-node-name="${escapeHtml(n.name)}" style="font-size:10px; padding:2px 8px; border-color:#ef444466; color:#f87171; flex-shrink:0;">
          <i class="fa-solid fa-trash-can"></i> Purge
        </button>
      </div>
    `).join("");
  }
  const matterErrs = telemetry.logs_sample?.matter_server_recent_errors || [];
  if (matterErrs.length > 0) {
    nodeHtml += `<div style="margin-top:8px; font-weight:700; color:var(--text-muted);">Recent Matter Server Log Warnings/Errors:</div>`;
    nodeHtml += matterErrs.slice(-5).map(l => `<div style="font-family:monospace; font-size:11px; color:#fca5a5;">${escapeHtml(l)}</div>`).join("");
  }
  if (!nodeHtml) {
    nodeHtml = `<div style="color:var(--color-success)">🟢 All commissioned nodes responding with healthy link quality and no recent log errors.</div>`;
  }
  nodesDetail.innerHTML = nodeHtml;
  nodesDetail.querySelectorAll(".btn-purge-inline").forEach(btn => {
    btn.addEventListener("click", () => {
      const nodeId = parseInt(btn.getAttribute("data-node-id"), 10);
      const nodeName = btn.getAttribute("data-node-name") || `Node #${nodeId}`;
      triggerPurgeNode(nodeId, nodeName, btn);
    });
  });
}

/* Purge / Decommission Matter Node (Single & Bulk) */
async function triggerPurgeNode(nodeId, nodeName, btnElem) {
  const confirmed = window.confirm(
    `Purge ${nodeName} (Node #${nodeId}) from your Matter & Thread network?\n\n` +
    `This will decommission and remove Node #${nodeId} from python-matter-server and clean up its Home Assistant Device Registry entry.`
  );
  if (!confirmed) return;

  const resBox = document.getElementById(`ping-res-${nodeId}`);
  const origHtml = btnElem ? btnElem.innerHTML : "";
  if (btnElem) {
    btnElem.disabled = true;
    btnElem.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Purging...`;
  }
  if (resBox) {
    resBox.innerHTML = `<span style="color:#fbbf24;">Decommissioning Node #${nodeId}...</span>`;
  }

  try {
    const res = await fetch(apiPath("/api/matter/purge_node"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ node_id: nodeId }),
    });
    const data = await res.json();
    if (data.success) {
      if (data.telemetry) {
        currentTelemetry = data.telemetry;
        renderKPIs(currentTelemetry);
        renderRulesAndTables(currentTelemetry);
        if (currentTelemetry.topology) {
          renderTopologyData(currentTelemetry.topology);
        }
      } else {
        await fetchLiveDiagnostics();
      }
      const inspector = document.getElementById("node-inspector");
      if (inspector) inspector.classList.add("hidden");
    } else {
      const errMsg = data.matter_server?.error || data.error || "Purge failed";
      if (resBox) {
        resBox.innerHTML = `<span style="color:var(--color-danger);">Purge failed: ${escapeHtml(errMsg)}</span>`;
      } else {
        alert(`Could not purge Node #${nodeId}: ${errMsg}`);
      }
    }
  } catch (err) {
    if (resBox) {
      resBox.innerHTML = `<span style="color:var(--color-danger);">Error: ${escapeHtml(err.message)}</span>`;
    } else {
      alert(`Error purging Node #${nodeId}: ${err.message}`);
    }
  } finally {
    if (btnElem) {
      btnElem.disabled = false;
      btnElem.innerHTML = origHtml || `<i class="fa-solid fa-trash-can"></i> Purge`;
    }
  }
}

async function triggerBulkPurgeOfflineNodes(btnElem) {
  const allNodes = currentTelemetry?.telemetry?.matter_server?.nodes || [];
  const offlineNodes = allNodes.filter(n => !n.available);
  if (offlineNodes.length === 0) {
    alert("There are no offline Matter nodes to purge.");
    return;
  }

  const summaryList = offlineNodes
    .map(n => `• Node #${n.node_id}: ${n.product_name || 'Matter Device'} (${n.vendor_name || 'Unknown'})`)
    .join("\n");

  const confirmed = window.confirm(
    `Purge all ${offlineNodes.length} offline Matter node(s) from your network?\n\n` +
    `${summaryList}\n\n` +
    `This will permanently remove these offline nodes from python-matter-server and Home Assistant.`
  );
  if (!confirmed) return;

  const origHtml = btnElem ? btnElem.innerHTML : "";
  if (btnElem) {
    btnElem.disabled = true;
    btnElem.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Purging ${offlineNodes.length} Node(s)...`;
  }

  try {
    const nodeIds = offlineNodes.map(n => n.node_id);
    const res = await fetch(apiPath("/api/matter/purge_nodes_bulk"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ node_ids: nodeIds }),
    });
    const data = await res.json();
    if (data.telemetry) {
      currentTelemetry = data.telemetry;
      renderKPIs(currentTelemetry);
      renderRulesAndTables(currentTelemetry);
      if (currentTelemetry.topology) {
        renderTopologyData(currentTelemetry.topology);
      }
    } else {
      await fetchLiveDiagnostics();
    }
    if (data.failed && data.failed.length > 0) {
      const failStr = data.failed.map(f => `Node #${f.node_id}: ${f.error}`).join("\n");
      alert(`Purged ${data.purged_node_ids?.length || 0} node(s).\nFailed (${data.failed.length}):\n${failStr}`);
    }
  } catch (err) {
    alert(`Bulk purge error: ${err.message}`);
  } finally {
    if (btnElem) {
      btnElem.disabled = false;
      btnElem.innerHTML = origHtml;
    }
  }
}

/* Live On-Demand Matter + ICMPv6 Node Ping */
async function triggerLiveNodePing(nodeId, ipv6Address, btnElem) {
  const resBox = document.getElementById(`ping-res-${nodeId}`);
  if (btnElem) {
    btnElem.disabled = true;
    btnElem.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Pinging...`;
  }
  if (resBox) {
    resBox.innerHTML = `<span style="color:var(--text-muted);">Probing Matter &amp; IPv6...</span>`;
  }

  try {
    const res = await fetch(apiPath("/api/matter/ping_node"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ node_id: nodeId, ipv6_address: ipv6Address || null }),
    });
    const data = await res.json();
    const mOk = data.matter_ping?.success;
    const icmp = data.icmpv6_ping;

    let parts = [];
    parts.push(mOk ? `<span style="color:#34d399;">Matter: OK</span>` : `<span style="color:#f87171;">Matter: Fail</span>`);
    if (icmp) {
      parts.push(
        icmp.reachable
          ? `<span style="color:#34d399;">ICMPv6: ${icmp.rtt_ms ?? '<1'}ms</span>`
          : `<span style="color:#f87171;">ICMPv6: Timeout</span>`
      );
    }
    if (resBox) resBox.innerHTML = parts.join(" | ");
  } catch (err) {
    if (resBox) resBox.innerHTML = `<span style="color:var(--color-danger);">Error: ${err.message}</span>`;
  } finally {
    if (btnElem) {
      btnElem.disabled = false;
      btnElem.innerHTML = `<i class="fa-solid fa-bolt"></i> Ping`;
    }
  }
}

/* AI Diagnostics Execution */
async function runAIDiagnosis() {
  const loading = document.getElementById("ai-loading-indicator");
  const resultsCard = document.getElementById("ai-results-container");
  const reportBody = document.getElementById("ai-report-body");
  const userNotes = document.getElementById("user-symptoms").value;
  const studioProvider = document.getElementById("studio-provider")?.value || document.getElementById("cfg-provider")?.value;
  const studioModel = document.getElementById("studio-model")?.value || document.getElementById("cfg-model")?.value;

  loading.classList.remove("hidden");
  resultsCard.classList.add("hidden");

  try {
    const res = await fetch(apiPath("/api/diagnostics/analyze"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_notes: userNotes,
        use_cached_scan: true,
        ai_provider: studioProvider,
        ai_model: studioModel,
      }),
    });

    const data = await res.json();
    loading.classList.add("hidden");
    resultsCard.classList.remove("hidden");

    if (data.telemetry) {
      currentTelemetry = data.telemetry;
      renderKPIs(currentTelemetry);
      renderRulesAndTables(currentTelemetry);
    }

    if (data.ai_result && data.ai_result.success) {
      document.getElementById("report-model-badge").innerText = `${data.ai_result.provider.toUpperCase()} (${data.ai_result.model})`;
      reportBody.innerHTML = marked.parse(data.ai_result.analysis);
      fetchStatus();
    } else {
      const errMsg = (data.ai_result && data.ai_result.error) || "AI diagnosis could not be completed.";
      const isKeyMissing = errMsg.toLowerCase().includes("missing or invalid api key") || errMsg.toLowerCase().includes("empty or invalid");
      reportBody.innerHTML = `
        <div class="badge badge-danger" style="margin-bottom: 12px;"><i class="fa-solid fa-triangle-exclamation"></i> ${isKeyMissing ? 'AI API Key Required' : 'AI Request Error'}</div>
        <p>${escapeHtml(errMsg)}</p>
        ${isKeyMissing ? `<p style="margin-top: 10px;">Open the <strong>Settings &amp; API Keys</strong> tab, enter your API key, and click <strong>Save Settings</strong>.</p>` : `<p style="margin-top: 10px; color: var(--text-muted);">Click <strong>Run AI Diagnosis on Live Scan</strong> to retry or select a different model above.</p>`}
      `;
    }
  } catch (err) {
    loading.classList.add("hidden");
    resultsCard.classList.remove("hidden");
    reportBody.innerHTML = `<p style="color:var(--color-danger)">Network error: ${escapeHtml(err.message)}</p>`;
  }
}

async function runManualLogAnalysis() {
  const logContent = document.getElementById("manual-log-input").value.trim();
  if (!logContent) {
    alert("Please click 'Load Latest Live Scan JSON' or paste diagnostic logs first.");
    return;
  }

  const studioProvider = document.getElementById("studio-provider")?.value || document.getElementById("cfg-provider")?.value;
  const studioModel = document.getElementById("studio-model")?.value || document.getElementById("cfg-model")?.value;

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
      body: JSON.stringify({
        log_content: logContent,
        ai_provider: studioProvider,
        ai_model: studioModel,
      }),
    });

    const data = await res.json();
    loading.classList.add("hidden");
    resultsCard.classList.remove("hidden");

    if (data.ai_result && data.ai_result.success) {
      document.getElementById("report-model-badge").innerText = `${data.ai_result.provider.toUpperCase()} (${data.ai_result.model})`;
      reportBody.innerHTML = marked.parse(data.ai_result.analysis);
    } else {
      reportBody.innerHTML = `<p style="color:var(--color-danger)">${escapeHtml(data.ai_result?.error || 'Analysis failed')}</p>`;
    }
  } catch (err) {
    loading.classList.add("hidden");
    resultsCard.classList.remove("hidden");
    reportBody.innerHTML = `<p style="color:var(--color-danger)">Error: ${escapeHtml(err.message)}</p>`;
  }
}

/* Topology Graph (Real Cluster 0x0035 Links) */
async function fetchAndRenderTopology() {
  try {
    const res = await fetch(apiPath("/api/topology"));
    if (!res.ok) return;
    const data = await res.json();
    renderTopologyData(data);
  } catch (err) {
    console.error("Topology fetch failed:", err);
  }
}

let lastTopologyData = { nodes: [], edges: [] };

function renderTopologyData(data) {
  if (!data) return;
  lastTopologyData = data;
  dispatchTopologyRender();

  const brs = (data.nodes || []).filter(n => n.type === "border_router");
  const scanElem = document.getElementById("topology-last-scan");
  const countElem = document.getElementById("topology-router-count");
  if (scanElem) {
    const now = new Date();
    scanElem.innerText = `Last scanned: ${now.toLocaleTimeString()}`;
  }
  if (countElem) {
    const brNames = brs.map(b => b.label).join(", ");
    countElem.innerText = `Discovered Border Routers (${brs.length}): ${brNames || 'None detected yet'}`;
  }
}

function dispatchTopologyRender() {
  if (!lastTopologyData) return;
  const nodes = lastTopologyData.nodes || [];
  const edges = lastTopologyData.edges || [];
  const mode = topologyPhysicsState.layoutMode || "force";

  const svg = document.getElementById("mesh-svg");
  const matrixContainer = document.getElementById("topology-matrix-container");
  if (!svg || !matrixContainer) return;

  if (topologyPhysicsState.animFrameId) {
    cancelAnimationFrame(topologyPhysicsState.animFrameId);
    topologyPhysicsState.animFrameId = null;
  }

  if (mode === "matrix") {
    svg.style.display = "none";
    matrixContainer.classList.remove("hidden");
    renderSignalMatrix(matrixContainer, nodes, edges);
    return;
  }

  svg.style.display = "block";
  matrixContainer.classList.add("hidden");

  if (mode === "force") {
    renderSvgTopology(nodes, edges);
  } else if (mode === "transit") {
    renderTransitMap(nodes, edges);
  } else if (mode === "sankey") {
    renderSankeyFlow(nodes, edges);
  } else if (mode === "radar") {
    renderRadarScope(nodes, edges);
  } else if (mode === "sunburst") {
    renderSunburst(nodes, edges);
  } else if (mode === "chord") {
    renderChordBundle(nodes, edges);
  } else {
    renderSvgTopology(nodes, edges);
  }
}

function showNodeInspector(n) {
  if (!n) return;
  const panel = document.getElementById("node-inspector");
  const title = document.getElementById("inspector-title");
  const content = document.getElementById("inspector-content");
  if (!panel || !title || !content) return;

  panel.classList.remove("hidden");
  title.innerText = `${n.label || 'Device'} (${n.routing_role || (n.type ? n.type.replace('_', ' ').toUpperCase() : 'THREAD DEVICE')})${n.preferred ? ' ★ Preferred Router' : ''}`;
  const hasMatterNodeId = n.node_id !== undefined && n.node_id !== null;
  content.innerHTML = `
    <div style="font-size: 13px; line-height: 1.6;">
      <div><strong>Status:</strong> <span class="badge ${n.status === 'online' ? 'badge-success' : 'badge-warning'}">${(n.status || 'ONLINE').toUpperCase()}</span></div>
      ${n.ha_area ? `<div><strong>Area / Room:</strong> <span class="badge badge-info">📍 ${escapeHtml(n.ha_area)}</span></div>` : ''}
      ${n.rssi !== null && n.rssi !== undefined ? `<div><strong>Signal Strength:</strong> <code>${escapeHtml(String(n.rssi))} dBm</code></div>` : ''}
      <div><strong>Telemetry:</strong> ${escapeHtml(n.details || 'Cluster 0x0035 Thread link active')}</div>
      ${hasMatterNodeId ? `
        <div style="margin-top: 10px; display: flex; gap: 8px; align-items: center;">
          <button type="button" id="btn-inspector-purge" class="btn btn-outline" style="font-size: 11px; padding: 4px 12px; border-color: #ef444488; color: #f87171;">
            <i class="fa-solid fa-trash-can"></i> Purge Node #${n.node_id} from Network
          </button>
        </div>
      ` : ''}
    </div>
  `;
  if (hasMatterNodeId) {
    const btnInspPurge = document.getElementById("btn-inspector-purge");
    if (btnInspPurge) {
      btnInspPurge.addEventListener("click", () => {
        triggerPurgeNode(n.node_id, n.label || `Node #${n.node_id}`, btnInspPurge);
      });
    }
  }
}

function renderEmptyTopology(svg, width, height) {
  svg.innerHTML = "";
  const cx = width / 2;
  const cy = height / 2;
  const textGroup = document.createElementNS("http://www.w3.org/2000/svg", "g");

  const icon = document.createElementNS("http://www.w3.org/2000/svg", "text");
  icon.setAttribute("x", cx);
  icon.setAttribute("y", cy - 15);
  icon.setAttribute("fill", "#64748b");
  icon.setAttribute("font-size", "36");
  icon.setAttribute("text-anchor", "middle");
  icon.textContent = "📡";
  textGroup.appendChild(icon);

  const title = document.createElementNS("http://www.w3.org/2000/svg", "text");
  title.setAttribute("x", cx);
  title.setAttribute("y", cy + 22);
  title.setAttribute("fill", "#e2e8f0");
  title.setAttribute("font-size", "15");
  title.setAttribute("font-weight", "600");
  title.setAttribute("text-anchor", "middle");
  title.textContent = "No Live Thread Border Routers or Matter Devices Discovered Yet";
  textGroup.appendChild(title);

  const subtitle = document.createElementNS("http://www.w3.org/2000/svg", "text");
  subtitle.setAttribute("x", cx);
  subtitle.setAttribute("y", cy + 46);
  subtitle.setAttribute("fill", "#94a3b8");
  subtitle.setAttribute("font-size", "12");
  subtitle.setAttribute("text-anchor", "middle");
  subtitle.textContent = "Click '2. Scan Selected Network' above to probe mDNS (_meshcop._udp), OTBR, and Matter Server.";
  textGroup.appendChild(subtitle);

  svg.appendChild(textGroup);
}

function renderSvgTopology(nodes, edges) {
  const svg = document.getElementById("mesh-svg");
  if (!svg) return;

  if (topologyPhysicsState.animFrameId) {
    cancelAnimationFrame(topologyPhysicsState.animFrameId);
    topologyPhysicsState.animFrameId = null;
  }

  svg.innerHTML = "";
  const rect = svg.getBoundingClientRect();
  const width = Math.max(rect.width || svg.clientWidth || 880, 600);
  const height = Math.max(rect.height || 540, 480);
  const cx = width / 2;
  const cy = height / 2;

  if (!nodes || nodes.length === 0) {
    renderEmptyTopology(svg, width, height);
    return;
  }

  // Root viewport group for pan & zoom
  const viewportG = document.createElementNS("http://www.w3.org/2000/svg", "g");
  const edgesG = document.createElementNS("http://www.w3.org/2000/svg", "g");
  const nodesG = document.createElementNS("http://www.w3.org/2000/svg", "g");
  viewportG.appendChild(edgesG);
  viewportG.appendChild(nodesG);
  svg.appendChild(viewportG);

  // Calculate Border Router partition / affinity mapping
  const affinityData = resolveBorderRouterAffinity(nodes, edges);
  topologyPhysicsState.affinityData = affinityData;

  // Preserve previous positions when possible so re-scans transition smoothly
  const prevPosById = {};
  (topologyPhysicsState.nodes || []).forEach(pn => {
    prevPosById[pn.id] = { x: pn.x, y: pn.y };
  });

  const simNodes = [];
  const nodeById = {};

  nodes.forEach((n, idx) => {
    const angle = (2 * Math.PI * idx) / Math.max(nodes.length, 1);
    let initRadius = 150;
    if (n.type === "border_router") initRadius = nodes.length > 4 ? 85 : 70;
    else if (n.type === "router") initRadius = 155;
    else initRadius = 215;

    // Scale initial distance by signal strength if available (stronger RSSI starts closer to center)
    if (n.rssi !== null && n.rssi !== undefined) {
      const rssiNorm = Math.max(0, Math.min(1, (-45 - Number(n.rssi)) / 50));
      initRadius = 85 + rssiNorm * 165;
    }

    const prev = prevPosById[n.id];
    const x = prev ? prev.x : cx + Math.cos(angle) * initRadius + (Math.random() - 0.5) * 20;
    const y = prev ? prev.y : cy + Math.sin(angle) * initRadius + (Math.random() - 0.5) * 20;

    let radius = 21;
    if (n.type === "border_router") {
      radius = n.preferred ? 28 : 25;
    } else if (n.type === "end_device") {
      radius = 17;
    }
    const fill = getNodeColor(n, topologyPhysicsState.colorMode, affinityData.brMap, affinityData.nodeAffinity);

    const simNode = {
      ...n,
      x,
      y,
      vx: 0,
      vy: 0,
      radius,
      fill,
      phase: idx * 1.37,
      dragging: false,
    };
    simNodes.push(simNode);
    nodeById[n.id] = simNode;
  });

  // Build physics edges with target spring distance derived from real RF RSSI / LQI / Ping RTT
  const simEdges = [];
  edges.forEach((e) => {
    const src = nodeById[e.source];
    const tgt = nodeById[e.target];
    if (!src || !tgt) return;

    let targetDist = e.target_distance || 135;
    if (!e.target_distance) {
      if (e.rssi !== null && e.rssi !== undefined) {
        const norm = Math.max(0, Math.min(1, (-45 - Number(e.rssi)) / 50));
        targetDist = Math.round(70 + norm * 155);
      } else if (tgt.rssi !== null && tgt.rssi !== undefined) {
        const norm = Math.max(0, Math.min(1, (-45 - Number(tgt.rssi)) / 50));
        targetDist = Math.round(70 + norm * 155);
      }
    }

    // Stronger signal = stiffer spring and thicker line
    const stiffness = targetDist < 105 ? 0.065 : (targetDist < 165 ? 0.045 : 0.028);
    const strokeWidth = targetDist < 105 ? "3" : (targetDist < 165 ? "2.2" : "1.6");
    const strokeColor = e.status === "warning" ? "#f59e0b" : (targetDist < 105 ? "#34d399" : "#38bdf8");

    const edgeG = document.createElementNS("http://www.w3.org/2000/svg", "g");
    const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
    line.setAttribute("stroke", strokeColor);
    line.setAttribute("stroke-width", strokeWidth);
    line.setAttribute("stroke-opacity", "0.78");
    if (e.status === "warning" || targetDist > 185) {
      line.setAttribute("stroke-dasharray", "6,4");
    }
    edgeG.appendChild(line);

    let lblBg = null;
    let lbl = null;
    if (e.label) {
      lblBg = document.createElementNS("http://www.w3.org/2000/svg", "rect");
      lblBg.setAttribute("rx", "4");
      lblBg.setAttribute("ry", "4");
      lblBg.setAttribute("fill", "#0f172acc");
      edgeG.appendChild(lblBg);

      lbl = document.createElementNS("http://www.w3.org/2000/svg", "text");
      lbl.setAttribute("fill", e.status === "warning" ? "#fbbf24" : (targetDist < 105 ? "#6ee7b7" : "#bae6fd"));
      lbl.setAttribute("font-size", "10");
      lbl.setAttribute("font-weight", "600");
      lbl.setAttribute("text-anchor", "middle");
      lbl.textContent = e.label;
      edgeG.appendChild(lbl);
    }

    edgesG.appendChild(edgeG);
    simEdges.push({
      ...e,
      src,
      tgt,
      targetDist,
      stiffness,
      lineElem: line,
      lblElem: lbl,
      lblBgElem: lblBg,
      groupElem: edgeG,
    });
  });

  // Create SVG elements for each node
  simNodes.forEach((n) => {
    const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
    g.style.cursor = "grab";

    // Outer search/preferred halo ring
    const halo = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    halo.setAttribute("r", n.radius + 7);
    halo.setAttribute("fill", "none");
    halo.setAttribute("stroke", n.preferred ? "#10b981" : "#38bdf8");
    halo.setAttribute("stroke-width", n.preferred ? "2.5" : "0");
    halo.setAttribute("stroke-dasharray", n.preferred ? "4,3" : "none");
    halo.setAttribute("opacity", n.preferred ? "0.85" : "0");
    g.appendChild(halo);

    const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    circle.setAttribute("r", n.radius);
    circle.setAttribute("fill", n.fill);
    circle.setAttribute("stroke", n.is_target === false ? "#ef4444" : (n.preferred ? "#34d399" : "#0f172a"));
    circle.setAttribute("stroke-width", n.preferred ? "3.5" : "3");
    g.appendChild(circle);

    // Role / Preferred icon badge inside circle
    const badgeText = document.createElementNS("http://www.w3.org/2000/svg", "text");
    badgeText.setAttribute("y", "4");
    badgeText.setAttribute("fill", "#ffffff");
    badgeText.setAttribute("font-size", n.type === "border_router" ? "11" : "10");
    badgeText.setAttribute("font-weight", "700");
    badgeText.setAttribute("text-anchor", "middle");
    badgeText.style.pointerEvents = "none";
    badgeText.textContent = n.type === "border_router" ? (n.preferred ? "★ TBR" : "TBR") : (n.type === "router" ? "RTR" : "SED");
    g.appendChild(badgeText);

    const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
    text.setAttribute("y", n.radius + 15);
    text.setAttribute("fill", "#f8fafc");
    text.setAttribute("font-size", "12");
    text.setAttribute("font-weight", "600");
    text.setAttribute("text-anchor", "middle");
    text.style.pointerEvents = "none";
    text.textContent = n.label;
    g.appendChild(text);

    // Sub-label showing RLOC16 or signal RSSI / RTT
    const subParts = [];
    if (n.rloc16) subParts.push(n.rloc16);
    if (n.rssi !== null && n.rssi !== undefined) subParts.push(`${n.rssi} dBm`);
    else if (n.rtt_ms !== null && n.rtt_ms !== undefined) subParts.push(`${n.rtt_ms} ms`);
    if (subParts.length > 0) {
      const subText = document.createElementNS("http://www.w3.org/2000/svg", "text");
      subText.setAttribute("y", n.radius + 28);
      subText.setAttribute("fill", "#38bdf8");
      subText.setAttribute("font-size", "10");
      subText.setAttribute("text-anchor", "middle");
      subText.style.pointerEvents = "none";
      subText.textContent = subParts.join(" • ");
      g.appendChild(subText);
    }

    // Pointer drag & click inspector
    let dragMoved = false;
    g.addEventListener("pointerdown", (ev) => {
      ev.stopPropagation();
      n.dragging = true;
      dragMoved = false;
      g.style.cursor = "grabbing";
      topologyPhysicsState.energy = Math.max(topologyPhysicsState.energy, 0.85);
      g.setPointerCapture(ev.pointerId);
    });

    g.addEventListener("pointermove", (ev) => {
      if (!n.dragging) return;
      dragMoved = true;
      const svgRect = svg.getBoundingClientRect();
      const mouseX = (ev.clientX - svgRect.left - topologyPhysicsState.panX) / topologyPhysicsState.zoom;
      const mouseY = (ev.clientY - svgRect.top - topologyPhysicsState.panY) / topologyPhysicsState.zoom;
      n.x = mouseX;
      n.y = mouseY;
      n.vx = 0;
      n.vy = 0;
      topologyPhysicsState.energy = Math.max(topologyPhysicsState.energy, 0.65);
    });

    const endDrag = (ev) => {
      if (!n.dragging) return;
      n.dragging = false;
      g.style.cursor = "grab";
      try {
        g.releasePointerCapture(ev.pointerId);
      } catch (_) {}
      if (!dragMoved) {
        showNodeInspector(n);
      }
    };

    g.addEventListener("pointerup", endDrag);
    g.addEventListener("pointercancel", endDrag);

    nodesG.appendChild(g);
    n.elem = g;
    n.haloElem = halo;
    n.circleElem = circle;
  });

  // Canvas background pan & wheel zoom
  let isPanning = false;
  let panStartX = 0;
  let panStartY = 0;

  svg.onpointerdown = (ev) => {
    if (ev.target !== svg) return;
    isPanning = true;
    panStartX = ev.clientX - topologyPhysicsState.panX;
    panStartY = ev.clientY - topologyPhysicsState.panY;
    svg.style.cursor = "grabbing";
  };

  window.addEventListener("pointermove", (ev) => {
    if (!isPanning) return;
    topologyPhysicsState.panX = ev.clientX - panStartX;
    topologyPhysicsState.panY = ev.clientY - panStartY;
  });

  window.addEventListener("pointerup", () => {
    if (isPanning) {
      isPanning = false;
      svg.style.cursor = "grab";
    }
  });

  svg.onwheel = (ev) => {
    ev.preventDefault();
    const scaleFactor = ev.deltaY < 0 ? 1.1 : 0.9;
    const newZoom = Math.max(0.45, Math.min(2.5, topologyPhysicsState.zoom * scaleFactor));
    const svgRect = svg.getBoundingClientRect();
    const mx = ev.clientX - svgRect.left;
    const my = ev.clientY - svgRect.top;
    topologyPhysicsState.panX = mx - ((mx - topologyPhysicsState.panX) * newZoom) / topologyPhysicsState.zoom;
    topologyPhysicsState.panY = my - ((my - topologyPhysicsState.panY) * newZoom) / topologyPhysicsState.zoom;
    topologyPhysicsState.zoom = newZoom;
  };

  topologyPhysicsState.nodes = simNodes;
  topologyPhysicsState.edges = simEdges;
  topologyPhysicsState.energy = 1.0;

  computeLayoutTargetPositions(simNodes, simEdges, width, height, topologyPhysicsState.layoutMode);
  updateTopologySearchHighlight();
  applyTopologyVisibilityFilter();
  updateTopologyLegend();

  let tickCount = 0;
  const stepPhysics = () => {
    tickCount++;
    const t = tickCount * 0.025;
    const N = simNodes.length;
    const energy = topologyPhysicsState.energy;

    // 0. Layout Mode Target Springs (Tree / Radial / Room)
    if (topologyPhysicsState.layoutMode !== "force") {
      for (let i = 0; i < N; i++) {
        const n = simNodes[i];
        if (!n.dragging && n.targetX !== null && n.targetX !== undefined && n.targetY !== null && n.targetY !== undefined) {
          const kRestoring = 0.085;
          n.vx += (n.targetX - n.x) * kRestoring;
          n.vy += (n.targetY - n.y) * kRestoring;
        }
      }
    }

    // 1. All-pairs Coulomb repulsion so nodes and labels don't overlap
    for (let i = 0; i < N; i++) {
      const a = simNodes[i];
      for (let j = i + 1; j < N; j++) {
        const b = simNodes[j];
        let dx = b.x - a.x;
        let dy = b.y - a.y;
        let distSq = dx * dx + dy * dy;
        if (distSq < 4) {
          dx = (Math.random() - 0.5) * 4;
          dy = (Math.random() - 0.5) * 4;
          distSq = dx * dx + dy * dy;
        }
        const dist = Math.sqrt(distSq);
        const minSep = a.radius + b.radius + 55;
        let repulse = 2400 / distSq;
        if (dist < minSep) {
          repulse += (minSep - dist) * 0.18;
        }
        const fx = (dx / dist) * repulse;
        const fy = (dy / dist) * repulse;
        if (!a.dragging) {
          a.vx -= fx;
          a.vy -= fy;
        }
        if (!b.dragging) {
          b.vx += fx;
          b.vy += fy;
        }
      }
    }

    // 2. RF Signal-Proximity Spring Force along edges (Hooke's law toward targetDist)
    const edgeSpringScale = topologyPhysicsState.layoutMode === "force" ? 1.0 : 0.18;
    for (let i = 0; i < simEdges.length; i++) {
      const e = simEdges[i];
      const a = e.src;
      const b = e.tgt;
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const dist = Math.sqrt(dx * dx + dy * dy) || 1;
      const displacement = dist - e.targetDist;
      const force = displacement * e.stiffness * edgeSpringScale;
      const fx = (dx / dist) * force;
      const fy = (dy / dist) * force;

      if (!a.dragging) {
        a.vx += fx;
        a.vy += fy;
      }
      if (!b.dragging) {
        b.vx -= fx;
        b.vy -= fy;
      }
    }

    // 3. Soft center gravity + subtle organic micro-motion so topology stays alive
    const pad = 48;
    for (let i = 0; i < N; i++) {
      const n = simNodes[i];
      if (!n.dragging) {
        if (topologyPhysicsState.layoutMode === "force") {
          const gravity = n.type === "border_router" ? 0.012 : 0.005;
          n.vx += (cx - n.x) * gravity;
          n.vy += (cy - n.y) * gravity;

          // Continuous subtle harmonic float proportional to signal distance
          n.vx += Math.sin(t + n.phase) * 0.045;
          n.vy += Math.cos(t * 0.85 + n.phase) * 0.045;
        }

        // Damping
        n.vx *= 0.82;
        n.vy *= 0.82;

        n.x += n.vx * Math.max(energy, 0.35);
        n.y += n.vy * Math.max(energy, 0.35);

        // Soft viewport boundary bounce
        if (n.x < pad) { n.x = pad; n.vx *= -0.5; }
        if (n.x > width - pad) { n.x = width - pad; n.vx *= -0.5; }
        if (n.y < pad) { n.y = pad; n.vy *= -0.5; }
        if (n.y > height - pad) { n.y = height - pad; n.vy *= -0.5; }
      }

      n.elem.setAttribute("transform", `translate(${n.x.toFixed(1)}, ${n.y.toFixed(1)})`);
    }

    // 4. Update edge lines & midpoint labels
    for (let i = 0; i < simEdges.length; i++) {
      const e = simEdges[i];
      e.lineElem.setAttribute("x1", e.src.x.toFixed(1));
      e.lineElem.setAttribute("y1", e.src.y.toFixed(1));
      e.lineElem.setAttribute("x2", e.tgt.x.toFixed(1));
      e.lineElem.setAttribute("y2", e.tgt.y.toFixed(1));

      if (e.lblElem && e.lblBgElem) {
        const mx = (e.src.x + e.tgt.x) / 2;
        const my = (e.src.y + e.tgt.y) / 2;
        const textLen = (e.label || "").length * 5.6 + 10;
        e.lblBgElem.setAttribute("x", (mx - textLen / 2).toFixed(1));
        e.lblBgElem.setAttribute("y", (my - 10).toFixed(1));
        e.lblBgElem.setAttribute("width", textLen.toFixed(1));
        e.lblBgElem.setAttribute("height", "14");
        e.lblElem.setAttribute("x", mx.toFixed(1));
        e.lblElem.setAttribute("y", (my + 1).toFixed(1));
      }
    }

    viewportG.setAttribute(
      "transform",
      `translate(${topologyPhysicsState.panX.toFixed(1)}, ${topologyPhysicsState.panY.toFixed(1)}) scale(${topologyPhysicsState.zoom.toFixed(3)})`
    );

    topologyPhysicsState.energy = Math.max(0.35, topologyPhysicsState.energy * 0.992);
    topologyPhysicsState.animFrameId = requestAnimationFrame(stepPhysics);
  };

  topologyPhysicsState.animFrameId = requestAnimationFrame(stepPhysics);
}

const BR_AFFINITY_PALETTE = [
  "#3b82f6", // Blue
  "#10b981", // Emerald
  "#f59e0b", // Amber
  "#ec4899", // Pink
  "#8b5cf6", // Purple
  "#06b6d4", // Cyan
  "#f97316", // Orange
  "#14b8a6", // Teal
];

function resolveBorderRouterAffinity(nodes, edges) {
  const brMap = {};
  const tbrNodes = (nodes || []).filter(n => n.type === "border_router");

  tbrNodes.forEach((tbr, idx) => {
    const color = BR_AFFINITY_PALETTE[idx % BR_AFFINITY_PALETTE.length];
    brMap[tbr.id] = {
      id: tbr.id,
      label: tbr.label || `TBR ${idx + 1}`,
      color: color,
    };
  });

  const adj = {};
  (nodes || []).forEach(n => { adj[n.id] = []; });
  (edges || []).forEach(e => {
    const s = typeof e.source === "object" ? e.source.id : e.source;
    const t = typeof e.target === "object" ? e.target.id : e.target;
    if (adj[s]) adj[s].push(t);
    if (adj[t]) adj[t].push(s);
  });

  const nodeAffinity = {};
  tbrNodes.forEach(tbr => {
    nodeAffinity[tbr.id] = brMap[tbr.id];
  });

  const queue = tbrNodes.map(tbr => ({ id: tbr.id, br: brMap[tbr.id] }));
  const visited = new Set(tbrNodes.map(tbr => tbr.id));

  while (queue.length > 0) {
    const { id, br } = queue.shift();
    const neighbors = adj[id] || [];
    for (const nbrId of neighbors) {
      if (!visited.has(nbrId)) {
        visited.add(nbrId);
        nodeAffinity[nbrId] = br;
        queue.push({ id: nbrId, br });
      }
    }
  }

  return { brMap, nodeAffinity };
}

function getNodeColor(n, colorMode, brMap, nodeAffinity) {
  if (colorMode === "rssi") {
    if (n.status === "offline") return "#64748b";
    const rssi = (n.rssi !== null && n.rssi !== undefined) ? Number(n.rssi) : null;
    if (rssi === null) return "#64748b";
    if (rssi >= -60) return "#10b981";
    if (rssi >= -70) return "#84cc16";
    if (rssi >= -80) return "#f59e0b";
    return "#ef4444";
  }

  if (colorMode === "affinity") {
    const aff = nodeAffinity && nodeAffinity[n.id];
    if (aff && aff.color) return aff.color;
    return "#64748b";
  }

  if (colorMode === "power") {
    if (n.status === "offline") return "#ef4444";
    if (n.type === "end_device") return "#a855f7";
    return "#06b6d4";
  }

  // Default: "role"
  if (n.status === "offline") return "#ef4444";
  if (n.status === "weak" || n.status === "warning") return "#f59e0b";
  if (n.type === "border_router") {
    if (n.vendor === "nest") return "#4285F4";
    if (n.vendor === "apple") return "#94a3b8";
    if (n.vendor === "ha") return "#03A9F4";
    return "#3b82f6";
  }
  if (n.type === "end_device") {
    return "#8b5cf6";
  }
  return "#10b981";
}

function computeLayoutTargetPositions(simNodes, simEdges, width, height, layoutMode) {
  simNodes = simNodes || topologyPhysicsState.nodes || [];
  if (!simNodes.length) return;

  const svg = document.getElementById("mesh-svg");
  if (!width || !height) {
    const rect = svg ? svg.getBoundingClientRect() : null;
    width = Math.max((rect && rect.width) || (svg && svg.clientWidth) || 880, 600);
    height = Math.max((rect && rect.height) || 540, 480);
  }
  const cx = width / 2;
  const cy = height / 2;
  layoutMode = layoutMode || topologyPhysicsState.layoutMode || "force";

  if (layoutMode === "force") {
    simNodes.forEach(n => {
      n.targetX = null;
      n.targetY = null;
    });
    return;
  }

  if (layoutMode === "tree") {
    const tbrs = simNodes.filter(n => n.type === "border_router");
    const routers = simNodes.filter(n => n.type === "router");
    const seds = simNodes.filter(n => n.type !== "border_router" && n.type !== "router");

    const assignTier = (tierNodes, yPos) => {
      const count = tierNodes.length;
      if (count === 0) return;
      const margin = Math.min(width * 0.12, 100);
      const span = width - margin * 2;
      tierNodes.forEach((n, idx) => {
        n.targetX = count === 1 ? cx : margin + (idx / (count - 1)) * span;
        n.targetY = yPos;
      });
    };

    assignTier(tbrs, height * 0.16);
    assignTier(routers, height * 0.50);
    assignTier(seds, height * 0.82);
    return;
  }

  if (layoutMode === "radial") {
    const tbrs = simNodes.filter(n => n.type === "border_router");
    const routers = simNodes.filter(n => n.type === "router");
    const seds = simNodes.filter(n => n.type !== "border_router" && n.type !== "router");

    let centerNode = tbrs.find(t => t.preferred) || tbrs[0] || simNodes[0];
    centerNode.targetX = cx;
    centerNode.targetY = cy;

    const innerNodes = [...tbrs.filter(t => t !== centerNode), ...routers];
    const outerNodes = seds;

    const minDim = Math.min(width, height);
    const rInner = minDim * 0.22;
    const rOuter = minDim * 0.40;

    const placeRing = (nodes, radius) => {
      const count = nodes.length;
      if (count === 0) return;
      nodes.forEach((n, idx) => {
        const angle = (2 * Math.PI * idx) / count - Math.PI / 2;
        n.targetX = cx + Math.cos(angle) * radius;
        n.targetY = cy + Math.sin(angle) * radius;
      });
    };

    placeRing(innerNodes, rInner);
    placeRing(outerNodes, rOuter);
    return;
  }

  if (layoutMode === "room") {
    const groups = {};
    simNodes.forEach(n => {
      const area = (n.ha_area && n.ha_area.trim()) || "Unassigned";
      if (!groups[area]) groups[area] = [];
      groups[area].push(n);
    });

    const areaNames = Object.keys(groups);
    const numAreas = areaNames.length;
    const areaRadius = Math.min(width, height) * 0.32;

    areaNames.forEach((area, aIdx) => {
      const areaAngle = (2 * Math.PI * aIdx) / numAreas - Math.PI / 2;
      const areaCenterX = numAreas === 1 ? cx : cx + Math.cos(areaAngle) * areaRadius;
      const areaCenterY = numAreas === 1 ? cy : cy + Math.sin(areaAngle) * areaRadius;

      const groupNodes = groups[area];
      const gCount = groupNodes.length;
      const subRadius = Math.min(75, 24 + gCount * 7);

      groupNodes.forEach((n, idx) => {
        if (gCount === 1) {
          n.targetX = areaCenterX;
          n.targetY = areaCenterY;
        } else {
          const subAngle = (2 * Math.PI * idx) / gCount;
          n.targetX = areaCenterX + Math.cos(subAngle) * subRadius;
          n.targetY = areaCenterY + Math.sin(subAngle) * subRadius;
        }
      });
    });
    return;
  }
}

function updateTopologyNodeColors() {
  const nodes = topologyPhysicsState.nodes || [];
  const colorMode = topologyPhysicsState.colorMode || "role";
  const { brMap, nodeAffinity } = topologyPhysicsState.affinityData || { brMap: {}, nodeAffinity: {} };

  nodes.forEach(n => {
    const fill = getNodeColor(n, colorMode, brMap, nodeAffinity);
    n.fill = fill;
    if (n.circleElem) {
      n.circleElem.setAttribute("fill", fill);
    }
  });
}

function updateTopologyLegend() {
  const legend = document.getElementById("topology-legend");
  if (!legend) return;

  const colorMode = topologyPhysicsState.colorMode || "role";
  const { brMap } = topologyPhysicsState.affinityData || { brMap: {} };

  if (colorMode === "rssi") {
    legend.innerHTML = `
      <span><span class="dot" style="background: #10b981;"></span> Excellent (&gt; -60 dBm)</span>
      <span><span class="dot" style="background: #84cc16;"></span> Good (-60 to -70 dBm)</span>
      <span><span class="dot" style="background: #f59e0b;"></span> Fair (-70 to -80 dBm)</span>
      <span><span class="dot" style="background: #ef4444;"></span> Poor (&lt; -80 dBm)</span>
      <span><span class="dot" style="background: #64748b;"></span> Offline / Unknown</span>
    `;
    return;
  }

  if (colorMode === "affinity") {
    const brKeys = Object.keys(brMap || {});
    if (brKeys.length === 0) {
      legend.innerHTML = `<span><span class="dot" style="background: #64748b;"></span> No Border Routers Detected</span>`;
      return;
    }
    legend.innerHTML = brKeys.map(k => {
      const br = brMap[k];
      return `<span><span class="dot" style="background: ${br.color};"></span> ${escapeHtml(br.label)}</span>`;
    }).join("") + `<span><span class="dot" style="background: #64748b;"></span> Unpartitioned</span>`;
    return;
  }

  if (colorMode === "power") {
    legend.innerHTML = `
      <span><span class="dot" style="background: #06b6d4;"></span> Mains Powered (Always-On Backbone)</span>
      <span><span class="dot" style="background: #a855f7;"></span> Battery Powered (Sleepy Sensor / SED)</span>
      <span><span class="dot" style="background: #ef4444;"></span> Offline</span>
    `;
    return;
  }

  // Default: role
  legend.innerHTML = `
    <span><span class="dot" style="background: #4285F4;"></span> Google Nest TBR</span>
    <span><span class="dot" style="background: #94a3b8;"></span> Apple TV / HomePod TBR</span>
    <span><span class="dot" style="background: #03A9F4;"></span> HA OTBR (ZBT-1)</span>
    <span><span class="dot" style="background: #10b981;"></span> Thread Router (Mains)</span>
    <span><span class="dot" style="background: #8b5cf6;"></span> Battery End Device (SED)</span>
    <span><span class="dot" style="background: #f59e0b;"></span> Weak Signal / Warning</span>
    <span><span class="dot" style="background: #ef4444;"></span> Offline</span>
  `;
}

function applyTopologyVisibilityFilter() {
  const filter = topologyPhysicsState.filterMode || "all";
  const showLabels = topologyPhysicsState.showLinkLabels !== false;
  const nodes = topologyPhysicsState.nodes || [];
  const edges = topologyPhysicsState.edges || [];

  const hiddenNodeIds = new Set();

  nodes.forEach(n => {
    let visible = true;
    if (filter === "routers_only") {
      if (n.type === "end_device") visible = false;
    } else if (filter === "end_only") {
      if (n.type !== "end_device") visible = false;
    } else if (filter === "online_only") {
      if (n.status === "offline") visible = false;
    }

    if (!visible) hiddenNodeIds.add(n.id);
    if (n.elem) {
      n.elem.style.display = visible ? "" : "none";
    }
  });

  edges.forEach(e => {
    const sId = e.src ? e.src.id : null;
    const tId = e.tgt ? e.tgt.id : null;
    const edgeVisible = !hiddenNodeIds.has(sId) && !hiddenNodeIds.has(tId);

    if (e.groupElem) {
      e.groupElem.style.display = edgeVisible ? "" : "none";
    }
    if (e.lblElem && e.lblBgElem) {
      const lblDisplay = (edgeVisible && showLabels) ? "" : "none";
      e.lblElem.style.display = lblDisplay;
      e.lblBgElem.style.display = lblDisplay;
    }
  });
}

/* ==========================================================================
   VISUAL PERSPECTIVE 1: Subway / Transit Map (Schematic Metro Tracks)
   ========================================================================== */
function renderTransitMap(nodes, edges) {
  const svg = document.getElementById("mesh-svg");
  if (!svg) return;
  svg.innerHTML = "";
  const rect = svg.getBoundingClientRect();
  const width = Math.max(rect.width || svg.clientWidth || 880, 720);
  const height = Math.max(rect.height || 540, 500);

  if (!nodes || nodes.length === 0) {
    renderEmptyTopology(svg, width, height);
    return;
  }

  const affinity = resolveBorderRouterAffinity(nodes, edges);
  topologyPhysicsState.affinityData = affinity;

  const viewportG = document.createElementNS("http://www.w3.org/2000/svg", "g");
  svg.appendChild(viewportG);

  // Background metro coordinate grid
  const gridG = document.createElementNS("http://www.w3.org/2000/svg", "g");
  gridG.setAttribute("opacity", "0.12");
  for (let x = 40; x < width; x += 55) {
    const l = document.createElementNS("http://www.w3.org/2000/svg", "line");
    l.setAttribute("x1", x); l.setAttribute("y1", 0);
    l.setAttribute("x2", x); l.setAttribute("y2", height);
    l.setAttribute("stroke", "#475569"); l.setAttribute("stroke-width", "1");
    gridG.appendChild(l);
  }
  for (let y = 40; y < height; y += 55) {
    const l = document.createElementNS("http://www.w3.org/2000/svg", "line");
    l.setAttribute("x1", 0); l.setAttribute("y1", y);
    l.setAttribute("x2", width); l.setAttribute("y2", y);
    l.setAttribute("stroke", "#475569"); l.setAttribute("stroke-width", "1");
    gridG.appendChild(l);
  }
  viewportG.appendChild(gridG);

  const linesG = document.createElementNS("http://www.w3.org/2000/svg", "g");
  const stationsG = document.createElementNS("http://www.w3.org/2000/svg", "g");
  viewportG.appendChild(linesG);
  viewportG.appendChild(stationsG);

  const tbrs = nodes.filter(n => n.type === "border_router");
  const routers = nodes.filter(n => n.type === "router");
  const seds = nodes.filter(n => n.type !== "border_router" && n.type !== "router");

  const posMap = {};
  const tbrCount = Math.max(tbrs.length, 1);
  tbrs.forEach((tbr, idx) => {
    const y = ((idx + 1) / (tbrCount + 1)) * (height - 80) + 40;
    posMap[tbr.id] = { x: 130, y };
  });

  const rtrCount = Math.max(routers.length, 1);
  routers.forEach((rtr, idx) => {
    const col = idx % 2;
    const row = Math.floor(idx / 2);
    const rows = Math.ceil(rtrCount / 2);
    const x = 320 + col * 160;
    const y = ((row + 1) / (rows + 1)) * (height - 80) + 40;
    posMap[rtr.id] = { x, y };
  });

  const sedCount = Math.max(seds.length, 1);
  seds.forEach((sed, idx) => {
    const col = idx % 2;
    const row = Math.floor(idx / 2);
    const rows = Math.ceil(sedCount / 2);
    const x = Math.min(width - 160, 680) + col * 90;
    const y = ((row + 1) / (rows + 1)) * (height - 80) + 40;
    posMap[sed.id] = { x, y };
  });

  nodes.forEach((n, idx) => {
    if (!posMap[n.id]) {
      posMap[n.id] = { x: 220 + (idx * 45) % (width - 300), y: 80 + (idx * 35) % (height - 120) };
    }
  });

  // Draw 45°/90° Metro Track Lines
  edges.forEach((e) => {
    const sId = typeof e.source === "object" ? e.source.id : e.source;
    const tId = typeof e.target === "object" ? e.target.id : e.target;
    const p1 = posMap[sId];
    const p2 = posMap[tId];
    if (!p1 || !p2) return;

    const aff = affinity.nodeAffinity[sId] || affinity.nodeAffinity[tId] || { color: "#38bdf8" };
    const lineColor = aff.color || "#0284c7";

    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    const dx = p2.x - p1.x;
    const dy = p2.y - p1.y;
    let d = "";
    if (Math.abs(dx) > Math.abs(dy)) {
      const midX = p1.x + (dx - dy);
      d = `M ${p1.x} ${p1.y} L ${midX} ${p1.y} L ${p2.x} ${p2.y}`;
    } else {
      const midY = p1.y + (dy - dx);
      d = `M ${p1.x} ${p1.y} L ${p1.x} ${midY} L ${p2.x} ${p2.y}`;
    }
    path.setAttribute("d", d);
    path.setAttribute("fill", "none");
    path.setAttribute("stroke", lineColor);
    path.setAttribute("stroke-width", "5");
    path.setAttribute("stroke-linecap", "round");
    path.setAttribute("stroke-linejoin", "round");
    path.setAttribute("stroke-opacity", "0.85");
    linesG.appendChild(path);
  });

  // Draw Stations
  nodes.forEach((n) => {
    const pos = posMap[n.id];
    const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
    g.style.cursor = "pointer";
    g.setAttribute("transform", `translate(${pos.x.toFixed(1)}, ${pos.y.toFixed(1)})`);

    const isTbr = n.type === "border_router";
    const isRouter = n.type === "router";

    if (isTbr) {
      const outerRing = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      outerRing.setAttribute("r", "16");
      outerRing.setAttribute("fill", "#0f172a");
      outerRing.setAttribute("stroke", "#f8fafc");
      outerRing.setAttribute("stroke-width", "3");
      g.appendChild(outerRing);

      const innerCore = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      innerCore.setAttribute("r", "9");
      innerCore.setAttribute("fill", n.vendor === "nest" ? "#4285F4" : (n.vendor === "apple" ? "#94a3b8" : "#03A9F4"));
      g.appendChild(innerCore);
    } else if (isRouter) {
      const disc = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      disc.setAttribute("r", "10");
      disc.setAttribute("fill", "#ffffff");
      disc.setAttribute("stroke", "#10b981");
      disc.setAttribute("stroke-width", "3.5");
      g.appendChild(disc);
    } else {
      const tick = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      tick.setAttribute("r", "7");
      tick.setAttribute("fill", n.status === "offline" ? "#ef4444" : "#ffffff");
      tick.setAttribute("stroke", "#8b5cf6");
      tick.setAttribute("stroke-width", "2.5");
      g.appendChild(tick);
    }

    const lbl = document.createElementNS("http://www.w3.org/2000/svg", "text");
    lbl.setAttribute("x", isTbr ? -22 : 14);
    lbl.setAttribute("y", "4");
    lbl.setAttribute("fill", "#f8fafc");
    lbl.setAttribute("font-size", isTbr ? "12" : "11");
    lbl.setAttribute("font-weight", isTbr ? "700" : "600");
    lbl.setAttribute("text-anchor", isTbr ? "end" : "start");
    lbl.textContent = n.label || `Node #${n.node_id}`;
    g.appendChild(lbl);

    g.addEventListener("click", () => showNodeInspector(n));
    stationsG.appendChild(g);
    n.elem = g;
  });

  const headerG = document.createElementNS("http://www.w3.org/2000/svg", "g");
  headerG.setAttribute("transform", "translate(20, 30)");
  headerG.innerHTML = `
    <rect width="185" height="26" rx="6" fill="#0f172acc" stroke="#334155" />
    <text x="12" y="17" fill="#38bdf8" font-size="11" font-weight="700">🚇 THREAD METRO TRANSIT</text>
  `;
  svg.appendChild(headerG);
  updateTopologyLegend();
}

/* ==========================================================================
   VISUAL PERSPECTIVE 2: 2D Signal Cross-Matrix & Link Budget Heatmap
   ========================================================================== */
function renderSignalMatrix(container, nodes, edges) {
  if (!container) return;
  container.innerHTML = "";

  if (!nodes || nodes.length === 0) {
    container.innerHTML = `<div style="padding: 40px; text-align: center; color: #64748b;"><i class="fa-solid fa-satellite-dish" style="font-size: 32px; margin-bottom: 8px;"></i><p>No Thread nodes discovered yet. Click '2. Scan Selected Network' above.</p></div>`;
    return;
  }

  // Build direct adjacency lookup
  const linkMap = {};
  let totalSignalSum = 0;
  let signalCount = 0;
  let bestRssi = -999;
  let worstRssi = 999;

  (edges || []).forEach(e => {
    const s = typeof e.source === "object" ? e.source.id : e.source;
    const t = typeof e.target === "object" ? e.target.id : e.target;
    linkMap[`${s}_${t}`] = e;
    linkMap[`${t}_${s}`] = e;

    if (e.rssi !== null && e.rssi !== undefined) {
      const val = Number(e.rssi);
      totalSignalSum += val;
      signalCount++;
      if (val > bestRssi) bestRssi = val;
      if (val < worstRssi) worstRssi = val;
    }
  });

  const avgRssi = signalCount > 0 ? (totalSignalSum / signalCount).toFixed(1) : null;
  const directLinkCount = edges ? edges.length : 0;
  const maxPossibleLinks = Math.max(1, (nodes.length * (nodes.length - 1)) / 2);
  const densityPct = Math.round((directLinkCount / maxPossibleLinks) * 100);

  // Top Metric Cards
  let html = `
    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px; margin-bottom: 16px;">
      <div style="background: #0f172a; padding: 10px 14px; border-radius: 6px; border: 1px solid #334155;">
        <div style="font-size: 11px; color: #94a3b8; text-transform: uppercase;">Total Devices</div>
        <div style="font-size: 18px; font-weight: 700; color: #f8fafc; margin-top: 2px;">${nodes.length}</div>
      </div>
      <div style="background: #0f172a; padding: 10px 14px; border-radius: 6px; border: 1px solid #334155;">
        <div style="font-size: 11px; color: #94a3b8; text-transform: uppercase;">Direct RF Links</div>
        <div style="font-size: 18px; font-weight: 700; color: #38bdf8; margin-top: 2px;">${directLinkCount}</div>
      </div>
      <div style="background: #0f172a; padding: 10px 14px; border-radius: 6px; border: 1px solid #334155;">
        <div style="font-size: 11px; color: #94a3b8; text-transform: uppercase;">Mesh Density</div>
        <div style="font-size: 18px; font-weight: 700; color: #10b981; margin-top: 2px;">${densityPct}%</div>
      </div>
      <div style="background: #0f172a; padding: 10px 14px; border-radius: 6px; border: 1px solid #334155;">
        <div style="font-size: 11px; color: #94a3b8; text-transform: uppercase;">Avg Link Signal</div>
        <div style="font-size: 18px; font-weight: 700; color: ${avgRssi && Number(avgRssi) > -70 ? '#34d399' : '#f59e0b'}; margin-top: 2px;">
          ${avgRssi ? `${avgRssi} dBm` : 'N/A'}
        </div>
      </div>
    </div>

    <div style="overflow-x: auto; max-width: 100%; border: 1px solid #334155; border-radius: 6px;">
      <table class="matrix-table">
        <thead>
          <tr>
            <th class="sticky-col" style="min-width: 180px;">Device / Peer</th>
  `;

  nodes.forEach((n) => {
    const shortName = (n.label || `Node ${n.node_id}`).substring(0, 14);
    html += `<th title="${escapeHtml(n.label || '')}">${escapeHtml(shortName)}</th>`;
  });
  html += `</tr></thead><tbody>`;

  nodes.forEach((rowNode) => {
    const roleIcon = rowNode.type === "border_router" ? "📡" : (rowNode.type === "router" ? "🔁" : "🔋");
    html += `
      <tr>
        <td class="sticky-col" style="cursor: pointer;" title="Click to inspect device" onclick="showNodeInspector(lastTopologyData.nodes.find(x => x.id === '${rowNode.id}'))">
          <span style="margin-right: 6px;">${roleIcon}</span>
          <strong>${escapeHtml(rowNode.label || `Node ${rowNode.node_id}`)}</strong>
          ${rowNode.ha_area ? `<span style="font-size: 10px; color: #94a3b8; margin-left: 4px;">📍 ${escapeHtml(rowNode.ha_area)}</span>` : ''}
        </td>
    `;

    nodes.forEach((colNode) => {
      if (rowNode.id === colNode.id) {
        html += `<td style="background: #0f172a;"><span style="color: #475569;">—</span></td>`;
        return;
      }

      const link = linkMap[`${rowNode.id}_${colNode.id}`];
      if (!link) {
        html += `<td><span style="color: #334155;">·</span></td>`;
      } else {
        const rssi = link.rssi !== null && link.rssi !== undefined ? Number(link.rssi) : null;
        let bg = "#1e293b";
        let textCol = "#38bdf8";
        let badge = "LINK";

        if (rssi !== null) {
          badge = `${rssi} dBm`;
          if (rssi >= -60) { bg = "#064e3b"; textCol = "#6ee7b7"; }
          else if (rssi >= -70) { bg = "#14532d"; textCol = "#a3e635"; }
          else if (rssi >= -80) { bg = "#713f12"; textCol = "#fde047"; }
          else { bg = "#7f1d1d"; textCol = "#fca5a5"; }
        }

        html += `
          <td style="cursor: pointer;" title="Direct link between ${escapeHtml(rowNode.label)} and ${escapeHtml(colNode.label)} (${badge})" onclick="showNodeInspector(lastTopologyData.nodes.find(x => x.id === '${rowNode.id}'))">
            <span class="matrix-cell" style="background: ${bg}; color: ${textCol};">${badge}</span>
          </td>
        `;
      }
    });

    html += `</tr>`;
  });

  html += `</tbody></table></div>`;
  container.innerHTML = html;
}

/* ==========================================================================
   VISUAL PERSPECTIVE 3: Sankey / Alluvial Routing Flow
   ========================================================================== */
function renderSankeyFlow(nodes, edges) {
  const svg = document.getElementById("mesh-svg");
  if (!svg) return;
  svg.innerHTML = "";
  const rect = svg.getBoundingClientRect();
  const width = Math.max(rect.width || svg.clientWidth || 880, 720);
  const height = Math.max(rect.height || 540, 500);

  if (!nodes || nodes.length === 0) {
    renderEmptyTopology(svg, width, height);
    return;
  }

  const affinity = resolveBorderRouterAffinity(nodes, edges);
  topologyPhysicsState.affinityData = affinity;

  const tbrs = nodes.filter(n => n.type === "border_router");
  const routers = nodes.filter(n => n.type === "router");
  const seds = nodes.filter(n => n.type !== "border_router" && n.type !== "router");

  const colX = {
    tbr: 70,
    router: width / 2 - 80,
    sed: width - 230,
  };

  const nodePos = {};
  const assignCol = (colNodes, x) => {
    const count = Math.max(colNodes.length, 1);
    colNodes.forEach((n, idx) => {
      const y = ((idx + 1) / (count + 1)) * (height - 90) + 40;
      nodePos[n.id] = { x, y };
    });
  };

  assignCol(tbrs, colX.tbr);
  assignCol(routers, colX.router);
  assignCol(seds, colX.sed);

  nodes.forEach((n, idx) => {
    if (!nodePos[n.id]) {
      nodePos[n.id] = { x: width / 2, y: 50 + idx * 40 };
    }
  });

  const ribbonsG = document.createElementNS("http://www.w3.org/2000/svg", "g");
  const nodesG = document.createElementNS("http://www.w3.org/2000/svg", "g");
  svg.appendChild(ribbonsG);
  svg.appendChild(nodesG);

  // Column Headers
  const cols = [
    { label: "1. BORDER ROUTERS (GATEWAYS)", x: colX.tbr + 75 },
    { label: "2. ROUTERS (MESH BACKBONE)", x: colX.router + 75 },
    { label: "3. SLEEPY SENSORS (END DEVICES)", x: colX.sed + 75 },
  ];
  cols.forEach(c => {
    const t = document.createElementNS("http://www.w3.org/2000/svg", "text");
    t.setAttribute("x", c.x);
    t.setAttribute("y", "26");
    t.setAttribute("fill", "#38bdf8");
    t.setAttribute("font-size", "11");
    t.setAttribute("font-weight", "700");
    t.setAttribute("text-anchor", "middle");
    t.textContent = c.label;
    svg.appendChild(t);
  });

  // Flow Ribbons
  edges.forEach((e) => {
    const sId = typeof e.source === "object" ? e.source.id : e.source;
    const tId = typeof e.target === "object" ? e.target.id : e.target;
    let p1 = nodePos[sId];
    let p2 = nodePos[tId];
    if (!p1 || !p2) return;

    // Direct ribbons from left to right
    if (p1.x > p2.x) { const tmp = p1; p1 = p2; p2 = tmp; }

    const aff = affinity.nodeAffinity[sId] || affinity.nodeAffinity[tId] || { color: "#38bdf8" };
    const strokeColor = aff.color || "#0284c7";

    const x1 = p1.x + 155;
    const y1 = p1.y + 17;
    const x2 = p2.x;
    const y2 = p2.y + 17;
    const cX = x1 + (x2 - x1) * 0.5;

    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", `M ${x1} ${y1} C ${cX} ${y1}, ${cX} ${y2}, ${x2} ${y2}`);
    path.setAttribute("fill", "none");
    path.setAttribute("stroke", strokeColor);
    path.setAttribute("stroke-width", "3.5");
    path.setAttribute("stroke-opacity", "0.65");
    path.style.transition = "stroke-width 0.2s, stroke-opacity 0.2s";

    path.addEventListener("mouseenter", () => {
      path.setAttribute("stroke-width", "6.5");
      path.setAttribute("stroke-opacity", "1.0");
    });
    path.addEventListener("mouseleave", () => {
      path.setAttribute("stroke-width", "3.5");
      path.setAttribute("stroke-opacity", "0.65");
    });

    ribbonsG.appendChild(path);
  });

  // Node Pill Cards
  nodes.forEach((n) => {
    const pos = nodePos[n.id];
    const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
    g.style.cursor = "pointer";
    g.setAttribute("transform", `translate(${pos.x}, ${pos.y})`);

    const isTbr = n.type === "border_router";
    const isRouter = n.type === "router";
    const cardBorder = isTbr ? "#38bdf8" : (isRouter ? "#10b981" : "#8b5cf6");

    const bgRect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    bgRect.setAttribute("width", "155");
    bgRect.setAttribute("height", "34");
    bgRect.setAttribute("rx", "6");
    bgRect.setAttribute("fill", "#0f172a");
    bgRect.setAttribute("stroke", cardBorder);
    bgRect.setAttribute("stroke-width", "1.5");
    g.appendChild(bgRect);

    const iconText = document.createElementNS("http://www.w3.org/2000/svg", "text");
    iconText.setAttribute("x", "12");
    iconText.setAttribute("y", "21");
    iconText.setAttribute("font-size", "12");
    iconText.textContent = isTbr ? "📡" : (isRouter ? "🔁" : "🔋");
    g.appendChild(iconText);

    const nameText = document.createElementNS("http://www.w3.org/2000/svg", "text");
    nameText.setAttribute("x", "30");
    nameText.setAttribute("y", "21");
    nameText.setAttribute("fill", "#f8fafc");
    nameText.setAttribute("font-size", "11");
    nameText.setAttribute("font-weight", "600");
    nameText.textContent = (n.label || `Node ${n.node_id}`).substring(0, 16);
    g.appendChild(nameText);

    if (n.rssi !== null && n.rssi !== undefined) {
      const rssiBadge = document.createElementNS("http://www.w3.org/2000/svg", "text");
      rssiBadge.setAttribute("x", "146");
      rssiBadge.setAttribute("y", "21");
      rssiBadge.setAttribute("fill", Number(n.rssi) > -70 ? "#34d399" : "#fbbf24");
      rssiBadge.setAttribute("font-size", "9");
      rssiBadge.setAttribute("font-weight", "700");
      rssiBadge.setAttribute("text-anchor", "end");
      rssiBadge.textContent = `${n.rssi}`;
      g.appendChild(rssiBadge);
    }

    g.addEventListener("click", () => showNodeInspector(n));
    nodesG.appendChild(g);
    n.elem = g;
  });

  updateTopologyLegend();
}

/* ==========================================================================
   VISUAL PERSPECTIVE 4: Tactical Sonar / Radar Scope
   ========================================================================== */
function renderRadarScope(nodes, edges) {
  const svg = document.getElementById("mesh-svg");
  if (!svg) return;
  svg.innerHTML = "";
  const rect = svg.getBoundingClientRect();
  const width = Math.max(rect.width || svg.clientWidth || 880, 600);
  const height = Math.max(rect.height || 540, 500);

  if (!nodes || nodes.length === 0) {
    renderEmptyTopology(svg, width, height);
    return;
  }

  const cx = width / 2;
  const cy = height / 2;
  const R = Math.min(cx, cy) - 35;

  // Radar Base Scope Circle
  const scopeBg = document.createElementNS("http://www.w3.org/2000/svg", "circle");
  scopeBg.setAttribute("cx", cx);
  scopeBg.setAttribute("cy", cy);
  scopeBg.setAttribute("r", R);
  scopeBg.setAttribute("fill", "#030712");
  scopeBg.setAttribute("stroke", "#0284c7");
  scopeBg.setAttribute("stroke-width", "2");
  svg.appendChild(scopeBg);

  // Concentric Range Rings
  const rings = [
    { pct: 0.25, label: "-40 dBm (Point-Blank)" },
    { pct: 0.50, label: "-60 dBm (Strong)" },
    { pct: 0.75, label: "-75 dBm (Good)" },
    { pct: 1.00, label: "-90 dBm (Fringe)" },
  ];

  rings.forEach((r) => {
    const ringCircle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    ringCircle.setAttribute("cx", cx);
    ringCircle.setAttribute("cy", cy);
    ringCircle.setAttribute("r", R * r.pct);
    ringCircle.setAttribute("fill", "none");
    ringCircle.setAttribute("stroke", "#0369a1");
    ringCircle.setAttribute("stroke-width", "1");
    ringCircle.setAttribute("stroke-dasharray", "4,4");
    svg.appendChild(ringCircle);

    const lbl = document.createElementNS("http://www.w3.org/2000/svg", "text");
    lbl.setAttribute("x", cx + 8);
    lbl.setAttribute("y", cy - R * r.pct + 12);
    lbl.setAttribute("fill", "#38bdf8");
    lbl.setAttribute("font-size", "10");
    lbl.setAttribute("font-family", "monospace");
    lbl.textContent = r.label;
    svg.appendChild(lbl);
  });

  // Crosshair Axes
  const axesG = document.createElementNS("http://www.w3.org/2000/svg", "g");
  axesG.setAttribute("stroke", "#0c4a6e");
  axesG.setAttribute("stroke-width", "1");
  axesG.innerHTML = `
    <line x1="${cx - R}" y1="${cy}" x2="${cx + R}" y2="${cy}" />
    <line x1="${cx}" y1="${cy - R}" x2="${cx}" y2="${cy + R}" />
    <line x1="${cx - R * 0.7}" y1="${cy - R * 0.7}" x2="${cx + R * 0.7}" y2="${cy + R * 0.7}" stroke-dasharray="2,4" />
    <line x1="${cx - R * 0.7}" y1="${cy + R * 0.7}" x2="${cx + R * 0.7}" y2="${cy - R * 0.7}" stroke-dasharray="2,4" />
  `;
  svg.appendChild(axesG);

  // Animated Rotating Sweep Beam
  const sweepG = document.createElementNS("http://www.w3.org/2000/svg", "g");
  sweepG.setAttribute("class", "radar-sweep-beam");
  sweepG.style.transformOrigin = `${cx}px ${cy}px`;
  sweepG.innerHTML = `
    <defs>
      <linearGradient id="sweepGrad" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stop-color="#38bdf8" stop-opacity="0.4" />
        <stop offset="100%" stop-color="#38bdf8" stop-opacity="0" />
      </linearGradient>
    </defs>
    <path d="M ${cx} ${cy} L ${cx + R} ${cy} A ${R} ${R} 0 0 1 ${cx + R * 0.707} ${cy + R * 0.707} Z" fill="url(#sweepGrad)" />
    <line x1="${cx}" y1="${cy}" x2="${cx + R}" y2="${cy}" stroke="#38bdf8" stroke-width="2" />
  `;
  svg.appendChild(sweepG);

  // Plot Target Blips
  const blipsG = document.createElementNS("http://www.w3.org/2000/svg", "g");
  svg.appendChild(blipsG);

  const N = Math.max(nodes.length, 1);
  nodes.forEach((n, idx) => {
    let r = R * 0.55;
    if (n.type === "border_router") {
      r = R * 0.18;
    } else if (n.rssi !== null && n.rssi !== undefined) {
      const norm = Math.max(0.12, Math.min(0.95, (-30 - Number(n.rssi)) / 65));
      r = R * norm;
    } else if (n.type === "end_device") {
      r = R * 0.78;
    }

    const angle = (2 * Math.PI * idx) / N - Math.PI / 2;
    const x = cx + Math.cos(angle) * r;
    const y = cy + Math.sin(angle) * r;

    const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
    g.style.cursor = "pointer";
    g.setAttribute("transform", `translate(${x}, ${y})`);

    const isWeak = n.status === "weak" || (n.rssi !== null && Number(n.rssi) < -80);
    const blipColor = n.type === "border_router" ? "#38bdf8" : (isWeak ? "#f59e0b" : "#22c55e");

    if (isWeak || n.status === "offline") {
      const halo = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      halo.setAttribute("r", "14");
      halo.setAttribute("fill", "none");
      halo.setAttribute("stroke", blipColor);
      halo.setAttribute("stroke-width", "1.5");
      halo.setAttribute("stroke-dasharray", "3,2");
      g.appendChild(halo);
    }

    const blip = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    blip.setAttribute("r", n.type === "border_router" ? "8" : "5.5");
    blip.setAttribute("fill", blipColor);
    blip.setAttribute("stroke", "#ffffff");
    blip.setAttribute("stroke-width", "1.5");
    g.appendChild(blip);

    const lbl = document.createElementNS("http://www.w3.org/2000/svg", "text");
    lbl.setAttribute("x", "10");
    lbl.setAttribute("y", "4");
    lbl.setAttribute("fill", "#f8fafc");
    lbl.setAttribute("font-size", "10");
    lbl.setAttribute("font-family", "monospace");
    lbl.setAttribute("font-weight", "600");
    lbl.textContent = `${n.label || `Node ${n.node_id}`}${n.rssi ? ` (${n.rssi}dBm)` : ''}`;
    g.appendChild(lbl);

    g.addEventListener("click", () => showNodeInspector(n));
    blipsG.appendChild(g);
    n.elem = g;
  });

  // Tactical Corner Header
  const head = document.createElementNS("http://www.w3.org/2000/svg", "text");
  head.setAttribute("x", "20");
  head.setAttribute("y", "30");
  head.setAttribute("fill", "#22c55e");
  head.setAttribute("font-size", "11");
  head.setAttribute("font-family", "monospace");
  head.setAttribute("font-weight", "700");
  head.textContent = `🎯 SONAR SWEEP: ${nodes.length} TARGETS ACQUIRED`;
  svg.appendChild(head);

  updateTopologyLegend();
}

/* ==========================================================================
   VISUAL PERSPECTIVE 5: Radial Sunburst Partition View
   ========================================================================== */
function renderSunburst(nodes, edges) {
  const svg = document.getElementById("mesh-svg");
  if (!svg) return;
  svg.innerHTML = "";
  const rect = svg.getBoundingClientRect();
  const width = Math.max(rect.width || svg.clientWidth || 880, 600);
  const height = Math.max(rect.height || 540, 500);

  if (!nodes || nodes.length === 0) {
    renderEmptyTopology(svg, width, height);
    return;
  }

  const cx = width / 2;
  const cy = height / 2;
  const affinity = resolveBorderRouterAffinity(nodes, edges);
  topologyPhysicsState.affinityData = affinity;

  const tbrs = nodes.filter(n => n.type === "border_router");
  const nonTbrs = nodes.filter(n => n.type !== "border_router");

  const sunburstG = document.createElementNS("http://www.w3.org/2000/svg", "g");
  svg.appendChild(sunburstG);

  // Center Core Circle (Thread Network PAN)
  const coreCircle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
  coreCircle.setAttribute("cx", cx);
  coreCircle.setAttribute("cy", cy);
  coreCircle.setAttribute("r", "52");
  coreCircle.setAttribute("fill", "#0f172a");
  coreCircle.setAttribute("stroke", "#38bdf8");
  coreCircle.setAttribute("stroke-width", "2.5");
  sunburstG.appendChild(coreCircle);

  const coreText1 = document.createElementNS("http://www.w3.org/2000/svg", "text");
  coreText1.setAttribute("x", cx);
  coreText1.setAttribute("y", cy - 6);
  coreText1.setAttribute("fill", "#38bdf8");
  coreText1.setAttribute("font-size", "11");
  coreText1.setAttribute("font-weight", "700");
  coreText1.setAttribute("text-anchor", "middle");
  coreText1.textContent = "THREAD PAN";
  sunburstG.appendChild(coreText1);

  const coreText2 = document.createElementNS("http://www.w3.org/2000/svg", "text");
  coreText2.setAttribute("x", cx);
  coreText2.setAttribute("y", cy + 12);
  coreText2.setAttribute("fill", "#94a3b8");
  coreText2.setAttribute("font-size", "10");
  coreText2.setAttribute("font-weight", "600");
  coreText2.setAttribute("text-anchor", "middle");
  coreText2.textContent = `${nodes.length} Devices`;
  sunburstG.appendChild(coreText2);

  // SVG Donut Arc Helper
  const describeArc = (x, y, r1, r2, startAngle, endAngle) => {
    const p1 = { x: x + r2 * Math.cos(startAngle), y: y + r2 * Math.sin(startAngle) };
    const p2 = { x: x + r2 * Math.cos(endAngle), y: y + r2 * Math.sin(endAngle) };
    const p3 = { x: x + r1 * Math.cos(endAngle), y: y + r1 * Math.sin(endAngle) };
    const p4 = { x: x + r1 * Math.cos(startAngle), y: y + r1 * Math.sin(startAngle) };
    const largeArc = endAngle - startAngle > Math.PI ? 1 : 0;
    return `M ${p1.x} ${p1.y} A ${r2} ${r2} 0 ${largeArc} 1 ${p2.x} ${p2.y} L ${p3.x} ${p3.y} A ${r1} ${r1} 0 ${largeArc} 0 ${p4.x} ${p4.y} Z`;
  };

  // Ring 1: Border Routers (r: 60 -> 135)
  const tbrCount = Math.max(tbrs.length, 1);
  const tbrAngleSpan = (2 * Math.PI) / tbrCount;

  tbrs.forEach((tbr, idx) => {
    const a1 = idx * tbrAngleSpan - Math.PI / 2;
    const a2 = a1 + tbrAngleSpan - 0.04;
    const aff = affinity.brMap[tbr.id] || { color: "#0284c7" };

    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", describeArc(cx, cy, 60, 135, a1, a2));
    path.setAttribute("fill", aff.color || "#0284c7");
    path.setAttribute("fill-opacity", "0.85");
    path.setAttribute("stroke", "#0f172a");
    path.setAttribute("stroke-width", "2");
    path.style.cursor = "pointer";

    path.addEventListener("click", () => showNodeInspector(tbr));
    sunburstG.appendChild(path);
    tbr.elem = path;

    const midAngle = (a1 + a2) / 2;
    const midR = 98;
    const lbl = document.createElementNS("http://www.w3.org/2000/svg", "text");
    lbl.setAttribute("x", cx + midR * Math.cos(midAngle));
    lbl.setAttribute("y", cy + midR * Math.sin(midAngle) + 4);
    lbl.setAttribute("fill", "#ffffff");
    lbl.setAttribute("font-size", "10");
    lbl.setAttribute("font-weight", "700");
    lbl.setAttribute("text-anchor", "middle");
    lbl.textContent = (tbr.label || `TBR ${idx + 1}`).substring(0, 12);
    sunburstG.appendChild(lbl);
  });

  // Ring 2: Member Devices (r: 142 -> 235)
  const nonTbrCount = Math.max(nonTbrs.length, 1);
  const nonTbrAngleSpan = (2 * Math.PI) / nonTbrCount;

  nonTbrs.forEach((n, idx) => {
    const a1 = idx * nonTbrAngleSpan - Math.PI / 2;
    const a2 = a1 + nonTbrAngleSpan - 0.03;
    const isRouter = n.type === "router";
    const sliceColor = isRouter ? "#10b981" : "#8b5cf6";

    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", describeArc(cx, cy, 142, 235, a1, a2));
    path.setAttribute("fill", sliceColor);
    path.setAttribute("fill-opacity", "0.78");
    path.setAttribute("stroke", "#0f172a");
    path.setAttribute("stroke-width", "1.5");
    path.style.cursor = "pointer";

    path.addEventListener("click", () => showNodeInspector(n));
    sunburstG.appendChild(path);
    n.elem = path;

    const midAngle = (a1 + a2) / 2;
    const midR = 188;
    const lbl = document.createElementNS("http://www.w3.org/2000/svg", "text");
    lbl.setAttribute("x", cx + midR * Math.cos(midAngle));
    lbl.setAttribute("y", cy + midR * Math.sin(midAngle) + 3);
    lbl.setAttribute("fill", "#ffffff");
    lbl.setAttribute("font-size", "9");
    lbl.setAttribute("font-weight", "600");
    lbl.setAttribute("text-anchor", "middle");
    lbl.textContent = (n.label || `Node ${n.node_id}`).substring(0, 10);
    sunburstG.appendChild(lbl);
  });

  const header = document.createElementNS("http://www.w3.org/2000/svg", "text");
  header.setAttribute("x", "20");
  header.setAttribute("y", "30");
  header.setAttribute("fill", "#38bdf8");
  header.setAttribute("font-size", "11");
  header.setAttribute("font-weight", "700");
  header.textContent = "🍩 RADIAL SUNBURST PARTITION HIERARCHY";
  svg.appendChild(header);

  updateTopologyLegend();
}

/* ==========================================================================
   VISUAL PERSPECTIVE 6: Circular Chord / Routing Ribbon Bundle
   ========================================================================== */
function renderChordBundle(nodes, edges) {
  const svg = document.getElementById("mesh-svg");
  if (!svg) return;
  svg.innerHTML = "";
  const rect = svg.getBoundingClientRect();
  const width = Math.max(rect.width || svg.clientWidth || 880, 600);
  const height = Math.max(rect.height || 540, 500);

  if (!nodes || nodes.length === 0) {
    renderEmptyTopology(svg, width, height);
    return;
  }

  const cx = width / 2;
  const cy = height / 2;
  const R = Math.min(cx, cy) - 75;

  const chordsG = document.createElementNS("http://www.w3.org/2000/svg", "g");
  const perimeterG = document.createElementNS("http://www.w3.org/2000/svg", "g");
  svg.appendChild(chordsG);
  svg.appendChild(perimeterG);

  const N = Math.max(nodes.length, 1);
  const posMap = {};

  nodes.forEach((n, idx) => {
    const angle = (2 * Math.PI * idx) / N - Math.PI / 2;
    posMap[n.id] = {
      x: cx + R * Math.cos(angle),
      y: cy + R * Math.sin(angle),
      angle,
    };
  });

  const chordElemsByNode = {};
  nodes.forEach(n => { chordElemsByNode[n.id] = []; });

  // Interior Curved Chords
  edges.forEach((e) => {
    const sId = typeof e.source === "object" ? e.source.id : e.source;
    const tId = typeof e.target === "object" ? e.target.id : e.target;
    const p1 = posMap[sId];
    const p2 = posMap[tId];
    if (!p1 || !p2) return;

    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", `M ${p1.x} ${p1.y} Q ${cx} ${cy} ${p2.x} ${p2.y}`);
    path.setAttribute("fill", "none");
    path.setAttribute("stroke", "#38bdf8");
    path.setAttribute("stroke-width", "2.2");
    path.setAttribute("stroke-opacity", "0.5");
    path.style.transition = "stroke 0.2s, stroke-width 0.2s, stroke-opacity 0.2s";

    chordsG.appendChild(path);
    if (chordElemsByNode[sId]) chordElemsByNode[sId].push(path);
    if (chordElemsByNode[tId]) chordElemsByNode[tId].push(path);
  });

  // Perimeter Node Badges
  nodes.forEach((n) => {
    const pos = posMap[n.id];
    const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
    g.style.cursor = "pointer";

    const isTbr = n.type === "border_router";
    const isRouter = n.type === "router";
    const color = isTbr ? "#38bdf8" : (isRouter ? "#10b981" : "#8b5cf6");

    const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    circle.setAttribute("cx", pos.x);
    circle.setAttribute("cy", pos.y);
    circle.setAttribute("r", isTbr ? "9" : "7");
    circle.setAttribute("fill", color);
    circle.setAttribute("stroke", "#0f172a");
    circle.setAttribute("stroke-width", "2");
    g.appendChild(circle);

    const lbl = document.createElementNS("http://www.w3.org/2000/svg", "text");
    const isRight = Math.cos(pos.angle) >= 0;
    const lx = pos.x + (isRight ? 12 : -12);
    const ly = pos.y + 4;
    lbl.setAttribute("x", lx);
    lbl.setAttribute("y", ly);
    lbl.setAttribute("fill", "#f8fafc");
    lbl.setAttribute("font-size", "10");
    lbl.setAttribute("font-weight", isTbr ? "700" : "600");
    lbl.setAttribute("text-anchor", isRight ? "start" : "end");
    lbl.textContent = (n.label || `Node ${n.node_id}`).substring(0, 14);
    g.appendChild(lbl);

    // Hover isolate interaction
    g.addEventListener("mouseenter", () => {
      const activeSet = new Set(chordElemsByNode[n.id] || []);
      chordsG.childNodes.forEach((ch) => {
        if (activeSet.has(ch)) {
          ch.setAttribute("stroke", "#10b981");
          ch.setAttribute("stroke-width", "4");
          ch.setAttribute("stroke-opacity", "1.0");
        } else {
          ch.setAttribute("stroke-opacity", "0.06");
        }
      });
    });

    g.addEventListener("mouseleave", () => {
      chordsG.childNodes.forEach((ch) => {
        ch.setAttribute("stroke", "#38bdf8");
        ch.setAttribute("stroke-width", "2.2");
        ch.setAttribute("stroke-opacity", "0.5");
      });
    });

    g.addEventListener("click", () => showNodeInspector(n));
    perimeterG.appendChild(g);
    n.elem = g;
  });

  const header = document.createElementNS("http://www.w3.org/2000/svg", "text");
  header.setAttribute("x", "20");
  header.setAttribute("y", "30");
  header.setAttribute("fill", "#38bdf8");
  header.setAttribute("font-size", "11");
  header.setAttribute("font-weight", "700");
  header.textContent = "🕸️ CIRCULAR CHORD / ROUTING RIBBON BUNDLE";
  svg.appendChild(header);

  updateTopologyLegend();
}

function updateTopologySearchHighlight() {
  const q = (currentNodeSearchQuery || "").toLowerCase();
  (topologyPhysicsState.nodes || []).forEach((n) => {
    if (!n.elem || !n.haloElem) return;
    if (!q) {
      n.elem.style.opacity = "1";
      n.haloElem.setAttribute("stroke-width", n.preferred ? "2.5" : "0");
      n.haloElem.setAttribute("opacity", n.preferred ? "0.85" : "0");
      return;
    }
    const hay = [
      n.label || "",
      n.node_id ? `#${n.node_id}` : "",
      n.brand || "",
      n.model || "",
      n.rloc16 || "",
      n.ext_address || "",
      n.extended_pan_id || "",
      n.details || "",
    ].join(" ").toLowerCase();
    const matched = hay.includes(q);
    n.elem.style.opacity = matched ? "1" : "0.25";
    n.haloElem.setAttribute("stroke", matched ? "#38bdf8" : "#10b981");
    n.haloElem.setAttribute("stroke-width", matched ? "4" : "0");
    n.haloElem.setAttribute("stroke-dasharray", "none");
    n.haloElem.setAttribute("opacity", matched ? "1" : "0");
  });
}

async function downloadDiagnosticLogs(btnElem) {
  const origHtml = btnElem ? btnElem.innerHTML : "";
  if (btnElem) {
    btnElem.disabled = true;
    btnElem.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Building Log...`;
  }

  try {
    let bundleText = "";
    const res = await fetch(apiPath("/api/diagnostics/logs"));
    if (res.ok) {
      const data = await res.json();
      bundleText = data.bundle_text || "";
    }
    if (!bundleText) {
      bundleText = JSON.stringify(currentTelemetry || { status: "No telemetry cached yet" }, null, 2);
    }

    const now = new Date();
    const pad2 = (n) => String(n).padStart(2, "0");
    const ts = `${now.getFullYear()}${pad2(now.getMonth() + 1)}${pad2(now.getDate())}-${pad2(now.getHours())}${pad2(now.getMinutes())}${pad2(now.getSeconds())}`;
    const filename = `matter-thread-diagnostics-${ts}.log`;

    const blob = new Blob([bundleText], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => {
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }, 200);

    if (btnElem) {
      btnElem.innerHTML = `<i class="fa-solid fa-check"></i> Downloaded!`;
      setTimeout(() => {
        btnElem.disabled = false;
        btnElem.innerHTML = origHtml;
      }, 1500);
    }
  } catch (err) {
    console.error("Failed to download diagnostic logs:", err);
    if (btnElem) {
      btnElem.disabled = false;
      btnElem.innerHTML = origHtml;
    }
  }
}

function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

/* =========================================================================
   ZBT-1 & OpenThread Border Router (OTBR) Thread Channel Management
   ========================================================================= */

let currentOtbrChannelData = null;
let selectedTargetChannel = 25;
let channelMigrationInterval = null;

async function fetchOtbrChannelInfo(showSpinner = false) {
  const refreshBtn = document.getElementById("btn-refresh-channel-status");
  const origHtml = refreshBtn ? refreshBtn.innerHTML : "";
  if (showSpinner && refreshBtn) {
    refreshBtn.disabled = true;
    refreshBtn.innerHTML = `<i class="fa-solid fa-arrows-rotate fa-spin"></i> Checking Radio...`;
  }

  try {
    const res = await fetch(apiPath("/api/otbr/channel"));
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    currentOtbrChannelData = data;
    renderChannelTab(data);
  } catch (err) {
    console.error("Failed fetching OTBR channel info:", err);
    const grid = document.getElementById("channel-picker-grid");
    if (grid) {
      grid.innerHTML = `<div style="padding:12px; color:var(--color-danger);"><i class="fa-solid fa-triangle-exclamation"></i> Could not connect to OpenThread Border Router API: ${escapeHtml(err.message)}</div>`;
    }
  } finally {
    if (showSpinner && refreshBtn) {
      refreshBtn.disabled = false;
      refreshBtn.innerHTML = origHtml;
    }
  }
}

function renderChannelTab(data) {
  if (!data) return;

  const hw = data.hardware || {};
  const otbr = data.otbr || {};
  const curCh = data.current_channel;

  // 1. Hardware card details
  const nameEl = document.getElementById("zbt1-hardware-name");
  const modelEl = document.getElementById("zbt1-hardware-model");
  const stateBadge = document.getElementById("zbt1-radio-state");
  const otbrBadge = document.getElementById("zbt1-otbr-status");

  if (nameEl) nameEl.innerText = hw.name || "Home Assistant Connect ZBT-1";
  if (modelEl) modelEl.innerText = hw.model || "Silicon Labs EFR32MG21 (Nabu Casa)";
  if (stateBadge) {
    const st = (otbr.state || "unknown").toLowerCase();
    stateBadge.innerText = `State: ${st.toUpperCase()}`;
    stateBadge.className = `badge ${st === "leader" || st === "router" ? "badge-success" : (st === "detached" ? "badge-warning" : "badge-info")}`;
  }
  if (otbrBadge) {
    otbrBadge.innerText = otbr.reachable ? `OTBR Online (:8081)` : `OTBR Offline`;
    otbrBadge.className = `badge ${otbr.reachable ? "badge-success" : "badge-warning"}`;
  }

  // 2. Current Channel & Frequency
  const chNumEl = document.getElementById("zbt1-current-channel-num");
  const freqEl = document.getElementById("zbt1-current-freq");
  const rfBadgeContainer = document.getElementById("zbt1-current-rf-badge");

  if (chNumEl) chNumEl.innerText = curCh ? `Ch ${curCh}` : "Unknown";
  if (freqEl) {
    const freq = curCh ? 2405 + (curCh - 11) * 5 : null;
    freqEl.innerText = freq ? `(${freq} MHz)` : "";
  }
  if (rfBadgeContainer) {
    if (curCh) {
      const chInfo = (data.channels_matrix || []).find(c => c.channel === curCh) || {};
      const sev = chInfo.severity || "UNKNOWN";
      if (curCh === 26) {
        rfBadgeContainer.innerHTML = `<span class="badge badge-success" style="font-size:11px;"><i class="fa-solid fa-shield-check"></i> Channel 26 — Cleanest (0% Wi-Fi Overlap)</span>`;
      } else if (curCh === 25) {
        rfBadgeContainer.innerHTML = `<span class="badge badge-success" style="font-size:11px;"><i class="fa-solid fa-check"></i> Channel 25 — Recommended (Clear of Wi-Fi 11)</span>`;
      } else if (sev === "HIGH") {
        rfBadgeContainer.innerHTML = `<span class="badge badge-danger" style="font-size:11px;"><i class="fa-solid fa-triangle-exclamation"></i> High Interference: Overlaps Wi-Fi Ch ${chInfo.wifi_overlap_channel || '1/6/11'}</span>`;
      } else {
        rfBadgeContainer.innerHTML = `<span class="badge badge-warning" style="font-size:11px;"><i class="fa-solid fa-circle-exclamation"></i> Moderate: Guard Band between Wi-Fi channels</span>`;
      }
    } else {
      rfBadgeContainer.innerHTML = `<span class="badge badge-warning" style="font-size:11px;">Channel not reported by radio</span>`;
    }
  }

  // 3. Network Identity
  const netNameEl = document.getElementById("zbt1-network-name");
  const xpanEl = document.getElementById("zbt1-xpan");
  const panidEl = document.getElementById("zbt1-panid");
  const rloc16El = document.getElementById("zbt1-rloc16");

  if (netNameEl) netNameEl.innerText = otbr.network_name || "Thread Mesh";
  if (xpanEl) xpanEl.innerText = otbr.extended_pan_id || "--";
  if (panidEl) panidEl.innerText = otbr.pan_id || "--";
  if (rloc16El) rloc16El.innerText = otbr.rloc16 || "--";

  // Pick sensible target channel if not yet selected
  if (curCh && selectedTargetChannel === curCh) {
    selectedTargetChannel = curCh === 25 ? 26 : 25;
  }

  // 4. Render 16-channel picker grid
  renderChannelPickerGrid(data.channels_matrix || [], curCh);
}

function renderChannelPickerGrid(channels, curCh) {
  const grid = document.getElementById("channel-picker-grid");
  if (!grid) return;

  grid.innerHTML = channels.map(ch => {
    const isCur = curCh !== null && curCh !== undefined && ch.channel === curCh;
    const isSel = ch.channel === selectedTargetChannel;

    let borderCol = "#334155";
    let bgCol = "#1e293b";
    let badgeHtml = "";

    if (isSel) {
      borderCol = "#10b981";
      bgCol = "#064e3b44";
    } else if (isCur) {
      borderCol = "#38bdf8";
      bgCol = "#0c4a6e33";
    }

    if (ch.channel === 26) {
      badgeHtml = `<span class="badge badge-success" style="font-size:9px; padding:1px 5px;">★ Best</span>`;
    } else if (ch.channel === 25) {
      badgeHtml = `<span class="badge badge-success" style="font-size:9px; padding:1px 5px;">★ Recommended</span>`;
    } else if (ch.severity === "HIGH") {
      badgeHtml = `<span class="badge badge-danger" style="font-size:9px; padding:1px 5px;">Wi-Fi ${ch.wifi_overlap_channel}</span>`;
    } else {
      badgeHtml = `<span class="badge badge-warning" style="font-size:9px; padding:1px 5px;">Guard Band</span>`;
    }

    return `
      <div
        class="channel-tile"
        data-channel="${ch.channel}"
        data-freq="${ch.frequency_mhz}"
        data-rec="${escapeHtml(ch.recommendation_badge || '')}"
        style="
          background: ${bgCol};
          border: 2px solid ${borderCol};
          padding: 10px 8px;
          border-radius: 6px;
          cursor: pointer;
          text-align: center;
          transition: all 0.2s ease;
          position: relative;
        "
        title="${escapeHtml(ch.description || '')}"
      >
        ${isCur ? `<span style="position:absolute; top:-8px; right:4px; font-size:8px; background:#38bdf8; color:#0f172a; padding:1px 4px; border-radius:3px; font-weight:800;">ACTIVE</span>` : ''}
        <div style="font-size: 15px; font-weight: 800; color: ${isSel ? '#34d399' : (isCur ? '#38bdf8' : '#f8fafc')};">
          Ch ${ch.channel}
        </div>
        <div style="font-size: 11px; color: var(--text-muted); margin-bottom: 4px;">
          ${ch.frequency_mhz} MHz
        </div>
        <div>${badgeHtml}</div>
      </div>
    `;
  }).join("");

  // Attach click listener to channel tiles
  grid.querySelectorAll(".channel-tile").forEach(tile => {
    tile.addEventListener("click", () => {
      const ch = parseInt(tile.getAttribute("data-channel"), 10);
      selectedTargetChannel = ch;
      const freq = tile.getAttribute("data-freq");
      const rec = tile.getAttribute("data-rec");

      const labelEl = document.getElementById("selected-target-channel-label");
      if (labelEl) {
        labelEl.innerText = `Channel ${ch} (${freq} MHz) — ${rec}`;
      }

      // Re-render picker grid to highlight selected tile
      if (currentOtbrChannelData && currentOtbrChannelData.channels_matrix) {
        renderChannelPickerGrid(currentOtbrChannelData.channels_matrix, currentOtbrChannelData.current_channel);
      }
    });
  });

  // Update selected target channel label
  const curTargetInfo = channels.find(c => c.channel === selectedTargetChannel) || {};
  const labelEl = document.getElementById("selected-target-channel-label");
  if (labelEl) {
    labelEl.innerText = `Channel ${selectedTargetChannel} (${curTargetInfo.frequency_mhz || 2475} MHz) — ${curTargetInfo.recommendation_badge || 'Selected'}`;
  }
}

async function triggerChannelChange() {
  const curCh = currentOtbrChannelData?.current_channel;
  const targetCh = selectedTargetChannel;

  if (curCh && targetCh === curCh) {
    alert(`Home Assistant Connect ZBT-1 is already running on Channel ${targetCh}. Select a different channel to migrate.`);
    return;
  }

  const modeRadio = document.querySelector('input[name="channel-migration-mode"]:checked');
  const delaySec = parseInt(modeRadio?.value || "30", 10);
  const freq = 2405 + (targetCh - 11) * 5;

  const modeText = delaySec > 0
    ? `Graceful Mesh Migration (${delaySec}-second delay countdown)\nThread will broadcast a Pending Operational Dataset so all battery sensors and routers switch channels together.`
    : `Immediate Switch (0-second delay)\nThe active radio dataset will update immediately.`;

  const confirmed = window.confirm(
    `Change Home Assistant Connect ZBT-1 Thread Channel?\n\n` +
    `• Target Channel: Channel ${targetCh} (${freq} MHz)\n` +
    `• Migration Strategy: ${modeText}\n\n` +
    `Do you want to proceed with this channel migration?`
  );
  if (!confirmed) return;

  const btnApply = document.getElementById("btn-apply-channel-change");
  const banner = document.getElementById("channel-migration-banner");
  const bannerTitle = document.getElementById("migration-banner-title");
  const bannerDesc = document.getElementById("migration-banner-desc");
  const badgeCountdown = document.getElementById("migration-countdown-badge");
  const progressBar = document.getElementById("migration-progress-bar");

  if (btnApply) btnApply.disabled = true;
  if (banner) banner.classList.remove("hidden");
  if (bannerTitle) bannerTitle.innerText = `Broadcasting Pending Dataset to Channel ${targetCh}...`;
  if (bannerDesc) bannerDesc.innerText = `Applying Thread channel change via Home Assistant Core OTBR...`;

  try {
    const res = await fetch(apiPath("/api/otbr/set_channel"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        channel: targetCh,
        delay_seconds: delaySec,
      }),
    });

    const data = await res.json();
    if (!data.success) {
      throw new Error(data.error || "Channel change failed");
    }

    if (delaySec > 0) {
      if (bannerTitle) bannerTitle.innerText = `Thread Mesh Synchronizing to Channel ${targetCh}...`;
      if (bannerDesc) bannerDesc.innerText = `Pending Operational Dataset active. All devices are counting down together.`;

      let remaining = delaySec;
      if (channelMigrationInterval) clearInterval(channelMigrationInterval);

      channelMigrationInterval = setInterval(() => {
        remaining -= 1;
        if (badgeCountdown) badgeCountdown.innerText = `${remaining}s`;
        if (progressBar) {
          const pct = Math.min(100, Math.round(((delaySec - remaining) / delaySec) * 100));
          progressBar.style.width = `${pct}%`;
        }

        if (remaining <= 0) {
          clearInterval(channelMigrationInterval);
          channelMigrationInterval = null;
          completeChannelMigrationSuccess(targetCh);
        }
      }, 1000);
    } else {
      completeChannelMigrationSuccess(targetCh);
    }
  } catch (err) {
    if (channelMigrationInterval) {
      clearInterval(channelMigrationInterval);
      channelMigrationInterval = null;
    }
    if (bannerTitle) bannerTitle.innerText = `Channel Change Error`;
    if (bannerDesc) bannerDesc.innerText = err.message;
    if (badgeCountdown) {
      badgeCountdown.innerText = `Failed`;
      badgeCountdown.className = `badge badge-danger`;
    }
    if (btnApply) btnApply.disabled = false;
  }
}

async function completeChannelMigrationSuccess(targetCh) {
  const btnApply = document.getElementById("btn-apply-channel-change");
  const bannerTitle = document.getElementById("migration-banner-title");
  const bannerDesc = document.getElementById("migration-banner-desc");
  const badgeCountdown = document.getElementById("migration-countdown-badge");
  const progressBar = document.getElementById("migration-progress-bar");

  if (bannerTitle) bannerTitle.innerText = `Channel Change Completed Successfully!`;
  if (bannerDesc) bannerDesc.innerText = `Home Assistant Connect ZBT-1 is now operating on Channel ${targetCh}. Re-scanning mesh telemetry...`;
  if (badgeCountdown) {
    badgeCountdown.innerText = `Active`;
    badgeCountdown.className = `badge badge-success`;
  }
  if (progressBar) progressBar.style.width = `100%`;

  await fetchOtbrChannelInfo();
  await scanSelectedNetwork(false);

  setTimeout(() => {
    if (btnApply) btnApply.disabled = false;
    const banner = document.getElementById("channel-migration-banner");
    if (banner) {
      banner.innerHTML = `
        <div style="display:flex; align-items:center; justify-content:space-between; gap:10px;">
          <div style="display:flex; align-items:center; gap:8px;">
            <i class="fa-solid fa-circle-check" style="color:#34d399; font-size:18px;"></i>
            <span style="color:#a7f3d0; font-size:13px; font-weight:700;">ZBT-1 successfully operating on Channel ${targetCh}!</span>
          </div>
          <button type="button" class="btn btn-outline" onclick="document.getElementById('channel-migration-banner').classList.add('hidden')" style="padding:2px 8px; font-size:11px;">Dismiss</button>
        </div>
      `;
    }
  }, 2500);
}

/* =========================================================================
   Join Existing PAN / Thread Mesh Controllers
   ========================================================================= */

let currentJoinableNetworksData = null;

async function fetchJoinableNetworks(showSpinner = false) {
  const refreshBtn = document.getElementById("btn-refresh-joinable-networks");
  const origHtml = refreshBtn ? refreshBtn.innerHTML : "";
  if (showSpinner && refreshBtn) {
    refreshBtn.disabled = true;
    refreshBtn.innerHTML = `<i class="fa-solid fa-arrows-rotate fa-spin"></i> Scanning PANs...`;
  }

  try {
    const res = await fetch(apiPath("/api/otbr/joinable_networks"));
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    currentJoinableNetworksData = data;
    renderJoinableNetworks(data);
  } catch (err) {
    console.warn("Could not fetch joinable networks:", err);
    const sel = document.getElementById("select-target-join-network");
    if (sel) {
      sel.innerHTML = `<option value="">Error loading available networks: ${escapeHtml(err.message)}</option>`;
    }
  } finally {
    if (showSpinner && refreshBtn) {
      setTimeout(() => {
        refreshBtn.disabled = false;
        refreshBtn.innerHTML = origHtml;
      }, 500);
    }
  }
}

function renderJoinableNetworks(data) {
  const currentMesh = data?.current_mesh || {};
  const networks = data?.networks || [];

  const curLabel = document.getElementById("join-current-mesh-label");
  if (curLabel) {
    curLabel.innerText = `${currentMesh.network_name || "Unknown"} (PAN: ${currentMesh.pan_id || "--"}, Ch ${currentMesh.channel || "--"})`;
  }

  const select = document.getElementById("select-target-join-network");
  if (!select) return;

  select.innerHTML = "";

  const defaultOpt = document.createElement("option");
  defaultOpt.value = "";
  defaultOpt.innerText = "-- Select an existing Thread Network / PAN to join --";
  select.appendChild(defaultOpt);

  let joinableCount = 0;
  networks.forEach((net) => {
    const opt = document.createElement("option");
    opt.value = net.dataset_id || "";
    opt.dataset.networkName = net.network_name || "";
    opt.dataset.panId = net.pan_id || "";
    opt.dataset.channel = net.channel || "";
    opt.dataset.xpan = net.extended_pan_id || "";
    opt.dataset.isCurrent = net.is_current ? "true" : "false";

    let label = `${net.network_name} • PAN: ${net.pan_id} • Ch ${net.channel || "??"}`;
    if (net.preferred) label += " ★ Preferred";
    if (net.is_current) {
      label += " (Currently Active on ZBT-1)";
    }
    joinableCount += 1;
    opt.innerText = label;
    select.appendChild(opt);
  });

  // Custom TLV import option
  const customOpt = document.createElement("option");
  customOpt.value = "custom_tlv";
  customOpt.innerText = "➕ Enter Custom Dataset TLV (Import from Apple / Google / Nanoleaf)...";
  select.appendChild(customOpt);

  const statusPill = document.getElementById("join-status-pill");
  if (statusPill) {
    statusPill.innerHTML = `<span class="badge badge-info" style="font-size:11px;">${joinableCount} Available Network${joinableCount === 1 ? "" : "s"}</span>`;
  }

  onJoinNetworkSelectChange(select.value);
}

function onJoinNetworkSelectChange(selectedValue) {
  const detailsBox = document.getElementById("join-network-details-box");
  const customTlvContainer = document.getElementById("join-custom-tlv-container");
  const btnJoin = document.getElementById("btn-execute-join-network");
  const select = document.getElementById("select-target-join-network");

  if (!selectedValue) {
    if (detailsBox) detailsBox.classList.add("hidden");
    if (customTlvContainer) customTlvContainer.classList.add("hidden");
    if (btnJoin) btnJoin.disabled = true;
    return;
  }

  if (selectedValue === "custom_tlv") {
    if (detailsBox) detailsBox.classList.add("hidden");
    if (customTlvContainer) customTlvContainer.classList.remove("hidden");
    if (btnJoin) {
      btnJoin.disabled = false;
      btnJoin.innerHTML = `<i class="fa-solid fa-file-import"></i> Import & Join Mesh`;
      btnJoin.title = "Import external dataset TLV and join network";
    }
    return;
  }

  if (customTlvContainer) customTlvContainer.classList.add("hidden");

  const selectedOpt = select.querySelector(`option[value="${selectedValue}"]`);
  if (selectedOpt && detailsBox) {
    document.getElementById("join-preview-name").innerText = selectedOpt.dataset.networkName || "--";
    document.getElementById("join-preview-pan").innerText = selectedOpt.dataset.panId || "--";
    document.getElementById("join-preview-ch").innerText = `Channel ${selectedOpt.dataset.channel || "--"}`;
    document.getElementById("join-preview-xpan").innerText = selectedOpt.dataset.xpan || "--";
    detailsBox.classList.remove("hidden");
  }

  if (btnJoin) {
    const isCurrent = selectedOpt?.dataset.isCurrent === "true";
    btnJoin.disabled = false;
    if (isCurrent) {
      btnJoin.innerHTML = `<i class="fa-solid fa-arrows-rotate"></i> Re-apply / Sync Active PAN Credentials`;
      btnJoin.title = "Re-synchronize the OpenThread Border Router radio with this dataset";
    } else {
      btnJoin.innerHTML = `<i class="fa-solid fa-link"></i> Join Selected PAN`;
      btnJoin.title = "Switch ZBT-1 to this Thread network";
    }
  }
}

async function triggerJoinNetwork() {
  const select = document.getElementById("select-target-join-network");
  const selectedVal = select?.value;
  if (!selectedVal) return;

  let datasetId = null;
  let rawTlv = null;
  let netDisplayName = "";
  const selectedOpt = select.querySelector(`option[value="${selectedVal}"]`);
  const isCurrent = selectedOpt?.dataset.isCurrent === "true";

  if (selectedVal === "custom_tlv") {
    const tlvInput = document.getElementById("join-custom-tlv-input");
    rawTlv = tlvInput ? tlvInput.value.trim() : "";
    if (!rawTlv) {
      alert("Please paste a valid raw Operational Dataset TLV in hex format.");
      return;
    }
    netDisplayName = "Custom Imported Dataset";
  } else {
    datasetId = selectedVal;
    netDisplayName = selectedOpt?.dataset.networkName || "Selected Network";
  }

  const makePref = document.getElementById("chk-make-preferred-dataset")?.checked ?? true;

  let confirmMsg = "";
  if (isCurrent) {
    confirmMsg = (
      `Re-apply / Sync Thread Network '${netDisplayName}'?\n\n` +
      `• Your Home Assistant Connect ZBT-1 is currently associated with this network.\n` +
      `• This will re-synchronize the active operational dataset (PAN ID, Network Key, Channel) from Home Assistant into the OpenThread Border Router radio.\n` +
      (makePref ? `• It will also re-assert this dataset as Home Assistant's Preferred Thread Network.\n\n` : `\n`) +
      `Do you want to re-apply these network credentials to the ZBT-1 radio?`
    );
  } else {
    confirmMsg = (
      `Join Thread Network '${netDisplayName}'?\n\n` +
      `• Your Home Assistant Connect ZBT-1 will switch its active PAN ID, Extended PAN ID, and Network Key to match this network.\n` +
      `• It will become a Border Router / Router on the existing mesh.\n` +
      (makePref ? `• This network will be marked as Home Assistant's Preferred Thread Dataset.\n\n` : `\n`) +
      `Do you want to proceed?`
    );
  }

  const confirmed = window.confirm(confirmMsg);
  if (!confirmed) return;

  const btnJoin = document.getElementById("btn-execute-join-network");
  const banner = document.getElementById("join-network-banner");
  const bannerTitle = document.getElementById("join-banner-title");
  const bannerDesc = document.getElementById("join-banner-desc");
  const bannerSpinner = document.getElementById("join-banner-spinner");

  if (btnJoin) btnJoin.disabled = true;
  if (banner) banner.classList.remove("hidden");
  if (bannerTitle) bannerTitle.innerText = `Joining Thread Network '${netDisplayName}'...`;
  if (bannerDesc) bannerDesc.innerText = `Applying operational dataset via Home Assistant Core OTBR...`;
  if (bannerSpinner) {
    bannerSpinner.className = "fa-solid fa-spinner fa-spin";
    bannerSpinner.style.color = "#60a5fa";
  }

  try {
    const res = await fetch(apiPath("/api/otbr/join_network"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        dataset_id: datasetId,
        raw_tlv: rawTlv,
        make_preferred: makePref,
      }),
    });

    const data = await res.json();
    if (!data.success) {
      throw new Error(data.error || "Failed to join Thread network");
    }

    if (bannerTitle) bannerTitle.innerText = `Successfully Joined Network!`;
    if (bannerDesc) bannerDesc.innerText = data.message || `ZBT-1 is now active on '${netDisplayName}'.`;
    if (bannerSpinner) {
      bannerSpinner.className = "fa-solid fa-circle-check";
      bannerSpinner.style.color = "#34d399";
    }

    await fetchOtbrChannelInfo();
    await fetchJoinableNetworks();
    await scanSelectedNetwork(false);

    setTimeout(() => {
      if (btnJoin) btnJoin.disabled = false;
    }, 2000);
  } catch (err) {
    if (bannerTitle) bannerTitle.innerText = `Join Network Error`;
    if (bannerDesc) bannerDesc.innerText = err.message || "Failed to join network";
    if (bannerSpinner) {
      bannerSpinner.className = "fa-solid fa-triangle-exclamation";
      bannerSpinner.style.color = "#f87171";
    }
    if (btnJoin) btnJoin.disabled = false;
  }
}
