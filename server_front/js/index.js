const annotatorForm = document.getElementById("annotator-form");
const fileInput = document.getElementById("upload-file");
const uploadZone = document.getElementById("upload-zone");
const uploadLabel = document.getElementById("upload-label");
const uploadMeta = document.getElementById("upload-meta");
const modelSelect = document.getElementById("model-select");
const confidenceRange = document.getElementById("confidence-range");
const confidenceValue = document.getElementById("confidence-value");
const fpsSelect = document.getElementById("fps-select");

let selectedFile = null;

const runConfigs = [
  {
    name: "Run 1: ByteTrack  (Baseline)",
    tracker: "bytetrack",
    enabledEl: document.getElementById("run-1-enabled"),
    stepEl: document.getElementById("run-1-step"),
  },
  {
    name: "Run 2: DeepOCSORT (Motion+)",
    tracker: "deepocsort",
    enabledEl: document.getElementById("run-2-enabled"),
    stepEl: document.getElementById("run-2-step"),
  },
  {
    name: "Run 3: StrongSORT (ReID)",
    tracker: "strongsort",
    enabledEl: document.getElementById("run-3-enabled"),
    stepEl: document.getElementById("run-3-step"),
  },
  {
    name: "Run 4: BoT-SORT   (Hybrid)",
    tracker: "botsort",
    enabledEl: document.getElementById("run-4-enabled"),
    stepEl: document.getElementById("run-4-step"),
  },
];

function showToast(message, type = "info") {
  const toastStack = document.getElementById("toast-stack");
  if (!toastStack) return;
  const node = document.createElement("div");
  node.className = `toast ${type}`;
  node.textContent = message;
  toastStack.appendChild(node);
  window.setTimeout(() => node.remove(), 3200);
}

function setSelectedFile(file) {
  selectedFile = file || null;
  if (!selectedFile) {
    uploadZone.classList.remove("has-file");
    uploadLabel.textContent = "Drag and drop your footage";
    uploadMeta.textContent = "Supports MP4, MOV, AVI, MKV";
    return;
  }

  uploadZone.classList.add("has-file");
  uploadLabel.textContent = selectedFile.name;
  uploadMeta.textContent = `${(selectedFile.size / (1024 * 1024)).toFixed(2)} MB`;
}

if (uploadZone && fileInput) {
  uploadZone.addEventListener("click", () => fileInput.click());

  fileInput.addEventListener("change", (event) => {
    const file = event.target.files?.[0] || null;
    setSelectedFile(file);
  });

  ["dragenter", "dragover"].forEach((evt) => {
    uploadZone.addEventListener(evt, (event) => {
      event.preventDefault();
      uploadZone.classList.add("dragging");
    });
  });

  ["dragleave", "drop"].forEach((evt) => {
    uploadZone.addEventListener(evt, (event) => {
      event.preventDefault();
      uploadZone.classList.remove("dragging");
    });
  });

  uploadZone.addEventListener("drop", (event) => {
    const file = event.dataTransfer?.files?.[0] || null;
    setSelectedFile(file);
  });
}

if (confidenceRange && confidenceValue) {
  const syncConfidence = () => {
    confidenceValue.textContent = Number(confidenceRange.value).toFixed(2);
  };
  confidenceRange.addEventListener("input", syncConfidence);
  syncConfidence();
}

if (annotatorForm) {
  annotatorForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!selectedFile) {
      showToast("Veuillez choisir une video", "error");
      return;
    }

    const submitBtn = document.getElementById("start-processing");
    submitBtn.disabled = true;
    submitBtn.textContent = "Starting...";

    try {
      const selectedRuns = runConfigs
        .filter((run) => run.enabledEl && run.enabledEl.checked)
        .map((run, index) => {
          const rawStep = Number.parseInt(run.stepEl?.value || "1", 10);
          const step = Number.isFinite(rawStep) && rawStep > 0 ? rawStep : 1;
          return {
            name: run.name,
            tracker: run.tracker,
            step,
            enabled: true,
            order: index + 1,
          };
        });

      if (!selectedRuns.length) {
        showToast("Activez au moins un run (Run 1..Run 4)", "error");
        submitBtn.disabled = false;
        submitBtn.textContent = "Start Processing";
        return;
      }

      const model = modelSelect?.value || "yolo11l.pt";
      const confidence = Number(confidenceRange?.value || "0.23");
      const fps = fpsSelect?.value || "Original";

      const formData = new FormData();
      formData.append("file", selectedFile);
      formData.append("model", model);
      formData.append("confidence", String(confidence));
      formData.append("fps", fps);
      formData.append("tracking_runs_json", JSON.stringify(selectedRuns));

      const res = await fetch("/annotate/upload-start", {
        method: "POST",
        body: formData,
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || `HTTP ${res.status}`);
      }

      const data = await res.json();
      window.location.href = `/front/processing?job_id=${encodeURIComponent(data.job_id)}`;
    } catch (err) {
      showToast(`Echec lancement: ${err.message}`, "error");
      submitBtn.disabled = false;
      submitBtn.textContent = "Start Processing";
    }
  });
}
