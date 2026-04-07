const API_BASE = "http://127.0.0.1:8080";

const app = document.querySelector<HTMLDivElement>("#app");
if (!app) {
  throw new Error("Missing app root");
}

app.innerHTML = `
  <section style="font-family: ui-monospace, monospace; max-width: 860px; margin: 24px auto; padding: 16px;">
    <h1>FTL Offline Ground Station</h1>
    <p>Prototype operations panel (offline-first).</p>
    <button id="refresh">Refresh Health</button>
    <button id="emergency" style="margin-left: 8px;">Emergency Spray Disable</button>
    <pre id="health" style="margin-top: 12px; background: #111; color: #9ef; padding: 12px; border-radius: 8px; min-height: 140px;"></pre>
  </section>
`;

const healthPre = document.querySelector<HTMLPreElement>("#health");
const refreshBtn = document.querySelector<HTMLButtonElement>("#refresh");
const emergencyBtn = document.querySelector<HTMLButtonElement>("#emergency");

async function refreshHealth(): Promise<void> {
  if (!healthPre) return;
  try {
    const response = await fetch(`${API_BASE}/health`);
    const data = await response.json();
    healthPre.textContent = JSON.stringify(data, null, 2);
  } catch (error) {
    healthPre.textContent = `Failed to contact backend: ${String(error)}`;
  }
}

async function sendEmergencyDisable(): Promise<void> {
  try {
    await fetch(`${API_BASE}/command/emergency-spray-disable`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ issued_by: "ui", reason: "manual_test" }),
    });
    await refreshHealth();
  } catch (error) {
    if (healthPre) {
      healthPre.textContent = `Failed to send emergency command: ${String(error)}`;
    }
  }
}

refreshBtn?.addEventListener("click", refreshHealth);
emergencyBtn?.addEventListener("click", sendEmergencyDisable);

void refreshHealth();
