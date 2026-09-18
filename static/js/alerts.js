/**
 * SmartMineGuard - Alerts Center & Vigilance Supervisory Actions
 */

async function acknowledgeAlert(alertId) {
  const remarks = prompt("Enter officer verification notes (optional):", "Squad acknowledged alert. Flagged for corridor verification.") || "";
  try {
    const res = await fetch(`/api/alerts/${alertId}/action`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: "ACKNOWLEDGED", remarks: remarks })
    });
    if (res.ok) {
      showToast(`Alert #${alertId} acknowledged.`, "info");
      const badge = document.getElementById(`status-badge-${alertId}`);
      if (badge) badge.textContent = "ACKNOWLEDGED";
      setTimeout(() => window.location.reload(), 600);
    }
  } catch (err) {
    showToast("Error acknowledging alert: " + err, "critical");
  }
}

async function dismissAlert(alertId) {
  const remarks = prompt(
    "⚠️ STATUTORY ACCOUNTABILITY REQUIRED:\nEnter official field verification remarks / reason for clearing/dismissing this anomaly:\n(e.g., 'Inspected physical e-way bill; scale calibration mismatch confirmed at checkpost')",
    "Physically inspected by duty squad; verified valid transit pass and legitimate transport."
  );
  if (remarks === null) return; // User pressed cancel

  try {
    const res = await fetch(`/api/alerts/${alertId}/action`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: "DISMISSED", remarks: remarks.trim() })
    });
    const data = await res.json();
    if (res.ok && data.success) {
      showToast(`Alert #${alertId} dismissed. Audit logged with officer remarks.`, "info");
      const row = document.getElementById(`alert-row-${alertId}`);
      if (row) {
        row.style.opacity = "0.3";
        row.style.pointerEvents = "none";
      }
      setTimeout(() => window.location.reload(), 800);
    } else {
      showToast("Failed to dismiss alert: " + (data.error || "Unknown error"), "critical");
    }
  } catch (err) {
    showToast("Error dismissing alert: " + err, "critical");
  }
}

async function createInvestigationFromAlert(alertId) {
  try {
    const res = await fetch(`/api/alerts/${alertId}/investigate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" }
    });
    const data = await res.json();
    if (res.ok && data.success) {
      showToast(`Elevated to Formal Case ${data.case_id}. PDF Dossier generated.`, "success");
      setTimeout(() => {
        window.location.href = `/investigations/${data.investigation_id}`;
      }, 1000);
    } else {
      showToast("Error creating case: " + (data.error || "Unknown"), "critical");
    }
  } catch (err) {
    showToast("Network error creating investigation case.", "critical");
  }
}

// Admin Supervisory Vigilance Review
async function adminReviewAlert(alertId, decision) {
  let notes = "";
  if (decision === "CONFIRM") {
    notes = prompt("Enter supervisory audit remarks (optional):", "Supervisory review confirmed. Ground officer justification accepted.") || "Supervisory review confirmed.";
  } else if (decision === "FLAG_INQUIRY") {
    notes = prompt(
      "⚖️ ORDER VIGILANCE INQUIRY:\nEnter administrative directive / grounds for investigating this officer override:",
      "Suspicious clearance of severe statutory anomaly. Formal Anti-Corruption & Vigilance Inquiry ordered."
    );
    if (notes === null) return;
  }

  try {
    const res = await fetch(`/api/alerts/${alertId}/admin_review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision: decision, notes: notes })
    });
    const data = await res.json();
    if (res.ok && data.success) {
      if (decision === "FLAG_INQUIRY" && data.investigation_id) {
        showToast(`Formal Vigilance Case ${data.case_id} established! Dossier PDF generated.`, "success");
        setTimeout(() => {
          window.location.href = `/investigations/${data.investigation_id}`;
        }, 1000);
      } else {
        showToast(data.message || "Officer action audited and confirmed.", "success");
        setTimeout(() => window.location.reload(), 800);
      }
    } else {
      showToast("Error reviewing alert: " + (data.error || "Unknown error"), "critical");
    }
  } catch (err) {
    showToast("Network error executing vigilance review: " + err, "critical");
  }
}

// Global helper for officer dashboard buttons
async function handleAlertAction(alertId, action) {
  if (action === "ACKNOWLEDGED") {
    await acknowledgeAlert(alertId);
  } else if (action === "DISMISSED") {
    await dismissAlert(alertId);
  }
}

async function elevateAlertToCase(alertId) {
  await createInvestigationFromAlert(alertId);
}
