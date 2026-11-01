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
let currentZigbeeTelemetry = null;
let currentNetworkProtocol = "thread";
try {
  const savedProto = localStorage.getItem("mta_network_protocol");
  if (savedProto === "zigbee") currentNetworkProtocol = "zigbee";
} catch (_) {}
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
  layoutMode: (typeof localStorage !== "undefined" && localStorage.getItem("ha_matter_topology_layout")) || "house3d",
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
  initRoomSetterModal();

  fetchStatus();
  if (currentNetworkProtocol === "zigbee") {
    setNetworkProtocol("zigbee", false);
  } else {
    setNetworkProtocol("thread", false);
    loadThreadNetworks();
  }

  document.getElementById("btn-refresh").addEventListener("click", () => {
    if (currentNetworkProtocol === "zigbee") {
      fetchZigbeeDiagnostics(true);
    } else {
      scanSelectedNetwork();
    }
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
      if (currentNetworkProtocol === "zigbee") {
        if (currentZigbeeTelemetry) {
          box.value = JSON.stringify(currentZigbeeTelemetry, null, 2);
          return;
        }
        box.value = "Loading Zigbee telemetry...";
        try {
          const res = await fetch(apiPath("/api/zigbee/scan"));
          if (res.ok) {
            const zData = await res.json();
            currentZigbeeTelemetry = zData;
            box.value = JSON.stringify(zData, null, 2);
            return;
          }
        } catch (_) {}
      }
      box.value = "Loading full diagnostic log bundle...";
      try {
        const res = await fetch(apiPath("/api/diagnostics/logs"));
        if (res.ok) {
          const data = await res.json();
          box.value = data.bundle_text || JSON.stringify(currentNetworkProtocol === "zigbee" ? currentZigbeeTelemetry : currentTelemetry, null, 2);
          return;
        }
      } catch (_) {}
      const activeData = currentNetworkProtocol === "zigbee" ? currentZigbeeTelemetry : currentTelemetry;
      if (activeData) {
        box.value = JSON.stringify(activeData, null, 2);
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
    btnRefreshChannel.addEventListener("click", () => {
      if (currentNetworkProtocol === "zigbee") {
        fetchZigbeeDiagnostics(false);
      } else {
        fetchOtbrChannelInfo(true);
      }
      fetchCoexistenceSpectrum(true);
    });
  }

  const btnScanSpectrum = document.getElementById("btn-scan-spectrum");
  if (btnScanSpectrum) {
    btnScanSpectrum.addEventListener("click", () => fetchCoexistenceSpectrum(true));
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
      if (currentNetworkProtocol === "zigbee") {
        await fetchZigbeeDiagnostics(false);
      } else {
        await scanSelectedNetwork(false);
      }
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

  const btnProtoThread = document.getElementById("btn-protocol-thread");
  const btnProtoZigbee = document.getElementById("btn-protocol-zigbee");

  if (btnProtoThread) {
    btnProtoThread.addEventListener("click", () => setNetworkProtocol("thread", false));
  }
  if (btnProtoZigbee) {
    btnProtoZigbee.addEventListener("click", () => setNetworkProtocol("zigbee", false));
  }

  const btnTopRefresh = document.getElementById("btn-top-refresh-nets");
  if (btnTopRefresh) {
    btnTopRefresh.addEventListener("click", () => {
      if (currentNetworkProtocol === "zigbee") {
        fetchZigbeeDiagnostics(false);
      } else {
        loadThreadNetworks();
      }
    });
  }

  const btnCfgRefresh = document.getElementById("btn-refresh-thread-networks");
  if (btnCfgRefresh) {
    btnCfgRefresh.addEventListener("click", () => loadThreadNetworks());
  }

  const btnTopScan = document.getElementById("btn-top-scan");
  if (btnTopScan) {
    btnTopScan.addEventListener("click", () => {
      if (currentNetworkProtocol === "zigbee") {
        fetchZigbeeDiagnostics(true);
      } else {
        scanSelectedNetwork(true);
      }
    });
  }

  const btnCfgScan = document.getElementById("btn-scan-selected-network");
  if (btnCfgScan) {
    btnCfgScan.addEventListener("click", () => {
      if (currentNetworkProtocol === "zigbee") {
        fetchZigbeeDiagnostics(true);
      } else {
        scanSelectedNetwork(true);
      }
    });
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
      const symptoms = document.getElementById("user-symptoms");
      if (symptoms) {
        if (currentNetworkProtocol === "zigbee") {
          symptoms.value = "Analyze my Zigbee network health, identify any weak LQI router/end-device bottlenecks, check 2.4 GHz interference with Wi-Fi and Thread, and recommend fixes.";
        } else {
          symptoms.value = "Analyze my live Thread mesh and Matter nodes. Identify any split network conditions, weak RF signal links, offline nodes, or border router sync issues, and recommend specific fixes.";
        }
      }
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
    if (currentNetworkProtocol === "zigbee") {
      if (currentZigbeeTelemetry) renderZigbeeTables(currentZigbeeTelemetry);
    } else {
      if (currentTelemetry) renderRulesAndTables(currentTelemetry);
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
      if (currentNetworkProtocol === "zigbee") {
        if (currentZigbeeTelemetry) renderZigbeeTables(currentZigbeeTelemetry);
      } else {
        if (currentTelemetry) renderRulesAndTables(currentTelemetry);
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
      const vpG = document.getElementById("topology-viewport-g");
      if (vpG) {
        vpG.setAttribute("transform", "translate(0, 0) scale(1)");
      }
    });
  }

  // Topology Layout Mode Switcher (Force, Tree, Transit, Sankey, Matrix, 3D House Twin)
  const currentMode = topologyPhysicsState.layoutMode || "house3d";
  document.querySelectorAll(".btn-layout-mode").forEach((b) => {
    b.classList.toggle("active", b.getAttribute("data-layout") === currentMode);
  });

  document.querySelectorAll(".btn-layout-mode").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".btn-layout-mode").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      const mode = btn.getAttribute("data-layout") || "house3d";
      topologyPhysicsState.layoutMode = mode;
      try {
        localStorage.setItem("ha_matter_topology_layout", mode);
      } catch (_) {}
      dispatchTopologyRender();
    });
  });

  const btnQuick3D = document.getElementById("btn-quick-switch-3d");
  if (btnQuick3D) {
    btnQuick3D.addEventListener("click", () => {
      document.querySelectorAll(".btn-layout-mode").forEach((b) => b.classList.remove("active"));
      const btn3D = document.querySelector('.btn-layout-mode[data-layout="house3d"]');
      if (btn3D) btn3D.classList.add("active");
      topologyPhysicsState.layoutMode = "house3d";
      try {
        localStorage.setItem("ha_matter_topology_layout", "house3d");
      } catch (_) {}
      dispatchTopologyRender();
    });
  }

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
    if (topologyPhysicsState.layoutMode === "house3d") {
      setTimeout(() => onHouse3DResize(), 60);
    }
    if (currentNetworkProtocol === "zigbee") {
      if (currentZigbeeTelemetry && currentZigbeeTelemetry.topology) {
        renderTopologyData(currentZigbeeTelemetry.topology);
      } else {
        fetchZigbeeDiagnostics(false);
      }
    } else {
      if (currentTelemetry && currentTelemetry.topology) {
        renderTopologyData(currentTelemetry.topology);
      } else {
        fetchAndRenderTopology();
      }
    }
  } else if (tabId === "tab-channel") {
    if (currentNetworkProtocol === "zigbee") {
      if (currentZigbeeTelemetry) {
        renderZigbeeChannelInfo(currentZigbeeTelemetry);
      } else {
        fetchZigbeeDiagnostics(false);
      }
      fetchCoexistenceSpectrum();
    } else {
      fetchOtbrChannelInfo();
      fetchJoinableNetworks();
      fetchCoexistenceSpectrum();
    }
  } else if (tabId === "tab-rules") {
    if (currentNetworkProtocol === "zigbee") {
      if (currentZigbeeTelemetry) {
        renderZigbeeView(currentZigbeeTelemetry);
      } else {
        fetchZigbeeDiagnostics(false);
      }
    } else {
      if (currentTelemetry) {
        renderThreadView(currentTelemetry);
      } else {
        scanSelectedNetwork();
      }
    }
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

/* ==========================================================================
   NETWORK PROTOCOL SWITCHER: Thread (802.15.4) vs Zigbee (ZHA / Z2M)
   ========================================================================== */

function setNetworkProtocol(proto, triggerScan = false) {
  currentNetworkProtocol = proto === "zigbee" ? "zigbee" : "thread";
  try {
    localStorage.setItem("mta_network_protocol", currentNetworkProtocol);
  } catch (_) {}

  const btnThread = document.getElementById("btn-protocol-thread");
  const btnZigbee = document.getElementById("btn-protocol-zigbee");
  if (btnThread && btnZigbee) {
    if (currentNetworkProtocol === "zigbee") {
      btnThread.classList.remove("active");
      btnZigbee.classList.add("active");
    } else {
      btnZigbee.classList.remove("active");
      btnThread.classList.add("active");
    }
  }

  const scannerCard = document.getElementById("scanner-bar-card");
  const labelNet = document.getElementById("top-network-label");
  const topSelect = document.getElementById("top-thread-network");
  const btnScan = document.getElementById("btn-top-scan");
  const tabRulesBtn = document.getElementById("tab-nav-rules");
  const tabTopoBtn = document.getElementById("tab-nav-topology");
  const tabChanBtn = document.getElementById("tab-nav-channel");
  const tabAiBtn = document.getElementById("tab-nav-ai");
  const tabManualBtn = document.getElementById("tab-nav-manual");

  const headingTopo = document.getElementById("heading-topology");
  const descTopo = document.getElementById("desc-topology");
  const headingChan = document.getElementById("heading-channel");
  const descChan = document.getElementById("desc-channel");
  const headingAi = document.getElementById("heading-ai");
  const descAi = document.getElementById("desc-ai");
  const headingManual = document.getElementById("heading-manual");
  const descManual = document.getElementById("desc-manual");
  const symptomsArea = document.getElementById("user-symptoms");
  const joinCard = document.getElementById("select-target-join-network")?.closest(".card");

  if (currentNetworkProtocol === "zigbee") {
    if (scannerCard) {
      scannerCard.style.borderColor = "rgba(234, 179, 8, 0.45)";
      scannerCard.style.background = "linear-gradient(180deg, rgba(234, 179, 8, 0.08), rgba(31, 41, 55, 0.95))";
    }
    if (labelNet) {
      labelNet.style.color = "#facc15";
      labelNet.innerHTML = `<i class="fa-solid fa-cube"></i> 1. Select Zigbee Coordinator / Network`;
    }
    if (topSelect) {
      topSelect.innerHTML = `<option value="zigbee_active">🐝 Active Zigbee Mesh (ZHA / Zigbee2MQTT Coordinator)</option>`;
    }
    if (btnScan) {
      btnScan.innerHTML = `<i class="fa-solid fa-microchip"></i> 2. Scan Zigbee Network`;
    }
    if (tabRulesBtn) {
      tabRulesBtn.innerHTML = `<i class="fa-solid fa-cube"></i> Live Scan &amp; Zigbee Devices`;
    }
    if (tabTopoBtn) {
      tabTopoBtn.innerHTML = `<i class="fa-solid fa-diagram-project"></i> Zigbee Mesh Topology`;
    }
    if (tabChanBtn) {
      tabChanBtn.innerHTML = `<i class="fa-solid fa-tower-broadcast"></i> Zigbee Channel &amp; Coexistence`;
    }
    if (tabAiBtn) {
      tabAiBtn.innerHTML = `<i class="fa-solid fa-wand-magic-sparkles"></i> Zigbee AI Diagnostics`;
    }
    if (tabManualBtn) {
      tabManualBtn.innerHTML = `<i class="fa-solid fa-file-code"></i> Zigbee Logs &amp; Raw JSON`;
    }

    if (headingTopo) {
      headingTopo.innerHTML = `<i class="fa-solid fa-diagram-project" style="color: #facc15;"></i> Live Force-Directed Zigbee Mesh Topology (LQI Proximity Physics)`;
    }
    if (descTopo) {
      descTopo.innerHTML = `Zigbee Coordinator, Mains Routers, and End Devices dynamically position themselves by real LQI signal link quality. Stronger LQI links cluster together; weak links stretch further apart. Drag any node to interact!`;
    }
    if (headingChan) {
      headingChan.innerHTML = `<i class="fa-solid fa-tower-broadcast" style="color: #facc15;"></i> Zigbee Radio Adapter &amp; Channel Status`;
    }
    if (descChan) {
      descChan.innerHTML = `Inspect your active 802.15.4 Zigbee radio channel, evaluate 2.4 GHz Wi-Fi and Thread RF interference, and discover clean guard bands.`;
    }
    if (joinCard) {
      joinCard.style.display = "none";
    }
    if (headingAi) {
      headingAi.innerHTML = `<i class="fa-solid fa-wand-magic-sparkles" style="color: #facc15;"></i> Zigbee AI Diagnostic Engine`;
    }
    if (descAi) {
      descAi.innerHTML = `Sends your real scanned Zigbee telemetry (Coordinator, ZHA / Zigbee2MQTT device registry, LQI link qualities, RSSI metrics, 2.4 GHz coexistence, and mesh topology) to your chosen AI model for expert diagnosis and optimization advice.`;
    }
    if (symptomsArea) {
      symptomsArea.placeholder = "e.g. Why are some Zigbee sensors showing weak LQI, are there Wi-Fi channel conflicts on Ch 15, or where should I place additional Zigbee repeaters?";
    }
    if (headingManual) {
      headingManual.innerHTML = `<i class="fa-solid fa-file-code" style="color: #facc15;"></i> Raw Zigbee Telemetry &amp; Log Analyzer`;
    }
    if (descManual) {
      descManual.innerHTML = `Inspect and download the complete raw Zigbee JSON telemetry bundle, device list, LQI matrix, and 2.4 GHz RF coexistence data.`;
    }

    // Toggle Zigbee-specific UI controls across all tabs
    const btnPurgeOffline = document.getElementById("btn-purge-offline-nodes");
    if (btnPurgeOffline) btnPurgeOffline.style.display = "none";
    const migCard = document.getElementById("thread-migration-strategy-container");
    if (migCard) migCard.style.display = "none";
    const zbInfoBox = document.getElementById("zigbee-channel-info-box");
    if (zbInfoBox) zbInfoBox.style.display = "block";
    const faqCard = document.getElementById("card-channel-faq");
    if (faqCard) faqCard.style.display = "none";
    const lblPicker = document.getElementById("lbl-channel-picker-title");
    if (lblPicker) lblPicker.innerText = "Zigbee 802.15.4 Channels & Interference Assessment (11–26):";

    const colorSel = document.getElementById("topology-color-mode");
    if (colorSel) {
      colorSel.innerHTML = `
        <option value="role">Device Role (Coordinator / Router / End Device)</option>
        <option value="rssi">Signal Quality (LQI / RSSI Heatmap)</option>
        <option value="affinity">Coordinator / Parent Affinity</option>
        <option value="power">Power Source (Mains vs Battery)</option>
      `;
    }
    updateTopologyLegend();

    const btnRunAi = document.getElementById("btn-run-ai");
    if (btnRunAi) btnRunAi.innerHTML = `<i class="fa-solid fa-wand-magic-sparkles"></i> Run Zigbee AI Network Diagnosis`;
    const btnLoadRaw = document.getElementById("btn-load-raw-scan");
    if (btnLoadRaw) btnLoadRaw.innerHTML = `<i class="fa-solid fa-bolt"></i> Load Latest Zigbee Telemetry JSON`;
    const btnDownRaw = document.getElementById("btn-download-logs-manual");
    if (btnDownRaw) btnDownRaw.innerHTML = `<i class="fa-solid fa-file-arrow-down"></i> Download Zigbee JSON (.json)`;

    if (currentZigbeeTelemetry && !triggerScan) {
      renderZigbeeView(currentZigbeeTelemetry);
    } else {
      fetchZigbeeDiagnostics(triggerScan);
    }
  } else {
    // Thread mode
    if (scannerCard) {
      scannerCard.style.borderColor = "rgba(3, 169, 244, 0.45)";
      scannerCard.style.background = "linear-gradient(180deg, rgba(3, 169, 244, 0.08), rgba(31, 41, 55, 0.95))";
    }
    if (labelNet) {
      labelNet.style.color = "#38bdf8";
      labelNet.innerHTML = `<i class="fa-solid fa-tower-cell"></i> 1. Select Thread Network to Inspect`;
    }
    if (btnScan) {
      btnScan.innerHTML = `<i class="fa-solid fa-satellite-dish"></i> 2. Scan Selected Network`;
    }
    if (tabRulesBtn) {
      tabRulesBtn.innerHTML = `<i class="fa-solid fa-microscope"></i> Live Scan &amp; Nodes (Cluster 0x0035)`;
    }
    if (tabTopoBtn) {
      tabTopoBtn.innerHTML = `<i class="fa-solid fa-diagram-project"></i> Live Mesh Topology`;
    }
    if (tabChanBtn) {
      tabChanBtn.innerHTML = `<i class="fa-solid fa-tower-broadcast"></i> ZBT-1 / Channel &amp; Coexistence`;
    }
    if (tabAiBtn) {
      tabAiBtn.innerHTML = `<i class="fa-solid fa-wand-magic-sparkles"></i> AI Diagnostics Studio`;
    }
    if (tabManualBtn) {
      tabManualBtn.innerHTML = `<i class="fa-solid fa-file-code"></i> Log &amp; Raw JSON Analyzer`;
    }

    if (headingTopo) {
      headingTopo.innerHTML = `<i class="fa-solid fa-diagram-project"></i> Live Force-Directed Thread Mesh Topology (RF Proximity Physics)`;
    }
    if (descTopo) {
      descTopo.innerHTML = `Nodes dynamically position themselves by real RF signal proximity (<code>RSSI dBm</code>, <code>LQI</code> &amp; <code>Ping RTT</code>) — stronger signals pull closer together; weak links stretch further apart. Drag any node to interact!`;
    }
    if (headingChan) {
      headingChan.innerHTML = `<i class="fa-solid fa-tower-broadcast"></i> Home Assistant Connect ZBT-1 / OTBR Radio Channel Management`;
    }
    if (descChan) {
      descChan.innerHTML = `Inspect your active 802.15.4 radio channel, evaluate 2.4 GHz Wi-Fi interference, and safely migrate your Thread mesh to clean channels (e.g. Channel 25 or 26) with automatic Pending Dataset propagation across all devices.`;
    }
    if (joinCard) {
      joinCard.style.display = "";
    }
    const migCard = document.getElementById("thread-migration-strategy-container");
    if (migCard) migCard.style.display = "block";
    const zbInfoBox = document.getElementById("zigbee-channel-info-box");
    if (zbInfoBox) zbInfoBox.style.display = "none";
    const faqCard = document.getElementById("card-channel-faq");
    if (faqCard) faqCard.style.display = "block";
    const lblPicker = document.getElementById("lbl-channel-picker-title");
    if (lblPicker) lblPicker.innerText = "Select Target Operating Channel (11–26):";

    const colorSel = document.getElementById("topology-color-mode");
    if (colorSel) {
      colorSel.innerHTML = `
        <option value="role">Device Role (TBR / Router / SED)</option>
        <option value="rssi">Signal Quality (RSSI Heatmap)</option>
        <option value="affinity">Border Router / Parent Affinity</option>
        <option value="power">Power Source (Mains vs Battery)</option>
      `;
    }
    updateTopologyLegend();

    const btnRunAi = document.getElementById("btn-run-ai");
    if (btnRunAi) btnRunAi.innerHTML = `<i class="fa-solid fa-wand-magic-sparkles"></i> Run AI Diagnosis on Live Scan`;
    const btnLoadRaw = document.getElementById("btn-load-raw-scan");
    if (btnLoadRaw) btnLoadRaw.innerHTML = `<i class="fa-solid fa-eye"></i> Load Logs &amp; Scan into Box`;
    const btnDownRaw = document.getElementById("btn-download-logs-manual");
    if (btnDownRaw) btnDownRaw.innerHTML = `<i class="fa-solid fa-file-arrow-down"></i> Download Log Bundle (.log)`;

    if (headingAi) {
      headingAi.innerHTML = `<i class="fa-solid fa-robot"></i> AI Root-Cause Diagnostic Engine`;
    }
    if (descAi) {
      descAi.innerHTML = `Sends your real scanned telemetry (selected Thread network, Border Routers, Matter Cluster 0x0035 Neighbor Tables, RLOC16s, RSSI/LQI, kernel IPv6 routes, and ICMPv6 ping results) to your chosen AI model.`;
    }
    if (symptomsArea) {
      symptomsArea.placeholder = "e.g. Node 4 drops offline overnight, my Apple TV and HA ZBT-1 show different PAN IDs, or pings to fd00:: addresses time out...";
    }
    if (headingManual) {
      headingManual.innerHTML = `<i class="fa-solid fa-file-code"></i> Raw Telemetry Inspector &amp; Log Analyzer`;
    }
    if (descManual) {
      descManual.innerHTML = `Load or download the complete log &amp; telemetry bundle (Add-on logs, Matter Server logs, OTBR logs, and Cluster 0x0035 JSON), or paste external logs for AI analysis.`;
    }

    if (availableThreadNetworks && availableThreadNetworks.length > 0 && topSelect) {
      populateNetworkDropdown(topSelect, availableThreadNetworks, topSelect.value);
    }

    if (currentTelemetry && !triggerScan) {
      renderThreadView(currentTelemetry);
    } else {
      fetchLiveDiagnostics();
    }
  }
}

function renderThreadView(data) {
  if (!data) return;
  // Reset table headers and headings for Thread
  const headingBr = document.getElementById("heading-br-table");
  if (headingBr) headingBr.innerHTML = `<i class="fa-solid fa-tower-broadcast"></i> Discovered Thread Border Routers (mDNS <code>_meshcop._udp</code>, HA &amp; OTBR)`;

  const descBr = document.getElementById("desc-br-table");
  if (descBr) descBr.innerText = "Live Border Routers detected on your network with their Extended PAN ID, Channel, Mesh-Local Prefix, and ICMPv6 reachability.";

  const th1 = document.getElementById("th-br-1"); if (th1) th1.innerText = "Border Router";
  const th2 = document.getElementById("th-br-2"); if (th2) th2.innerText = "Thread Network";
  const th3 = document.getElementById("th-br-3"); if (th3) th3.innerText = "Extended PAN ID";
  const th4 = document.getElementById("th-br-4"); if (th4) th4.innerText = "Channel / PAN";
  const th5 = document.getElementById("th-br-5"); if (th5) th5.innerText = "IPv6 / IPv4 Address";
  const th6 = document.getElementById("th-br-6"); if (th6) th6.innerText = "Discovery Source";
  const th7 = document.getElementById("th-br-7"); if (th7) th7.innerText = "Ping RTT";

  const headingMatter = document.getElementById("heading-matter-table");
  if (headingMatter) headingMatter.innerHTML = `<i class="fa-solid fa-microchip"></i> Commissioned Matter Nodes &amp; Thread Cluster <code>0x0035</code> Telemetry`;

  const descMatter = document.getElementById("desc-matter-table");
  if (descMatter) descMatter.innerText = "Real-time attributes queried from python-matter-server: Routing Role, RLOC16, Extended PAN ID, Neighbor Table RSSI/LQI, Parent RLOC16, and live Ping test.";

  const tn1 = document.getElementById("th-node-1"); if (tn1) tn1.innerText = "ID";
  const tn2 = document.getElementById("th-node-2"); if (tn2) tn2.innerText = "Device / Vendor";
  const tn3 = document.getElementById("th-node-3"); if (tn3) tn3.innerText = "Role & RLOC16";
  const tn4 = document.getElementById("th-node-4"); if (tn4) tn4.innerText = "Extended PAN ID";
  const tn5 = document.getElementById("th-node-5"); if (tn5) tn5.innerText = "RF Signal (RSSI / LQI)";
  const tn6 = document.getElementById("th-node-6"); if (tn6) tn6.innerText = "Neighbors / Counters";
  const tn7 = document.getElementById("th-node-7"); if (tn7) tn7.innerText = "Thread IPv6 ULA";
  const tn8 = document.getElementById("th-node-8"); if (tn8) tn8.innerText = "Actions";

  renderKPIs(data);
  renderRulesAndTables(data);
  const rulesGrid = document.querySelector(".rules-grid");
  if (rulesGrid) {
    rulesGrid.style.display = "grid";
  }
  if (data.topology) {
    renderTopologyData(data.topology);
  }
  const topSelect = document.getElementById("top-thread-network");
  const selectedId = topSelect ? topSelect.value : "";
  updateSelectedNetworkStrip(selectedId);
}

async function fetchZigbeeDiagnostics(switchToScanTab = false) {
  const topFeedback = document.getElementById("top-scan-feedback");
  const btnTopScan = document.getElementById("btn-top-scan");
  if (btnTopScan) {
    btnTopScan.disabled = true;
    btnTopScan.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Scanning Zigbee (ZHA / Z2M)...`;
  }
  if (topFeedback) {
    topFeedback.style.color = "#facc15";
    topFeedback.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Probing Home Assistant Zigbee Coordinator, devices, neighbor tables &amp; LQI...`;
  }

  try {
    const res = await fetch(apiPath("/api/zigbee/scan"));
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    currentZigbeeTelemetry = data;

    renderZigbeeView(data);

    if (topFeedback) {
      if (data.scan_warning) {
        topFeedback.style.color = "#fbbf24";
        topFeedback.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> ${escapeHtml(data.scan_warning)}`;
      } else {
        topFeedback.style.color = "var(--color-success)";
        topFeedback.innerHTML = `✓ Zigbee scan complete: ${escapeHtml(data.coordinator?.name || 'Coordinator')} online • ${data.total_devices || 0} Devices (${data.routers_count || 0} Routers, ${data.end_devices_count || 0} End Devices)`;
      }
    }

    if (switchToScanTab) {
      activateTab("tab-rules");
    }
  } catch (err) {
    if (topFeedback) {
      topFeedback.style.color = "var(--color-danger)";
      topFeedback.innerHTML = `Zigbee scan failed: ${err.message}`;
    }
  } finally {
    if (btnTopScan) {
      btnTopScan.disabled = false;
      btnTopScan.innerHTML = `<i class="fa-solid fa-microchip"></i> 2. Scan Zigbee Network`;
    }
  }
}

function renderZigbeeKPIs(data) {
  // 1. Health Index
  const score = data.health_score !== undefined ? data.health_score : 100;
  const scoreElem = document.getElementById("health-score");
  const scoreDesc = document.getElementById("health-desc");
  if (scoreElem && scoreDesc) {
    scoreElem.innerText = score;
    if (score >= 80) {
      scoreElem.style.color = "var(--color-success)";
      scoreDesc.innerText = data.health_status || "Healthy Zigbee mesh";
    } else if (score >= 55) {
      scoreElem.style.color = "var(--color-warning)";
      scoreDesc.innerText = data.health_status || "Weak links detected";
    } else {
      scoreElem.style.color = "var(--color-danger)";
      scoreDesc.innerText = data.health_status || "Action required (Dropouts)";
    }
  }

  // 2. Coordinator & Mesh Density
  const splitElem = document.getElementById("split-status");
  const splitDesc = document.getElementById("split-desc");
  if (splitElem && splitDesc) {
    splitElem.innerHTML = `<span class="badge" style="background: #ca8a04; color: #fff;">Online</span>`;
    splitDesc.innerText = `${data.routers_count || 0} Routers, ${data.end_devices_count || 0} End Devices`;
  }

  // 3. 2.4GHz RF Coexistence
  const rfElem = document.getElementById("rf-status");
  const rfDesc = document.getElementById("rf-desc");
  if (rfElem && rfDesc) {
    const coex = data.coexistence || {};
    if (coex.thread_zigbee_collision) {
      rfElem.innerHTML = `<span class="badge badge-danger">Ch ${data.channel} Clash</span>`;
      rfDesc.innerText = "Frequency collision with Thread!";
    } else {
      rfElem.innerHTML = `<span class="badge badge-success">Ch ${data.channel}</span>`;
      rfDesc.innerText = `${data.frequency_mhz} MHz (${coex.thread_zigbee_message || 'Clean'})`;
    }
  }

  // 4. Link Quality
  const ipv6Elem = document.getElementById("ipv6-status");
  const ipv6Desc = document.getElementById("ipv6-desc");
  if (ipv6Elem && ipv6Desc) {
    const avg = data.avg_lqi || 200;
    const badgeClass = avg >= 180 ? 'badge-success' : (avg >= 100 ? 'badge-warning' : 'badge-danger');
    ipv6Elem.innerHTML = `<span class="badge ${badgeClass}">${avg} / 255</span>`;
    ipv6Desc.innerText = `${data.offline_count || 0} Offline, ${data.weak_count || 0} Weak Link(s)`;
  }
}

function renderZigbeeTables(data) {
  const coord = data.coordinator || {};
  const devices = data.devices || [];

  // Table 1: Coordinator
  const brCountBadge = document.getElementById("br-table-count");
  if (brCountBadge) brCountBadge.innerText = `1 Coordinator (${data.integration || 'ZHA'})`;

  const headingBr = document.getElementById("heading-br-table");
  if (headingBr) headingBr.innerHTML = `<i class="fa-solid fa-cube" style="color: #facc15;"></i> Discovered Zigbee Coordinators &amp; Adapters (${escapeHtml(data.integration || 'ZHA / Z2M')})`;

  const descBr = document.getElementById("desc-br-table");
  if (descBr) descBr.innerText = `Active Zigbee Coordinator, IEEE MAC, Radio Channel ${data.channel}, and PAN ID.`;

  const th1 = document.getElementById("th-br-1"); if (th1) th1.innerText = "Coordinator / Gateway";
  const th2 = document.getElementById("th-br-2"); if (th2) th2.innerText = "Integration Source";
  const th3 = document.getElementById("th-br-3"); if (th3) th3.innerText = "Extended PAN ID";
  const th4 = document.getElementById("th-br-4"); if (th4) th4.innerText = "Channel / PAN";
  const th5 = document.getElementById("th-br-5"); if (th5) th5.innerText = "IEEE 64-Bit Address";
  const th6 = document.getElementById("th-br-6"); if (th6) th6.innerText = "Devices Attached";
  const th7 = document.getElementById("th-br-7"); if (th7) th7.innerText = "Status";

  const tbodyBr = document.getElementById("tbody-border-routers");
  if (tbodyBr) {
    tbodyBr.innerHTML = `
      <tr style="border-bottom: 1px solid #37415166;">
        <td style="padding: 10px 8px;">
          <div style="display:flex; align-items:center; gap:6px; flex-wrap:wrap;">
            <strong style="color: #facc15;">${escapeHtml(coord.name || 'Zigbee Coordinator')}</strong>
            <span class="badge" style="background:#ca8a04; color:#fff; font-size:10px;">★ Root Coordinator</span>
          </div>
          <div style="font-size: 11px; color: var(--text-muted);">${escapeHtml(coord.model || coord.vendor || 'Zigbee 3.0 Adapter')}</div>
        </td>
        <td style="padding: 10px 8px;">
          <span class="badge badge-ha">${escapeHtml(data.integration || 'ZHA')}</span>
        </td>
        <td style="padding: 10px 8px;">
          <code style="color: #facc15;">${escapeHtml(data.extended_pan_id || 'N/A')}</code>
        </td>
        <td style="padding: 10px 8px;">
          <span class="badge" style="background: #3b82f6; color: #fff;">Ch ${data.channel}</span>
          <div style="font-size:11px; color:var(--text-muted); margin-top:2px;">PAN: <code>${escapeHtml(String(data.pan_id || 'N/A'))}</code></div>
        </td>
        <td style="padding: 10px 8px; font-family: monospace; font-size: 12px; color: #38bdf8;">
          ${escapeHtml(coord.ieee || 'N/A')}
        </td>
        <td style="padding: 10px 8px;">
          <span class="badge badge-info">${data.total_devices || 0} Device(s)</span>
          <div style="font-size:11px; color:var(--text-muted);">${data.routers_count || 0} Routers • ${data.end_devices_count || 0} End Devices</div>
        </td>
        <td style="padding: 10px 8px;">
          <span class="badge badge-success">${escapeHtml(coord.status || 'Online')}</span>
        </td>
      </tr>
    `;
  }

  // Table 2: Zigbee Devices
  const headingMatter = document.getElementById("heading-matter-table");
  if (headingMatter) headingMatter.innerHTML = `<i class="fa-solid fa-network-wired" style="color: #facc15;"></i> Commissioned Zigbee Nodes &amp; Mesh Telemetry (${data.total_devices || 0} Total)`;

  const descMatter = document.getElementById("desc-matter-table");
  if (descMatter) descMatter.innerText = `Real-time attributes queried from ${data.integration}: NWK Address, IEEE MAC, LQI, RSSI, Power Source, Area, and neighbor links.`;

  const tn1 = document.getElementById("th-node-1"); if (tn1) tn1.innerText = "NWK";
  const tn2 = document.getElementById("th-node-2"); if (tn2) tn2.innerText = "Device / Friendly Name";
  const tn3 = document.getElementById("th-node-3"); if (tn3) tn3.innerText = "Role";
  const tn4 = document.getElementById("th-node-4"); if (tn4) tn4.innerText = "IEEE 64-Bit MAC";
  const tn5 = document.getElementById("th-node-5"); if (tn5) tn5.innerText = "Signal (LQI / RSSI)";
  const tn6 = document.getElementById("th-node-6"); if (tn6) tn6.innerText = "Power & Battery";
  const tn7 = document.getElementById("th-node-7"); if (tn7) tn7.innerText = "Area / Room";
  const tn8 = document.getElementById("th-node-8"); if (tn8) tn8.innerText = "Actions";

  const qLower = (currentNodeSearchQuery || "").toLowerCase();
  const filtered = devices.filter(d => {
    if (currentNodeRoleFilter === "online" && !d.available) return false;
    if (currentNodeRoleFilter === "issues") {
      const isWeak = (d.lqi !== null && d.lqi !== undefined && d.lqi < 65) || (d.rssi !== null && d.rssi < -82);
      if (d.available && !isWeak) return false;
    } else if (currentNodeRoleFilter === "router" && d.device_type !== "router") {
      return false;
    } else if (currentNodeRoleFilter === "end_device" && d.device_type === "router") {
      return false;
    }

    if (!qLower) return true;
    const searchable = [
      d.name || "",
      d.model || "",
      d.manufacturer || "",
      d.ieee || "",
      String(d.nwk || ""),
      d.ha_area || "",
    ].join(" ").toLowerCase();
    return searchable.includes(qLower);
  });

  const matterCountBadge = document.getElementById("matter-table-count");
  if (matterCountBadge) matterCountBadge.innerText = `${filtered.length} Zigbee Node(s)`;

  const tbodyMatter = document.getElementById("tbody-matter-nodes");
  if (!tbodyMatter) return;

  if (filtered.length === 0) {
    tbodyMatter.innerHTML = `
      <tr>
        <td colspan="8" style="padding: 18px; color: var(--text-muted); text-align: center;">
          No matching Zigbee devices found.
        </td>
      </tr>
    `;
    return;
  }

  tbodyMatter.innerHTML = filtered.map(d => {
    const isRouter = d.device_type === "router";
    const lqi = d.lqi !== null && d.lqi !== undefined ? d.lqi : null;
    let lqiBadge = `<span style="color:var(--text-muted)">--</span>`;
    if (lqi !== null) {
      const badgeClass = lqi >= 180 ? 'badge-success' : (lqi >= 90 ? 'badge-warning' : 'badge-danger');
      lqiBadge = `<span class="badge ${badgeClass}">${lqi} / 255</span>`;
    }

    let powerCell = `<span class="badge" style="background:#334155; color:#cbd5e1;"><i class="fa-solid fa-bolt"></i> Mains</span>`;
    if (d.power_source === "Battery" || d.battery !== undefined) {
      const batVal = d.battery !== undefined ? d.battery : '--';
      powerCell = `<span class="badge" style="background:#1e1b4b; color:#a78bfa; border:1px solid #6366f144;"><i class="fa-solid fa-battery-half"></i> ${batVal}%</span>`;
    }

    const nwkStr = d.nwk !== null && d.nwk !== undefined ? (typeof d.nwk === 'number' ? `0x${d.nwk.toString(16).padStart(4, '0').toUpperCase()}` : d.nwk) : '--';

    return `
      <tr style="border-bottom: 1px solid #37415166;">
        <td style="padding: 10px 8px; font-family: monospace; font-size: 12px; color: #facc15;">
          ${escapeHtml(nwkStr)}
        </td>
        <td style="padding: 10px 8px;">
          <strong>${escapeHtml(d.name || 'Zigbee Device')}</strong>
          <div style="font-size: 11px; color: var(--text-muted);">${escapeHtml(d.manufacturer || '')} • ${escapeHtml(d.model || '')}</div>
        </td>
        <td style="padding: 10px 8px;">
          ${isRouter 
            ? `<span class="badge" style="background:#065f46; color:#34d399; font-weight:700;"><i class="fa-solid fa-repeat"></i> Router</span>` 
            : `<span class="badge" style="background:#312e81; color:#c084fc;"><i class="fa-solid fa-satellite"></i> End Device</span>`}
        </td>
        <td style="padding: 10px 8px; font-family: monospace; font-size: 11px; color: var(--text-muted);">
          ${escapeHtml(d.ieee || '--')}
        </td>
        <td style="padding: 10px 8px;">
          <div style="display:flex; align-items:center; gap:6px;">
            ${lqiBadge}
            ${d.rssi !== null && d.rssi !== undefined ? `<span style="font-size:11px; color:var(--text-muted);">${d.rssi}dBm</span>` : ''}
          </div>
        </td>
        <td style="padding: 10px 8px;">
          ${powerCell}
        </td>
        <td style="padding: 10px 8px;">
          ${d.ha_area ? `<span class="badge badge-info">📍 ${escapeHtml(d.ha_area)}</span>` : '<span style="color:var(--text-muted)">--</span>'}
        </td>
        <td style="padding: 10px 8px;">
          <button type="button" class="btn btn-outline" style="font-size:11px; padding:3px 8px;" onclick="inspectZigbeeDevice('${escapeHtml(d.ieee)}')">
            <i class="fa-solid fa-magnifying-glass"></i> Inspect
          </button>
        </td>
      </tr>
    `;
  }).join("");
}

function renderZigbeeView(data) {
  if (!data) return;
  renderZigbeeKPIs(data);
  renderZigbeeTables(data);
  renderZigbeeDiagnosticRules(data);
  renderZigbeeChannelInfo(data);

  const rulesGrid = document.querySelector(".rules-grid");
  if (rulesGrid) {
    rulesGrid.style.display = "grid";
  }

  if (data.topology) {
    renderTopologyData(data.topology);
  }

  // Update selected network strip
  const strip = document.getElementById("selected-network-badges");
  if (strip) {
    const coord = data.coordinator || {};
    strip.innerHTML = `
      <span class="badge" style="background:#ca8a04; color:#fff;"><i class="fa-solid fa-cube"></i> Zigbee</span>
      <span><strong>Coordinator:</strong> ${escapeHtml(coord.name || 'Coordinator')}</span>
      <span class="badge badge-ha">Ch ${data.channel} (${data.frequency_mhz} MHz)</span>
      <span class="badge badge-info">PAN: ${escapeHtml(String(data.pan_id || '0x1A2B'))}</span>
      <span class="badge" style="background:#1e293b; color:#94a3b8;">${data.total_devices || 0} Devices (${data.routers_count || 0} Routers, ${data.end_devices_count || 0} Sensors)</span>
      ${data.is_demo ? `<span class="badge badge-warning" style="font-size:10px;">Demonstration Network</span>` : ''}
    `;
  }
}

function renderZigbeeDiagnosticRules(data) {
  if (!data) return;
  const coord = data.coordinator || {};
  const coex = data.coexistence || {};

  // Card 1: Coordinator & Network Identity
  const t1 = document.getElementById("rule-title-1"); if (t1) t1.innerText = "1. Zigbee Coordinator & Network Identity";
  const s1 = document.getElementById("rule-sub-1"); if (s1) s1.innerText = "ZHA / Zigbee2MQTT Settings, Channel & PAN ID";
  const i1 = document.getElementById("rule-icon-1"); if (i1) i1.className = "fa-solid fa-tower-broadcast rule-icon";
  const b1 = document.getElementById("rule-badge-split");
  if (b1) {
    b1.innerText = coord.status || "Online";
    b1.className = "badge badge-success";
  }
  const txt1 = document.getElementById("rule-text-split");
  if (txt1) {
    txt1.innerText = `${coord.name || 'Coordinator'} online on Channel ${data.channel} (${data.frequency_mhz} MHz) • PAN ID: ${data.pan_id}`;
  }
  const d1 = document.getElementById("split-networks-detail");
  if (d1) {
    d1.innerHTML = `
      <div style="font-size:12px; display:flex; flex-direction:column; gap:6px;">
        <div><strong>Coordinator Adapter:</strong> <span style="color:#facc15;">${escapeHtml(coord.name || 'Zigbee Coordinator')}</span> (${escapeHtml(coord.model || coord.vendor || 'Zigbee 3.0 Adapter')})</div>
        <div><strong>Integration Source:</strong> <span class="badge badge-ha">${escapeHtml(data.integration || 'ZHA')}</span></div>
        <div><strong>Operating Channel:</strong> <span class="badge badge-info">Channel ${data.channel} (${data.frequency_mhz} MHz)</span></div>
        <div><strong>PAN ID:</strong> <code>${escapeHtml(String(data.pan_id || '0x1A2B'))}</code> • <strong>Extended PAN ID:</strong> <code>${escapeHtml(String(data.extended_pan_id || 'N/A'))}</code></div>
        <div><strong>IEEE MAC:</strong> <code style="color:#38bdf8;">${escapeHtml(String(coord.ieee || 'N/A'))}</code></div>
      </div>
    `;
  }

  // Card 2: 2.4 GHz RF Coexistence
  const t2 = document.getElementById("rule-title-2"); if (t2) t2.innerText = "2. 2.4 GHz Zigbee RF Coexistence";
  const s2 = document.getElementById("rule-sub-2"); if (s2) s2.innerText = `Zigbee Channel ${data.channel} vs 20MHz Wi-Fi (1, 6, 11) & Thread`;
  const i2 = document.getElementById("rule-icon-2"); if (i2) i2.className = "fa-solid fa-satellite-dish rule-icon";
  const b2 = document.getElementById("rule-badge-rf");
  const txt2 = document.getElementById("rule-text-rf");
  const d2 = document.getElementById("rf-coexistence-detail");

  const isCollision = coex.thread_zigbee_collision;
  let rfStatus = "CLEAN";
  let rfBadgeClass = "badge-success";
  let rfDesc = `Zigbee Channel ${data.channel} has minimal 2.4 GHz interference.`;

  if (isCollision) {
    rfStatus = "COLLISION";
    rfBadgeClass = "badge-danger";
    rfDesc = `Direct collision: Zigbee and Thread share Channel ${data.channel}! Migrate one protocol.`;
  } else if (data.channel === 15 || data.channel === 20 || data.channel === 25 || data.channel === 26) {
    rfStatus = "GUARD BAND";
    rfBadgeClass = "badge-success";
    rfDesc = `Channel ${data.channel} sits in a safe guard band between 2.4 GHz Wi-Fi channels.`;
  } else {
    rfStatus = "MODERATE";
    rfBadgeClass = "badge-warning";
    rfDesc = `Channel ${data.channel} operates inside a standard Wi-Fi channel spectrum band.`;
  }

  if (b2) {
    b2.innerText = rfStatus;
    b2.className = `badge ${rfBadgeClass}`;
  }
  if (txt2) txt2.innerText = rfDesc;
  if (d2) {
    d2.style.display = "block";
    d2.innerHTML = `
      <div style="font-size:12px;">
        <div><strong>Thread Network Status:</strong> ${isCollision ? '<span style="color:#f87171;">Operating on Same Channel</span>' : '<span style="color:#34d399;">Operating on Separate Channel</span>'}</div>
        <div><strong>Coexistence Recommendation:</strong> ${escapeHtml(coex.recommendation_summary || 'Channels 15, 20, and 25 provide the cleanest 2.4 GHz clearance.')}</div>
      </div>
    `;
  }

  // Card 3: Mesh Density & Routing Backbone
  const t3 = document.getElementById("rule-title-3"); if (t3) t3.innerText = "3. Zigbee Mesh Density & Routing Backbone";
  const s3 = document.getElementById("rule-sub-3"); if (s3) s3.innerText = "Mains-Powered Routers vs Battery-Powered End Devices";
  const i3 = document.getElementById("rule-icon-3"); if (i3) i3.className = "fa-solid fa-sitemap rule-icon";
  const b3 = document.getElementById("rule-badge-ipv6");
  const txt3 = document.getElementById("rule-text-ipv6");
  const d3 = document.getElementById("ipv6-routes-detail");

  const rCount = data.routers_count || 0;
  const eCount = data.end_devices_count || 0;
  const isHealthyDensity = rCount >= 2 || (rCount >= 1 && eCount <= 4);

  if (b3) {
    b3.innerText = isHealthyDensity ? "HEALTHY BACKBONE" : "LOW REPEATERS";
    b3.className = `badge ${isHealthyDensity ? 'badge-success' : 'badge-warning'}`;
  }
  if (txt3) {
    txt3.innerText = `${rCount} Mains-powered Routers providing mesh repeating for ${eCount} Battery End Devices.`;
  }
  if (d3) {
    const routerList = (data.devices || []).filter(d => (d.device_type || "").toLowerCase() === "router" || d.power_source === "Mains");
    d3.innerHTML = routerList.length > 0
      ? `<pre style="margin:0; font-family:var(--font-mono); font-size:11px; color:#cbd5e1;">` + routerList.map(r => `• ${escapeHtml(r.name)} (${escapeHtml(r.model || 'Router')}) — LQI: ${r.lqi || 'N/A'}/255 ${r.ha_area ? '[' + escapeHtml(r.ha_area) + ']' : ''}`).join("\n") + `</pre>`
      : `<span style="color:#fbbf24; font-size:12px;">No dedicated mains-powered router nodes discovered. Battery sensors are connecting directly to Coordinator. Consider adding Zigbee smart plugs to extend coverage.</span>`;
  }

  // Card 4: Link Quality (LQI) & Battery Health
  const t4 = document.getElementById("rule-title-4"); if (t4) t4.innerText = "4. Link Quality (LQI) & Battery Health";
  const s4 = document.getElementById("rule-sub-4"); if (s4) s4.innerText = "LQI Signal Attenuation & Battery Levels";
  const i4 = document.getElementById("rule-icon-4"); if (i4) i4.className = "fa-solid fa-signal rule-icon";
  const b4 = document.getElementById("rule-badge-nodes");
  const txt4 = document.getElementById("rule-text-nodes");
  const d4 = document.getElementById("nodes-detail-list");

  const avgLqi = data.avg_lqi || 200;
  const weakCount = data.weak_count || 0;
  const offCount = data.offline_count || 0;

  if (b4) {
    b4.innerText = `Avg LQI: ${avgLqi}/255`;
    b4.className = `badge ${avgLqi >= 140 ? 'badge-success' : (avgLqi >= 90 ? 'badge-warning' : 'badge-danger')}`;
  }
  if (txt4) {
    txt4.innerText = `${data.total_devices - offCount}/${data.total_devices} devices operational. ${offCount} offline, ${weakCount} weak link(s).`;
  }
  if (d4) {
    const weakDevs = (data.devices || []).filter(d => !d.available || (d.lqi !== null && d.lqi < 65) || (d.battery !== null && d.battery < 20));
    if (weakDevs.length > 0) {
      d4.innerHTML = weakDevs.map(d => {
        const isOff = !d.available;
        return `
          <div style="padding:4px 0; border-bottom:1px solid #334155; font-size:12px;">
            <strong style="color:${isOff ? '#f87171' : '#fbbf24'};">${isOff ? '🔴 OFFLINE' : '⚠️ ATTENTION'}: ${escapeHtml(d.name)}</strong>
            <span style="color:var(--text-muted); font-size:11px;">(${escapeHtml(d.model || '')}) — LQI: ${d.lqi || 'N/A'}/255 • Battery: ${d.battery !== null && d.battery !== undefined ? d.battery + '%' : 'Mains'}</span>
          </div>
        `;
      }).join("");
    } else {
      d4.innerHTML = `<span style="color:#34d399; font-size:12px;">✓ All Zigbee devices have healthy LQI signal strength and adequate battery reserves.</span>`;
    }
  }
}

function renderZigbeeChannelInfo(data) {
  if (!data) return;
  const coord = data.coordinator || {};

  // 1. Hardware card details
  const lblAdapter = document.getElementById("lbl-radio-adapter");
  if (lblAdapter) lblAdapter.innerText = "Zigbee Radio Coordinator";

  const nameEl = document.getElementById("zbt1-hardware-name");
  const modelEl = document.getElementById("zbt1-hardware-model");
  const stateBadge = document.getElementById("zbt1-radio-state");
  const otbrBadge = document.getElementById("zbt1-otbr-status");

  if (nameEl) nameEl.innerText = coord.name || "Zigbee Coordinator";
  if (modelEl) modelEl.innerText = `${coord.model || coord.vendor || "Silicon Labs EFR32 / Zigbee Adapter"} (${data.integration || "ZHA"})`;
  if (stateBadge) {
    stateBadge.innerText = `ZIGBEE ACTIVE`;
    stateBadge.className = `badge badge-success`;
  }
  if (otbrBadge) {
    otbrBadge.innerText = `${data.total_devices || 0} Nodes Connected`;
    otbrBadge.className = `badge badge-info`;
  }

  // 2. Current Channel & Frequency
  const chNumEl = document.getElementById("zbt1-current-channel-num");
  const freqEl = document.getElementById("zbt1-current-freq");
  const rfBadgeContainer = document.getElementById("zbt1-current-rf-badge");

  const zbCh = data.channel || 15;
  const zbFreq = data.frequency_mhz || (2405 + 5 * (zbCh - 11));

  if (chNumEl) {
    chNumEl.innerText = `Ch ${zbCh}`;
    chNumEl.style.color = "#facc15";
  }
  if (freqEl) freqEl.innerText = `(${zbFreq} MHz)`;
  if (rfBadgeContainer) {
    if (zbCh === 15 || zbCh === 20 || zbCh === 25 || zbCh === 26) {
      rfBadgeContainer.innerHTML = `<span class="badge badge-success" style="font-size:11px;"><i class="fa-solid fa-shield-check"></i> Channel ${zbCh} — Clean Guard Band</span>`;
    } else {
      rfBadgeContainer.innerHTML = `<span class="badge badge-warning" style="font-size:11px;"><i class="fa-solid fa-triangle-exclamation"></i> Channel ${zbCh} — Moderate Wi-Fi Overlap</span>`;
    }
  }

  // 3. Network Identity
  const lblMesh = document.getElementById("lbl-mesh-identity");
  if (lblMesh) lblMesh.innerText = "Zigbee Mesh Identity";

  const netNameEl = document.getElementById("zbt1-network-name");
  const xpanEl = document.getElementById("zbt1-xpan");
  const panidEl = document.getElementById("zbt1-panid");
  const rloc16El = document.getElementById("zbt1-rloc16");

  if (netNameEl) netNameEl.innerText = `Zigbee Mesh (${data.integration || "ZHA"})`;
  if (xpanEl) {
    xpanEl.innerText = data.extended_pan_id || "--";
    xpanEl.style.color = "#facc15";
  }
  if (panidEl) panidEl.innerText = String(data.pan_id || "--");
  if (rloc16El) rloc16El.innerText = `IEEE: ${coord.ieee || "--"}`;

  // Hide Thread PAN join card & Thread migration card
  const joinCard = document.getElementById("select-target-join-network")?.closest(".card");
  if (joinCard) joinCard.style.display = "none";
  const migCard = document.getElementById("thread-migration-strategy-container");
  if (migCard) migCard.style.display = "none";
  const zbInfoBox = document.getElementById("zigbee-channel-info-box");
  if (zbInfoBox) zbInfoBox.style.display = "block";
  const faqCard = document.getElementById("card-channel-faq");
  if (faqCard) faqCard.style.display = "none";
  const lblPicker = document.getElementById("lbl-channel-picker-title");
  if (lblPicker) lblPicker.innerText = "Zigbee 802.15.4 Channels & Interference Assessment (11–26):";

  renderZigbeeChannelPickerGrid(zbCh);
}

function renderZigbeeChannelPickerGrid(activeCh) {
  const grid = document.getElementById("channel-picker-grid");
  if (!grid) return;

  const zbChannels = [
    { channel: 11, frequency_mhz: 2405, wifi_overlap: "Wi-Fi 1", is_guard: false },
    { channel: 12, frequency_mhz: 2410, wifi_overlap: "Wi-Fi 1", is_guard: false },
    { channel: 13, frequency_mhz: 2415, wifi_overlap: "Wi-Fi 1", is_guard: false },
    { channel: 14, frequency_mhz: 2420, wifi_overlap: "Wi-Fi 1", is_guard: false },
    { channel: 15, frequency_mhz: 2425, wifi_overlap: null, is_guard: true, label: "★ Best Guard" },
    { channel: 16, frequency_mhz: 2430, wifi_overlap: "Wi-Fi 6", is_guard: false },
    { channel: 17, frequency_mhz: 2435, wifi_overlap: "Wi-Fi 6", is_guard: false },
    { channel: 18, frequency_mhz: 2440, wifi_overlap: "Wi-Fi 6", is_guard: false },
    { channel: 19, frequency_mhz: 2445, wifi_overlap: "Wi-Fi 6", is_guard: false },
    { channel: 20, frequency_mhz: 2450, wifi_overlap: null, is_guard: true, label: "★ Guard Band" },
    { channel: 21, frequency_mhz: 2455, wifi_overlap: "Wi-Fi 11", is_guard: false },
    { channel: 22, frequency_mhz: 2460, wifi_overlap: "Wi-Fi 11", is_guard: false },
    { channel: 23, frequency_mhz: 2465, wifi_overlap: "Wi-Fi 11", is_guard: false },
    { channel: 24, frequency_mhz: 2470, wifi_overlap: "Wi-Fi 11", is_guard: false },
    { channel: 25, frequency_mhz: 2475, wifi_overlap: null, is_guard: true, label: "★ Clean Zone" },
    { channel: 26, frequency_mhz: 2480, wifi_overlap: null, is_guard: true, label: "Low Power" },
  ];

  grid.innerHTML = zbChannels.map(ch => {
    const isCur = ch.channel === activeCh;
    let borderCol = isCur ? "#facc15" : (ch.is_guard ? "#10b98155" : "#334155");
    let bgCol = isCur ? "#854d0e44" : (ch.is_guard ? "#064e3b22" : "#1e293b");
    let badgeHtml = "";

    if (isCur) {
      badgeHtml = `<span class="badge" style="background:#ca8a04; color:#fff; font-size:9px; padding:1px 5px;">🐝 Active Zigbee</span>`;
    } else if (ch.label) {
      badgeHtml = `<span class="badge badge-success" style="font-size:9px; padding:1px 5px;">${ch.label}</span>`;
    } else if (ch.wifi_overlap) {
      badgeHtml = `<span class="badge badge-danger" style="font-size:9px; padding:1px 5px;">${ch.wifi_overlap}</span>`;
    }

    return `
      <div
        class="channel-tile"
        data-channel="${ch.channel}"
        data-freq="${ch.frequency_mhz}"
        style="
          background: ${bgCol};
          border: 2px solid ${borderCol};
          padding: 10px 8px;
          border-radius: 6px;
          cursor: pointer;
          transition: all 0.15s ease;
          display: flex;
          flex-direction: column;
          gap: 4px;
        "
        onclick="onSelectZigbeeChannelTile(${ch.channel}, ${ch.frequency_mhz}, '${ch.is_guard ? 'Clean Guard Band' : 'Wi-Fi 20MHz Overlap'}')"
      >
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <strong style="color:${isCur ? '#facc15' : '#f8fafc'}; font-size:13px;">Ch ${ch.channel}</strong>
          <span style="font-size:10px; color:var(--text-muted);">${ch.frequency_mhz} MHz</span>
        </div>
        <div style="margin-top:2px;">${badgeHtml}</div>
      </div>
    `;
  }).join("");
}

function onSelectZigbeeChannelTile(ch, freq, rec) {
  const lbl = document.getElementById("selected-target-channel-label");
  if (lbl) {
    lbl.innerText = `Zigbee Channel ${ch} (${freq} MHz) — ${rec}`;
    lbl.style.color = "#facc15";
  }
}
window.onSelectZigbeeChannelTile = onSelectZigbeeChannelTile;

function inspectZigbeeDevice(ieee) {
  if (!currentZigbeeTelemetry || !currentZigbeeTelemetry.devices) return;
  const dev = currentZigbeeTelemetry.devices.find(d => (d.ieee || "").toLowerCase() === (ieee || "").toLowerCase());
  if (!dev) return;

  const nodeObj = {
    id: `zb_${(dev.ieee || '').replace(/:/g, '')}`,
    node_id: null,
    label: dev.name,
    routing_role: dev.device_type === "router" ? "Zigbee Router (Mains Relay)" : "Zigbee End Device (Battery)",
    vendor: dev.manufacturer,
    model: dev.model,
    rloc16: dev.nwk ? (typeof dev.nwk === 'number' ? `0x${dev.nwk.toString(16).padStart(4, '0').toUpperCase()}` : dev.nwk) : null,
    ext_address: dev.ieee,
    extended_pan_id: currentZigbeeTelemetry.extended_pan_id,
    rssi: dev.rssi,
    lqi: dev.lqi,
    battery: dev.battery,
    status: dev.available ? (dev.lqi !== null && dev.lqi < 65 ? "weak" : "online") : "offline",
    ha_area: dev.ha_area,
    details: `${dev.device_type === "router" ? "Mains-powered Router" : "Battery Sleepy Sensor"} • LQI ${dev.lqi || 'N/A'}/255` + (dev.battery !== undefined ? ` • Battery ${dev.battery}%` : ''),
  };
  showNodeInspector(nodeObj);
}

window.inspectZigbeeDevice = inspectZigbeeDevice;
window.setNetworkProtocol = setNetworkProtocol;

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
    const payload = {
      user_notes: userNotes,
      use_cached_scan: currentNetworkProtocol !== "zigbee",
      protocol: currentNetworkProtocol,
      ai_provider: studioProvider,
      ai_model: studioModel,
    };
    if (currentNetworkProtocol === "zigbee" && currentZigbeeTelemetry) {
      payload.custom_data = currentZigbeeTelemetry;
    }

    const res = await fetch(apiPath("/api/diagnostics/analyze"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const data = await res.json();
    loading.classList.add("hidden");
    resultsCard.classList.remove("hidden");

    if (data.telemetry) {
      if (currentNetworkProtocol === "zigbee") {
        currentZigbeeTelemetry = data.telemetry;
        renderZigbeeView(currentZigbeeTelemetry);
      } else {
        currentTelemetry = data.telemetry;
        renderKPIs(currentTelemetry);
        renderRulesAndTables(currentTelemetry);
      }
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
    if (currentNetworkProtocol === "zigbee") {
      countElem.innerText = `Discovered Zigbee Coordinator: ${brNames || 'None detected yet'}`;
    } else {
      countElem.innerText = `Discovered Border Routers (${brs.length}): ${brNames || 'None detected yet'}`;
    }
  }
}

function dispatchTopologyRender() {
  if (currentNetworkProtocol === "zigbee") {
    if (currentZigbeeTelemetry && currentZigbeeTelemetry.topology) {
      lastTopologyData = currentZigbeeTelemetry.topology;
    }
  } else {
    if (currentTelemetry && currentTelemetry.topology) {
      lastTopologyData = currentTelemetry.topology;
    }
  }
  if (!lastTopologyData) return;
  const nodes = lastTopologyData.nodes || [];
  const edges = lastTopologyData.edges || [];
  const mode = topologyPhysicsState.layoutMode || "force";

  const svg = document.getElementById("mesh-svg");
  const matrixContainer = document.getElementById("topology-matrix-container");
  const house3dContainer = document.getElementById("topology-3d-container");
  if (!svg || !matrixContainer) return;

  if (topologyPhysicsState.animFrameId) {
    cancelAnimationFrame(topologyPhysicsState.animFrameId);
    topologyPhysicsState.animFrameId = null;
  }

  if (mode === "house3d") {
    svg.style.display = "none";
    matrixContainer.classList.add("hidden");
    if (house3dContainer) {
      house3dContainer.classList.remove("hidden");
      onHouse3DResize();
    }
    renderHouse3DTopology(nodes, edges);
    return;
  }

  if (house3dContainer) house3dContainer.classList.add("hidden");

  if (mode === "matrix") {
    svg.style.display = "none";
    matrixContainer.classList.remove("hidden");
    renderSignalMatrix(matrixContainer, nodes, edges);
    return;
  }

  svg.style.display = "block";
  matrixContainer.classList.add("hidden");

  if (mode === "force" || mode === "tree") {
    topologyPhysicsState.layoutMode = mode;
    renderSvgTopology(nodes, edges);
  } else if (mode === "transit") {
    renderTransitMap(nodes, edges);
  } else if (mode === "sankey") {
    renderSankeyFlow(nodes, edges);
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

  const isZigbee = currentNetworkProtocol === "zigbee" || (n.routing_role && n.routing_role.toLowerCase().includes("zigbee")) || String(n.id).startsWith("zb_");
  const hasMatterNodeId = !isZigbee && n.node_id !== undefined && n.node_id !== null && n.node_id !== 0;

  const roomAssigned = resolveDeviceRoom(n);

  panel.classList.remove("hidden");
  title.innerText = `${n.label || 'Device'} (${n.routing_role || (n.type ? n.type.replace('_', ' ').toUpperCase() : 'DEVICE')})${n.preferred ? ' ★ Root/Preferred' : ''}`;
  content.innerHTML = `
    <div style="font-size: 13px; line-height: 1.6;">
      <div><strong>Status:</strong> <span class="badge ${n.status === 'online' ? 'badge-success' : (n.status === 'weak' ? 'badge-warning' : 'badge-danger')}">${(n.status || 'ONLINE').toUpperCase()}</span></div>
      ${n.ha_area ? `<div><strong>Area / Room:</strong> <span class="badge badge-info">📍 ${escapeHtml(n.ha_area)}</span></div>` : ''}
      ${n.ext_address ? `<div><strong>IEEE MAC Address:</strong> <code>${escapeHtml(n.ext_address)}</code></div>` : ''}
      ${n.rloc16 ? `<div><strong>${isZigbee ? 'NWK Address' : 'RLOC16'}:</strong> <code>${escapeHtml(n.rloc16)}</code></div>` : ''}
      ${n.lqi !== null && n.lqi !== undefined ? `<div><strong>Link Quality (LQI):</strong> <code>${escapeHtml(String(n.lqi))} / 255</code></div>` : ''}
      ${n.rssi !== null && n.rssi !== undefined ? `<div><strong>Signal Strength (RSSI):</strong> <code>${escapeHtml(String(n.rssi))} dBm</code></div>` : ''}
      ${n.battery !== undefined && n.battery !== null ? `<div><strong>Battery:</strong> <span class="badge" style="background:#1e1b4b; color:#a78bfa;">🔋 ${n.battery}%</span></div>` : ''}
      <div><strong>Telemetry:</strong> ${escapeHtml(n.details || 'Active network link')}</div>

      <!-- 3D Digital Twin Room Assignment -->
      <div style="margin-top: 12px; padding: 10px 12px; background: #0f172a; border-radius: 6px; border: 1px solid #334155;">
        <div style="font-size: 11px; font-weight: 700; color: #38bdf8; margin-bottom: 6px; display: flex; align-items: center; justify-content: space-between;">
          <span><i class="fa-solid fa-house-laptop"></i> 3D House Twin Room Assignment:</span>
          <span id="inspector-room-badge" class="badge" style="font-size: 10px; background: ${roomAssigned.isCustom ? '#0284c7' : '#334155'}; color: #f8fafc;">
            ${roomAssigned.isCustom ? 'Custom Override' : 'Auto-Detected'}
          </span>
        </div>
        <div style="display: flex; gap: 8px; align-items: center;">
          <select id="inspector-room-select" class="form-control" style="font-size: 12px; padding: 5px 8px; background: #1e293b; color: #f8fafc; border: 1px solid #475569; border-radius: 4px; flex: 1;">
            ${generateRoomOptionsHtml(roomAssigned.roomId)}
          </select>
          <button type="button" id="btn-inspector-save-room" class="btn btn-primary" style="padding: 5px 12px; font-size: 11px; white-space: nowrap;">
            <i class="fa-solid fa-check"></i> Set Room
          </button>
        </div>
      </div>

      ${hasMatterNodeId ? `
        <div style="margin-top: 10px; display: flex; gap: 8px; align-items: center;">
          <button type="button" id="btn-inspector-purge" class="btn btn-outline" style="font-size: 11px; padding: 4px 12px; border-color: #ef444488; color: #f87171;">
            <i class="fa-solid fa-trash-can"></i> Purge Node #${n.node_id} from Network
          </button>
        </div>
      ` : ''}
    </div>
  `;

  const btnInspSaveRoom = document.getElementById("btn-inspector-save-room");
  const selInspRoom = document.getElementById("inspector-room-select");
  if (btnInspSaveRoom && selInspRoom) {
    btnInspSaveRoom.addEventListener("click", () => {
      const chosenRoom = selInspRoom.value;
      setStoredRoomAssignment(n.id || n.ext_address || n.label, chosenRoom);
      const badge = document.getElementById("inspector-room-badge");
      if (badge) {
        badge.innerText = "Custom Override";
        badge.style.background = "#0284c7";
      }
      btnInspSaveRoom.innerHTML = `<i class="fa-solid fa-check-double"></i> Saved!`;
      setTimeout(() => {
        btnInspSaveRoom.innerHTML = `<i class="fa-solid fa-check"></i> Set Room`;
      }, 1500);

      if (topologyPhysicsState.layoutMode === "house3d" && lastTopologyData) {
        renderHouse3DTopology(lastTopologyData.nodes, lastTopologyData.edges);
        focus3DDevice(n.id || n.label);
      }
    });
  }

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

  const isZigbee = currentNetworkProtocol === "zigbee";
  const icon = document.createElementNS("http://www.w3.org/2000/svg", "text");
  icon.setAttribute("x", cx);
  icon.setAttribute("y", cy - 15);
  icon.setAttribute("fill", isZigbee ? "#facc15" : "#64748b");
  icon.setAttribute("font-size", "36");
  icon.setAttribute("text-anchor", "middle");
  icon.textContent = isZigbee ? "🐝" : "📡";
  textGroup.appendChild(icon);

  const title = document.createElementNS("http://www.w3.org/2000/svg", "text");
  title.setAttribute("x", cx);
  title.setAttribute("y", cy + 22);
  title.setAttribute("fill", "#e2e8f0");
  title.setAttribute("font-size", "15");
  title.setAttribute("font-weight", "600");
  title.setAttribute("text-anchor", "middle");
  title.textContent = isZigbee ? "No Zigbee Coordinator or Devices Discovered Yet" : "No Live Thread Border Routers or Matter Devices Discovered Yet";
  textGroup.appendChild(title);

  const subtitle = document.createElementNS("http://www.w3.org/2000/svg", "text");
  subtitle.setAttribute("x", cx);
  subtitle.setAttribute("y", cy + 46);
  subtitle.setAttribute("fill", "#94a3b8");
  subtitle.setAttribute("font-size", "12");
  subtitle.setAttribute("text-anchor", "middle");
  subtitle.textContent = isZigbee ? "Click '2. Scan Zigbee Network' above to probe your ZHA or Zigbee2MQTT coordinator." : "Click '2. Scan Selected Network' above to probe mDNS (_meshcop._udp), OTBR, and Matter Server.";
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
  viewportG.setAttribute("id", "topology-viewport-g");
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
    const isZigbee = currentNetworkProtocol === "zigbee" || (n.routing_role && n.routing_role.toLowerCase().includes("zigbee")) || String(n.id).startsWith("zb_");
    const badgeText = document.createElementNS("http://www.w3.org/2000/svg", "text");
    badgeText.setAttribute("y", "4");
    badgeText.setAttribute("fill", "#ffffff");
    badgeText.setAttribute("font-size", n.type === "border_router" ? "11" : "10");
    badgeText.setAttribute("font-weight", "700");
    badgeText.setAttribute("text-anchor", "middle");
    badgeText.style.pointerEvents = "none";
    badgeText.textContent = n.type === "border_router"
      ? (isZigbee ? (n.preferred ? "★ COORD" : "COORD") : (n.preferred ? "★ TBR" : "TBR"))
      : (n.type === "router" ? "RTR" : (isZigbee ? "DEV" : "SED"));
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

    // Sub-label showing NWK/RLOC16 or signal LQI / RSSI
    const subParts = [];
    if (isZigbee) {
      if (n.rloc16) subParts.push(n.rloc16);
      if (n.lqi !== null && n.lqi !== undefined) subParts.push(`LQI ${n.lqi}`);
      else if (n.rssi !== null && n.rssi !== undefined) subParts.push(`${n.rssi} dBm`);
    } else {
      if (n.rloc16) subParts.push(n.rloc16);
      if (n.rssi !== null && n.rssi !== undefined) subParts.push(`${n.rssi} dBm`);
      else if (n.rtt_ms !== null && n.rtt_ms !== undefined) subParts.push(`${n.rtt_ms} ms`);
    }
    if (subParts.length > 0) {
      const subText = document.createElementNS("http://www.w3.org/2000/svg", "text");
      subText.setAttribute("y", n.radius + 28);
      subText.setAttribute("fill", isZigbee ? "#facc15" : "#38bdf8");
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
    if (currentNetworkProtocol === "zigbee" || (n.routing_role && n.routing_role.toLowerCase().includes("zigbee"))) return "#eab308";
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
  if (currentNetworkProtocol === "zigbee") {
    legend.innerHTML = `
      <span><span class="dot" style="background: #eab308;"></span> Zigbee Coordinator</span>
      <span><span class="dot" style="background: #10b981;"></span> Zigbee Router (Mains Plug/Switch)</span>
      <span><span class="dot" style="background: #8b5cf6;"></span> Zigbee End Device (Battery Sensor)</span>
      <span><span class="dot" style="background: #f59e0b;"></span> Weak LQI (&lt; 65)</span>
      <span><span class="dot" style="background: #ef4444;"></span> Offline</span>
    `;
    return;
  }

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
  viewportG.setAttribute("id", "topology-viewport-g");
  svg.appendChild(viewportG);

  // Background metro coordinate grid extending well beyond visible bounds
  const gridG = document.createElementNS("http://www.w3.org/2000/svg", "g");
  gridG.setAttribute("opacity", "0.10");
  for (let x = -1000; x < width + 1500; x += 60) {
    const l = document.createElementNS("http://www.w3.org/2000/svg", "line");
    l.setAttribute("x1", x); l.setAttribute("y1", -1000);
    l.setAttribute("x2", x); l.setAttribute("y2", height + 1500);
    l.setAttribute("stroke", "#475569"); l.setAttribute("stroke-width", "1");
    gridG.appendChild(l);
  }
  for (let y = -1000; y < height + 1500; y += 60) {
    const l = document.createElementNS("http://www.w3.org/2000/svg", "line");
    l.setAttribute("x1", -1000); l.setAttribute("y1", y);
    l.setAttribute("x2", width + 1500); l.setAttribute("y2", y);
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
    const y = ((idx + 1) / (tbrCount + 1)) * (height - 100) + 50;
    posMap[tbr.id] = { x: 140, y };
  });

  const rtrCount = Math.max(routers.length, 1);
  routers.forEach((rtr, idx) => {
    const col = idx % 2;
    const row = Math.floor(idx / 2);
    const rows = Math.ceil(rtrCount / 2);
    const x = 360 + col * 180;
    const y = ((row + 1) / (rows + 1)) * (height - 100) + 50;
    posMap[rtr.id] = { x, y };
  });

  const sedCount = Math.max(seds.length, 1);
  seds.forEach((sed, idx) => {
    const col = idx % 2;
    const row = Math.floor(idx / 2);
    const rows = Math.ceil(sedCount / 2);
    const x = Math.min(width - 150, 720) + col * 110;
    const y = ((row + 1) / (rows + 1)) * (height - 100) + 50;
    posMap[sed.id] = { x, y };
  });

  nodes.forEach((n, idx) => {
    if (!posMap[n.id]) {
      posMap[n.id] = { x: 220 + (idx * 50) % (width - 300), y: 90 + (idx * 40) % (height - 140) };
    }
  });

  // Track Line Elements & Redraw Logic
  const lineEntries = [];
  const isZigbee = currentNetworkProtocol === "zigbee";
  edges.forEach((e) => {
    const sId = typeof e.source === "object" ? e.source.id : e.source;
    const tId = typeof e.target === "object" ? e.target.id : e.target;
    if (!posMap[sId] || !posMap[tId]) return;

    const aff = affinity.nodeAffinity[sId] || affinity.nodeAffinity[tId] || { color: isZigbee ? "#eab308" : "#38bdf8" };
    const lineColor = isZigbee ? "#ca8a04" : (aff.color || "#0284c7");

    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("fill", "none");
    path.setAttribute("stroke", lineColor);
    path.setAttribute("stroke-width", "5");
    path.setAttribute("stroke-linecap", "round");
    path.setAttribute("stroke-linejoin", "round");
    path.setAttribute("stroke-opacity", "0.85");
    linesG.appendChild(path);

    lineEntries.push({ path, sId, tId });
  });

  const getMetroPathD = (p1, p2) => {
    const dx = p2.x - p1.x;
    const dy = p2.y - p1.y;
    if (Math.abs(dx) > Math.abs(dy)) {
      const midX = p1.x + (dx - dy);
      return `M ${p1.x.toFixed(1)} ${p1.y.toFixed(1)} L ${midX.toFixed(1)} ${p1.y.toFixed(1)} L ${p2.x.toFixed(1)} ${p2.y.toFixed(1)}`;
    } else {
      const midY = p1.y + (dy - dx);
      return `M ${p1.x.toFixed(1)} ${p1.y.toFixed(1)} L ${p1.x.toFixed(1)} ${midY.toFixed(1)} L ${p2.x.toFixed(1)} ${p2.y.toFixed(1)}`;
    }
  };

  const redrawMetroLines = () => {
    lineEntries.forEach(entry => {
      const p1 = posMap[entry.sId];
      const p2 = posMap[entry.tId];
      if (p1 && p2) {
        entry.path.setAttribute("d", getMetroPathD(p1, p2));
      }
    });
  };

  redrawMetroLines();

  // Draw Stations with Dragging & Pointer Capture
  nodes.forEach((n) => {
    const pos = posMap[n.id];
    const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
    g.setAttribute("class", "metro-station");
    g.style.cursor = "grab";
    g.setAttribute("transform", `translate(${pos.x.toFixed(1)}, ${pos.y.toFixed(1)})`);

    const isTbr = n.type === "border_router";
    const isRouter = n.type === "router";
    const isNodeZigbee = isZigbee || (n.routing_role && n.routing_role.toLowerCase().includes("zigbee")) || String(n.id).startsWith("zb_");

    if (isTbr) {
      const outerRing = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      outerRing.setAttribute("r", "16");
      outerRing.setAttribute("fill", "#0f172a");
      outerRing.setAttribute("stroke", isNodeZigbee ? "#facc15" : "#f8fafc");
      outerRing.setAttribute("stroke-width", "3");
      g.appendChild(outerRing);

      const innerCore = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      innerCore.setAttribute("r", "9");
      innerCore.setAttribute("fill", isNodeZigbee ? "#eab308" : (n.vendor === "nest" ? "#4285F4" : (n.vendor === "apple" ? "#94a3b8" : "#03A9F4")));
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
    lbl.setAttribute("pointer-events", "none");
    lbl.textContent = n.label || (isNodeZigbee ? 'Zigbee Device' : `Node #${n.node_id}`);
    g.appendChild(lbl);

    let isStationDragging = false;
    let stationMoved = false;

    g.addEventListener("pointerdown", (ev) => {
      ev.stopPropagation();
      isStationDragging = true;
      stationMoved = false;
      g.style.cursor = "grabbing";
      try {
        g.setPointerCapture(ev.pointerId);
      } catch (_) {}
    });

    g.addEventListener("pointermove", (ev) => {
      if (!isStationDragging) return;
      stationMoved = true;
      const svgRect = svg.getBoundingClientRect();
      const mouseX = (ev.clientX - svgRect.left - topologyPhysicsState.panX) / topologyPhysicsState.zoom;
      const mouseY = (ev.clientY - svgRect.top - topologyPhysicsState.panY) / topologyPhysicsState.zoom;
      pos.x = mouseX;
      pos.y = mouseY;
      g.setAttribute("transform", `translate(${mouseX.toFixed(1)}, ${mouseY.toFixed(1)})`);
      redrawMetroLines();
    });

    const endStationDrag = (ev) => {
      if (!isStationDragging) return;
      isStationDragging = false;
      g.style.cursor = "grab";
      try {
        g.releasePointerCapture(ev.pointerId);
      } catch (_) {}
      if (!stationMoved) {
        showNodeInspector(n);
      }
    };

    g.addEventListener("pointerup", endStationDrag);
    g.addEventListener("pointercancel", endStationDrag);

    stationsG.appendChild(g);
    n.elem = g;
  });

  // Viewport Pan & Zoom Handling
  const updateViewportTransform = () => {
    viewportG.setAttribute(
      "transform",
      `translate(${topologyPhysicsState.panX.toFixed(1)}, ${topologyPhysicsState.panY.toFixed(1)}) scale(${topologyPhysicsState.zoom.toFixed(3)})`
    );
  };
  updateViewportTransform();

  let isCanvasPanning = false;
  let panStartX = 0;
  let panStartY = 0;
  svg.style.cursor = "grab";

  svg.onpointerdown = (ev) => {
    if (ev.target && ev.target.closest && ev.target.closest(".metro-station")) return;
    isCanvasPanning = true;
    panStartX = ev.clientX - topologyPhysicsState.panX;
    panStartY = ev.clientY - topologyPhysicsState.panY;
    svg.style.cursor = "grabbing";
  };

  const onWindowPointerMove = (ev) => {
    if (!isCanvasPanning) return;
    topologyPhysicsState.panX = ev.clientX - panStartX;
    topologyPhysicsState.panY = ev.clientY - panStartY;
    updateViewportTransform();
  };

  const onWindowPointerUp = () => {
    if (isCanvasPanning) {
      isCanvasPanning = false;
      svg.style.cursor = "grab";
    }
  };

  window.addEventListener("pointermove", onWindowPointerMove);
  window.addEventListener("pointerup", onWindowPointerUp);

  svg.onwheel = (ev) => {
    ev.preventDefault();
    const scaleFactor = ev.deltaY < 0 ? 1.1 : 0.9;
    const newZoom = Math.max(0.35, Math.min(3.0, topologyPhysicsState.zoom * scaleFactor));
    const svgRect = svg.getBoundingClientRect();
    const mx = ev.clientX - svgRect.left;
    const my = ev.clientY - svgRect.top;
    topologyPhysicsState.panX = mx - ((mx - topologyPhysicsState.panX) * newZoom) / topologyPhysicsState.zoom;
    topologyPhysicsState.panY = my - ((my - topologyPhysicsState.panY) * newZoom) / topologyPhysicsState.zoom;
    topologyPhysicsState.zoom = newZoom;
    updateViewportTransform();
  };

  const headerG = document.createElementNS("http://www.w3.org/2000/svg", "g");
  headerG.setAttribute("transform", "translate(20, 30)");
  headerG.innerHTML = `
    <rect width="260" height="26" rx="6" fill="#0f172acc" stroke="#334155" />
    <text x="12" y="17" fill="#38bdf8" font-size="11" font-weight="700">🚇 ${currentNetworkProtocol === 'zigbee' ? 'ZIGBEE' : 'THREAD'} METRO (DRAGGABLE &amp; ZOOMABLE)</text>
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

  const isZigbee = currentNetworkProtocol === "zigbee";
  if (!nodes || nodes.length === 0) {
    container.innerHTML = `<div style="padding: 40px; text-align: center; color: #64748b;"><i class="fa-solid fa-satellite-dish" style="font-size: 32px; margin-bottom: 8px;"></i><p>${isZigbee ? "No Zigbee nodes discovered yet. Click '2. Scan Zigbee Network' above." : "No Thread nodes discovered yet. Click '2. Scan Selected Network' above."}</p></div>`;
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
        <div style="font-size: 11px; color: #94a3b8; text-transform: uppercase;">Direct ${isZigbee ? 'Zigbee' : 'RF'} Links</div>
        <div style="font-size: 18px; font-weight: 700; color: ${isZigbee ? '#facc15' : '#38bdf8'}; margin-top: 2px;">${directLinkCount}</div>
      </div>
      <div style="background: #0f172a; padding: 10px 14px; border-radius: 6px; border: 1px solid #334155;">
        <div style="font-size: 11px; color: #94a3b8; text-transform: uppercase;">Mesh Density</div>
        <div style="font-size: 18px; font-weight: 700; color: #10b981; margin-top: 2px;">${densityPct}%</div>
      </div>
      <div style="background: #0f172a; padding: 10px 14px; border-radius: 6px; border: 1px solid #334155;">
        <div style="font-size: 11px; color: #94a3b8; text-transform: uppercase;">${isZigbee ? 'Avg Link Quality' : 'Avg Link Signal'}</div>
        <div style="font-size: 18px; font-weight: 700; color: ${isZigbee ? '#facc15' : (avgRssi && Number(avgRssi) > -70 ? '#34d399' : '#f59e0b')}; margin-top: 2px;">
          ${isZigbee && currentZigbeeTelemetry?.avg_lqi ? `${currentZigbeeTelemetry.avg_lqi} / 255` : (avgRssi ? `${avgRssi} dBm` : 'N/A')}
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
    const roleIcon = isZigbee
      ? (rowNode.type === "border_router" ? "🐝" : (rowNode.type === "router" ? "🔁" : "🔋"))
      : (rowNode.type === "border_router" ? "📡" : (rowNode.type === "router" ? "🔁" : "🔋"));
    html += `
      <tr>
        <td class="sticky-col" style="cursor: pointer;" title="Click to inspect device" onclick="showNodeInspector(lastTopologyData.nodes.find(x => x.id === '${rowNode.id}'))">
          <span style="margin-right: 6px;">${roleIcon}</span>
          <strong>${escapeHtml(rowNode.label || (isZigbee ? 'Zigbee Device' : `Node ${rowNode.node_id}`))}</strong>
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

        if (isZigbee && link.lqi !== null && link.lqi !== undefined) {
          const lqi = Number(link.lqi);
          badge = `LQI ${lqi}`;
          if (lqi >= 140) { bg = "#064e3b"; textCol = "#6ee7b7"; }
          else if (lqi >= 80) { bg = "#14532d"; textCol = "#a3e635"; }
          else if (lqi >= 50) { bg = "#713f12"; textCol = "#fde047"; }
          else { bg = "#7f1d1d"; textCol = "#fca5a5"; }
        } else if (rssi !== null) {
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
   VISUAL PERSPECTIVE 3: Sankey / Alluvial Routing Flow (Zoomable & Draggable)
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

  const viewportG = document.createElementNS("http://www.w3.org/2000/svg", "g");
  viewportG.setAttribute("id", "topology-viewport-g");
  svg.appendChild(viewportG);

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

  // Column Headers inside viewport
  const isZigbee = currentNetworkProtocol === "zigbee";
  const cols = [
    { label: isZigbee ? "1. COORDINATOR (ROOT GATEWAY)" : "1. BORDER ROUTERS (GATEWAYS)", x: colX.tbr + 75 },
    { label: isZigbee ? "2. ZIGBEE ROUTERS (MAINS BACKBONE)" : "2. ROUTERS (MESH BACKBONE)", x: colX.router + 75 },
    { label: isZigbee ? "3. SLEEPY SENSORS (BATTERY END DEVICES)" : "3. SLEEPY SENSORS (END DEVICES)", x: colX.sed + 75 },
  ];
  cols.forEach(c => {
    const t = document.createElementNS("http://www.w3.org/2000/svg", "text");
    t.setAttribute("x", c.x);
    t.setAttribute("y", "26");
    t.setAttribute("fill", isZigbee ? "#fbbf24" : "#38bdf8");
    t.setAttribute("font-size", "11");
    t.setAttribute("font-weight", "700");
    t.setAttribute("text-anchor", "middle");
    t.textContent = c.label;
    viewportG.appendChild(t);
  });

  const ribbonsG = document.createElementNS("http://www.w3.org/2000/svg", "g");
  const nodesG = document.createElementNS("http://www.w3.org/2000/svg", "g");
  viewportG.appendChild(ribbonsG);
  viewportG.appendChild(nodesG);

  // Flow Ribbon Elements & Redraw Logic
  const ribbonEntries = [];
  edges.forEach((e) => {
    const sId = typeof e.source === "object" ? e.source.id : e.source;
    const tId = typeof e.target === "object" ? e.target.id : e.target;
    if (!nodePos[sId] || !nodePos[tId]) return;

    const aff = affinity.nodeAffinity[sId] || affinity.nodeAffinity[tId] || { color: "#38bdf8" };
    const strokeColor = aff.color || "#0284c7";

    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
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
    ribbonEntries.push({ path, sId, tId });
  });

  const getRibbonD = (p1Raw, p2Raw) => {
    let p1 = p1Raw;
    let p2 = p2Raw;
    if (p1.x > p2.x) { const tmp = p1; p1 = p2; p2 = tmp; }
    const x1 = p1.x + 155;
    const y1 = p1.y + 17;
    const x2 = p2.x;
    const y2 = p2.y + 17;
    const cX = x1 + (x2 - x1) * 0.5;
    return `M ${x1.toFixed(1)} ${y1.toFixed(1)} C ${cX.toFixed(1)} ${y1.toFixed(1)}, ${cX.toFixed(1)} ${y2.toFixed(1)}, ${x2.toFixed(1)} ${y2.toFixed(1)}`;
  };

  const redrawRibbons = () => {
    ribbonEntries.forEach(entry => {
      const p1 = nodePos[entry.sId];
      const p2 = nodePos[entry.tId];
      if (p1 && p2) {
        entry.path.setAttribute("d", getRibbonD(p1, p2));
      }
    });
  };

  redrawRibbons();

  // Node Pill Cards with Dragging
  nodes.forEach((n) => {
    const pos = nodePos[n.id];
    const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
    g.setAttribute("class", "sankey-node-card");
    g.style.cursor = "grab";
    g.setAttribute("transform", `translate(${pos.x.toFixed(1)}, ${pos.y.toFixed(1)})`);

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
    iconText.setAttribute("pointer-events", "none");
    iconText.textContent = isTbr ? "📡" : (isRouter ? "🔁" : "🔋");
    g.appendChild(iconText);

    const nameText = document.createElementNS("http://www.w3.org/2000/svg", "text");
    nameText.setAttribute("x", "30");
    nameText.setAttribute("y", "21");
    nameText.setAttribute("fill", "#f8fafc");
    nameText.setAttribute("font-size", "11");
    nameText.setAttribute("font-weight", "600");
    nameText.setAttribute("pointer-events", "none");
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
      rssiBadge.setAttribute("pointer-events", "none");
      rssiBadge.textContent = `${n.rssi}`;
      g.appendChild(rssiBadge);
    }

    let isCardDragging = false;
    let cardMoved = false;

    g.addEventListener("pointerdown", (ev) => {
      ev.stopPropagation();
      isCardDragging = true;
      cardMoved = false;
      g.style.cursor = "grabbing";
      try {
        g.setPointerCapture(ev.pointerId);
      } catch (_) {}
    });

    g.addEventListener("pointermove", (ev) => {
      if (!isCardDragging) return;
      cardMoved = true;
      const svgRect = svg.getBoundingClientRect();
      const mouseX = (ev.clientX - svgRect.left - topologyPhysicsState.panX) / topologyPhysicsState.zoom;
      const mouseY = (ev.clientY - svgRect.top - topologyPhysicsState.panY) / topologyPhysicsState.zoom;
      pos.x = mouseX;
      pos.y = mouseY;
      g.setAttribute("transform", `translate(${mouseX.toFixed(1)}, ${mouseY.toFixed(1)})`);
      redrawRibbons();
    });

    const endCardDrag = (ev) => {
      if (!isCardDragging) return;
      isCardDragging = false;
      g.style.cursor = "grab";
      try {
        g.releasePointerCapture(ev.pointerId);
      } catch (_) {}
      if (!cardMoved) {
        showNodeInspector(n);
      }
    };

    g.addEventListener("pointerup", endCardDrag);
    g.addEventListener("pointercancel", endCardDrag);

    nodesG.appendChild(g);
    n.elem = g;
  });

  // Viewport Pan & Zoom Handling
  const updateViewportTransform = () => {
    viewportG.setAttribute(
      "transform",
      `translate(${topologyPhysicsState.panX.toFixed(1)}, ${topologyPhysicsState.panY.toFixed(1)}) scale(${topologyPhysicsState.zoom.toFixed(3)})`
    );
  };
  updateViewportTransform();

  let isCanvasPanning = false;
  let panStartX = 0;
  let panStartY = 0;
  svg.style.cursor = "grab";

  svg.onpointerdown = (ev) => {
    if (ev.target && ev.target.closest && ev.target.closest(".sankey-node-card")) return;
    isCanvasPanning = true;
    panStartX = ev.clientX - topologyPhysicsState.panX;
    panStartY = ev.clientY - topologyPhysicsState.panY;
    svg.style.cursor = "grabbing";
  };

  const onWindowPointerMove = (ev) => {
    if (!isCanvasPanning) return;
    topologyPhysicsState.panX = ev.clientX - panStartX;
    topologyPhysicsState.panY = ev.clientY - panStartY;
    updateViewportTransform();
  };

  const onWindowPointerUp = () => {
    if (isCanvasPanning) {
      isCanvasPanning = false;
      svg.style.cursor = "grab";
    }
  };

  window.addEventListener("pointermove", onWindowPointerMove);
  window.addEventListener("pointerup", onWindowPointerUp);

  svg.onwheel = (ev) => {
    ev.preventDefault();
    const scaleFactor = ev.deltaY < 0 ? 1.1 : 0.9;
    const newZoom = Math.max(0.35, Math.min(3.0, topologyPhysicsState.zoom * scaleFactor));
    const svgRect = svg.getBoundingClientRect();
    const mx = ev.clientX - svgRect.left;
    const my = ev.clientY - svgRect.top;
    topologyPhysicsState.panX = mx - ((mx - topologyPhysicsState.panX) * newZoom) / topologyPhysicsState.zoom;
    topologyPhysicsState.panY = my - ((my - topologyPhysicsState.panY) * newZoom) / topologyPhysicsState.zoom;
    topologyPhysicsState.zoom = newZoom;
    updateViewportTransform();
  };

  updateTopologyLegend();
}

/* ==========================================================================
   VISUAL PERSPECTIVE 4: Interactive 3D Digital Twin House Model
   Taylor Wimpey 'The Blair 4 TK' Left-Hand Semi-Detached House
   ========================================================================== */

const BLAIR_ROOMS = {
  living_room: {
    id: "living_room",
    name: "Living Room / Lounge",
    floor: "ground",
    coords: { x: 1.88, y: 1.25, z: -2.35 },
    aliases: ["living room", "lounge", "sitting room", "living_room", "living", "tv lamp", "tv", "living room light", "living room tv plug", "living room lamp"]
  },
  kitchen: {
    id: "kitchen",
    name: "Kitchen & Dining Room",
    floor: "ground",
    coords: { x: 2.80, y: 1.25, z: -7.40 },
    aliases: ["kitchen", "dining", "cooker", "fridge", "boiler", "dishwasher", "kitchen light", "french doors", "combi boiler"]
  },
  entrance_hall: {
    id: "entrance_hall",
    name: "Entrance Hall",
    floor: "ground",
    coords: { x: 4.40, y: 1.25, z: -1.60 },
    aliases: ["entrance", "front door", "entry", "vestibule", "porch", "front hall", "hallway", "front"]
  },
  meter_cupboard: {
    id: "meter_cupboard",
    name: "Entrance Meter Cupboard (Fusebox & OTBR)",
    floor: "ground",
    coords: { x: 4.50, y: 1.40, z: -3.20 },
    aliases: ["meter", "cupboard", "fusebox", "consumer unit", "electric meter", "ha otbr", "zbt-1", "connect zbt-1", "borderrouter #be73", "otbr", "openthread", "coordinator"]
  },
  downstairs_wc: {
    id: "downstairs_wc",
    name: "Downstairs WC",
    floor: "ground",
    coords: { x: 0.92, y: 1.25, z: -5.30 },
    aliases: ["downstairs wc", "toilet", "cloakroom", "powder room", "wc", "ground floor wc"]
  },
  downstairs_hallway: {
    id: "downstairs_hallway",
    name: "Downstairs Hallway / Lobby",
    floor: "ground",
    coords: { x: 2.50, y: 1.25, z: -5.30 },
    aliases: ["downstairs hallway", "downstairs hall", "lobby", "ground hallway", "stair lobby", "tado x downstairs"]
  },
  driveway: {
    id: "driveway",
    name: "Driveway & EV Wallbox (Peugeot e-2008)",
    floor: "ground",
    coords: { x: 4.30, y: 0.90, z: 3.20 },
    aliases: ["driveway", "drive", "car", "ev", "peugeot", "charger", "wallbox", "outside", "garden", "front garden"]
  },
  master_bedroom: {
    id: "master_bedroom",
    name: "Master Bedroom (Largest)",
    floor: "first",
    coords: { x: 1.95, y: 3.75, z: -2.10 },
    aliases: ["master bedroom", "bedroom 1", "bed 1", "master", "main bedroom", "bedroom light", "bedroom"]
  },
  master_ensuite: {
    id: "master_ensuite",
    name: "Master En-Suite",
    floor: "first",
    coords: { x: 4.50, y: 3.75, z: -1.22 },
    aliases: ["en-suite", "ensuite", "master bath", "shower", "en suite", "en-suite light", "ensuite light"]
  },
  guest_room: {
    id: "guest_room",
    name: "Guest Room (Bed 2 - Second Smallest)",
    floor: "first",
    coords: { x: 1.75, y: 3.75, z: -7.28 },
    aliases: ["guest room", "guest", "bedroom 2", "bed 2", "spare room", "office", "study", "guest room light", "guestroom"]
  },
  nursery: {
    id: "nursery",
    name: "Nursery (Bed 3 - Smallest)",
    floor: "first",
    coords: { x: 4.27, y: 3.75, z: -7.28 },
    aliases: ["nursery", "bed 3", "bedroom 3", "kids room", "child", "small bedroom", "box room"]
  },
  family_bathroom: {
    id: "family_bathroom",
    name: "Family Bathroom",
    floor: "first",
    coords: { x: 1.22, y: 3.75, z: -4.95 },
    aliases: ["family bathroom", "bathroom", "bath", "upstairs bathroom", "main bath", "bathroom light"]
  },
  upstairs_hallway: {
    id: "upstairs_hallway",
    name: "Upstairs Landing / Hallway",
    floor: "first",
    coords: { x: 3.30, y: 3.75, z: -4.07 },
    aliases: ["upstairs hallway", "upstairs hall", "landing", "first floor hall", "upstairs", "tado x upstairs"]
  },
  roof_solar: {
    id: "roof_solar",
    name: "Roof / Solar Array",
    floor: "roof",
    coords: { x: 2.80, y: 6.20, z: -6.50 },
    aliases: ["roof", "solar", "inverter", "attic", "loft"]
  }
};

const BLAIR_CAMERA_PRESETS = {
  overview: { pos: [11.5, 10.5, 8.5], target: [2.81, 2.5, -4.44] },
  rear_solar: { pos: [2.81, 9.0, -17.0], target: [2.81, 3.8, -5.5] },
  living_room: { pos: [1.88, 3.2, 2.5], target: [1.88, 1.25, -2.35] },
  kitchen: { pos: [2.80, 3.8, -13.0], target: [2.80, 1.25, -7.40] },
  entrance_hall: { pos: [7.2, 2.8, -1.6], target: [4.45, 1.35, -2.4] },
  master_bedroom: { pos: [1.95, 5.5, 2.5], target: [1.95, 3.75, -2.10] },
  guest_room: { pos: [1.75, 5.5, -12.5], target: [1.75, 3.75, -7.28] },
  nursery: { pos: [4.27, 5.5, -12.5], target: [4.27, 3.75, -7.28] },
  family_bathroom: { pos: [-3.5, 5.2, -4.95], target: [1.22, 3.75, -4.95] },
  driveway: { pos: [4.30, 3.2, 8.5], target: [4.30, 0.90, 3.20] },
  garden: { pos: [-12.0, 9.0, 14.0], target: [0.0, 2.0, -4.5] },
  gas_tank: { pos: [-6.5, 3.2, -6.0], target: [-1.3, 1.2, -7.5] },
  utility_pylon: { pos: [11.0, 5.5, 12.0], target: [6.4, 3.5, 7.2] }
};

const house3DState = {
  isInitialized: false,
  isLoading: false,
  scene: null,
  camera: null,
  renderer: null,
  controls: null,
  modelRoot: null,
  meshesByCategory: {
    exterior_walls_party: [],
    roof_ceiling: [],
    interior_walls: [],
    core_structure: [],
    fixtures: [],
    driveway_car: []
  },
  originalMaterials: new Map(),
  nodeObjects: new Map(),
  edgeObjects: [],
  pulseObjects: [],
  linkDataList: [],
  isDraggingNode: false,
  draggedGroup: null,
  dragPlane: null,
  dragOffset: null,
  dragIntersect: null,
  floorCutawayMode: "all",
  xrayPercent: 0,
  wallOpacity: 1.0,
  raycaster: null,
  mouse: null,
  hoveredNode: null,
  selectedNode: null,
  cameraAnimation: null,
  animFrameId: null,
  resizeObserver: null
};

function getStoredCustom3DPositions() {
  try {
    const raw = localStorage.getItem("ha_matter_custom_3d_positions");
    return raw ? JSON.parse(raw) : {};
  } catch (_) {
    return {};
  }
}

function setStoredCustom3DPosition(devKey, pos) {
  try {
    const positions = getStoredCustom3DPositions();
    positions[String(devKey)] = {
      x: Number(pos.x.toFixed(3)),
      y: Number(pos.y.toFixed(3)),
      z: Number(pos.z.toFixed(3))
    };
    localStorage.setItem("ha_matter_custom_3d_positions", JSON.stringify(positions));
  } catch (err) {
    console.warn("Failed to persist custom 3D position:", err);
  }
}

function resetStoredCustom3DPositions() {
  try {
    localStorage.removeItem("ha_matter_custom_3d_positions");
  } catch (_) {}
}

function getStoredRoomAssignments() {
  try {
    const raw = localStorage.getItem("ha_matter_room_assignments");
    return raw ? JSON.parse(raw) : {};
  } catch (_) {
    return {};
  }
}

function setStoredRoomAssignment(devKey, roomId) {
  try {
    const assignments = getStoredRoomAssignments();
    assignments[String(devKey)] = roomId;
    localStorage.setItem("ha_matter_room_assignments", JSON.stringify(assignments));
  } catch (err) {
    console.warn("Failed to persist room assignment:", err);
  }
}

function autoDetectDeviceRoom(node) {
  if (!node) return "living_room";
  const nameStr = (node.label || "").toLowerCase();
  const areaStr = (node.ha_area || "").toLowerCase();
  const typeStr = (node.type || node.routing_role || "").toLowerCase();

  // 1. Direct check against HA Area if available
  if (areaStr) {
    for (const [rId, room] of Object.entries(BLAIR_ROOMS)) {
      if (areaStr.includes(rId) || areaStr.includes(room.name.toLowerCase())) {
        return rId;
      }
      for (const alias of room.aliases) {
        if (areaStr.includes(alias)) return rId;
      }
    }
  }

  // 2. Check node label against aliases
  for (const [rId, room] of Object.entries(BLAIR_ROOMS)) {
    for (const alias of room.aliases) {
      if (nameStr.includes(alias)) {
        return rId;
      }
    }
  }

  // 3. Role/type heuristics
  if (typeStr.includes("coordinator") || typeStr.includes("otbr") || nameStr.includes("be73") || nameStr.includes("connect zbt")) {
    return "meter_cupboard";
  }
  if (nameStr.includes("nest wifi")) {
    if (nameStr.includes("9166")) return "living_room";
    if (nameStr.includes("9074")) return "kitchen";
    if (nameStr.includes("guest")) return "guest_room";
    return "entrance_hall";
  }
  if (nameStr.includes("tado")) {
    return nameStr.includes("upstairs") ? "upstairs_hallway" : "downstairs_hallway";
  }

  return "living_room";
}

function resolveDeviceRoom(node) {
  if (!node) return { roomId: "living_room", isCustom: false };
  const assignments = getStoredRoomAssignments();
  const candidates = [
    node.id !== undefined && node.id !== null ? String(node.id) : "",
    node.ext_address || "",
    node.label || ""
  ].filter(Boolean);

  for (const k of candidates) {
    if (assignments[k] && BLAIR_ROOMS[assignments[k]]) {
      return { roomId: assignments[k], isCustom: true };
    }
  }

  const detected = autoDetectDeviceRoom(node);
  return { roomId: detected, isCustom: false };
}

function generateRoomOptionsHtml(selectedId) {
  let html = `<optgroup label="Ground Floor">`;
  for (const [rId, room] of Object.entries(BLAIR_ROOMS)) {
    if (room.floor === "ground") {
      const isSel = rId === selectedId ? "selected" : "";
      html += `<option value="${rId}" ${isSel}>${escapeHtml(room.name)}</option>`;
    }
  }
  html += `</optgroup><optgroup label="First Floor">`;
  for (const [rId, room] of Object.entries(BLAIR_ROOMS)) {
    if (room.floor === "first") {
      const isSel = rId === selectedId ? "selected" : "";
      html += `<option value="${rId}" ${isSel}>${escapeHtml(room.name)}</option>`;
    }
  }
  html += `</optgroup><optgroup label="Roof &amp; External">`;
  for (const [rId, room] of Object.entries(BLAIR_ROOMS)) {
    if (room.floor === "roof") {
      const isSel = rId === selectedId ? "selected" : "";
      html += `<option value="${rId}" ${isSel}>${escapeHtml(room.name)}</option>`;
    }
  }
  html += `</optgroup>`;
  return html;
}

function classifyMeshCategory(meshName) {
  const nm = (meshName || "").toLowerCase();
  if (
    nm.includes("exterior_walls") ||
    nm.includes("separating_party_wall") ||
    nm.includes("windows_") ||
    nm.includes("entrance_door") ||
    nm.includes("exterior_hardware") ||
    nm.includes("french_doors")
  ) {
    return "exterior_walls_party";
  }
  if (
    nm.includes("roof_") ||
    nm.includes("fascia_") ||
    nm.includes("rainwater_") ||
    nm.includes("first_floor_ceiling") ||
    nm.includes("solar_pv_")
  ) {
    return "roof_ceiling";
  }
  if (
    nm.includes("interior_walls") ||
    nm.includes("interior_doors")
  ) {
    return "interior_walls";
  }
  if (
    nm.includes("ground_floor_") ||
    nm.includes("first_floor_structure") ||
    nm.includes("landing_carpet") ||
    nm.includes("carpet_") ||
    nm.includes("first_floor_tiles") ||
    nm.includes("staircase") ||
    nm.includes("room_labels")
  ) {
    return "core_structure";
  }
  if (
    nm.includes("kitchen_") ||
    nm.includes("entrance_meter") ||
    nm.includes("sanitaryware")
  ) {
    return "fixtures";
  }
  if (
    nm.includes("driveway") ||
    nm.includes("car_peugeot") ||
    nm.includes("ev_charger") ||
    nm.includes("ev_charging") ||
    nm.includes("landscape_") ||
    nm.includes("utility_") ||
    nm.includes("gas_")
  ) {
    return "driveway_car";
  }
  return "core_structure";
}

function setMeshTransparency(mesh, opacity, isVisible) {
  if (!mesh) return;
  mesh.visible = isVisible && opacity > 0.001;
  if (!mesh.visible) return;

  const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
  mats.forEach((mat) => {
    if (!mat) return;
    if (opacity >= 0.999) {
      mat.transparent = false;
      mat.opacity = 1.0;
      mat.depthWrite = true;
    } else {
      mat.transparent = true;
      mat.opacity = opacity;
      mat.depthWrite = false;
    }
  });
}

function apply3DCutawayAndTransparency() {
  const mode = house3DState.floorCutawayMode;
  const pct = Math.max(0, Math.min(100, house3DState.xrayPercent !== undefined ? house3DState.xrayPercent : 0));

  const {
    exterior_walls_party = [],
    roof_ceiling = [],
    interior_walls = [],
    core_structure = [],
    fixtures = [],
    driveway_car = []
  } = house3DState.meshesByCategory;

  if (mode === "solid") {
    [...exterior_walls_party, ...roof_ceiling, ...interior_walls, ...core_structure, ...fixtures, ...driveway_car].forEach(m => {
      setMeshTransparency(m, 1.0, true);
    });
    return;
  }

  if (mode === "ground") {
    roof_ceiling.forEach(m => setMeshTransparency(m, 0.0, false));
    interior_walls.forEach(m => {
      const isGround = (m.name || "").toLowerCase().includes("ground");
      setMeshTransparency(m, 1.0, isGround);
    });
    core_structure.forEach(m => {
      const isFirst = (m.name || "").toLowerCase().includes("first") || (m.name || "").toLowerCase().includes("carpet");
      setMeshTransparency(m, 1.0, !isFirst);
    });
    exterior_walls_party.forEach(m => setMeshTransparency(m, 0.25, true));
    fixtures.forEach(m => setMeshTransparency(m, 1.0, true));
    driveway_car.forEach(m => setMeshTransparency(m, 1.0, true));
    return;
  }

  if (mode === "first") {
    roof_ceiling.forEach(m => setMeshTransparency(m, 0.0, false));
    interior_walls.forEach(m => {
      const isFirst = (m.name || "").toLowerCase().includes("first");
      setMeshTransparency(m, 1.0, isFirst);
    });
    core_structure.forEach(m => setMeshTransparency(m, 1.0, true));
    exterior_walls_party.forEach(m => setMeshTransparency(m, 0.25, true));
    fixtures.forEach(m => setMeshTransparency(m, 1.0, true));
    driveway_car.forEach(m => setMeshTransparency(m, 1.0, true));
    return;
  }

  // mode === "all": Progressive Layer Peeler
  // 0%: House fully rendered
  // 25%: External walls and party wall removed
  // 50%: Roof and upstairs ceiling removed (+ external & party walls removed)
  // 100%: Internal walls removed (+ all previous stuff removed)
  // Every move up is new stuff removed and all previous stuff removed also!

  // 1. Exterior walls & party wall (solid at 0%, fades 0% -> 25%, completely removed at >= 25%)
  let extOpacity = 1.0;
  let extVisible = true;
  if (pct >= 25) {
    extOpacity = 0.0;
    extVisible = false;
  } else if (pct > 0) {
    extOpacity = (25 - pct) / 25;
    extVisible = true;
  }
  exterior_walls_party.forEach(m => setMeshTransparency(m, extOpacity, extVisible));

  // 2. Roof & upstairs ceiling (solid <= 25%, fades 25% -> 50%, completely removed at >= 50%)
  let roofOpacity = 1.0;
  let roofVisible = true;
  if (pct >= 50) {
    roofOpacity = 0.0;
    roofVisible = false;
  } else if (pct > 25) {
    roofOpacity = (50 - pct) / 25;
    roofVisible = true;
  }
  roof_ceiling.forEach(m => setMeshTransparency(m, roofOpacity, roofVisible));

  // 3. Internal walls and doors (solid <= 50%, fades 50% -> 100%, completely removed at >= 100%)
  let intOpacity = 1.0;
  let intVisible = true;
  if (pct >= 100) {
    intOpacity = 0.0;
    intVisible = false;
  } else if (pct > 50) {
    intOpacity = (100 - pct) / 50;
    intVisible = true;
  }
  interior_walls.forEach(m => setMeshTransparency(m, intOpacity, intVisible));

  // 4. Core structure (slabs, floors, carpets, staircase, room labels), fixtures, and driveway/car
  core_structure.forEach(m => setMeshTransparency(m, 1.0, true));
  fixtures.forEach(m => setMeshTransparency(m, 1.0, true));
  driveway_car.forEach(m => setMeshTransparency(m, 1.0, true));
}

function setXRayPercent(pct) {
  const clamped = Math.max(0, Math.min(100, Math.round(pct)));
  house3DState.xrayPercent = clamped;

  const slider = document.getElementById("slider-3d-opacity");
  if (slider && parseInt(slider.value, 10) !== clamped) {
    slider.value = clamped;
  }

  const label = document.getElementById("label-3d-opacity");
  if (label) {
    let tag = `${clamped}%`;
    if (clamped === 0) tag = "0% (Solid)";
    else if (clamped === 25) tag = "25% (No Ext)";
    else if (clamped === 50) tag = "50% (No Roof)";
    else if (clamped === 100) tag = "100% (No Walls)";
    label.innerText = tag;
    label.title = `X-Ray: ${clamped}% (0%=Fully Rendered, 25%=No External Walls, 50%=No Roof/Ceiling, 100%=No Internal Walls)`;
  }

  // Update quick step buttons active state
  document.querySelectorAll(".btn-3d-xray-step").forEach((btn) => {
    const stepVal = parseInt(btn.getAttribute("data-xray"), 10);
    if (stepVal === clamped) {
      btn.classList.add("active");
      btn.style.background = "#0284c7";
      btn.style.color = "#ffffff";
    } else {
      btn.classList.remove("active");
      btn.style.background = "#1e293b";
      btn.style.color = "#94a3b8";
    }
  });

  // If user adjusts X-Ray, ensure Floor mode is "all" unless user clicked solid
  if (house3DState.floorCutawayMode !== "all" && house3DState.floorCutawayMode !== "solid") {
    house3DState.floorCutawayMode = "all";
    document.querySelectorAll(".btn-3d-floor").forEach((b) => {
      if (b.getAttribute("data-floor") === "all") b.classList.add("active");
      else b.classList.remove("active");
    });
  }

  apply3DCutawayAndTransparency();
}

function flyCameraTo(posArray, targetArray, duration = 800) {
  if (!house3DState.camera || !house3DState.controls) return;
  const startPos = house3DState.camera.position.clone();
  const startTarget = house3DState.controls.target.clone();
  const endPos = new THREE.Vector3(...posArray);
  const endTarget = new THREE.Vector3(...targetArray);

  house3DState.cameraAnimation = {
    startPos,
    endPos,
    startTarget,
    endTarget,
    startTime: performance.now(),
    duration
  };
}

function focus3DDevice(devIdOrLabel) {
  if (!devIdOrLabel || !house3DState.nodeObjects) return;
  for (const [id, grp] of house3DState.nodeObjects.entries()) {
    if (String(id) === String(devIdOrLabel) || (grp.userData && grp.userData.nodeData && grp.userData.nodeData.label === devIdOrLabel)) {
      const p = grp.position;
      flyCameraTo([p.x + 1.2, p.y + 1.2, p.z + 2.4], [p.x, p.y, p.z], 700);
      break;
    }
  }
}

function createCanvasTextSprite(text, accentColor = "#38bdf8") {
  const canvas = document.createElement("canvas");
  canvas.width = 256;
  canvas.height = 64;
  const ctx = canvas.getContext("2d");

  // Rounded pill background
  ctx.fillStyle = "rgba(15, 23, 42, 0.88)";
  ctx.beginPath();
  ctx.roundRect ? ctx.roundRect(4, 4, 248, 56, 12) : ctx.rect(4, 4, 248, 56);
  ctx.fill();

  // Border outline
  ctx.strokeStyle = accentColor;
  ctx.lineWidth = 3;
  ctx.stroke();

  // Text label
  ctx.fillStyle = "#ffffff";
  ctx.font = "bold 20px sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";

  const cleanText = text.length > 20 ? text.slice(0, 19) + "…" : text;
  ctx.fillText(cleanText, 128, 32);

  const texture = new THREE.CanvasTexture(canvas);
  texture.minFilter = THREE.LinearFilter;
  const spriteMat = new THREE.SpriteMaterial({ map: texture, depthTest: false, transparent: true });
  const sprite = new THREE.Sprite(spriteMat);
  sprite.scale.set(0.9, 0.22, 1.0);
  return sprite;
}

function onHouse3DResize() {
  const container = document.getElementById("topology-3d-container");
  const canvas = document.getElementById("canvas-3d-house");
  if (!container || !canvas || !house3DState.renderer || !house3DState.camera) return;

  const width = container.clientWidth || 800;
  const height = container.clientHeight || 640;
  if (width === 0 || height === 0) return;

  house3DState.camera.aspect = width / height;
  house3DState.camera.updateProjectionMatrix();
  house3DState.renderer.setSize(width, height, false);
}

function initHouse3DViewer() {
  if (house3DState.isInitialized) return;
  if (typeof THREE === "undefined" || !THREE.GLTFLoader || !THREE.OrbitControls) {
    console.warn("Three.js or GLTFLoader / OrbitControls not yet available, retrying in 200ms...");
    setTimeout(initHouse3DViewer, 200);
    return;
  }

  const container = document.getElementById("topology-3d-container");
  const canvas = document.getElementById("canvas-3d-house");
  if (!container || !canvas) return;

  house3DState.isInitialized = true;
  house3DState.isLoading = true;

  // 1. Scene
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x060913);
  house3DState.scene = scene;

  // 2. Camera
  const width = container.clientWidth || 800;
  const height = container.clientHeight || 640;
  const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 1000);
  camera.position.set(...BLAIR_CAMERA_PRESETS.overview.pos);
  house3DState.camera = camera;

  // 3. Renderer
  const renderer = new THREE.WebGLRenderer({
    canvas,
    antialias: true,
    alpha: true,
    powerPreference: "high-performance"
  });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setSize(width, height, false);
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.1;
  house3DState.renderer = renderer;

  // 4. OrbitControls
  const controls = new THREE.OrbitControls(camera, canvas);
  controls.enableDamping = true;
  controls.dampingFactor = 0.05;
  controls.maxPolarAngle = Math.PI / 2 + 0.05;
  controls.minDistance = 2.0;
  controls.maxDistance = 60.0;
  controls.target.set(...BLAIR_CAMERA_PRESETS.overview.target);
  controls.update();
  house3DState.controls = controls;

  // 5. Lighting
  const ambientLight = new THREE.AmbientLight(0xffffff, 0.85);
  scene.add(ambientLight);

  const sunLight = new THREE.DirectionalLight(0xfff5e6, 1.1);
  sunLight.position.set(15, 25, 20);
  scene.add(sunLight);

  const fillLight = new THREE.DirectionalLight(0x93c5fd, 0.55);
  fillLight.position.set(-15, 15, -15);
  scene.add(fillLight);

  const hemiLight = new THREE.HemisphereLight(0xdbeafe, 0x1e293b, 0.45);
  scene.add(hemiLight);

  // 6. Ground Grid floor helper for visual depth
  const gridHelper = new THREE.GridHelper(40, 40, 0x1e293b, 0x0f172a);
  gridHelper.position.y = -0.22;
  scene.add(gridHelper);

  // 7. Raycaster, Drag Controls & Pointer interactions
  const raycaster = new THREE.Raycaster();
  const mouse = new THREE.Vector2();
  house3DState.raycaster = raycaster;
  house3DState.mouse = mouse;
  house3DState.dragPlane = new THREE.Plane();
  house3DState.dragOffset = new THREE.Vector3();
  house3DState.dragIntersect = new THREE.Vector3();

  let isPointerDragging = false;
  let downX = 0;
  let downY = 0;

  canvas.addEventListener("pointerdown", (e) => {
    isPointerDragging = false;
    downX = e.clientX;
    downY = e.clientY;

    if (e.button !== 0) return; // Only primary button for node dragging

    const rect = canvas.getBoundingClientRect();
    mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
    mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

    raycaster.setFromCamera(mouse, camera);
    const candidateSpheres = [];
    for (const grp of house3DState.nodeObjects.values()) {
      const sp = grp.getObjectByName("deviceSphere");
      if (sp) candidateSpheres.push(sp);
    }
    const intersects = raycaster.intersectObjects(candidateSpheres, false);
    if (intersects.length > 0) {
      const hitSphere = intersects[0].object;
      const targetGroup = hitSphere.parent;
      if (targetGroup) {
        house3DState.isDraggingNode = true;
        house3DState.draggedGroup = targetGroup;
        controls.enabled = false; // Disable orbit rotation so mouse moves the node!

        // Plane perpendicular to camera direction passing through node position
        const camDir = camera.getWorldDirection(new THREE.Vector3()).negate();
        house3DState.dragPlane.setFromNormalAndCoplanarPoint(camDir, targetGroup.position);

        if (raycaster.ray.intersectPlane(house3DState.dragPlane, house3DState.dragIntersect)) {
          house3DState.dragOffset.copy(house3DState.dragIntersect).sub(targetGroup.position);
        }

        canvas.style.cursor = "grabbing";
      }
    }
  });

  canvas.addEventListener("pointermove", (e) => {
    const rect = canvas.getBoundingClientRect();
    mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
    mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

    if (Math.hypot(e.clientX - downX, e.clientY - downY) > 5) {
      isPointerDragging = true;
    }

    raycaster.setFromCamera(mouse, camera);

    // Active 3D Node Dragging
    if (house3DState.isDraggingNode && house3DState.draggedGroup) {
      if (raycaster.ray.intersectPlane(house3DState.dragPlane, house3DState.dragIntersect)) {
        const newPos = house3DState.dragIntersect.clone().sub(house3DState.dragOffset);
        house3DState.draggedGroup.position.copy(newPos);
        update3DLinksForNode(house3DState.draggedGroup);

        const tooltip = document.getElementById("topology-3d-tooltip");
        const nData = (house3DState.draggedGroup.userData && house3DState.draggedGroup.userData.nodeData) || {};
        if (tooltip) {
          tooltip.innerHTML = `
            <div style="font-weight: 700; color: #38bdf8;">Moving: ${escapeHtml(nData.label || 'Device')}</div>
            <div style="font-size: 11px; color: #10b981; margin-top: 3px;">📍 Position: (${newPos.x.toFixed(2)}, ${newPos.y.toFixed(2)}, ${newPos.z.toFixed(2)})</div>
            <div style="font-size: 10px; color: #94a3b8; margin-top: 4px;"><i class="fa-solid fa-floppy-disk"></i> Release to save placement</div>
          `;
          tooltip.style.left = `${Math.min(e.clientX - rect.left + 16, rect.width - 240)}px`;
          tooltip.style.top = `${Math.max(10, e.clientY - rect.top - 20)}px`;
          tooltip.style.display = "block";
        }
      }
      return;
    }

    // Hover tooltip detection
    const candidateSpheres = [];
    for (const grp of house3DState.nodeObjects.values()) {
      const sp = grp.getObjectByName("deviceSphere");
      if (sp) candidateSpheres.push(sp);
    }
    const intersects = raycaster.intersectObjects(candidateSpheres, false);
    const tooltip = document.getElementById("topology-3d-tooltip");

    if (intersects.length > 0) {
      const hit = intersects[0].object;
      const nData = hit.userData.nodeData;
      canvas.style.cursor = "grab";
      if (tooltip && nData) {
        const roomName = (BLAIR_ROOMS[hit.userData.roomId] || {}).name || hit.userData.roomId;
        tooltip.innerHTML = `
          <div style="font-weight: 700; color: #38bdf8; margin-bottom: 2px;">${escapeHtml(nData.label || 'Device')}</div>
          <div style="font-size: 11px; color: #94a3b8;">${escapeHtml(nData.routing_role || nData.type || 'Node')}</div>
          <div style="font-size: 11px; margin-top: 4px;">📍 Room: <strong style="color: #f8fafc;">${escapeHtml(roomName)}</strong></div>
          ${nData.rssi !== null && nData.rssi !== undefined ? `<div style="font-size: 11px;">📶 RSSI: <strong>${escapeHtml(String(nData.rssi))} dBm</strong></div>` : ''}
          ${nData.lqi !== null && nData.lqi !== undefined ? `<div style="font-size: 11px;">📊 LQI: <strong>${escapeHtml(String(nData.lqi))} / 255</strong></div>` : ''}
          <div style="font-size: 10px; color: #38bdf8; margin-top: 6px;"><i class="fa-solid fa-arrows-up-down-left-right"></i> Drag to move anywhere • Click to inspect</div>
        `;
        tooltip.style.left = `${Math.min(e.clientX - rect.left + 14, rect.width - 240)}px`;
        tooltip.style.top = `${Math.max(10, e.clientY - rect.top - 20)}px`;
        tooltip.style.display = "block";
      }
    } else {
      canvas.style.cursor = "default";
      if (tooltip) tooltip.style.display = "none";
    }
  });

  canvas.addEventListener("pointerup", (e) => {
    // If user was dragging a node, save its position
    if (house3DState.isDraggingNode && house3DState.draggedGroup) {
      const movedGrp = house3DState.draggedGroup;
      const nData = (movedGrp.userData && movedGrp.userData.nodeData) || {};
      const devKey = nData.id !== undefined && nData.id !== null ? String(nData.id) : (nData.ext_address || nData.label || "");

      if (isPointerDragging) {
        setStoredCustom3DPosition(devKey, movedGrp.position);
        const lastScanElem = document.getElementById("topology-last-scan");
        if (lastScanElem) {
          lastScanElem.innerText = `✓ Position saved for ${nData.label || 'Device'}`;
        }
      } else {
        // Quick click without moving
        showNodeInspector(nData);
        focus3DDevice(devKey);
      }

      house3DState.isDraggingNode = false;
      house3DState.draggedGroup = null;
      controls.enabled = true;
      canvas.style.cursor = "grab";
      const tooltip = document.getElementById("topology-3d-tooltip");
      if (tooltip) tooltip.style.display = "none";
      return;
    }

    if (isPointerDragging) return;

    // Background or click on sphere
    const rect = canvas.getBoundingClientRect();
    mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
    mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

    raycaster.setFromCamera(mouse, camera);
    const candidateSpheres = [];
    for (const grp of house3DState.nodeObjects.values()) {
      const sp = grp.getObjectByName("deviceSphere");
      if (sp) candidateSpheres.push(sp);
    }
    const intersects = raycaster.intersectObjects(candidateSpheres, false);
    if (intersects.length > 0) {
      const hit = intersects[0].object;
      if (hit.userData && hit.userData.nodeData) {
        showNodeInspector(hit.userData.nodeData);
        focus3DDevice(hit.userData.nodeData.id || hit.userData.nodeData.label);
      }
    }
  });

  // 8. Robust GLB Model Loading with Ingress path candidates
  const curPath = window.location.pathname || "";
  const ingressBase = curPath.substring(0, curPath.lastIndexOf("/") + 1);
  const candidateUrls = [
    ingressBase + "models/Taylor_Wimpey_Blair.glb",
    "models/Taylor_Wimpey_Blair.glb",
    ingressBase + "static/models/Taylor_Wimpey_Blair.glb",
    "static/models/Taylor_Wimpey_Blair.glb",
    "./models/Taylor_Wimpey_Blair.glb"
  ];

  const loader = new THREE.GLTFLoader();
  const loaderStatus = document.getElementById("topology-3d-loader-status");
  const loaderTitle = document.getElementById("topology-3d-loader-title");
  const loaderOverlay = document.getElementById("topology-3d-loader");

  let urlIdx = 0;
  function tryLoadCandidate() {
    if (urlIdx >= candidateUrls.length) {
      console.error("All candidate URLs for 3D model failed to load.");
      house3DState.isLoading = false;
      if (loaderTitle) {
        loaderTitle.innerHTML = `<span style="color: #ef4444;"><i class="fa-solid fa-triangle-exclamation"></i> 3D Model Loading Error</span>`;
      }
      if (loaderStatus) {
        loaderStatus.innerHTML = `
          <span>Could not locate Taylor_Wimpey_Blair.glb at candidate routes.</span>
          <div style="margin-top: 10px;">
            <button id="btn-3d-retry-load" type="button" class="btn btn-primary" style="padding: 5px 12px; font-size: 11px;">
              <i class="fa-solid fa-rotate-right"></i> Retry Loading Model
            </button>
          </div>
        `;
        const btnRetry = document.getElementById("btn-3d-retry-load");
        if (btnRetry) {
          btnRetry.addEventListener("click", () => {
            urlIdx = 0;
            if (loaderTitle) loaderTitle.innerText = "Loading 3D Digital Twin House Model...";
            tryLoadCandidate();
          });
        }
      }
      return;
    }

    const currentUrl = candidateUrls[urlIdx];
    urlIdx++;
    if (loaderStatus) loaderStatus.innerText = `Connecting to 3D model asset (${urlIdx}/${candidateUrls.length})...`;

    loader.load(
      currentUrl,
      (gltf) => {
        house3DState.isLoading = false;
        if (loaderOverlay) loaderOverlay.style.display = "none";
        const model = gltf.scene;
        house3DState.modelRoot = model;
        scene.add(model);

        // Classify meshes and clone materials
        model.traverse((child) => {
          if (child.isMesh) {
            const cat = classifyMeshCategory(child.name);
            if (house3DState.meshesByCategory[cat]) {
              house3DState.meshesByCategory[cat].push(child);
            } else {
              house3DState.meshesByCategory.core_structure.push(child);
            }

            if (child.material) {
              if (Array.isArray(child.material)) {
                child.material = child.material.map(m => m.clone());
              } else {
                child.material = child.material.clone();
              }
              house3DState.originalMaterials.set(child.uuid, child.material);
            }
          }
        });

        apply3DCutawayAndTransparency();

        // Re-render nodes if data already available
        if (lastTopologyData && lastTopologyData.nodes) {
          renderHouse3DTopology(lastTopologyData.nodes, lastTopologyData.edges);
        }
      },
      (progress) => {
        if (loaderStatus && progress.total > 0) {
          const pct = Math.round((progress.loaded / progress.total) * 100);
          loaderStatus.innerText = `Downloading 3D house model: ${pct}%`;
        }
      },
      (err) => {
        console.warn(`Model candidate URL ${currentUrl} failed, trying next candidate...`, err);
        tryLoadCandidate();
      }
    );
  }

  tryLoadCandidate();

  // 9. Resize Observer
  if (window.ResizeObserver) {
    house3DState.resizeObserver = new ResizeObserver(() => {
      onHouse3DResize();
    });
    house3DState.resizeObserver.observe(container);
  }

  // 10. Toolbar Controls Event Listeners
  document.querySelectorAll(".btn-3d-floor").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".btn-3d-floor").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      const floor = btn.getAttribute("data-floor") || "all";
      house3DState.floorCutawayMode = floor;
      if (floor === "solid") {
        setXRayPercent(0);
      } else {
        apply3DCutawayAndTransparency();
      }
    });
  });

  const sliderOpacity = document.getElementById("slider-3d-opacity");
  if (sliderOpacity) {
    sliderOpacity.addEventListener("input", (e) => {
      const val = parseInt(e.target.value, 10);
      setXRayPercent(val);
    });
  }

  document.querySelectorAll(".btn-3d-xray-step").forEach((btn) => {
    btn.addEventListener("click", () => {
      const val = parseInt(btn.getAttribute("data-xray"), 10);
      setXRayPercent(val);
    });
  });

  const selectCam = document.getElementById("select-3d-camera");
  if (selectCam) {
    selectCam.addEventListener("change", (e) => {
      const key = e.target.value;
      if (BLAIR_CAMERA_PRESETS[key]) {
        flyCameraTo(BLAIR_CAMERA_PRESETS[key].pos, BLAIR_CAMERA_PRESETS[key].target);
      }
    });
  }

  const btnResetCam = document.getElementById("btn-3d-reset-cam");
  if (btnResetCam) {
    btnResetCam.addEventListener("click", () => {
      flyCameraTo(BLAIR_CAMERA_PRESETS.overview.pos, BLAIR_CAMERA_PRESETS.overview.target);
      if (selectCam) selectCam.value = "overview";
    });
  }

  const btnOpenRoomModal = document.getElementById("btn-open-room-setter");
  if (btnOpenRoomModal) {
    btnOpenRoomModal.addEventListener("click", () => {
      openRoomSetterModal();
    });
  }

  const btnResetPositions = document.getElementById("btn-reset-node-positions");
  if (btnResetPositions) {
    btnResetPositions.addEventListener("click", () => {
      resetStoredCustom3DPositions();
      btnResetPositions.innerHTML = `<i class="fa-solid fa-check"></i> Reset!`;
      setTimeout(() => {
        btnResetPositions.innerHTML = `<i class="fa-solid fa-rotate-left"></i> Reset Positions`;
      }, 1500);
      if (lastTopologyData && lastTopologyData.nodes) {
        renderHouse3DTopology(lastTopologyData.nodes, lastTopologyData.edges);
      }
    });
  }

  // 11. Render Animation Loop
  function animateHouse3D() {
    house3DState.animFrameId = requestAnimationFrame(animateHouse3D);

    // Camera animation interpolation
    if (house3DState.cameraAnimation) {
      const anim = house3DState.cameraAnimation;
      const now = performance.now();
      const elapsed = now - anim.startTime;
      const progress = Math.min(1.0, elapsed / anim.duration);
      // Smooth easing (ease-out cubic)
      const ease = 1 - Math.pow(1 - progress, 3);

      camera.position.lerpVectors(anim.startPos, anim.endPos, ease);
      controls.target.lerpVectors(anim.startTarget, anim.endTarget, ease);
      controls.update();

      if (progress >= 1.0) {
        house3DState.cameraAnimation = null;
      }
    } else {
      controls.update();
    }

    // Clean breathing glow on device spheres (pure spheres, no saturn rings)
    const emissiveGlow = 0.55 + Math.sin(performance.now() * 0.0035) * 0.22;
    for (const grp of house3DState.nodeObjects.values()) {
      const sp = grp.getObjectByName("deviceSphere");
      if (sp && sp.material && !house3DState.isDraggingNode) {
        sp.material.emissiveIntensity = emissiveGlow;
      }
    }

    // Wireless RF signal packets pulsing along link curves
    for (const p of house3DState.pulseObjects) {
      p.t = (p.t + p.speed) % 1.0;
      if (p.curve && p.mesh) {
        const pt = p.curve.getPoint(p.t);
        p.mesh.position.copy(pt);
      }
    }

    renderer.render(scene, camera);
  }

  animateHouse3D();
}

function renderHouse3DTopology(nodes, edges) {
  if (!house3DState.isInitialized) {
    initHouse3DViewer();
  }
  if (!house3DState.scene) return;

  const scene = house3DState.scene;

  // 1. Remove old nodes and edges
  for (const grp of house3DState.nodeObjects.values()) {
    scene.remove(grp);
  }
  house3DState.nodeObjects.clear();

  for (const edgeObj of house3DState.edgeObjects) {
    scene.remove(edgeObj);
  }
  house3DState.edgeObjects = [];
  house3DState.linkDataList = [];

  for (const pulse of house3DState.pulseObjects) {
    scene.remove(pulse.mesh);
  }
  house3DState.pulseObjects = [];

  const rawNodes = nodes || [];
  const rawEdges = edges || [];

  // Filter nodes if needed
  const filterMode = topologyPhysicsState.filterMode || "all";
  const filteredNodes = rawNodes.filter((n) => {
    if (filterMode === "routers_only") {
      const isR = n.is_router || (n.routing_role && (n.routing_role.includes("Router") || n.routing_role.includes("Coordinator") || n.routing_role.includes("TBR")));
      return isR;
    }
    if (filterMode === "end_only") {
      const isEnd = n.is_end_device || (n.routing_role && n.routing_role.includes("End Device"));
      return isEnd;
    }
    if (filterMode === "online_only") {
      return n.status !== "offline";
    }
    return true;
  });

  // Group nodes by assigned room to space them radially
  const roomGroups = {};
  filteredNodes.forEach((node) => {
    const res = resolveDeviceRoom(node);
    const rId = res.roomId;
    if (!roomGroups[rId]) roomGroups[rId] = [];
    roomGroups[rId].push({ node, isCustom: res.isCustom });
  });

  const customPositions = getStoredCustom3DPositions();

  // Build 3D Device Nodes (Pure glowing spheres, no Saturn rings)
  for (const [roomId, list] of Object.entries(roomGroups)) {
    const room = BLAIR_ROOMS[roomId] || BLAIR_ROOMS.living_room;
    const count = list.length;

    list.forEach((item, idx) => {
      const n = item.node;
      const devKey = n.id !== undefined && n.id !== null ? String(n.id) : (n.ext_address || n.label || "");
      const savedPos = customPositions[devKey] || (n.ext_address && customPositions[n.ext_address]) || (n.label && customPositions[n.label]);

      let x, y, z;
      if (savedPos && typeof savedPos.x === "number") {
        x = savedPos.x;
        y = savedPos.y;
        z = savedPos.z;
      } else {
        const angle = (idx / count) * 2 * Math.PI;
        const radius = count > 1 ? Math.min(0.25 + count * 0.08, 0.75) : 0;
        x = room.coords.x + (radius ? Math.cos(angle) * radius : 0);
        z = room.coords.z + (radius ? Math.sin(angle) * radius : 0);
        y = room.coords.y + (count > 2 && idx % 2 === 1 ? 0.22 : 0);
      }

      const group = new THREE.Group();
      group.position.set(x, y, z);
      group.userData = { isNode: true, nodeData: n, roomId, devKey };

      // Determine color
      let colorHex = "#10b981"; // default green
      const isTbrOrCoord = n.preferred || (n.routing_role && (n.routing_role.includes("Border Router") || n.routing_role.includes("Coordinator")));
      const isEnd = n.is_end_device || (n.routing_role && n.routing_role.includes("End Device"));
      const isOffline = n.status === "offline";
      const isWeak = n.status === "weak";

      if (isOffline) {
        colorHex = "#ef4444";
      } else if (isWeak) {
        colorHex = "#f59e0b";
      } else if (isTbrOrCoord) {
        colorHex = "#38bdf8";
      } else if (isEnd) {
        colorHex = "#a855f7";
      }

      const threeColor = new THREE.Color(colorHex);

      // 1. Core Glowing Sphere (No Saturn rings)
      const sphereGeo = new THREE.SphereGeometry(0.20, 32, 32);
      const sphereMat = new THREE.MeshStandardMaterial({
        color: threeColor,
        emissive: threeColor,
        emissiveIntensity: 0.65,
        roughness: 0.2,
        metalness: 0.4
      });
      const sphere = new THREE.Mesh(sphereGeo, sphereMat);
      sphere.name = "deviceSphere";
      sphere.userData = { isNode: true, nodeData: n, roomId, devKey };
      group.add(sphere);

      // 2. Floating Text Sprite Billboard
      const sprite = createCanvasTextSprite(n.label || "Device", colorHex);
      sprite.position.set(0, 0.38, 0);
      group.add(sprite);

      scene.add(group);
      house3DState.nodeObjects.set(n.id || n.label, group);
    });
  }

  // Build 3D Wireless RF Link Beams
  rawEdges.forEach((e) => {
    const srcId = e.source !== undefined && e.source !== null ? (e.source.id !== undefined ? e.source.id : e.source) : "";
    const tgtId = e.target !== undefined && e.target !== null ? (e.target.id !== undefined ? e.target.id : e.target) : "";

    const srcGroup = house3DState.nodeObjects.get(srcId);
    const tgtGroup = house3DState.nodeObjects.get(tgtId);

    if (srcGroup && tgtGroup) {
      const p1 = srcGroup.position.clone();
      const p2 = tgtGroup.position.clone();
      const dist = p1.distanceTo(p2);

      // Arched midpoint
      const mid = p1.clone().add(p2).multiplyScalar(0.5);
      mid.y += Math.min(0.35 + dist * 0.08, 1.2);

      const curve = new THREE.QuadraticBezierCurve3(p1, mid, p2);
      const points = curve.getPoints(24);

      // Color code by signal strength
      let edgeColor = "#10b981"; // green
      const rssi = e.rssi !== null && e.rssi !== undefined ? Number(e.rssi) : -65;
      if (rssi < -82) {
        edgeColor = "#ef4444";
      } else if (rssi < -70) {
        edgeColor = "#f59e0b";
      } else if (rssi < -60) {
        edgeColor = "#38bdf8";
      }

      const lineGeo = new THREE.BufferGeometry().setFromPoints(points);
      const lineMat = new THREE.LineBasicMaterial({
        color: new THREE.Color(edgeColor),
        transparent: true,
        opacity: 0.85,
        linewidth: 2
      });
      const line = new THREE.Line(lineGeo, lineMat);
      scene.add(line);
      house3DState.edgeObjects.push(line);

      // Signal Pulse Packet Particle
      const pulseGeo = new THREE.SphereGeometry(0.045, 12, 12);
      const pulseMat = new THREE.MeshBasicMaterial({ color: new THREE.Color(edgeColor) });
      const pulseMesh = new THREE.Mesh(pulseGeo, pulseMat);
      scene.add(pulseMesh);

      const pulseObj = {
        mesh: pulseMesh,
        curve,
        t: Math.random(),
        speed: 0.007 + Math.random() * 0.005
      };
      house3DState.pulseObjects.push(pulseObj);

      house3DState.linkDataList.push({
        line,
        pulseMesh,
        pulseObj,
        srcGroup,
        tgtGroup,
        edge: e
      });
    }
  });

  // Update Status Bar
  const lastScanElem = document.getElementById("topology-last-scan");
  const countElem = document.getElementById("topology-router-count");
  if (lastScanElem) {
    lastScanElem.innerText = `3D Twin Active: ${filteredNodes.length} devices mapped in Blair 4 TK house (drag any sphere to position & auto-save)`;
  }
  if (countElem) {
    const isZb = currentNetworkProtocol === "zigbee";
    countElem.innerText = isZb ? "Zigbee 3D Twin Mode" : "Thread & Matter 3D Twin Mode";
  }
}

function update3DLinksForNode(movedGroup) {
  if (!house3DState.linkDataList) return;
  for (const item of house3DState.linkDataList) {
    if (item.srcGroup === movedGroup || item.tgtGroup === movedGroup) {
      const p1 = item.srcGroup.position.clone();
      const p2 = item.tgtGroup.position.clone();
      const dist = p1.distanceTo(p2);
      const mid = p1.clone().add(p2).multiplyScalar(0.5);
      mid.y += Math.min(0.35 + dist * 0.08, 1.2);

      const curve = new THREE.QuadraticBezierCurve3(p1, mid, p2);
      const points = curve.getPoints(24);
      item.line.geometry.setFromPoints(points);
      item.line.geometry.attributes.position.needsUpdate = true;
      if (item.pulseObj) {
        item.pulseObj.curve = curve;
      }
    }
  }
}

/* ==========================================================================
   Room Setter Modal Implementation
   ========================================================================== */

function initRoomSetterModal() {
  const modal = document.getElementById("modal-room-setter");
  const btnClose = document.getElementById("btn-close-room-modal");
  const btnCancel = document.getElementById("btn-room-modal-cancel");
  const btnSave = document.getElementById("btn-room-modal-save");
  const btnAuto = document.getElementById("btn-room-auto-detect-all");

  if (btnClose) btnClose.addEventListener("click", closeRoomSetterModal);
  if (btnCancel) btnCancel.addEventListener("click", closeRoomSetterModal);
  if (btnSave) btnSave.addEventListener("click", saveRoomSetterModal);
  if (btnAuto) btnAuto.addEventListener("click", autoDetectAllRoomsModal);
}

function openRoomSetterModal() {
  const modal = document.getElementById("modal-room-setter");
  const listContainer = document.getElementById("room-setter-device-list");
  const statusElem = document.getElementById("room-setter-status");
  if (!modal || !listContainer) return;

  if (statusElem) statusElem.innerText = "";
  modal.classList.remove("hidden");

  let currentNodes = [];
  if (currentNetworkProtocol === "zigbee") {
    currentNodes = (currentZigbeeTelemetry && currentZigbeeTelemetry.topology && currentZigbeeTelemetry.topology.nodes) || [];
  } else {
    currentNodes = (currentTelemetry && currentTelemetry.topology && currentTelemetry.topology.nodes) || [];
  }

  if (currentNodes.length === 0) {
    listContainer.innerHTML = `
      <div style="text-align: center; color: #94a3b8; padding: 24px;">
        <i class="fa-solid fa-satellite-dish" style="font-size: 28px; margin-bottom: 8px; display: block; color: #64748b;"></i>
        No active devices discovered yet. Run a network scan first to populate your mesh devices!
      </div>
    `;
    return;
  }

  let html = "";
  currentNodes.forEach((n) => {
    const assigned = resolveDeviceRoom(n);
    const devKey = n.id !== undefined && n.id !== null ? String(n.id) : (n.ext_address || n.label || "");
    const role = n.routing_role || n.type || "Device";
    const area = n.ha_area ? `📍 HA Area: <strong>${escapeHtml(n.ha_area)}</strong>` : "No HA Area assigned";

    html += `
      <div class="room-setter-item" style="background: #1e293b; padding: 12px 14px; border-radius: 8px; border: 1px solid #334155; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;">
        <div style="min-width: 220px;">
          <div style="font-size: 13px; font-weight: 700; color: #f8fafc; display: flex; align-items: center; gap: 8px;">
            <i class="fa-solid ${n.status === 'offline' ? 'fa-triangle-exclamation' : 'fa-circle-dot'}" style="color: ${n.status === 'offline' ? '#ef4444' : '#10b981'}; font-size: 10px;"></i>
            ${escapeHtml(n.label || 'Device')}
          </div>
          <div style="font-size: 11px; color: #94a3b8; margin-top: 2px;">
            ${escapeHtml(role)} • ${area}
          </div>
        </div>

        <div style="display: flex; align-items: center; gap: 10px; flex-wrap: wrap;">
          <span class="badge" style="font-size: 10px; background: ${assigned.isCustom ? '#0284c7' : '#334155'}; color: #f8fafc;">
            ${assigned.isCustom ? 'Custom' : 'Auto'}
          </span>
          <select class="form-control room-select-input" data-devkey="${escapeHtml(devKey)}" style="background: #0f172a; border: 1px solid #475569; color: #f8fafc; padding: 5px 10px; border-radius: 6px; font-size: 12px; min-width: 200px;">
            ${generateRoomOptionsHtml(assigned.roomId)}
          </select>
        </div>
      </div>
    `;
  });

  listContainer.innerHTML = html;
}

function closeRoomSetterModal() {
  const modal = document.getElementById("modal-room-setter");
  if (modal) modal.classList.add("hidden");
}

function saveRoomSetterModal() {
  const selects = document.querySelectorAll(".room-select-input");
  const assignments = getStoredRoomAssignments();

  selects.forEach((sel) => {
    const k = sel.getAttribute("data-devkey");
    const v = sel.value;
    if (k && v) {
      assignments[k] = v;
    }
  });

  localStorage.setItem("ha_matter_room_assignments", JSON.stringify(assignments));

  const statusElem = document.getElementById("room-setter-status");
  if (statusElem) {
    statusElem.innerText = "✓ Room placements applied!";
  }

  // Refresh 3D Twin if open
  if (lastTopologyData && lastTopologyData.nodes) {
    renderHouse3DTopology(lastTopologyData.nodes, lastTopologyData.edges);
  }

  setTimeout(() => {
    closeRoomSetterModal();
  }, 600);
}

function autoDetectAllRoomsModal() {
  let currentNodes = [];
  if (currentNetworkProtocol === "zigbee") {
    currentNodes = (currentZigbeeTelemetry && currentZigbeeTelemetry.topology && currentZigbeeTelemetry.topology.nodes) || [];
  } else {
    currentNodes = (currentTelemetry && currentTelemetry.topology && currentTelemetry.topology.nodes) || [];
  }

  const selects = document.querySelectorAll(".room-select-input");
  selects.forEach((sel) => {
    const k = sel.getAttribute("data-devkey");
    const node = currentNodes.find((n) => String(n.id) === k || n.ext_address === k || n.label === k);
    if (node) {
      const autoRoom = autoDetectDeviceRoom(node);
      sel.value = autoRoom;
    }
  });

  const statusElem = document.getElementById("room-setter-status");
  if (statusElem) {
    statusElem.innerText = "Auto-detected all device rooms based on HA Area & names";
  }
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

  // Also highlight 3D nodes if 3D viewer is active
  if (house3dState.nodeObjects) {
    for (const [id, grp] of house3dState.nodeObjects.entries()) {
      const sp = grp.getObjectByName("deviceSphere");
      const nData = (sp && sp.userData && sp.userData.nodeData) || {};
      if (!q) {
        if (sp && sp.material) sp.material.emissiveIntensity = 0.65;
      } else {
        const hay = [
          nData.label || "",
          nData.node_id ? `#${nData.node_id}` : "",
          nData.brand || "",
          nData.model || "",
          nData.rloc16 || "",
          nData.ext_address || "",
          nData.ha_area || ""
        ].join(" ").toLowerCase();
        const matched = hay.includes(q);
        if (sp && sp.material) {
          sp.material.emissiveIntensity = matched ? 1.6 : 0.15;
        }
      }
    }
  }
}

async function downloadDiagnosticLogs(btnElem) {
  const origHtml = btnElem ? btnElem.innerHTML : "";
  if (btnElem) {
    btnElem.disabled = true;
    btnElem.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Building Log...`;
  }

  try {
    let bundleText = "";
    let filename = "";
    const now = new Date();
    const pad2 = (n) => String(n).padStart(2, "0");
    const ts = `${now.getFullYear()}${pad2(now.getMonth() + 1)}${pad2(now.getDate())}-${pad2(now.getHours())}${pad2(now.getMinutes())}${pad2(now.getSeconds())}`;

    if (currentNetworkProtocol === "zigbee") {
      filename = `zigbee-network-diagnostics-${ts}.json`;
      bundleText = JSON.stringify(currentZigbeeTelemetry || { protocol: "zigbee", status: "No Zigbee telemetry scanned yet" }, null, 2);
    } else {
      filename = `matter-thread-diagnostics-${ts}.log`;
      const res = await fetch(apiPath("/api/diagnostics/logs"));
      if (res.ok) {
        const data = await res.json();
        bundleText = data.bundle_text || "";
      }
      if (!bundleText) {
        bundleText = JSON.stringify(currentTelemetry || { status: "No telemetry cached yet" }, null, 2);
      }
    }

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
  if (currentNetworkProtocol === "zigbee") {
    if (currentZigbeeTelemetry) renderZigbeeChannelInfo(currentZigbeeTelemetry);
    return;
  }

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
  if (currentNetworkProtocol === "zigbee") return;

  const lblAdapter = document.getElementById("lbl-radio-adapter");
  if (lblAdapter) lblAdapter.innerText = "Thread Radio Adapter";
  const lblMesh = document.getElementById("lbl-mesh-identity");
  if (lblMesh) lblMesh.innerText = "Active Mesh Identity";
  const joinCard = document.getElementById("select-target-join-network")?.closest(".card");
  if (joinCard) joinCard.style.display = "";
  const migCard = document.getElementById("thread-migration-strategy-container");
  if (migCard) migCard.style.display = "block";
  const zbInfoBox = document.getElementById("zigbee-channel-info-box");
  if (zbInfoBox) zbInfoBox.style.display = "none";
  const faqCard = document.getElementById("card-channel-faq");
  if (faqCard) faqCard.style.display = "block";
  const lblPicker = document.getElementById("lbl-channel-picker-title");
  if (lblPicker) lblPicker.innerText = "Select Target Operating Channel (11–26):";

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
      onSelectTargetMigrationChannel(ch);
    });
  });

  // Update selected target channel label
  const curTargetInfo = channels.find(c => c.channel === selectedTargetChannel) || {};
  const labelEl = document.getElementById("selected-target-channel-label");
  if (labelEl) {
    labelEl.innerText = `Channel ${selectedTargetChannel} (${curTargetInfo.frequency_mhz || 2475} MHz) — ${curTargetInfo.recommendation_badge || 'Selected'}`;
  }
}

function onSelectTargetMigrationChannel(ch) {
  if (currentNetworkProtocol === "zigbee") {
    const freq = 2405 + (ch - 11) * 5;
    const isGuard = ch === 15 || ch === 20 || ch === 25 || ch === 26;
    onSelectZigbeeChannelTile(ch, freq, isGuard ? 'Clean Guard Band' : 'Wi-Fi 20MHz Overlap');
    return;
  }

  selectedTargetChannel = ch;
  const freq = 2405 + (ch - 11) * 5;
  const curTargetInfo = (currentOtbrChannelData?.channels_matrix || []).find(c => c.channel === ch) || {};
  const labelEl = document.getElementById("selected-target-channel-label");
  if (labelEl) {
    labelEl.innerText = `Channel ${ch} (${freq} MHz) — ${curTargetInfo.recommendation_badge || 'Selected'}`;
  }
  if (currentOtbrChannelData && currentOtbrChannelData.channels_matrix) {
    renderChannelPickerGrid(currentOtbrChannelData.channels_matrix, currentOtbrChannelData.current_channel);
  }
  if (currentCoexistenceData) {
    renderCoexistenceSpectrumGraph(currentCoexistenceData);
  }
}

/* =========================================================================
   2.4 GHz Network Coexistence Analyzer & Overlap Graph
   ========================================================================= */
let currentCoexistenceData = null;

async function fetchCoexistenceSpectrum(showSpinner = false) {
  const btnScan = document.getElementById("btn-scan-spectrum");
  const origHtml = btnScan ? btnScan.innerHTML : "";
  if (showSpinner && btnScan) {
    btnScan.disabled = true;
    btnScan.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Scanning Spectrum...`;
  }

  try {
    const res = await fetch(apiPath("/api/coexistence/scan"));
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    currentCoexistenceData = data;
    renderCoexistenceUI(data);
  } catch (err) {
    console.error("Failed fetching coexistence spectrum:", err);
    const alertDesc = document.getElementById("coex-alert-desc");
    if (alertDesc) {
      alertDesc.innerHTML = `<span style="color: var(--color-danger);"><i class="fa-solid fa-triangle-exclamation"></i> Spectrum scan failed: ${escapeHtml(err.message)}</span>`;
    }
  } finally {
    if (showSpinner && btnScan) {
      btnScan.disabled = false;
      btnScan.innerHTML = origHtml;
    }
  }
}

function renderCoexistenceUI(data) {
  if (!data) return;

  const th = data.thread || {};
  const zb = data.zigbee || {};
  const wf = data.wifi || {};
  const analysis = data.coexistence_analysis || {};

  // 1. Thread Status Pill
  const thChEl = document.getElementById("coex-thread-ch");
  const thFreqEl = document.getElementById("coex-thread-freq");
  const thNameEl = document.getElementById("coex-thread-name");
  const thBadgeEl = document.getElementById("coex-thread-badge");

  if (thChEl) thChEl.innerText = th.channel ? `Ch ${th.channel}` : "Ch --";
  if (thFreqEl) thFreqEl.innerText = th.frequency_mhz ? `(${th.frequency_mhz} MHz)` : "(-- MHz)";
  if (thNameEl) thNameEl.innerText = th.network_name || "Thread Mesh";
  if (thBadgeEl) {
    thBadgeEl.innerText = th.detected ? "Live Radio" : "No Radio";
    thBadgeEl.className = `badge ${th.detected ? "badge-success" : "badge-warning"}`;
  }

  // 2. Zigbee Status Pill
  const zbChEl = document.getElementById("coex-zigbee-ch");
  const zbFreqEl = document.getElementById("coex-zigbee-freq");
  const zbSourceEl = document.getElementById("coex-zigbee-source");
  const zbBadgeEl = document.getElementById("coex-zigbee-badge");

  if (zbChEl) zbChEl.innerText = zb.channel ? `Ch ${zb.channel}` : "Not Running";
  if (zbFreqEl) zbFreqEl.innerText = zb.frequency_mhz ? `(${zb.frequency_mhz} MHz)` : "";
  if (zbSourceEl) zbSourceEl.innerText = zb.source || "ZHA / Z2M";
  if (zbBadgeEl) {
    if (zb.detected && zb.channel) {
      zbBadgeEl.innerText = "Active Coordinator";
      zbBadgeEl.style.background = "#ca8a04";
      zbBadgeEl.style.color = "#fff";
    } else {
      zbBadgeEl.innerText = "Not Detected";
      zbBadgeEl.style.background = "#475569";
      zbBadgeEl.style.color = "#cbd5e1";
    }
  }

  // 3. Wi-Fi Status Pill
  const wfChEl = document.getElementById("coex-wifi-ch");
  const wfBwEl = document.getElementById("coex-wifi-bw");
  const wfSourceEl = document.getElementById("coex-wifi-source");
  const wfBadgeEl = document.getElementById("coex-wifi-badge");

  if (wfChEl) {
    const chList = wf.channels && wf.channels.length ? wf.channels.join(", ") : "1, 6, 11";
    wfChEl.innerText = `Ch ${chList}`;
  }
  if (wfBwEl) wfBwEl.innerText = `(${wf.bandwidth_mhz || 20} MHz wide)`;
  if (wfSourceEl) wfSourceEl.innerText = wf.source || "2.4 GHz Band";
  if (wfBadgeEl) {
    wfBadgeEl.innerText = wf.detected ? "Detected AP" : "Standard Plan";
    wfBadgeEl.className = `badge ${wf.detected ? "badge-info" : "badge-warning"}`;
  }

  // 4. Diagnostic Alert & Recommendation Box
  const alertBox = document.getElementById("coex-alert-box");
  const alertIcon = document.getElementById("coex-alert-icon");
  const alertTitle = document.getElementById("coex-alert-title");
  const alertDesc = document.getElementById("coex-alert-desc");
  const recEl = document.getElementById("coex-recommendation");

  if (alertBox && alertTitle && alertDesc) {
    if (currentNetworkProtocol === "zigbee") {
      const zbCh = zb.channel || currentZigbeeTelemetry?.channel || 15;
      const zbFreq = zb.frequency_mhz || currentZigbeeTelemetry?.frequency_mhz || (2405 + 5 * (zbCh - 11));
      if (analysis.thread_zigbee_collision) {
        alertBox.style.borderColor = "#ef4444";
        alertBox.style.background = "#450a0a33";
        if (alertIcon) alertIcon.innerHTML = `<i class="fa-solid fa-triangle-exclamation" style="color: #ef4444;"></i>`;
        alertTitle.innerHTML = `<span style="color: #f87171;">CRITICAL RF COLLISION: Zigbee &amp; Thread on Same Channel ${zbCh}!</span>`;
        alertDesc.innerHTML = `Both your Zigbee coordinator and Thread network are broadcasting on Channel ${zbCh} (${zbFreq} MHz). This causes 2.4 GHz carrier competition, packet drops, delayed sensor triggers, and battery drain.`;
      } else {
        const isGuard = zbCh === 15 || zbCh === 20 || zbCh === 25 || zbCh === 26;
        alertBox.style.borderColor = isGuard ? "#10b981" : "#f59e0b";
        alertBox.style.background = isGuard ? "#064e3b33" : "#451a0333";
        if (alertIcon) alertIcon.innerHTML = `<i class="fa-solid ${isGuard ? 'fa-circle-check' : 'fa-triangle-exclamation'}" style="color: ${isGuard ? '#10b981' : '#f59e0b'};"></i>`;
        alertTitle.innerHTML = `<span style="color: ${isGuard ? '#34d399' : '#fbbf24'};">${isGuard ? 'Clean RF Environment: Guard Band / Safe Zone' : 'Moderate Wi-Fi Overlap'}</span>`;
        alertDesc.innerHTML = `Your Zigbee network on Channel ${zbCh} (${zbFreq} MHz) is separated from Thread. ${isGuard ? 'It operates cleanly in a guard band between primary 20 MHz Wi-Fi channels.' : 'It falls inside a standard 2.4 GHz Wi-Fi transmission mask.'}`;
      }
      if (recEl) {
        recEl.innerHTML = `<i class="fa-solid fa-wand-magic-sparkles"></i> Zigbee Recommendation: Channels 15, 20, and 25 provide the cleanest 2.4 GHz clearance from Wi-Fi and Thread.`;
      }
    } else {
      if (analysis.thread_zigbee_collision) {
        alertBox.style.borderColor = "#ef4444";
        alertBox.style.background = "#450a0a33";
        if (alertIcon) alertIcon.innerHTML = `<i class="fa-solid fa-triangle-exclamation" style="color: #ef4444;"></i>`;
        alertTitle.innerHTML = `<span style="color: #f87171;">CRITICAL RF COLLISION: Thread &amp; Zigbee on Same Channel!</span>`;
        alertDesc.innerHTML = escapeHtml(analysis.thread_zigbee_message || "");
      } else if (analysis.thread_wifi_overlap) {
        alertBox.style.borderColor = "#f59e0b";
        alertBox.style.background = "#451a0333";
        if (alertIcon) alertIcon.innerHTML = `<i class="fa-solid fa-triangle-exclamation" style="color: #f59e0b;"></i>`;
        alertTitle.innerHTML = `<span style="color: #fbbf24;">High Wi-Fi Overlap: Inside Wi-Fi Channel ${analysis.overlapping_wifi_channel || '1/6/11'} Mask</span>`;
        alertDesc.innerHTML = `Your Thread network on Channel ${th.channel} (${th.frequency_mhz} MHz) is inside the 20 MHz transmission mask of Wi-Fi Channel ${analysis.overlapping_wifi_channel}. High-bandwidth Wi-Fi traffic (video streaming, downloads) will degrade Thread response times and cause packet retries.`;
      } else {
        alertBox.style.borderColor = "#10b981";
        alertBox.style.background = "#064e3b33";
        if (alertIcon) alertIcon.innerHTML = `<i class="fa-solid fa-circle-check" style="color: #10b981;"></i>`;
        alertTitle.innerHTML = `<span style="color: #34d399;">Clean RF Environment: Guard Band / Safe Zone</span>`;
        alertDesc.innerHTML = `Your Thread network on Channel ${th.channel} (${th.frequency_mhz} MHz) is operating cleanly outside of primary Wi-Fi channels and is separated from Zigbee.`;
      }

      if (recEl) {
        recEl.innerHTML = `<i class="fa-solid fa-wand-magic-sparkles"></i> Recommendation: ${escapeHtml(analysis.recommendation_summary || '')}`;
      }
    }
  }

  // 5. Render SVG Spectrum Graph
  renderCoexistenceSpectrumGraph(data);
}

function renderCoexistenceSpectrumGraph(data) {
  const svg = document.getElementById("spectrum-svg");
  if (!svg) return;
  svg.innerHTML = "";

  const rect = svg.getBoundingClientRect();
  const width = Math.max(rect.width || svg.clientWidth || 800, 600);
  const height = 240;
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);

  const L = 35;
  const R = 35;
  const T = 30;
  const B = 40;
  const GW = width - L - R;
  const GH = height - T - B;
  const Y_base = height - B;

  const X = (f) => L + ((f - 2400) / 85) * GW;

  const th = data.thread || {};
  const zb = data.zigbee || {};
  const wf = data.wifi || {};
  const wifiChannels = (wf.channels && wf.channels.length) ? wf.channels : [1, 6, 11];

  // 1. Guard Band Background Shading
  const safeZones = [
    { start: 2422, end: 2428, label: "Guard 1 (Ch 15)" },
    { start: 2447, end: 2453, label: "Guard 2 (Ch 20)" },
    { start: 2472, end: 2485, label: "★ Safe Zone (Ch 25-26)" },
  ];

  safeZones.forEach((sz) => {
    const x1 = X(sz.start);
    const x2 = X(sz.end);
    const w = x2 - x1;

    const rectEl = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    rectEl.setAttribute("x", x1);
    rectEl.setAttribute("y", T);
    rectEl.setAttribute("width", w);
    rectEl.setAttribute("height", GH);
    rectEl.setAttribute("fill", "#10b98112");
    rectEl.setAttribute("stroke", "#10b98133");
    rectEl.setAttribute("stroke-width", "1");
    rectEl.setAttribute("stroke-dasharray", "3,3");
    svg.appendChild(rectEl);

    const txt = document.createElementNS("http://www.w3.org/2000/svg", "text");
    txt.setAttribute("x", x1 + w / 2);
    txt.setAttribute("y", T - 8);
    txt.setAttribute("fill", "#34d399");
    txt.setAttribute("font-size", "9");
    txt.setAttribute("font-weight", "700");
    txt.setAttribute("text-anchor", "middle");
    txt.textContent = sz.label;
    svg.appendChild(txt);
  });

  // 2. Base Axis Line
  const axisLine = document.createElementNS("http://www.w3.org/2000/svg", "line");
  axisLine.setAttribute("x1", L);
  axisLine.setAttribute("y1", Y_base);
  axisLine.setAttribute("x2", width - R);
  axisLine.setAttribute("y2", Y_base);
  axisLine.setAttribute("stroke", "#475569");
  axisLine.setAttribute("stroke-width", "1.5");
  svg.appendChild(axisLine);

  // 3. Wi-Fi Parabolic 20 MHz Curves
  const WIFI_CENTERS = { 1: 2412, 6: 2437, 11: 2462 };
  wifiChannels.forEach((wch) => {
    const fCenter = WIFI_CENTERS[wch] || (2412 + (wch - 1) * 5);
    const fMin = fCenter - 11;
    const fMax = fCenter + 11;
    const peakH = GH * 0.62;

    let pathD = `M ${X(fMin).toFixed(1)} ${Y_base}`;
    const steps = 24;
    for (let i = 0; i <= steps; i++) {
      const f = fMin + (i / steps) * 22;
      const norm = (f - fCenter) / 11;
      const y = Y_base - Math.max(0, 1 - norm * norm) * peakH;
      pathD += ` L ${X(f).toFixed(1)} ${y.toFixed(1)}`;
    }
    pathD += ` L ${X(fMax).toFixed(1)} ${Y_base} Z`;

    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", pathD);
    path.setAttribute("fill", "#ef444420");
    path.setAttribute("stroke", "#ef444488");
    path.setAttribute("stroke-width", "1.8");
    svg.appendChild(path);

    const lbl = document.createElementNS("http://www.w3.org/2000/svg", "text");
    lbl.setAttribute("x", X(fCenter));
    lbl.setAttribute("y", Y_base - peakH - 6);
    lbl.setAttribute("fill", "#f87171");
    lbl.setAttribute("font-size", "11");
    lbl.setAttribute("font-weight", "700");
    lbl.setAttribute("text-anchor", "middle");
    lbl.textContent = `Wi-Fi Ch ${wch} (20 MHz)`;
    svg.appendChild(lbl);
  });

  // 4. All 16 802.15.4 Channels along X-Axis
  for (let ch = 11; ch <= 26; ch++) {
    const f = 2405 + 5 * (ch - 11);
    const x = X(f);

    const isCurrentThread = th.channel === ch;
    const isCurrentZigbee = zb.channel === ch;
    const isRecommended = data.coexistence_analysis?.recommended_channel === ch;
    const isSelected = selectedTargetChannel === ch;

    const tick = document.createElementNS("http://www.w3.org/2000/svg", "line");
    tick.setAttribute("x1", x);
    tick.setAttribute("y1", Y_base);
    tick.setAttribute("x2", x);
    tick.setAttribute("y2", Y_base + 6);
    tick.setAttribute("stroke", isCurrentThread ? "#38bdf8" : (isCurrentZigbee ? "#eab308" : (isSelected ? "#34d399" : "#475569")));
    tick.setAttribute("stroke-width", isCurrentThread || isCurrentZigbee || isSelected ? "2" : "1");
    svg.appendChild(tick);

    const chTxt = document.createElementNS("http://www.w3.org/2000/svg", "text");
    chTxt.setAttribute("x", x);
    chTxt.setAttribute("y", Y_base + 18);
    chTxt.setAttribute("fill", isCurrentThread ? "#38bdf8" : (isCurrentZigbee ? "#facc15" : (isSelected ? "#34d399" : (isRecommended ? "#a7f3d0" : "#94a3b8"))));
    chTxt.setAttribute("font-size", isCurrentThread || isCurrentZigbee || isSelected ? "11" : "9");
    chTxt.setAttribute("font-weight", isCurrentThread || isCurrentZigbee || isRecommended || isSelected ? "700" : "500");
    chTxt.setAttribute("text-anchor", "middle");
    chTxt.setAttribute("style", "cursor: pointer;");
    chTxt.textContent = `${ch}`;
    chTxt.addEventListener("click", () => {
      onSelectTargetMigrationChannel(ch);
    });
    svg.appendChild(chTxt);
  }

  // 5. Active Zigbee Channel (if detected)
  const isZigbeeMode = currentNetworkProtocol === "zigbee";
  const zbCh = zb.channel || (isZigbeeMode && currentZigbeeTelemetry?.channel ? currentZigbeeTelemetry.channel : null);
  const zbFreq = zb.frequency_mhz || (isZigbeeMode && currentZigbeeTelemetry?.frequency_mhz ? currentZigbeeTelemetry.frequency_mhz : (zbCh ? 2405 + 5 * (zbCh - 11) : null));

  if (zbCh && zbFreq) {
    const fZb = zbFreq;
    const xZb = X(fZb);
    const peakZb = isZigbeeMode ? GH * 0.95 : GH * 0.80;

    const zbPath = document.createElementNS("http://www.w3.org/2000/svg", "path");
    const x1 = X(fZb - 1.2);
    const x2 = X(fZb + 1.2);
    zbPath.setAttribute("d", `M ${x1} ${Y_base} L ${x1} ${Y_base - peakZb} L ${x2} ${Y_base - peakZb} L ${x2} ${Y_base} Z`);
    zbPath.setAttribute("fill", isZigbeeMode ? "#eab30888" : "#eab30844");
    zbPath.setAttribute("stroke", "#facc15");
    zbPath.setAttribute("stroke-width", isZigbeeMode ? "3.0" : "1.8");
    svg.appendChild(zbPath);

    const zbBadgeG = document.createElementNS("http://www.w3.org/2000/svg", "g");
    const badgeW = isZigbeeMode ? 140 : 120;
    zbBadgeG.innerHTML = `
      <rect x="${xZb - badgeW / 2}" y="${Y_base - peakZb - 24}" width="${badgeW}" height="20" rx="4" fill="${isZigbeeMode ? '#ca8a04' : '#854d0e'}" stroke="#facc15" stroke-width="${isZigbeeMode ? '2' : '1'}" />
      <text x="${xZb}" y="${Y_base - peakZb - 10}" fill="#ffffff" font-size="${isZigbeeMode ? '10' : '9'}" font-weight="${isZigbeeMode ? '800' : '600'}" text-anchor="middle">${isZigbeeMode ? '🐝 ACTIVE ZIGBEE Ch ' + zbCh : '🐝 Zigbee Ch ' + zbCh}</text>
    `;
    svg.appendChild(zbBadgeG);
  }

  // 6. Active Thread Channel (if detected)
  if (th.channel && th.frequency_mhz) {
    const fTh = th.frequency_mhz;
    const xTh = X(fTh);
    const peakTh = isZigbeeMode ? GH * 0.78 : GH * 0.95;

    const thPath = document.createElementNS("http://www.w3.org/2000/svg", "path");
    const x1 = X(fTh - 1.2);
    const x2 = X(fTh + 1.2);
    thPath.setAttribute("d", `M ${x1} ${Y_base} L ${x1} ${Y_base - peakTh} L ${x2} ${Y_base - peakTh} L ${x2} ${Y_base} Z`);
    thPath.setAttribute("fill", isZigbeeMode ? "#0284c744" : "#0284c766");
    thPath.setAttribute("stroke", "#38bdf8");
    thPath.setAttribute("stroke-width", isZigbeeMode ? "1.8" : "2.8");
    svg.appendChild(thPath);

    const thBadgeG = document.createElementNS("http://www.w3.org/2000/svg", "g");
    const badgeW = isZigbeeMode ? 125 : 140;
    thBadgeG.innerHTML = `
      <rect x="${xTh - badgeW / 2}" y="${Y_base - peakTh - 24}" width="${badgeW}" height="20" rx="4" fill="${isZigbeeMode ? '#075985' : '#0369a1'}" stroke="#38bdf8" stroke-width="${isZigbeeMode ? '1' : '1.8'}" />
      <text x="${xTh}" y="${Y_base - peakTh - 10}" fill="#ffffff" font-size="${isZigbeeMode ? '9' : '10'}" font-weight="${isZigbeeMode ? '600' : '800'}" text-anchor="middle">${isZigbeeMode ? '🧵 Thread Ch ' + th.channel : '🧵 ACTIVE THREAD Ch ' + th.channel}</text>
    `;
    svg.appendChild(thBadgeG);

    // Direct Collision Hazard Indicator
    if (zb.channel && th.channel === zb.channel) {
      const hazardG = document.createElementNS("http://www.w3.org/2000/svg", "g");
      hazardG.innerHTML = `
        <rect x="${xTh - 95}" y="${Y_base - (isZigbeeMode ? peakZb : peakTh) - 54}" width="190" height="24" rx="5" fill="#ef4444" stroke="#ffffff" stroke-width="2" />
        <text x="${xTh}" y="${Y_base - (isZigbeeMode ? peakZb : peakTh) - 38}" fill="#ffffff" font-size="10" font-weight="800" text-anchor="middle">🚨 DIRECT COLLISION: Ch ${th.channel}</text>
      `;
      svg.appendChild(hazardG);
    }
  }

  // 7. Target Migration Marker (if user selected a new channel)
  const activeChannelRef = isZigbeeMode ? zb.channel : th.channel;
  if (selectedTargetChannel && selectedTargetChannel !== activeChannelRef) {
    const fTarget = 2405 + 5 * (selectedTargetChannel - 11);
    const xTarget = X(fTarget);
    const targetBadgeG = document.createElementNS("http://www.w3.org/2000/svg", "g");
    const badgeW = 115;
    targetBadgeG.innerHTML = `
      <line x1="${xTarget}" y1="${Y_base}" x2="${xTarget}" y2="${T + 20}" stroke="#34d399" stroke-width="2" stroke-dasharray="4,3" />
      <rect x="${xTarget - badgeW / 2}" y="${T + 8}" width="${badgeW}" height="18" rx="4" fill="#065f46" stroke="#34d399" stroke-width="1.5" />
      <text x="${xTarget}" y="${T + 21}" fill="#34d399" font-size="9" font-weight="800" text-anchor="middle">🎯 TARGET: Ch ${selectedTargetChannel}</text>
    `;
    svg.appendChild(targetBadgeG);
  }

  // 8. Frequency Scale Labels
  const startLbl = document.createElementNS("http://www.w3.org/2000/svg", "text");
  startLbl.setAttribute("x", L);
  startLbl.setAttribute("y", Y_base + 32);
  startLbl.setAttribute("fill", "#64748b");
  startLbl.setAttribute("font-size", "9");
  startLbl.textContent = "2400 MHz";
  svg.appendChild(startLbl);

  const endLbl = document.createElementNS("http://www.w3.org/2000/svg", "text");
  endLbl.setAttribute("x", width - R);
  endLbl.setAttribute("y", Y_base + 32);
  endLbl.setAttribute("fill", "#64748b");
  endLbl.setAttribute("font-size", "9");
  endLbl.setAttribute("text-anchor", "end");
  endLbl.textContent = "2485 MHz";
  svg.appendChild(endLbl);
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
  if (currentNetworkProtocol === "zigbee") return;

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
