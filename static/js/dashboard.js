/**
 * SmartMineGuard - Dashboard Visuals & Real-time Feeds
 */

document.addEventListener("DOMContentLoaded", () => {
  initDashboardCharts();
});

function initDashboardCharts() {
  // 1. Violation Categories Chart
  const violCtx = document.getElementById("dashboardViolationChart");
  if (violCtx) {
    new Chart(violCtx, {
      type: "bar",
      data: {
        labels: [
          "Weight Anomaly", 
          "Route Deviation", 
          "GPS Blackout", 
          "Permit Reuse", 
          "Impossible Transit", 
          "Quota Mismatch"
        ],
        datasets: [{
          label: "Active Detections",
          data: [1, 1, 1, 1, 1, 1],
          backgroundColor: [
            "#DC2626", 
            "#EA580C", 
            "#D97706", 
            "#DC2626", 
            "#EA580C", 
            "#7C3AED"
          ],
          borderRadius: 4
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          y: { beginAtZero: true, ticks: { stepSize: 1 } },
          x: { ticks: { font: { size: 10 } } }
        }
      }
    });
  }

  // 2. Risk Distribution Chart
  const riskCtx = document.getElementById("dashboardRiskChart");
  if (riskCtx) {
    new Chart(riskCtx, {
      type: "doughnut",
      data: {
        labels: ["Low (0-30)", "Medium (31-60)", "High (61-80)", "Critical (81-100)"],
        datasets: [{
          data: [4, 1, 2, 1],
          backgroundColor: ["#16A34A", "#D97706", "#EA580C", "#DC2626"],
          borderWidth: 1
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: "right", labels: { boxWidth: 12, font: { size: 11 } } }
        }
      }
    });
  }
}

// Live alert injector
if (typeof socket !== "undefined") {
  socket.on("new_alert", (alertData) => {
    const tbody = document.getElementById("dashboard-alerts-tbody");
    if (!tbody) return;

    const row = document.createElement("tr");
    row.className = "bg-red-50/70 animate-pulse";
    row.innerHTML = `
      <td class="font-mono font-bold text-red-800">${alertData.alert_code}</td>
      <td>
        <div class="font-semibold text-slate-900 font-mono">${alertData.truck}</div>
        <div class="text-[11px] text-slate-500 font-mono">Live Telemetry</div>
      </td>
      <td>
        <div class="font-semibold text-red-900">${alertData.alert_type.replace('_', ' ')}</div>
        <div class="text-[11px] text-slate-600 truncate max-w-xs">${alertData.description}</div>
      </td>
      <td><span class="font-bold text-red-700">+${alertData.risk_score}</span></td>
      <td><span class="badge badge-critical">${alertData.severity}</span></td>
      <td><span class="text-xs font-semibold text-red-800">NEW</span></td>
      <td>
        <a href="/alerts" class="btn-gov btn-gov-secondary btn-sm">Review</a>
      </td>
    `;
    tbody.prepend(row);
  });
}
