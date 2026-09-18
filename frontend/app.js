const HUARAZ = [-9.53, -77.53];

const map = L.map("map").setView(HUARAZ, 11);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  attribution: "&copy; OpenStreetMap contributors",
  maxZoom: 19,
}).addTo(map);

const drawnItems = new L.FeatureGroup().addTo(map);
const drawControl = new L.Control.Draw({
  edit: { featureGroup: drawnItems, remove: false },
  draw: {
    rectangle: { shapeOptions: { color: "#e65100" } },
    polygon: { shapeOptions: { color: "#e65100" }, allowIntersection: false },
    circle: false,
    circlemarker: false,
    marker: false,
    polyline: false,
  },
});
map.addControl(drawControl);

let currentSelection = null; // { mode: "rect"|"polygon", ...geometry }
let currentJobId = null;
let contoursLayer = null;
let demOverlay = null;

map.on(L.Draw.Event.CREATED, (e) => {
  drawnItems.clearLayers();
  drawnItems.addLayer(e.layer);

  if (e.layerType === "rectangle") {
    const b = e.layer.getBounds();
    currentSelection = {
      mode: "rect",
      bounds: {
        min_lon: b.getWest(), min_lat: b.getSouth(),
        max_lon: b.getEast(), max_lat: b.getNorth(),
      },
    };
  } else if (e.layerType === "polygon") {
    const latlngs = e.layer.getLatLngs()[0];
    const ring = latlngs.map((p) => [p.lng, p.lat]);
    ring.push(ring[0]); // cerrar el anillo
    currentSelection = { mode: "polygon", polygon: ring };
  }
});

// API Key persistida en el navegador (nunca se manda a otro lado que no sea
// nuestro propio backend, que a su vez solo la reenvía a OpenTopography).
const apiKeyInput = document.getElementById("apiKey");
apiKeyInput.value = localStorage.getItem("topofast_api_key") || "";
apiKeyInput.addEventListener("change", () => {
  localStorage.setItem("topofast_api_key", apiKeyInput.value.trim());
});

// La equidistancia de curvas es el intervalo de las maestras: el de las
// intermedias nunca puede ser mayor o igual (si no, ninguna línea cae entre
// una maestra y la siguiente) — mismo criterio que topofast_dialog.py.
const intervalInput = document.getElementById("interval");
const intermediateCheck = document.getElementById("intermediateContours");
const intermediateIntervalInput = document.getElementById("intermediateInterval");

intermediateCheck.addEventListener("change", () => {
  intermediateIntervalInput.disabled = !intermediateCheck.checked;
});

function syncIntermediateMax() {
  const base = parseFloat(intervalInput.value) || 10;
  intermediateIntervalInput.max = Math.max(base - 0.1, 0.1);
}
intervalInput.addEventListener("input", syncIntermediateMax);
syncIntermediateMax();

const statusEl = document.getElementById("status");
const generateBtn = document.getElementById("generateBtn");
const resultPanel = document.getElementById("resultPanel");
const reportText = document.getElementById("reportText");

function setStatus(msg, isError) {
  statusEl.textContent = msg || "";
  statusEl.style.color = isError ? "#b00020" : "#666";
}

function styleContourFeature(feature) {
  const isMaster = feature.properties && feature.properties.master;
  return isMaster
    ? { color: "#654321", weight: 2.2 }
    : { color: "#996633", weight: 0.8 };
}

function renderResult(data) {
  if (contoursLayer) map.removeLayer(contoursLayer);
  if (demOverlay) map.removeLayer(demOverlay);

  const bounds = L.latLngBounds(
    [data.dem_bounds.south, data.dem_bounds.west],
    [data.dem_bounds.north, data.dem_bounds.east]
  );
  demOverlay = L.imageOverlay(data.dem_png_url, bounds, { opacity: 0.85 }).addTo(map);

  contoursLayer = L.geoJSON(data.contours, {
    style: data.intermediate_contours ? styleContourFeature : () => ({ color: "#5a3a1c", weight: 1 }),
    onEachFeature: (feature, layer) => {
      if (data.intermediate_contours && feature.properties && feature.properties.master) {
        const elev = feature.properties.ELEV;
        if (elev !== undefined) layer.bindTooltip(String(Math.round(elev)), { permanent: false });
      }
    },
  }).addTo(map);

  const r = data.report;
  const lines = [
    `Modelo de elevación: ${r.demtype}`,
    `Equidistancia de curvas: ${r.interval} m`,
    "",
    `Elevación mínima: ${r.elevation_min} m`,
    `Elevación máxima: ${r.elevation_max} m`,
    `Elevación media: ${r.elevation_mean} m`,
  ];
  if (r.slope_mean_deg !== null && r.slope_mean_deg !== undefined) {
    lines.push(`Pendiente media: ${r.slope_mean_deg}°`);
  }
  lines.push("", `Área: ${r.area_ha} ha (${r.area_km2} km²)`, `Zona UTM: ${r.utm_zone} / EPSG:${r.epsg}`);
  reportText.textContent = lines.join("\n");

  document.getElementById("downloadDem").href = data.dem_tif_url;
  document.getElementById("downloadContours").href = data.contours_url;

  resultPanel.hidden = false;
  currentJobId = data.job_id;

  if (data.void_warning) setStatus(data.void_warning, false);
}

document.getElementById("generateBtn").addEventListener("click", async () => {
  if (!currentSelection) {
    setStatus("Dibujá primero un área (rectángulo o polígono) en el mapa.", true);
    return;
  }
  const apiKey = apiKeyInput.value.trim();
  if (!apiKey) {
    setStatus("Falta la API Key de OpenTopography.", true);
    return;
  }

  const body = {
    ...currentSelection,
    api_key: apiKey,
    demtype: document.getElementById("demtype").value,
    interval: parseFloat(intervalInput.value),
    intermediate_contours: intermediateCheck.checked,
    intermediate_interval: parseFloat(intermediateIntervalInput.value),
    fill_voids: document.getElementById("fillVoids").checked,
  };

  generateBtn.disabled = true;
  setStatus("Generando (bajando DEM y extrayendo curvas)... puede tardar un rato.");
  try {
    const resp = await fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || "Error desconocido.");
    renderResult(data);
    if (!data.void_warning) setStatus("Listo.");
  } catch (err) {
    setStatus(err.message, true);
  } finally {
    generateBtn.disabled = false;
  }
});

async function downloadFromPost(url, body, filename) {
  setStatus("Exportando...");
  try {
    const resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}));
      throw new Error(data.detail || "Error al exportar.");
    }
    const blob = await resp.blob();
    const objectUrl = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = objectUrl;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(objectUrl);
    setStatus("Listo.");
  } catch (err) {
    setStatus(err.message, true);
  }
}

document.getElementById("exportDxfBtn").addEventListener("click", () => {
  if (!currentJobId) return;
  const dxfMode = document.getElementById("dxfMode").value;
  downloadFromPost(
    `/api/jobs/${currentJobId}/export/dxf`, { dxf_mode: dxfMode }, "topofast_curvas.dxf"
  );
});

document.getElementById("exportLandxmlBtn").addEventListener("click", () => {
  if (!currentJobId) return;
  downloadFromPost(`/api/jobs/${currentJobId}/export/landxml`, {}, "topofast_superficie.xml");
});
