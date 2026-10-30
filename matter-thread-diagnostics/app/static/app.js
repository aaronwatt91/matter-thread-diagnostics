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

const MODEL_OPTIONS_BY_PROVIDER = {
  gemini: [
    { value: "gemini-2.5-flash", label: "Gemini 2.5 Flash (Recommended / Default)" },
    { value: "gemini-2.5-pro", label: "Gemini 2.5 Pro" },
    { value: "gemini-2.0-flash", label: "Gemini 2.0 Flash" },
    { value: "gemini-1.5-flash", label: "Gemini 1.5 Flash" },
    { value: "gemini-1.5-pro", label: "Gemini 1.5 Pro" },
    { value: "gemini-3.8-flash", label: "Gemini 3.8 Flash" },
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
    btnLoadRaw.addEventListener("click", () => {
      const box = document.getElementById("manual-log-input");
      if (box && currentTelemetry) {
        box.value = JSON.stringify(currentTelemetry, null, 2);
      } else if (box) {
        box.value = "No scan telemetry cached yet. Click '2. Scan Selected Network' first.";
      }
    });
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
              <strong>${escapeHtml(r.name || 'Border Router')}</strong>
              <div style="font-size: 11px; color: var(--text-muted);">${escapeHtml(r.brand || '')} • ${escapeHtml(r.model || '')}${r.thread_version ? ` (Thread ${escapeHtml(r.thread_version)})` : ''}</div>
            </td>
            <td style="padding: 10px 8px;">
              ${escapeHtml(r.network_name || '--')}
              ${r.preferred ? `<span class="badge badge-success" style="font-size:10px; padding:1px 6px;">★ Preferred</span>` : ''}
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
  const nodes = matterServer.nodes || [];
  const matterCountBadge = document.getElementById("matter-table-count");
  if (matterCountBadge) {
    matterCountBadge.innerText = matterServer.connected
      ? `${nodes.length} Commissioned Node(s)`
      : `Matter Server Disconnected`;
    matterCountBadge.className = matterServer.connected ? "badge badge-info" : "badge badge-warning";
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
    } else if (nodes.length === 0) {
      tbodyNodes.innerHTML = `
        <tr>
          <td colspan="8" style="padding: 18px; color: var(--text-muted); text-align: center;">
            Connected to Matter Server (Fabric ID: <code>${escapeHtml(String(matterServer.compressed_fabric_id || matterServer.fabric_id || 'OK'))}</code>), but 0 Matter nodes are currently commissioned.
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
        if (rssi !== null && rssi !== undefined) {
          const sigClass = rssi < -82 ? "badge-danger" : (rssi < -72 ? "badge-warning" : "badge-success");
          signalBadge = `<span class="badge ${sigClass}">${rssi} dBm</span>`;
          if (lqi !== null && lqi !== undefined) {
            signalBadge += ` <small style="color:var(--text-muted);">LQI ${lqi}</small>`;
          }
        } else if (lqi !== null && lqi !== undefined) {
          signalBadge = `<span class="badge badge-info">LQI ${lqi}/255</span>`;
        }

        return `
          <tr style="border-bottom: 1px solid #37415166;">
            <td style="padding: 10px 8px; font-weight: 700;">#${nid}</td>
            <td style="padding: 10px 8px;">
              <div>
                <span class="badge ${avail ? 'badge-success' : 'badge-danger'}" style="font-size:10px; padding:2px 6px;">${avail ? 'Online' : 'Offline'}</span>
                <strong>${escapeHtml(n.product_name || `Node ${nid}`)}</strong>
              </div>
              <div style="font-size: 11px; color: var(--text-muted);">
                ${escapeHtml(n.vendor_name || 'Unknown')} • Transport: <code>${escapeHtml(n.transport || 'thread')}</code>
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
              <button type="button" class="btn btn-outline btn-ping-node" data-node-id="${nid}" data-ipv6="${escapeHtml(ulaIp)}" style="font-size: 11px; padding: 4px 10px;">
                <i class="fa-solid fa-bolt"></i> Ping
              </button>
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
    nodeHtml += nq.offline_nodes.map(n => `<div style="color:var(--color-danger); margin-bottom:4px;">🔴 Node #${n.node_id} (${escapeHtml(n.name)}) — ${escapeHtml(n.reason)}</div>`).join("");
  }
  if (nq.weak_nodes && nq.weak_nodes.length > 0) {
    nodeHtml += nq.weak_nodes.map(n => `<div style="color:var(--color-warning); margin-bottom:4px;">⚠️ Node #${n.node_id} (${escapeHtml(n.name)}) — ${escapeHtml(n.reason)}</div>`).join("");
  }
  if (nq.wrong_network_nodes && nq.wrong_network_nodes.length > 0) {
    nodeHtml += nq.wrong_network_nodes.map(n => `<div style="color:#f87171; margin-bottom:4px;">🔀 Node #${n.node_id} (${escapeHtml(n.name)}) — ${escapeHtml(n.reason)}</div>`).join("");
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
      reportBody.innerHTML = `
        <div class="badge badge-danger" style="margin-bottom: 12px;"><i class="fa-solid fa-triangle-exclamation"></i> AI Configuration Required</div>
        <p>${escapeHtml(errMsg)}</p>
        <p style="margin-top: 10px;">Open the <strong>Settings &amp; API Keys</strong> tab, enter your API key, and click <strong>Save Settings</strong>.</p>
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

function renderTopologyData(data) {
  if (!data) return;
  renderSvgTopology(data.nodes || [], data.edges || []);

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

function renderSvgTopology(nodes, edges) {
  const svg = document.getElementById("mesh-svg");
  if (!svg) return;
  svg.innerHTML = "";

  const width = svg.clientWidth || 860;
  const height = 460;
  const cx = width / 2;
  const cy = height / 2;

  if (!nodes || nodes.length === 0) {
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
    return;
  }

  const borderRouters = nodes.filter(n => n.type === "border_router");
  const routerNodes = nodes.filter(n => n.type === "router");
  const endDevices = nodes.filter(n => n.type !== "border_router" && n.type !== "router");
  const nodeMap = {};

  const layoutRow = (list, yPos, spreadWidth) => {
    const count = list.length;
    list.forEach((n, idx) => {
      let x;
      if (count === 1) {
        x = cx;
      } else {
        const spacing = Math.min(220, spreadWidth / Math.max(count - 1, 1));
        const startX = cx - ((count - 1) * spacing) / 2;
        x = startX + idx * spacing;
      }
      nodeMap[n.id] = { ...n, x, y: yPos };
    });
  };

  layoutRow(borderRouters, 90, width - 160);
  if (routerNodes.length > 0 && endDevices.length > 0) {
    layoutRow(routerNodes, 230, width - 140);
    layoutRow(endDevices, 365, width - 120);
  } else {
    const combinedDevices = [...routerNodes, ...endDevices];
    layoutRow(combinedDevices, 290, width - 140);
  }

  edges.forEach(e => {
    const src = nodeMap[e.source];
    const tgt = nodeMap[e.target];
    if (!src || !tgt) return;

    const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
    line.setAttribute("x1", src.x);
    line.setAttribute("y1", src.y);
    line.setAttribute("x2", tgt.x);
    line.setAttribute("y2", tgt.y);
    line.setAttribute("stroke", e.status === "warning" ? "#f59e0b" : "#38bdf8");
    line.setAttribute("stroke-width", e.status === "warning" ? "2" : "2.5");
    if (e.status === "warning") {
      line.setAttribute("stroke-dasharray", "6,4");
    }
    svg.appendChild(line);

    if (e.label) {
      const midX = (src.x + tgt.x) / 2;
      const midY = (src.y + tgt.y) / 2 - 6;
      const lbl = document.createElementNS("http://www.w3.org/2000/svg", "text");
      lbl.setAttribute("x", midX);
      lbl.setAttribute("y", midY);
      lbl.setAttribute("fill", e.status === "warning" ? "#fbbf24" : "#9ca3af");
      lbl.setAttribute("font-size", "11");
      lbl.setAttribute("text-anchor", "middle");
      lbl.textContent = e.label;
      svg.appendChild(lbl);
    }
  });

  Object.values(nodeMap).forEach(n => {
    const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
    g.style.cursor = "pointer";

    let fill = "#10b981";
    let radius = 20;
    if (n.type === "border_router") {
      radius = 25;
      if (n.vendor === "nest") fill = "#4285F4";
      else if (n.vendor === "apple") fill = "#64748b";
      else if (n.vendor === "ha") fill = "#03A9F4";
      else fill = "#3b82f6";
    } else if (n.type === "end_device") {
      radius = 18;
      fill = "#8b5cf6";
    }

    if (n.status === "offline") fill = "#ef4444";
    else if (n.status === "weak" || n.status === "warning") fill = "#f59e0b";

    const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    circle.setAttribute("cx", n.x);
    circle.setAttribute("cy", n.y);
    circle.setAttribute("r", radius);
    circle.setAttribute("fill", fill);
    circle.setAttribute("stroke", n.is_target === false ? "#ef4444" : "#1f2937");
    circle.setAttribute("stroke-width", "3");
    g.appendChild(circle);

    const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
    text.setAttribute("x", n.x);
    text.setAttribute("y", n.y + radius + 16);
    text.setAttribute("fill", "#f9fafb");
    text.setAttribute("font-size", "12");
    text.setAttribute("font-weight", "600");
    text.setAttribute("text-anchor", "middle");
    text.textContent = n.label;
    g.appendChild(text);

    if (n.rloc16) {
      const subText = document.createElementNS("http://www.w3.org/2000/svg", "text");
      subText.setAttribute("x", n.x);
      subText.setAttribute("y", n.y + radius + 30);
      subText.setAttribute("fill", "#38bdf8");
      subText.setAttribute("font-size", "10");
      subText.setAttribute("text-anchor", "middle");
      subText.textContent = n.rloc16;
      g.appendChild(subText);
    }

    g.addEventListener("click", () => {
      const panel = document.getElementById("node-inspector");
      const title = document.getElementById("inspector-title");
      const content = document.getElementById("inspector-content");
      panel.classList.remove("hidden");
      title.innerText = `${n.label} (${n.routing_role || n.type.replace('_', ' ').toUpperCase()})`;
      content.innerHTML = `
        <div style="font-size: 13px; line-height: 1.6;">
          <div><strong>Status:</strong> <span class="badge ${n.status === 'online' ? 'badge-success' : 'badge-warning'}">${n.status.toUpperCase()}</span></div>
          <div><strong>Telemetry:</strong> ${escapeHtml(n.details || '')}</div>
        </div>
      `;
    });

    svg.appendChild(g);
  });
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
