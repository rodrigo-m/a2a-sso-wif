/**
 * A2A SSO & GCP Workload Identity Federation (Direct Principal Access) Client
 */

let appConfig = null;
let msalInstance = null;
let activeAccount = null;
let entraIdToken = null;
let gcpWifToken = null;
let activeWifData = null;
let currentSessionId = null;

// DOM Elements
const entraBadge = document.getElementById("entra-badge");
const entraUnauthView = document.getElementById("entra-unauth-view");
const entraAuthView = document.getElementById("entra-auth-view");
const btnEntraLogin = document.getElementById("btn-entra-login");
const btnMockLogin = document.getElementById("btn-mock-login");
const btnEntraLogout = document.getElementById("btn-entra-logout");
const userPrincipalName = document.getElementById("user-principal-name");
const userDisplayName = document.getElementById("user-display-name");
const btnToggleClaims = document.getElementById("btn-toggle-claims");
const iconClaimsChevron = document.getElementById("icon-claims-chevron");
const claimsBox = document.getElementById("claims-box");
const claimsJson = document.getElementById("claims-json");
const lblTenant = document.getElementById("lbl-tenant");

const wifBadge = document.getElementById("wif-badge");
const btnExchangeWif = document.getElementById("btn-exchange-wif");
const chkSimulationMode = document.getElementById("chk-simulation-mode");
const wifSuccessView = document.getElementById("wif-success-view");
const wifErrorView = document.getElementById("wif-error-view");
const wifErrorMessage = document.getElementById("wif-error-message");
const wifPoolDisplay = document.getElementById("wif-pool-display");
const tokenLifetime = document.getElementById("token-lifetime");

const statusDot = document.getElementById("status-dot");
const statusText = document.getElementById("status-text");
const engineIdPill = document.getElementById("engine-id-pill");
const chatMessages = document.getElementById("chat-messages");
const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const btnSendMessage = document.getElementById("btn-send-message");
const btnClearChat = document.getElementById("btn-clear-chat");

// Settings Modal
const settingsModal = document.getElementById("settings-modal");
const btnOpenSettings = document.getElementById("btn-open-settings");
const btnCloseSettings = document.getElementById("btn-close-settings");
const btnSaveSettings = document.getElementById("btn-save-settings");
const cfgEntraClientId = document.getElementById("cfg-entra-client-id");
const cfgEntraTenantId = document.getElementById("cfg-entra-tenant-id");
const cfgWifPoolId = document.getElementById("cfg-wif-pool-id");
const cfgWifProviderId = document.getElementById("cfg-wif-provider-id");
const cfgReasoningEngineId = document.getElementById("cfg-reasoning-engine-id");

// ============================================================================
// Initialization & Configuration
// ============================================================================
async function initApp() {
  lucide.createIcons();

  try {
    const res = await fetch("/api/config");
    appConfig = await res.json();
    populateConfigUI();
    initMSAL();
  } catch (err) {
    console.error("Failed to load runtime config:", err);
  }

  setupEventListeners();
}

function populateConfigUI() {
  if (!appConfig) return;
  lblTenant.innerText = appConfig.entra_tenant_id || "Not configured";
  wifPoolDisplay.innerText = appConfig.wif_pool_id || "Not configured";
  engineIdPill.innerText = appConfig.reasoning_engine_id || "Not configured";

  const wifAudienceHint = document.getElementById("wif-audience-hint");
  if (wifAudienceHint) {
    wifAudienceHint.innerText = appConfig.wif_pool_id || "Not configured";
  }
  const wifProjectDisplay = document.getElementById("wif-project-display");
  if (wifProjectDisplay) {
    wifProjectDisplay.innerText = appConfig.project_number
      ? `${appConfig.project_number} (${appConfig.project_id || ''})`
      : (appConfig.project_id || "Not configured");
  }

  cfgEntraClientId.value = appConfig.entra_client_id || "";
  cfgEntraTenantId.value = appConfig.entra_tenant_id || "";
  cfgWifPoolId.value = appConfig.wif_pool_id || "";
  cfgWifProviderId.value = appConfig.wif_provider_id || "";
  cfgReasoningEngineId.value = appConfig.reasoning_engine_id || "";
}

function initMSAL() {
  if (!window.msal) {
    console.error("MSAL library (window.msal) is not loaded!");
    return;
  }
  if (!appConfig || !appConfig.entra_client_id) {
    console.info("ENTRA_CLIENT_ID not set in .env. Quick Mock Sign In is available.");
    return;
  }

  const msalConfig = {
    auth: {
      clientId: appConfig.entra_client_id,
      authority: `https://login.microsoftonline.com/${appConfig.entra_tenant_id || "common"}`,
      redirectUri: appConfig.entra_redirect_uri || window.location.origin,
    },
    cache: {
      cacheLocation: "sessionStorage",
      storeAuthStateInCookie: false,
    },
  };

  try {
    msalInstance = new window.msal.PublicClientApplication(msalConfig);
    console.log("MSAL initialized successfully with client ID:", appConfig.entra_client_id);
  } catch (e) {
    console.error("MSAL initialization error:", e);
  }
}

// ============================================================================
// Step 1: Microsoft Entra ID Authentication Flow
// ============================================================================
async function handleEntraLogin() {
  // Re-fetch latest config dynamically
  try {
    const res = await fetch("/api/config");
    appConfig = await res.json();
    populateConfigUI();
    initMSAL();
  } catch (e) {
    console.warn("Could not reload config:", e);
  }

  if (!appConfig || !appConfig.entra_client_id) {
    const useMock = confirm(
      "Entra Client ID is not yet configured in .env.\n\nWould you like to sign in using the simulated Entra ID account (user@example.com)?\n\nClick Cancel to open Settings and enter your Entra Client ID."
    );
    if (useMock) {
      handleMockLogin();
    } else {
      settingsModal.classList.remove("hidden");
    }
    return;
  }

  if (!msalInstance) {
    alert("MSAL library could not be initialized. Please check that /static/msal-browser.min.js loaded properly, or use Quick Mock Sign In.");
    return;
  }

  const loginRequest = {
    scopes: ["openid", "profile", "email"],
    prompt: "select_account",
  };

  try {
    const loginResponse = await msalInstance.loginPopup(loginRequest);
    activeAccount = loginResponse.account;
    entraIdToken = loginResponse.idToken;

    setEntraAuthenticated(
      activeAccount.username || "user@example.com",
      activeAccount.name || "Authenticated User",
      loginResponse.idTokenClaims || {}
    );

    // Automatically trigger WIF token exchange
    await handleWifExchange();
  } catch (err) {
    console.error("Entra ID login failed:", err);
    alert(`Entra ID Login Failed: ${err.message || err}`);
  }
}

function handleMockLogin() {
  const upn = "user@example.com";
  const name = "Mock User";
  const tenant = appConfig?.entra_tenant_id || "example.onmicrosoft.com";
  const claims = {
    aud: appConfig?.entra_client_id || "a2a-entra-client",
    iss: `https://login.microsoftonline.com/${tenant}/v2.0`,
    sub: "00000000-0000-0000-0000-000000000001",
    preferred_username: upn,
    email: upn,
    name: name,
    tid: tenant,
    exp: Math.floor(Date.now() / 1000) + 3600,
  };

  // Generate synthetic base64url JWT payload
  const header = btoa(JSON.stringify({ alg: "RS256", typ: "JWT" }));
  const payload = btoa(JSON.stringify(claims));
  entraIdToken = `${header}.${payload}.mockSignatureBytes`;

  setEntraAuthenticated(upn, name, claims);
  handleWifExchange();
}

function setEntraAuthenticated(upn, name, claims) {
  userPrincipalName.innerText = upn;
  userDisplayName.innerText = name;
  const userTenantName = document.getElementById("user-tenant-name");
  if (userTenantName) {
    userTenantName.innerText = claims?.tid || appConfig?.entra_tenant_id || "--";
  }
  claimsJson.innerText = JSON.stringify(claims, null, 2);

  entraBadge.innerText = "Authenticated";
  entraBadge.className = "text-xs px-2.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/30";

  entraUnauthView.classList.add("hidden");
  entraAuthView.classList.remove("hidden");

  btnExchangeWif.disabled = false;
  btnExchangeWif.className = "w-full py-3 px-4 rounded-xl bg-cyan-600 hover:bg-cyan-500 text-white font-medium shadow-lg shadow-cyan-500/20 flex items-center justify-center gap-2 transition cursor-pointer";

  wifBadge.innerText = "Ready to Exchange";
  wifBadge.className = "text-xs px-2.5 py-0.5 rounded-full bg-blue-500/10 text-blue-400 border border-blue-500/30";

  updateStatusPill("authenticated", `Entra: ${upn}`);
}

function handleEntraLogout() {
  entraIdToken = null;
  activeAccount = null;
  gcpWifToken = null;
  activeWifData = null;

  entraBadge.innerText = "Unauthenticated";
  entraBadge.className = "text-xs px-2.5 py-0.5 rounded-full bg-slate-800 text-slate-400 border border-slate-700";

  entraAuthView.classList.add("hidden");
  entraUnauthView.classList.remove("hidden");

  btnExchangeWif.disabled = true;
  btnExchangeWif.className = "w-full py-3 px-4 rounded-xl bg-slate-800 text-slate-400 font-medium border border-slate-700 cursor-not-allowed flex items-center justify-center gap-2 transition";

  wifBadge.innerText = "Waiting for Entra ID";
  wifBadge.className = "text-xs px-2.5 py-0.5 rounded-full bg-slate-800 text-slate-400 border border-slate-700";
  wifSuccessView.classList.add("hidden");
  wifErrorView.classList.add("hidden");

  updateStatusPill("ready", "Ready to Authenticate");
}

// ============================================================================
// Step 2: GCP Workload Identity Federation (WIF) Flow
// ============================================================================
async function handleWifExchange() {
  if (!entraIdToken) return;

  btnExchangeWif.disabled = true;
  btnExchangeWif.innerHTML = `<span class="animate-spin inline-block mr-2">&#9696;</span> Exchanging with Cloud STS...`;

  wifErrorView.classList.add("hidden");
  wifSuccessView.classList.add("hidden");

  const useDevFallback = chkSimulationMode.checked;

  try {
    const res = await fetch("/api/wif/exchange", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        entra_token: entraIdToken,
        pool_id: appConfig?.wif_pool_id,
        provider_id: appConfig?.wif_provider_id,
        use_dev_fallback: useDevFallback,
        principal_hint: userPrincipalName.innerText || null,
      }),
    });

    const data = await res.json();

    if (data.success && data.access_token) {
      gcpWifToken = data.access_token;
      activeWifData = data;
      tokenLifetime.innerText = `${data.expires_in || 3600} seconds`;

      const isWifUsed = Boolean(data.wif_token_used);
      wifBadge.innerText = isWifUsed ? "WIF Active (Direct Principal)" : "WIF Simulation (ADC Mode)";
      wifBadge.className = isWifUsed
        ? "text-xs px-2.5 py-0.5 rounded-full bg-cyan-500/10 text-cyan-400 border border-cyan-500/30 font-medium"
        : "text-xs px-2.5 py-0.5 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/30 font-medium";

      const elFullPrincipal = document.getElementById("wif-full-principal");
      if (elFullPrincipal) {
        elFullPrincipal.innerText = data.full_principal || data.principal || "N/A";
      }
      const elTokenUsedBadge = document.getElementById("wif-token-used-badge");
      if (elTokenUsedBadge) {
        elTokenUsedBadge.innerText = isWifUsed ? "Yes (Cloud STS Direct Principal)" : "No (ADC Fallback)";
        elTokenUsedBadge.className = isWifUsed
          ? "font-mono text-emerald-400 font-semibold px-2 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/30"
          : "font-mono text-amber-400 font-semibold px-2 py-0.5 rounded bg-amber-500/10 border border-amber-500/30";
      }

      wifSuccessView.classList.remove("hidden");
      btnExchangeWif.innerHTML = `<i data-lucide="check" class="w-4 h-4"></i><span>WIF Token Active</span>`;
      btnExchangeWif.className = "w-full py-3 px-4 rounded-xl bg-slate-800 text-slate-300 font-medium border border-slate-700 cursor-default flex items-center justify-center gap-2 transition";
      lucide.createIcons();

      updateStatusPill("connected", `Connected: ${data.principal}`);
    } else {
      wifErrorView.classList.remove("hidden");
      const errText = data.details ? `${data.error || "WIF Exchange Failed"}\n${typeof data.details === "string" ? data.details : JSON.stringify(data.details, null, 2)}` : (data.error || "WIF Token Exchange failed.");
      wifErrorMessage.innerText = errText;
      wifBadge.innerText = "Exchange Failed";
      wifBadge.className = "text-xs px-2.5 py-0.5 rounded-full bg-rose-500/10 text-rose-400 border border-rose-500/30";

      btnExchangeWif.disabled = false;
      btnExchangeWif.innerHTML = `<i data-lucide="refresh-cw" class="w-4 h-4"></i><span>Retry WIF Exchange</span>`;
      btnExchangeWif.className = "w-full py-3 px-4 rounded-xl bg-cyan-600 hover:bg-cyan-500 text-white font-medium cursor-pointer flex items-center justify-center gap-2 transition";
      lucide.createIcons();
    }
  } catch (err) {
    wifErrorView.classList.remove("hidden");
    wifErrorMessage.innerText = err.message || err;
    btnExchangeWif.disabled = false;
    btnExchangeWif.innerText = "Retry WIF Exchange";
  }
}

// ============================================================================
// Step 3: Interactive Chat with a2a_agent
// ============================================================================
async function sendMessage(text) {
  const message = text.trim();
  if (!message) return;

  if (!gcpWifToken) {
    alert("Please authenticate with Entra ID and complete the WIF exchange first!");
    return;
  }

  const invokedPrincipal = (activeWifData && activeWifData.full_principal)
    ? activeWifData.full_principal
    : (userPrincipalName.innerText || null);

  if (!invokedPrincipal) {
    alert("No authenticated caller principal found. Please sign in with Entra ID first.");
    return;
  }

  // Append user bubble
  appendUserMessage(message);
  chatInput.value = "";
  chatInput.focus();

  // Create assistant message container for streaming
  const assistantBubble = createAssistantMessageContainer();
  const textContentSpan = assistantBubble.querySelector(".agent-text-content");

  btnSendMessage.disabled = true;

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: message,
        token: gcpWifToken,
        user_id: invokedPrincipal,
        full_principal: activeWifData?.full_principal || invokedPrincipal,
        wif_token_used: activeWifData?.wif_token_used ?? false,
        session_id: currentSessionId,
      }),
    });

    if (!res.ok) {
      const err = await res.json();
      textContentSpan.innerHTML = `<span class="text-rose-400 font-semibold">Error:</span> ${err.detail || "Request failed"}`;
      textContentSpan.classList.remove("typing-cursor");
      btnSendMessage.disabled = false;
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let accumulatedText = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value, { stream: true });
      const lines = chunk.split("\n");

      for (const line of lines) {
        if (line.startsWith("data: ")) {
          try {
            const event = JSON.parse(line.substring(6));

            if (event.type === "text" && event.content) {
              accumulatedText += event.content;
              textContentSpan.innerText = accumulatedText;
              scrollChatToBottom();
            } else if (event.type === "tool_call") {
              renderToolCallChip(assistantBubble, event.name, event.args);
            } else if (event.type === "tool_response") {
              renderToolResponseChip(assistantBubble, event.name, event.response);
            } else if (event.type === "error") {
              accumulatedText += `\n[Agent Error: ${event.error}]`;
              textContentSpan.innerText = accumulatedText;
            }
          } catch (e) {
            // Ignore partial SSE chunk parse
          }
        }
      }
    }

    textContentSpan.classList.remove("typing-cursor");
  } catch (err) {
    textContentSpan.innerHTML = `<span class="text-rose-400">Connection error:</span> ${err.message || err}`;
    textContentSpan.classList.remove("typing-cursor");
  } finally {
    btnSendMessage.disabled = false;
  }
}

function appendUserMessage(text) {
  const wrapper = document.createElement("div");
  wrapper.className = "flex justify-end";
  wrapper.innerHTML = `
    <div class="max-w-[80%] rounded-2xl rounded-tr-none bg-blue-600 text-white p-4 text-sm shadow-md">
      ${escapeHtml(text)}
    </div>
  `;
  chatMessages.appendChild(wrapper);
  scrollChatToBottom();
}

function createAssistantMessageContainer() {
  const wrapper = document.createElement("div");
  wrapper.className = "flex items-start gap-3";
  wrapper.innerHTML = `
    <div class="w-8 h-8 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 flex items-center justify-center shrink-0 mt-0.5">
      <i data-lucide="bot" class="w-4 h-4"></i>
    </div>
    <div class="max-w-[85%] rounded-2xl rounded-tl-none bg-slate-800/80 border border-slate-700/60 p-4 text-sm text-slate-200 space-y-2">
      <div class="tool-chips-area space-y-1.5 mb-2"></div>
      <div class="agent-text-content whitespace-pre-wrap typing-cursor"></div>
    </div>
  `;
  chatMessages.appendChild(wrapper);
  lucide.createIcons();
  scrollChatToBottom();
  return wrapper;
}

function renderToolCallChip(container, toolName, args) {
  const chipsArea = container.querySelector(".tool-chips-area");
  const chip = document.createElement("div");
  chip.className = "tool-call-card text-[11px] px-2.5 py-1.5 rounded-lg bg-slate-900 border border-slate-700 text-slate-300 flex items-center gap-1.5 font-mono";
  chip.innerHTML = `
    <span class="w-2 h-2 rounded-full bg-amber-400 animate-pulse"></span>
    <span class="text-amber-300 font-semibold">tool_call:</span> ${toolName}()
  `;
  chipsArea.appendChild(chip);
  scrollChatToBottom();
}

function renderToolResponseChip(container, toolName, response) {
  const chipsArea = container.querySelector(".tool-chips-area");
  const chip = document.createElement("div");
  chip.className = "tool-call-card text-[11px] px-2.5 py-1.5 rounded-lg bg-slate-900 border border-emerald-700/60 text-slate-300 space-y-1 font-mono";
  chip.innerHTML = `
    <div class="flex items-center gap-1.5 text-emerald-400 font-semibold">
      <i data-lucide="check-circle" class="w-3.5 h-3.5"></i>
      <span>tool_output: ${toolName}</span>
    </div>
    <div class="text-[10px] text-slate-400 max-h-24 overflow-y-auto">
      ${escapeHtml(JSON.stringify(response, null, 2))}
    </div>
  `;
  chipsArea.appendChild(chip);
  lucide.createIcons();
  scrollChatToBottom();
}

function scrollChatToBottom() {
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function updateStatusPill(state, text) {
  statusText.innerText = text;
  if (state === "connected") {
    statusDot.className = "w-2 h-2 rounded-full bg-emerald-400 animate-pulse";
    statusText.className = "text-emerald-300 font-medium";
  } else if (state === "authenticated") {
    statusDot.className = "w-2 h-2 rounded-full bg-cyan-400";
    statusText.className = "text-cyan-300";
  } else {
    statusDot.className = "w-2 h-2 rounded-full bg-slate-500";
    statusText.className = "text-slate-400";
  }
}

function escapeHtml(str) {
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// ============================================================================
// Event Listeners
// ============================================================================
function setupEventListeners() {
  btnEntraLogin.addEventListener("click", handleEntraLogin);
  btnMockLogin.addEventListener("click", handleMockLogin);
  btnEntraLogout.addEventListener("click", handleEntraLogout);
  btnExchangeWif.addEventListener("click", handleWifExchange);

  btnToggleClaims.addEventListener("click", () => {
    const isHidden = claimsBox.classList.contains("hidden");
    if (isHidden) {
      claimsBox.classList.remove("hidden");
      iconClaimsChevron.style.transform = "rotate(90deg)";
    } else {
      claimsBox.classList.add("hidden");
      iconClaimsChevron.style.transform = "rotate(0deg)";
    }
  });

  chatForm.addEventListener("submit", (e) => {
    e.preventDefault();
    sendMessage(chatInput.value);
  });

  // Prompt chips
  document.querySelectorAll(".prompt-chip").forEach((btn) => {
    btn.addEventListener("click", () => {
      chatInput.value = btn.innerText.trim();
      sendMessage(chatInput.value);
    });
  });

  btnClearChat.addEventListener("click", () => {
    chatMessages.innerHTML = `
      <div class="flex items-start gap-3">
        <div class="w-8 h-8 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 flex items-center justify-center shrink-0 mt-0.5">
          <i data-lucide="bot" class="w-4 h-4"></i>
        </div>
        <div class="max-w-[85%] rounded-2xl rounded-tl-none bg-slate-800/80 border border-slate-700/60 p-4 text-sm text-slate-200">
          Chat cleared. Prompt me with <strong class="text-blue-300">"Hi"</strong> to see your authenticated identity and session context!
        </div>
      </div>
    `;
    lucide.createIcons();
  });

  // Settings
  btnOpenSettings.addEventListener("click", () => {
    settingsModal.classList.remove("hidden");
  });
  btnCloseSettings.addEventListener("click", () => {
    settingsModal.classList.add("hidden");
  });
  btnSaveSettings.addEventListener("click", () => {
    appConfig.entra_client_id = cfgEntraClientId.value.trim();
    appConfig.entra_tenant_id = cfgEntraTenantId.value.trim();
    appConfig.wif_pool_id = cfgWifPoolId.value.trim();
    appConfig.wif_provider_id = cfgWifProviderId.value.trim();
    populateConfigUI();
    initMSAL();
    settingsModal.classList.add("hidden");
    alert("Settings saved for this session!");
  });
}

// Start application
document.addEventListener("DOMContentLoaded", initApp);
