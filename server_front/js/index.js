const annotatorForm = document.getElementById("annotator-form");
const fileInput = document.getElementById("upload-file");
const uploadZone = document.getElementById("upload-zone");
const uploadLabel = document.getElementById("upload-label");
const uploadMeta = document.getElementById("upload-meta");
const model = "yolo11n.pt";
const confidence = 0.23;
const fps = "10";

let selectedFile = null;

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
      const formData = new FormData();
      formData.append("file", selectedFile);
      formData.append("model", model);
      formData.append("confidence", String(confidence));
      formData.append("fps", fps);

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
