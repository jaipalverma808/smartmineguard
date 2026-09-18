/**
 * SmartMineGuard - Leaflet GIS Telemetry & Spatial Monitoring Engine
 * Pure Vanilla JavaScript — Leaflet.js
 * Strictly India-Only Geographic Bounds & Trip Route Visualization
 */

let map = null;
let truckMarkers = {};
let breadcrumbLayers = {};
let activeTripRouteLayers = [];
let selectedTruckReg = "HR26AB1234";

// Strict India Geographic Geofence & Bounds
const INDIA_BOUNDS = L.latLngBounds(
  L.latLng(6.5, 68.0),   // South-West (Kanyakumari / Arabian Sea)
  L.latLng(36.0, 97.5)   // North-East (Kashmir / Arunachal Pradesh)
);

// Default Transit Hub (Rajasthan / Haryana Mining Corridor: Alwar - Kotputli - Rewari - Bhiwadi)
const DEFAULT_CENTER = [27.75, 76.45];
const DEFAULT_ZOOM = 10;

document.addEventListener("DOMContentLoaded", () => {
  if (typeof INITIAL_TRUCKS !== "undefined" && INITIAL_TRUCKS.length > 0) {
    selectedTruckReg = INITIAL_TRUCKS[0].registration_number;
  }
  initMap();
  initSpatialLayers();
  initTruckMarkers();
  setupSocketListeners();
  if (selectedTruckReg) {
    focusTruck(selectedTruckReg);
  }
});

function initMap() {
  const mapEl = document.getElementById("gis-map");
  if (!mapEl) return;
  if (!mapEl.style.height && mapEl.clientHeight === 0) {
    mapEl.style.height = "560px";
  }

  map = L.map("gis-map", {
    center: DEFAULT_CENTER,
    zoom: DEFAULT_ZOOM,
    minZoom: 5,
    maxZoom: 18,
    maxBounds: INDIA_BOUNDS,
    maxBoundsViscosity: 0.9,
    zoomControl: true
  });

  // Base Cartographic Tile Layer
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &bull; SmartMineGuard GIS India'
  }).addTo(map);

  // Force Leaflet to recalculate container dimensions immediately
  setTimeout(() => {
    if (map) map.invalidateSize();
  }, 100);
  setTimeout(() => {
    if (map) map.invalidateSize();
  }, 500);
}

function initSpatialLayers() {
  // 1. Render Authorized Mines
  if (typeof INITIAL_MINES !== "undefined") {
    INITIAL_MINES.forEach(mine => {
      const mineIcon = L.divIcon({
        className: "custom-mine-pin",
        html: `<div style="background-color:#0F3826; color:white; font-size:10px; font-weight:bold; padding:3px 6px; border-radius:4px; border:1px solid #10B981; white-space:nowrap; box-shadow:0 1px 4px rgba(0,0,0,0.35);">⛏ ${mine.name.substring(0, 18)}...</div>`,
        iconAnchor: [45, 12]
      });

      L.marker([mine.latitude, mine.longitude], { icon: mineIcon })
        .addTo(map)
        .bindPopup(`
          <div class="text-xs space-y-1">
            <div class="font-bold text-slate-800 text-sm">${mine.name}</div>
            <div><strong>Code:</strong> ${mine.mine_code}</div>
            <div><strong>Mineral:</strong> ${mine.mineral} (${mine.district}, ${mine.state})</div>
            <div><strong>Annual Quota:</strong> ${mine.authorized_annual_quota_mt.toLocaleString()} MT</div>
            <div><strong>Dispatched:</strong> ${mine.current_dispatch_mt.toLocaleString()} MT</div>
            <div><strong>Stock Available:</strong> ${(mine.current_stock_mt || 3500).toLocaleString()} MT</div>
            <div><strong>Operator:</strong> ${mine.operator_name}</div>
          </div>
        `);
    });
  }

  // 2. Render Permitted NH-48 Transit Corridor Polyline (Background reference)
  const legalCorridorWaypoints = [
    [27.5624, 76.6121], // Alwar Quarry Block A
    [27.6800, 76.5600],
    [27.7500, 76.5100], // NH-48 junction
    [27.8500, 76.5800],
    [27.9800, 76.6800],
    [28.0900, 76.7700],
    [28.2100, 76.8600]  // Bhiwadi Crushing Zone
  ];

  L.polyline(legalCorridorWaypoints, {
    color: "#2563EB",
    weight: 8,
    opacity: 0.18,
    dashArray: "4, 8"
  }).addTo(map);

  L.polyline(legalCorridorWaypoints, {
    color: "#1D4ED8",
    weight: 2,
    opacity: 0.6
  }).addTo(map).bindTooltip("Permitted NH-48 Transport Corridor", { sticky: true });

  // 3. Render Geofences (e.g. Sabi Riverbed Restricted Zone)
  if (typeof INITIAL_GEOFENCES !== "undefined") {
    INITIAL_GEOFENCES.forEach(gf => {
      try {
        const coords = JSON.parse(gf.polygon_coordinates_json);
        const isRestricted = gf.zone_type === "RESTRICTED_RIVERBED" || gf.severity === "CRITICAL";
        
        L.polygon(coords, {
          color: isRestricted ? "#DC2626" : "#D97706",
          fillColor: isRestricted ? "#F87171" : "#FBBF24",
          fillOpacity: 0.3,
          weight: 2,
          dashArray: "5, 5"
        }).addTo(map).bindPopup(`
          <div class="text-xs">
            <strong class="text-red-700 font-bold">${gf.name}</strong><br/>
            <span>Type: ${gf.zone_type}</span><br/>
            <span>Severity: ${gf.severity}</span>
          </div>
        `);
      } catch (e) {
        console.error("Geofence parse error:", e);
      }
    });
  }
}

function getMarkerColor(riskScore) {
  if (riskScore >= 80) return "#DC2626"; // Critical Red
  if (riskScore >= 60) return "#EA580C"; // High Orange
  if (riskScore >= 30) return "#D97706"; // Medium Amber
  return "#16A34A";                     // Low Green
}

function initTruckMarkers() {
  if (typeof INITIAL_TRUCKS !== "undefined") {
    INITIAL_TRUCKS.forEach(truck => {
      if (truck.current_lat && truck.current_lng) {
        createOrUpdateTruckMarker(truck);
      }
    });
  }
}

function createOrUpdateTruckMarker(truck) {
  const reg = truck.registration_number;
  const lat = truck.latitude || truck.current_lat;
  const lng = truck.longitude || truck.current_lng;
  const risk = truck.risk_score !== undefined ? truck.risk_score : (truck.current_risk_score || 0);
  const color = getMarkerColor(risk);

  const customIcon = L.divIcon({
    className: "custom-truck-pin",
    html: `
      <div style="background-color:${color}; color:white; font-size:10px; font-weight:bold; padding:2px 6px; border-radius:4px; border:1px solid white; box-shadow:0 2px 5px rgba(0,0,0,0.45); display:inline-flex; align-items:center; gap:3px;">
        <span>🚚</span>
        <span>${reg}</span>
      </div>
    `,
    iconAnchor: [35, 14]
  });

  if (truckMarkers[reg]) {
    truckMarkers[reg].setLatLng([lat, lng]);
    truckMarkers[reg].setIcon(customIcon);
  } else {
    const marker = L.marker([lat, lng], { icon: customIcon }).addTo(map);
    marker.on("click", () => focusTruck(reg));
    truckMarkers[reg] = marker;
  }

  // Update breadcrumbs trail
  if (!breadcrumbLayers[reg]) {
    breadcrumbLayers[reg] = L.polyline([], {
      color: color,
      weight: 2,
      opacity: 0.5,
      dashArray: "2, 4"
    }).addTo(map);
  }
  breadcrumbLayers[reg].addLatLng([lat, lng]);
}

function setupSocketListeners() {
  if (typeof socket === "undefined") return;

  socket.on("gps_batch_update", (data) => {
    if (data.trucks && Array.isArray(data.trucks)) {
      data.trucks.forEach(t => {
        createOrUpdateTruckMarker(t);

        // If currently focused truck, update telemetry
        if (t.registration_number === selectedTruckReg) {
          // Refresh route telemetry
          focusTruck(selectedTruckReg, false);
        }
      });
    }
  });
}

/**
 * Section 7: Select Truck -> Show its actual trip route
 * 1. Locate truck on map & zoom
 * 2. Draw route from Source Mine -> Weighbridge -> Checkpoints -> Destination
 * 3. Draw travelled route in solid vivid style
 * 4. Draw remaining planned route in dashed blue style
 * 5. Render key route pins (Mine, Weighbridge, Checkpoints, Destination)
 * 6. Populate all 14 trip information fields in the inspector drawer
 */
async function focusTruck(reg, shouldPan = true) {
  selectedTruckReg = reg;
  
  // Highlight in sidebar roster
  document.querySelectorAll(".truck-list-item").forEach(el => el.classList.remove("selected", "border-emerald-700", "bg-emerald-50"));
  const item = document.getElementById(`roster-item-${reg}`);
  if (item) {
    item.classList.add("selected", "border-emerald-700", "bg-emerald-50");
    item.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  // Find truck object from initial dataset
  let truckObj = null;
  if (typeof INITIAL_TRUCKS !== "undefined") {
    truckObj = INITIAL_TRUCKS.find(x => x.registration_number === reg);
  }

  const truckId = truckObj ? truckObj.id : (truckMarkers[reg] ? 1 : null);
  if (!truckId) return;

  try {
    const res = await fetch(`/api/trucks/${truckId}/route`);
    if (!res.ok) {
      console.warn(`Route API returned ${res.status}`);
      return;
    }
    const data = await res.json();
    if (!data.success) return;

    // Pan map to current truck position
    if (shouldPan && data.truck && data.truck.current_lat && data.truck.current_lng) {
      map.flyTo([data.truck.current_lat, data.truck.current_lng], 12, { duration: 0.8 });
    }

    // Clear existing trip route layers
    activeTripRouteLayers.forEach(l => map.removeLayer(l));
    activeTripRouteLayers = [];

    // 1. Draw Authorized Corridor (Distinct visual treatment: Translucent thick blue corridor with dashed centerline)
    const authRoute = data.authorized_route || data.full_corridor;
    if (authRoute && authRoute.length > 1) {
      const authCorridorBg = L.polyline(authRoute, {
        color: "#2563EB",
        weight: 9,
        opacity: 0.22,
        lineCap: "round"
      }).addTo(map);
      activeTripRouteLayers.push(authCorridorBg);

      const authCorridorLine = L.polyline(authRoute, {
        color: "#1D4ED8",
        weight: 2.5,
        opacity: 0.75,
        dashArray: "6, 8"
      }).addTo(map);
      authCorridorLine.bindTooltip("<b>AUTHORIZED STATUTORY ROUTE CORRIDOR</b>", { sticky: true });
      activeTripRouteLayers.push(authCorridorLine);
    }

    // 2. Draw Actual Historical GPS Route Followed (Solid Vibrant line with GPS Breadcrumbs)
    const actualRoute = data.actual_route || data.travelled_route;
    if (actualRoute && actualRoute.length > 1) {
      const isDev = data.is_deviated || (data.truck && data.truck.current_risk_score >= 70);
      const actualColor = isDev ? "#DC2626" : "#059669";
      const actualPoly = L.polyline(actualRoute, {
        color: actualColor,
        weight: 5,
        opacity: 0.95,
        lineCap: "round",
        lineJoin: "round"
      }).addTo(map);
      actualPoly.bindTooltip(`<b>ACTUAL GPS ROUTE FOLLOWED</b> (${data.metrics.distance_travelled_km} km travelled)`, { sticky: true });
      activeTripRouteLayers.push(actualPoly);

      // Add GPS Breadcrumb Milestone Pins along actual route
      actualRoute.forEach((pt, idx) => {
        if (idx === 0 || idx === actualRoute.length - 1 || idx % 2 === 0) {
          const crumb = L.circleMarker(pt, {
            radius: 3.5,
            color: actualColor,
            fillColor: "#FFFFFF",
            fillOpacity: 0.9,
            weight: 1.5
          }).addTo(map);
          crumb.bindTooltip(`Breadcrumb #${idx + 1} &bull; Lat ${pt[0].toFixed(4)}, Lng ${pt[1].toFixed(4)}`);
          activeTripRouteLayers.push(crumb);
        }
      });
    }

    // 3. Draw Route Deviation if active (ADMIN / OFFICER only)
    if (data.is_deviated && data.deviation_route && data.deviation_route.length > 0) {
      const devPoly = L.polyline(data.deviation_route, {
        color: "#DC2626",     // Red
        weight: 4.5,
        opacity: 0.95,
        dashArray: "4, 6"
      }).addTo(map);
      devPoly.bindTooltip("<b>ALERT: UNPERMITTED CORRIDOR DEVIATION DETECTED</b>", { sticky: true });
      activeTripRouteLayers.push(devPoly);
    }


    // 4. Pin: Source Mine
    if (data.source_mine && data.source_mine.lat && data.source_mine.lng) {
      const minePin = L.divIcon({
        className: "custom-route-pin",
        html: `<div style="background-color:#064E3B; color:#A7F3D0; font-size:10px; font-weight:bold; padding:2px 6px; border-radius:4px; border:1px solid #10B981; white-space:nowrap; box-shadow:0 1px 4px rgba(0,0,0,0.4);">⛏ Origin: ${data.source_mine.name.substring(0, 16)}</div>`,
        iconAnchor: [45, 12]
      });
      const mMarker = L.marker([data.source_mine.lat, data.source_mine.lng], { icon: minePin }).addTo(map);
      activeTripRouteLayers.push(mMarker);
    }

    // 5. Pin: Weighbridge
    if (data.weighbridge && data.weighbridge.lat && data.weighbridge.lng) {
      const wbPin = L.divIcon({
        className: "custom-route-pin",
        html: `<div style="background-color:#4C1D95; color:#DDD6FE; font-size:10px; font-weight:bold; padding:2px 6px; border-radius:4px; border:1px solid #8B5CF6; white-space:nowrap; box-shadow:0 1px 4px rgba(0,0,0,0.4);">⚖ Scale: ${data.weighbridge.name.substring(0, 16)}</div>`,
        iconAnchor: [45, 12]
      });
      const wbMarker = L.marker([data.weighbridge.lat, data.weighbridge.lng], { icon: wbPin }).addTo(map);
      activeTripRouteLayers.push(wbMarker);
    }

    // 6. Pins: Checkpoints
    if (data.checkpoints && Array.isArray(data.checkpoints)) {
      data.checkpoints.forEach(cp => {
        const cpPin = L.divIcon({
          className: "custom-route-pin",
          html: `<div style="background-color:#78350F; color:#FDE68A; font-size:10px; font-weight:bold; padding:2px 6px; border-radius:4px; border:1px solid #F59E0B; white-space:nowrap; box-shadow:0 1px 4px rgba(0,0,0,0.4);">🛑 ${cp.name.substring(0, 16)}</div>`,
          iconAnchor: [45, 12]
        });
        const cpMarker = L.marker([cp.lat, cp.lng], { icon: cpPin }).addTo(map);
        activeTripRouteLayers.push(cpMarker);
      });
    }

    // 7. Pin: Destination
    if (data.destination && data.destination.lat && data.destination.lng) {
      const destPin = L.divIcon({
        className: "custom-route-pin",
        html: `<div style="background-color:#1E293B; color:#E2E8F0; font-size:10px; font-weight:bold; padding:2px 6px; border-radius:4px; border:1px solid #64748B; white-space:nowrap; box-shadow:0 1px 4px rgba(0,0,0,0.4);">🏭 Dest: ${data.destination.name.substring(0, 16)}</div>`,
        iconAnchor: [45, 12]
      });
      const dMarker = L.marker([data.destination.lat, data.destination.lng], { icon: destPin }).addTo(map);
      activeTripRouteLayers.push(dMarker);
    }

    // 8. Update Inspector Drawer (All 14 metrics)
    updateInspectorWithRouteData(data);

  } catch (err) {
    console.error("Error fetching truck route telemetry:", err);
  }
}

function updateInspectorWithRouteData(data) {
  const m = data.metrics;
  const t = data.truck;

  // Header & IDs
  document.getElementById("inspector-reg").textContent = m.truck_number;
  document.getElementById("inspector-trip-id").textContent = m.trip_id;
  document.getElementById("inspector-permit").textContent = m.permit_number;
  document.getElementById("inspector-mineral").textContent = m.mineral;

  // Material MTs
  document.getElementById("inspector-permitted").textContent = `${m.permitted_quantity_mt.toFixed(1)} MT`;
  document.getElementById("inspector-actual").textContent = `${m.actual_quantity_mt.toFixed(1)} MT`;

  const excessEl = document.getElementById("inspector-excess");
  if (m.excess_quantity_mt > 0) {
    excessEl.textContent = `+${m.excess_quantity_mt.toFixed(1)} MT`;
    excessEl.className = "font-mono font-bold text-red-700";
  } else {
    excessEl.textContent = "0.0 MT";
    excessEl.className = "font-mono text-slate-500";
  }

  // Origin & Destination
  document.getElementById("inspector-source").textContent = m.source;
  document.getElementById("inspector-destination").textContent = m.destination;

  // Timing & Distance
  document.getElementById("inspector-start").textContent = m.trip_start;
  document.getElementById("inspector-arrival").textContent = m.expected_arrival;
  document.getElementById("inspector-dist-total").textContent = `${m.route_distance_km.toFixed(1)} km`;
  document.getElementById("inspector-dist-travelled").textContent = `${m.distance_travelled_km.toFixed(1)} km`;
  document.getElementById("inspector-dist-remaining").textContent = `${m.remaining_distance_km.toFixed(1)} km`;

  // Status & Risk Badges
  const riskBadge = document.getElementById("inspector-risk-badge");
  const statusEl = document.getElementById("inspector-status");

  const riskScore = t.current_risk_score || 0;
  riskBadge.textContent = `${t.current_risk_level || 'LOW'} (${riskScore}/100)`;
  if (riskScore >= 80) {
    riskBadge.className = "badge badge-critical text-[10px]";
  } else if (riskScore >= 60) {
    riskBadge.className = "badge badge-high text-[10px]";
  } else if (riskScore >= 30) {
    riskBadge.className = "badge badge-medium text-[10px]";
  } else {
    riskBadge.className = "badge badge-low text-[10px]";
  }

  if (data.is_deviated) {
    statusEl.textContent = "CORRIDOR DEVIATED • UNDER INVESTIGATION";
    statusEl.className = "font-bold text-red-700";
  } else if (m.excess_quantity_mt > 0) {
    statusEl.textContent = "OVERWEIGHT LOAD EXCEPTION DETECTED";
    statusEl.className = "font-bold text-red-700";
  } else {
    statusEl.textContent = `IN TRANSIT • LEGAL ROUTE COMPLIANT`;
    statusEl.className = "font-bold text-emerald-800";
  }

  // Populate Round Status
  if (data.round_metrics) {
    const rm = data.round_metrics;
    const roundEl = document.getElementById("inspector-round");
    if (roundEl) {
      roundEl.textContent = `Trip #${rm.current_round} (${rm.completed_rounds} trips today - Unrestricted)`;
    }
  }
  if (data.cumulative_material && data.cumulative_material.today) {
    const dispEl = document.getElementById("inspector-today-dispatched");
    if (dispEl) {
      dispEl.textContent = `${data.cumulative_material.today.material_mt} MT (${data.cumulative_material.today.trips} trips)`;
    }
  }

  // Populate Chronological Trip Timeline
  const timelineEl = document.getElementById("inspector-timeline");
  if (timelineEl) {
    if (data.timeline && data.timeline.length > 0) {
      timelineEl.innerHTML = data.timeline.map(e => `
        <div class="flex items-start gap-1.5 border-l-2 border-emerald-600 pl-1.5 py-0.5">
          <span class="font-mono text-[9px] text-slate-400 whitespace-nowrap">${e.timestamp ? (e.timestamp.length > 10 ? e.timestamp.substring(11, 16) : e.timestamp) : ''}</span>
          <div>
            <strong class="text-slate-800 text-[10px] block leading-tight">${e.title}</strong>
            <span class="text-slate-500 text-[9px] leading-tight block">${e.description || ''}</span>
          </div>
        </div>
      `).join("");
    } else {
      timelineEl.innerHTML = '<span class="text-slate-400 italic">No timeline events recorded yet.</span>';
    }
  }
}

function resetMapView() {
  map.setView(DEFAULT_CENTER, DEFAULT_ZOOM);
}

