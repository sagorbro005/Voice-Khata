/**
 * Voice Khata Deployment Configuration
 * Centralized API configuration for local development and production on Vercel/Render.
 */

// Production Render backend service URL.
// When you deploy your backend on Render, replace this with your actual Render URL (e.g., https://your-service-name.onrender.com)
const DEFAULT_RENDER_BACKEND_URL = "https://voice-khata-backend.onrender.com";

const VoiceKhataConfig = {
  getApiBase: function () {
    // 1. Priority 1: User-configured URL in localStorage (can be set anytime in browser)
    const customUrl = localStorage.getItem("VOICE_KHATA_API_BASE");
    if (customUrl && customUrl.trim() !== "") {
      return customUrl.trim().replace(/\/+$/, "");
    }

    // 2. Priority 2: Localhost environment
    const isLocal =
      window.location.hostname === "127.0.0.1" ||
      window.location.hostname === "localhost";

    if (isLocal) {
      return window.location.port === "8001"
        ? "http://127.0.0.1:8001"
        : "http://127.0.0.1:8000";
    }

    // 3. Priority 3: Configured Production URL (Render)
    return DEFAULT_RENDER_BACKEND_URL.replace(/\/+$/, "");
  },

  setApiBase: function (newUrl) {
    if (!newUrl || newUrl.trim() === "") {
      localStorage.removeItem("VOICE_KHATA_API_BASE");
    } else {
      let formatted = newUrl.trim().replace(/\/+$/, "");
      if (!formatted.startsWith("http://") && !formatted.startsWith("https://")) {
        formatted = "https://" + formatted;
      }
      localStorage.setItem("VOICE_KHATA_API_BASE", formatted);
    }
    window.location.reload();
  },

  checkBackendStatus: async function () {
    const apiBase = this.getApiBase();
    try {
      const res = await fetch(`${apiBase}/health`, { method: "GET", signal: AbortSignal.timeout(6000) });
      if (res.ok) {
        return { ok: true, url: apiBase };
      }
      return { ok: false, url: apiBase, error: `HTTP ${res.status}` };
    } catch (e) {
      return { ok: false, url: apiBase, error: e.message };
    }
  }
};

window.VoiceKhataConfig = VoiceKhataConfig;
window.API_BASE = VoiceKhataConfig.getApiBase();

// Add a backend settings badge to easily configure or view backend URL on production
document.addEventListener("DOMContentLoaded", () => {
  const isLocal = window.location.hostname === "127.0.0.1" || window.location.hostname === "localhost";
  const currentUrl = VoiceKhataConfig.getApiBase();

  const badge = document.createElement("div");
  badge.id = "backend-config-badge";
  badge.style.cssText = `
    position: fixed;
    bottom: 12px;
    right: 12px;
    z-index: 9999;
    background: rgba(15, 23, 42, 0.85);
    backdrop-filter: blur(8px);
    color: #e2e8f0;
    padding: 6px 12px;
    border-radius: 9999px;
    font-size: 11px;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    display: flex;
    align-items: center;
    gap: 8px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    border: 1px solid rgba(255,255,255,0.1);
    cursor: pointer;
    user-select: none;
    transition: all 0.2s ease;
  `;

  const dot = document.createElement("span");
  dot.style.cssText = "width: 8px; height: 8px; border-radius: 50%; background: #f59e0b; display: inline-block;";
  
  const text = document.createElement("span");
  text.innerText = isLocal ? "API: Localhost" : "API: Render";

  badge.appendChild(dot);
  badge.appendChild(text);
  document.body.appendChild(badge);

  // Ping backend to show active green or warning yellow
  VoiceKhataConfig.checkBackendStatus().then(status => {
    if (status.ok) {
      dot.style.background = "#10b981";
      text.title = `Connected to: ${status.url}`;
    } else {
      dot.style.background = "#ef4444";
      text.title = `Offline (${status.error}) - Click to configure URL`;
    }
  });

  // Clicking badge allows viewing/changing API base URL
  badge.addEventListener("click", () => {
    const entered = prompt(
      `Current Backend API URL:\n${currentUrl}\n\nTo connect to your Render backend, enter your Render URL below (e.g. https://your-backend.onrender.com):\n(Leave empty to reset to default)`,
      currentUrl
    );
    if (entered !== null) {
      VoiceKhataConfig.setApiBase(entered);
    }
  });
});
