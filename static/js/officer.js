/**
 * SmartMineGuard - Roadside Officer QR Verification Handler
 */

let html5QrCode = null;

function startScanner() {
  const readerEl = document.getElementById("reader");
  const placeholder = document.getElementById("scanner-placeholder");
  if (placeholder) placeholder.style.display = "none";

  html5QrCode = new Html5Qrcode("reader");
  const config = { fps: 10, qrbox: { width: 220, height: 220 } };

  html5QrCode.start(
    { facingMode: "environment" },
    config,
    (decodedText) => {
      console.log("QR scanned:", decodedText);
      stopScanner();
      verifyPermitQuery(decodedText);
    },
    (errorMessage) => {
      // ignore frame-by-frame errors
    }
  ).then(() => {
    document.getElementById("btn-start-scanner").classList.add("hidden");
    document.getElementById("btn-stop-scanner").classList.remove("hidden");
  }).catch((err) => {
    alert("Unable to access camera: " + err);
    if (placeholder) placeholder.style.display = "block";
  });
}

function stopScanner() {
  if (html5QrCode) {
    html5QrCode.stop().then(() => {
      html5QrCode.clear();
      document.getElementById("btn-start-scanner").classList.remove("hidden");
      document.getElementById("btn-stop-scanner").classList.add("hidden");
      const placeholder = document.getElementById("scanner-placeholder");
      if (placeholder) placeholder.style.display = "block";
    }).catch(err => console.error("Error stopping scanner:", err));
  }
}

function handleManualVerification(e) {
  e.preventDefault();
  const query = document.getElementById("manual-permit-input").value.trim();
  if (query) {
    verifyPermitQuery(query);
  }
}

function quickVerify(permitNo) {
  document.getElementById("manual-permit-input").value = permitNo;
  verifyPermitQuery(permitNo);
}

async function verifyPermitQuery(query) {
  const card = document.getElementById("verification-result-card");
  card.classList.remove("hidden");

  try {
    const res = await fetch("/api/verify/permit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ permit_query: query })
    });
    const data = await res.json();

    if (!res.ok) {
      renderRejectedPass(query, data.message || "Permit not recognized.");
      return;
    }

    renderVerificationSuccess(data);
  } catch (err) {
    showToast("Network error verifying permit: " + err, "critical");
  }
}

let currentBeaconTruck = null;

// Initialize Socket.IO listener for targeted intercept beacon (Idea 5)
if (typeof io !== "undefined") {
  const socket = io({ transports: ["polling"] });
  socket.on("targeted_intercept_beacon", (beacon) => {
    console.log("Targeted Intercept Beacon received:", beacon);
    const box = document.getElementById("targeted-intercept-box");
    if (box) {
      box.classList.remove("hidden");
      currentBeaconTruck = beacon.registration_number;
      const regEl = document.getElementById("beacon-reg");
      if (regEl) regEl.textContent = `TRUCK: ${beacon.registration_number}`;
      const etaEl = document.getElementById("beacon-eta");
      if (etaEl) etaEl.textContent = `ETA: ${beacon.eta_minutes || 4} MINS`;
      const titleEl = document.getElementById("beacon-title");
      if (titleEl) titleEl.textContent = `UNAUTHORIZED INTER-STATE BORDER CROSSING (${beacon.registration_number})`;
      const descEl = document.getElementById("beacon-desc");
      if (descEl) {
        descEl.textContent = `Commercial tipper crossed the Rajasthan-Haryana border without an authorized Inter-State Transit Pass (ISTP). Automated GPS Sentry alert dispatched to ${beacon.checkpoint || 'Bawal Checkpoint'}.`;
      }
      box.scrollIntoView({ behavior: "smooth" });
    }
  });
}

function interceptBeaconVehicle() {
  const truckToVerify = currentBeaconTruck || "RJ14GA5521";
  document.getElementById("manual-permit-input").value = truckToVerify;
  verifyPermitQuery(truckToVerify);
}

async function triggerBorderBreachDemo(truckReg) {
  try {
    const res = await fetch("/api/gps/simulator/trigger", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action: "interstate_breach",
        truck_reg: truckReg || "RJ14GA5521"
      })
    });
    const data = await res.json();
    if (res.ok) {
      if (typeof showToast === "function") {
        showToast(`GPS Border Crossing Breach Triggered for ${truckReg}! Intercept beacon emitted.`, "critical");
      }
      const box = document.getElementById("targeted-intercept-box");
      if (box) {
        box.classList.remove("hidden");
        currentBeaconTruck = truckReg;
        const regEl = document.getElementById("beacon-reg");
        if (regEl) regEl.textContent = `TRUCK: ${truckReg}`;
        const etaEl = document.getElementById("beacon-eta");
        if (etaEl) etaEl.textContent = "ETA: 4 MINS";
        box.scrollIntoView({ behavior: "smooth" });
      }
    } else {
      alert(data.error || "Failed to trigger simulation");
    }
  } catch (e) {
    alert("Error triggering border breach: " + e);
  }
}

function renderVerificationSuccess(data) {
  const p = data.permit;
  const w = data.weighment;
  const isValid = data.is_valid;
  const isRecycled = data.is_recycled;
  const warnings = data.warning_reasons || [];

  const banner = document.getElementById("result-header-banner");
  const title = document.getElementById("result-status-title");
  const catLabel = document.getElementById("result-category-label");
  const riskBadge = document.getElementById("result-risk-badge");
  const warnContainer = document.getElementById("result-warnings-container");

  if (isRecycled) {
    // Idea 1: Dedicated Fraud Header for Recycled / Reused Passes
    banner.className = "p-3 rounded border border-red-600 bg-red-900 text-white flex items-center justify-between shadow-lg";
    title.textContent = "🚨 FRAUD ALERT: RECYCLED / REUSED e-RAWANA PASS (PARCHI GHUMANA)";
    title.className = "text-base font-extrabold text-white";
    catLabel.textContent = "MMDR Act Section 21 & Rule 104 Violation";
    riskBadge.textContent = "CRITICAL FRAUD (98/100)";
    riskBadge.className = "badge badge-critical text-xs bg-red-700 text-white border border-red-400";

    warnContainer.innerHTML = warnings.map(w => `
      <div class="p-3 bg-red-950 border-2 border-red-500 rounded text-red-100 text-xs font-bold leading-relaxed flex items-start gap-2">
        <span class="text-base text-amber-400">⛔</span>
        <div>
          <div class="text-amber-300 uppercase tracking-wider text-[11px] mb-0.5">Statutory Permit Reuse Detection</div>
          <span>${w}</span>
          <div class="text-[10px] text-red-300 mt-1">
            * Seizure recommendation: Issue vehicle confiscation notice under MMDR Act Section 21(4) and compound penalty under Rule 104.
          </div>
        </div>
      </div>
    `).join("");
    warnContainer.classList.remove("hidden");
  } else if (isValid) {
    banner.className = "p-3 rounded border border-emerald-300 bg-emerald-50 text-emerald-950 flex items-center justify-between";
    title.textContent = "STATUTORY PASS VALIDATED (LEGAL TRANSIT)";
    title.className = "text-base font-bold text-emerald-900";
    catLabel.textContent = "Statutory Clearance Granted";
    riskBadge.textContent = `RISK: ${p.current_risk_score || 10}/100`;
    riskBadge.className = "badge badge-low text-xs";
    warnContainer.classList.add("hidden");
  } else {
    banner.className = "p-3 rounded border border-red-300 bg-red-50 text-red-950 flex items-center justify-between";
    title.textContent = "SUSPICIOUS ACTIVITY — REQUIRES VERIFICATION";
    title.className = "text-base font-bold text-red-900";
    catLabel.textContent = "Potential Statutory Violation";
    riskBadge.textContent = `CRITICAL (${p.current_risk_score || 85}/100)`;
    riskBadge.className = "badge badge-critical text-xs";

    warnContainer.innerHTML = warnings.map(w => `
      <div class="p-2 bg-red-100 border border-red-300 rounded text-red-900 text-xs font-semibold flex items-center gap-1.5">
        <span>⚠</span>
        <span>${w}</span>
      </div>
    `).join("");
    warnContainer.classList.remove("hidden");
  }

  // Populate Details
  document.getElementById("res-permit-no").textContent = p.permit_number;
  document.getElementById("res-truck-reg").textContent = p.registration_number || "Unassigned Vehicle";
  document.getElementById("res-driver").textContent = `${p.driver_name || "N/A"} (${p.driver_phone || "N/A"})`;
  document.getElementById("res-mineral").textContent = p.mineral;
  document.getElementById("res-permitted-weight").textContent = `${p.permitted_weight_mt} MT`;
  
  const actualWeightEl = document.getElementById("res-actual-weight");
  if (w) {
    actualWeightEl.textContent = `${w.net_weight_mt} MT (Diff: ${w.difference_mt > 0 ? '+' : ''}${w.difference_mt} MT)`;
    actualWeightEl.className = w.is_overweight ? "font-bold text-red-700" : "font-bold text-emerald-800";
  } else {
    actualWeightEl.textContent = "Awaiting Exit Weighment";
    actualWeightEl.className = "text-slate-500 italic";
  }

  document.getElementById("res-source").textContent = `${p.mine_name || p.source_name} (${p.mine_district || 'Leasehold'})`;
  document.getElementById("res-destination").textContent = `${p.destination_name} (Buyer: ${p.buyer_name})`;
  document.getElementById("res-validity").textContent = `${p.issued_at.substring(0, 16)} to ${p.expires_at.substring(0, 16)}`;

  card.scrollIntoView({ behavior: "smooth" });
}

function renderRejectedPass(query, message) {
  const banner = document.getElementById("result-header-banner");
  const title = document.getElementById("result-status-title");
  const warnContainer = document.getElementById("result-warnings-container");

  banner.className = "p-3 rounded border border-red-600 bg-red-900 text-white flex items-center justify-between";
  title.textContent = "REJECTED: UNREGISTERED / COUNTERFEIT PASS";
  title.className = "text-base font-bold text-white";

  warnContainer.innerHTML = `
    <div class="p-2.5 bg-red-100 border border-red-400 rounded text-red-900 text-xs font-bold">
      ${message}
    </div>
  `;
  warnContainer.classList.remove("hidden");

  document.getElementById("res-permit-no").textContent = query;
  document.getElementById("res-truck-reg").textContent = "UNKNOWN";
  document.getElementById("res-driver").textContent = "N/A";
  document.getElementById("res-mineral").textContent = "UNAUTHORIZED";
  document.getElementById("res-permitted-weight").textContent = "0.0 MT";
  document.getElementById("res-actual-weight").textContent = "NOT RECOGNIZED";
  document.getElementById("res-source").textContent = "N/A";
  document.getElementById("res-destination").textContent = "N/A";
  document.getElementById("res-validity").textContent = "INVALID";
}

function recordOfficerAction(action) {
  if (action === "INTERCEPTED") {
    showToast("Interception notice recorded in enforcement registry. Alert dispatched to zone squad.", "critical");
  } else {
    showToast("Transit clearance stamped. Gate barrier unlocked.", "success");
  }
}
