/**
 * SmartMineGuard - Global Application & Telemetry Script
 * Strictly Vanilla JavaScript — No React / No Node.js.
 */

// Initialize Socket.IO connection
const socket = io();

socket.on("connect", () => {
  console.log("Connected to SmartMineGuard real-time telemetry stream.");
});

// Toast Notification Helper
function showToast(message, type = "info") {
  const container = document.getElementById("toast-container");
  if (!container) return;

  const toast = document.createElement("div");
  toast.className = "toast";
  if (type === "critical") {
    toast.style.backgroundColor = "#991B1B";
  } else if (type === "warning") {
    toast.style.backgroundColor = "#B45309";
  } else if (type === "success") {
    toast.style.backgroundColor = "#166534";
  }

  toast.innerHTML = `
    <span class="font-bold uppercase text-[10px] tracking-wider">[${type.toUpperCase()}]</span>
    <span>${message}</span>
  `;

  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transition = "opacity 0.3s ease";
    setTimeout(() => toast.remove(), 300);
  }, 4500);
}

// Global alert listener
socket.on("new_alert", (data) => {
  console.log("Real-time alert received:", data);
  // Background telemetry alerts are logged silently to the Alerts section & table
  // No intrusive screen popup toasts to avoid clutter and alert fatigue.
  
  // Increment pending alert badge if present
  const badge = document.getElementById("alert-counter-badge");
  if (badge) {
    let count = parseInt(badge.textContent.trim()) || 0;
    badge.textContent = count + 1;
  }
});

// SIH Demo Scenarios Trigger Function
async function triggerDemoAction(action) {
  try {
    const res = await fetch("/api/simulator/action", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: action, truck_reg: "HR26AB1234" })
    });
    const data = await res.json();
    if (res.ok) {
      if (action === "reset") {
        showToast("SIH Demo state successfully reset to initial conditions.", "success");
        setTimeout(() => window.location.reload(), 800);
      } else {
        showToast(`Simulation scenario executed: ${action.replace('_', ' ').toUpperCase()}`, "warning");
      }
    } else {
      showToast("Error executing action: " + (data.error || "Unknown error"), "critical");
    }
  } catch (err) {
    console.error("Demo action error:", err);
    showToast("Network error executing demo scenario.", "critical");
  }
}
