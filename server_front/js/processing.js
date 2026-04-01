const params = new URLSearchParams(window.location.search);
const jobId = params.get("job_id") || "";
const EXPORT_DIR = "C:\\dora\\output";

const statusBox = document.getElementById("job-status");
const progressFill = document.getElementById("progress-fill");
const logsBox = document.getElementById("logs");
const activeJobIdLabel = document.getElementById("active-job-id");
const activeJobStateLabel = document.getElementById("active-job-state");
const activeJobOutputLabel = document.getElementById("active-job-output");
const stepCorrect = document.getElementById("step-correct");
const startCorrectionBtn = document.getElementById("start-correction");

let pollTimer = null;
let latestSegmentLink = "";

function showToast(message, type = "info") {
  const toastStack = document.getElementById("toast-stack");
  if (!toastStack) return;
  const node = document.createElement("div");
  node.className = `toast ${type}`;
  node.textContent = message;
  toastStack.appendChild(node);
  window.setTimeout(() => node.remove(), 3200);
}

function setProgress(value) {
  const bounded = Math.max(0, Math.min(100, Number(value || 0)));
  progressFill.style.width = `${bounded}%`;
  progressFill.textContent = `${bounded.toFixed(1)}%`;
}

function setMeta(job) {
  activeJobIdLabel.textContent = job?.job_id || "-";
  activeJobStateLabel.textContent = job?.status || "-";
  activeJobOutputLabel.textContent = job?.output_dir || "-";
}

async function resolveLatestSegment(outputDir) {
  const res = await fetch("/correct/segments_auto");
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const segments = await res.json();
  if (!segments.length) return "";

  const found = segments.find((s) => (s.base_dir || "") === (outputDir || ""));
  const target = found || segments[0];
  if (!target?.base_dir) return "";
  return `/front/corrector/editor?segment=${encodeURIComponent(target.name)}&base_dir=${encodeURIComponent(target.base_dir || "")}&output_dir=${encodeURIComponent(EXPORT_DIR)}`;
}

async function pollStatus() {
  if (!jobId) {
    statusBox.textContent = "Job ID missing. Start from home page.";
    return;
  }

  if (pollTimer) clearInterval(pollTimer);

  const update = async () => {
    try {
      const res = await fetch(`/annotate/status/${encodeURIComponent(jobId)}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      statusBox.textContent = `Job ${data.job_id} - ${data.status}`;
      setProgress(data.progress);
      logsBox.textContent = (data.logs || []).join("\n") || "No logs yet.";
      setMeta(data);

      const doneStates = ["done", "error", "cancelled"];
      if (!doneStates.includes(data.status)) return;

      clearInterval(pollTimer);
      pollTimer = null;

      if (data.status === "done") {
        latestSegmentLink = await resolveLatestSegment(data.output_dir || "");
        if (latestSegmentLink) {
          startCorrectionBtn.disabled = false;
          stepCorrect.classList.add("active");
          showToast("Processing complete", "success");
        } else {
          showToast("Done, but no segment found yet", "info");
        }
      }

      if (data.status === "error") showToast("Processing failed", "error");
      if (data.status === "cancelled") showToast("Processing cancelled", "info");
    } catch (err) {
      statusBox.textContent = `Polling error: ${err.message}`;
      showToast(`Polling error: ${err.message}`, "error");
      clearInterval(pollTimer);
      pollTimer = null;
    }
  };

  await update();
  pollTimer = setInterval(update, 2000);
}

startCorrectionBtn.addEventListener("click", () => {
  if (!latestSegmentLink) return;
  window.location.href = latestSegmentLink;
});

pollStatus();
