const segmentsList = document.getElementById("segments-list");
const detailsBox = document.getElementById("details");
const logsBox = document.getElementById("corrector-logs");
const correctorState = document.getElementById("corrector-state");
const segmentsCount = document.getElementById("segments-count");
const openLatestSegmentBtn = document.getElementById("open-latest-segment");

let latestSegment = null;
let segmentsCache = [];

function editorUrl(segment, baseDir) {
  return `/front/corrector/editor?segment=${encodeURIComponent(segment)}&base_dir=${encodeURIComponent(baseDir || "")}`;
}

function setState(active) {
  if (!correctorState) {
    return;
  }
  correctorState.textContent = active ? "Actif" : "Inactif";
  correctorState.classList.toggle("active", active);
  correctorState.classList.toggle("inactive", !active);
}

function renderSegments(items) {
  segmentsCache = items || [];
  if (segmentsCount) {
    segmentsCount.textContent = `${items.length} segment${items.length > 1 ? "s" : ""}`;
    segmentsCount.classList.toggle("active", items.length > 0);
    segmentsCount.classList.toggle("inactive", items.length === 0);
  }

  if (!items.length) {
    segmentsList.innerHTML = '<p class="empty">Aucun segment detecte.</p>';
    return;
  }

  latestSegment = items[0] || null;
  if (openLatestSegmentBtn) {
    openLatestSegmentBtn.disabled = !latestSegment;
  }

  segmentsList.innerHTML = items
    .map((segment) => {
      const safeName = encodeURIComponent(segment.name);
      const safeBaseDir = encodeURIComponent(segment.base_dir || "");
      return `
        <div class="segment-item" data-name="${safeName}" data-base="${safeBaseDir}">
          <div>
            <strong>${segment.name}</strong>
            <div class="empty">${segment.status} - ${segment.base_dir || ""}</div>
          </div>
          <button class="btn mini open-editor" type="button">Open Editor</button>
        </div>
      `;
    })
    .join("");
}

async function loadSegments() {
  segmentsList.innerHTML = '<p class="empty">Chargement...</p>';
  try {
    const res = await fetch("/correct/segments_auto");
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }
    const data = await res.json();
    renderSegments(data);
  } catch (err) {
    segmentsList.innerHTML = `<p class="empty">Erreur: ${err.message}</p>`;
  }
}

async function loadDetails(segment, baseDir) {
  detailsBox.innerHTML = "Chargement des details...";

  try {
    const framesRes = await fetch(`/correct/frames?segment=${encodeURIComponent(segment)}&base_dir=${encodeURIComponent(baseDir)}`);
    const trajRes = await fetch(`/correct/trajectories?segment=${encodeURIComponent(segment)}&base_dir=${encodeURIComponent(baseDir)}`);

    if (!framesRes.ok || !trajRes.ok) {
      throw new Error(`frames:${framesRes.status} trajectories:${trajRes.status}`);
    }

    const frames = await framesRes.json();
    const traj = await trajRes.json();

    const frameCount = (frames.frames || []).length;
    const trajCount = (traj.trajectories || []).length;
    const sample = (frames.frames || []).slice(0, 5).map((f) => f.filename).join("<br>") || "N/A";

    detailsBox.innerHTML = `
      <h3>${segment}</h3>
      <p><strong>Base dir:</strong> ${baseDir}</p>
      <p><strong>Frames:</strong> ${frameCount}</p>
      <p><strong>Trajectoires:</strong> ${trajCount}</p>
      <p><strong>Echantillon images:</strong><br>${sample}</p>
    `;
  } catch (err) {
    detailsBox.innerHTML = `Erreur de chargement: ${err.message}`;
  }
}

async function loadLogs() {
  setState(true);
  try {
    const res = await fetch("/correct/logs?limit=120");
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }
    const data = await res.json();
    logsBox.textContent = (data.logs || []).join("\n") || "Aucun log corrector.";
  } catch (err) {
    logsBox.textContent = `Erreur logs: ${err.message}`;
    setState(false);
  }
}

document.getElementById("reload-segments").addEventListener("click", loadSegments);
document.getElementById("reload-logs").addEventListener("click", loadLogs);

if (openLatestSegmentBtn) {
  openLatestSegmentBtn.addEventListener("click", () => {
    if (!latestSegment) return;
    window.location.href = editorUrl(latestSegment.name, latestSegment.base_dir || "");
  });
}

segmentsList.addEventListener("click", (event) => {
  const row = event.target.closest(".segment-item");
  if (!row) {
    return;
  }

  segmentsList.querySelectorAll(".segment-item").forEach((item) => {
    item.classList.remove("active");
  });
  row.classList.add("active");

  const segment = decodeURIComponent(row.dataset.name || "");
  const baseDir = decodeURIComponent(row.dataset.base || "");

  if (!segment || !baseDir) {
    detailsBox.textContent = "Informations segment invalides.";
    return;
  }

  const editButton = event.target.closest(".open-editor");
  if (editButton) {
    const url = editorUrl(segment, baseDir);
    window.location.href = url;
    return;
  }

  loadDetails(segment, baseDir);
});

loadLogs();
loadSegments();
setInterval(loadLogs, 5000);
