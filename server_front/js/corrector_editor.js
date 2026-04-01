const params = new URLSearchParams(window.location.search);
const segment = params.get("segment") || "";
const baseDir = params.get("base_dir") || "";
const outputDir = params.get("output_dir") || "C:\\dora\\output";

const CLASSES = ["person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck"];

const canvas = document.getElementById("editor-canvas");
const ctx = canvas.getContext("2d");
const globalIdsBox = document.getElementById("global-ids");
const localIdsBox = document.getElementById("local-ids");
const missingIdsBox = document.getElementById("missing-ids");
const menu = document.getElementById("editor-menu");
const modal = document.getElementById("editor-modal");
const modalTitle = document.getElementById("editor-modal-title");
const modalBody = document.getElementById("editor-modal-body");
const modalClose = document.getElementById("editor-modal-close");
const backLink = document.getElementById("editor-back-link");
const toastStack = document.getElementById("toast-stack");

const frameLabel = document.getElementById("editor-frame");
const segmentLabel = document.getElementById("editor-segment");
const modeLabel = document.getElementById("editor-mode");
const dirtyLabel = document.getElementById("editor-dirty");

const firstBtn = document.getElementById("first-frame");
const prevBtn = document.getElementById("prev-frame");
const nextBtn = document.getElementById("next-frame");
const lastBtn = document.getElementById("last-frame");
const rejectBtn = document.getElementById("reject-frame");
const acceptBtn = document.getElementById("accept-frame");
const undoBtn = document.getElementById("undo-frame");
const saveBtn = document.getElementById("save-all");

const state = {
  frames: [],
  imgDir: "",
  frameIndex: 0,
  boxesByFrame: {},
  modifiedFrames: new Set(),
  selectedId: null,
  drawing: null,
  dragging: null,
  mode: "select",
  undo: [],
  image: null,
  imageLoaded: false,
};

function apiUrl(path) {
  return path;
}

function showToast(message, type = "info") {
  if (!toastStack) return;
  const node = document.createElement("div");
  node.className = `toast ${type}`;
  node.textContent = message;
  toastStack.appendChild(node);
  window.setTimeout(() => node.remove(), 3200);
}

async function apiJson(path, options) {
  const res = await fetch(apiUrl(path), options);
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res.json();
}

function currentFrame() {
  return state.frames[state.frameIndex] || null;
}

function currentFrameName() {
  const frame = currentFrame();
  return frame ? frame.filename : "";
}

function currentBoxes() {
  return state.boxesByFrame[currentFrameName()] || [];
}

function prevBoxes() {
  if (state.frameIndex === 0) {
    return [];
  }
  const prev = state.frames[state.frameIndex - 1];
  return state.boxesByFrame[prev.filename] || [];
}

function setDirtyFlag() {
  const active = state.modifiedFrames.size > 0;
  dirtyLabel.textContent = active ? `${state.modifiedFrames.size} modified` : "No changes";
  dirtyLabel.classList.toggle("active", active);
  dirtyLabel.classList.toggle("inactive", !active);
}

function setMode(modeText) {
  modeLabel.textContent = modeText;
  const active = modeText.toLowerCase() !== "select";
  modeLabel.classList.toggle("active", active);
  modeLabel.classList.toggle("inactive", !active);
}

function pushUndo() {
  state.undo.push({ frame: currentFrameName(), boxes: structuredClone(currentBoxes()) });
  if (state.undo.length > 200) {
    state.undo.shift();
  }
}

function applyCurrentBoxes(boxes) {
  const frame = currentFrameName();
  if (!frame) return;
  state.boxesByFrame[frame] = boxes;
  state.modifiedFrames.add(frame);
  setDirtyFlag();
  renderLists();
  drawCanvas();
}

function allGlobalIds() {
  const map = new Map();
  Object.values(state.boxesByFrame).forEach((boxes) => {
    boxes.forEach((b) => {
      if (!map.has(b.id)) {
        map.set(b.id, b.class_name);
      }
    });
  });
  return Array.from(map.entries()).map(([id, class_name]) => ({ id, class_name }));
}

function openModal(title, bodyHtml) {
  modalTitle.textContent = title;
  modalBody.innerHTML = bodyHtml;
  modal.classList.remove("hidden");
}

function closeModal() {
  modal.classList.add("hidden");
  modalBody.innerHTML = "";
}

function confirmModal(title, message, confirmText = "Confirmer") {
  return new Promise((resolve) => {
    openModal(
      title,
      `
      <p class="empty">${message}</p>
      <div class="editor-modal-actions">
        <button class="btn subtle" data-confirm="no" type="button">Annuler</button>
        <button class="btn primary" data-confirm="yes" type="button">${confirmText}</button>
      </div>
    `
    );

    const onClick = (event) => {
      const btn = event.target.closest("[data-confirm]");
      if (!btn) return;
      const ok = btn.dataset.confirm === "yes";
      cleanup();
      resolve(ok);
    };

    const onClose = () => {
      cleanup();
      resolve(false);
    };

    function cleanup() {
      modalBody.removeEventListener("click", onClick);
      modalClose.removeEventListener("click", onClose);
      modal.removeEventListener("click", outsideClick);
      closeModal();
    }

    function outsideClick(event) {
      if (event.target === modal) onClose();
    }

    modalBody.addEventListener("click", onClick);
    modalClose.addEventListener("click", onClose);
    modal.addEventListener("click", outsideClick);
  });
}

function pickClassModal(defaultClass) {
  return new Promise((resolve) => {
    const safeDefault = defaultClass || CLASSES[0];
    const items = CLASSES.map((cls) => {
      const active = cls === safeDefault ? " editor-modal-item-active" : "";
      return `<button class="editor-modal-item${active}" data-class="${cls}" type="button">${cls}</button>`;
    }).join("");

    openModal("Choisir classe", `<div class="editor-modal-list">${items}</div>`);

    const onClick = (event) => {
      const btn = event.target.closest("[data-class]");
      if (!btn) return;
      const value = btn.dataset.class || "";
      cleanup();
      resolve(value || null);
    };

    const onClose = () => {
      cleanup();
      resolve(null);
    };

    function cleanup() {
      modalBody.removeEventListener("click", onClick);
      modalClose.removeEventListener("click", onClose);
      modal.removeEventListener("click", outsideClick);
      closeModal();
    }

    function outsideClick(event) {
      if (event.target === modal) {
        onClose();
      }
    }

    modalBody.addEventListener("click", onClick);
    modalClose.addEventListener("click", onClose);
    modal.addEventListener("click", outsideClick);
  });
}

function pickMergeTargetModal(sourceId) {
  return new Promise((resolve) => {
    const options = allGlobalIds().filter((g) => g.id !== sourceId);
    if (!options.length) {
      resolve(null);
      return;
    }

    const items = options
      .map((g) => `<button class="editor-modal-item" data-target="${g.id}" type="button"><strong>#${g.id}</strong> - ${g.class_name}</button>`)
      .join("");

    openModal(`Fusionner ID ${sourceId} vers`, `<div class="editor-modal-list">${items}</div>`);

    const onClick = (event) => {
      const btn = event.target.closest("[data-target]");
      if (!btn) return;
      const targetId = Number(btn.dataset.target || "");
      cleanup();
      resolve(Number.isFinite(targetId) ? targetId : null);
    };

    const onClose = () => {
      cleanup();
      resolve(null);
    };

    function cleanup() {
      modalBody.removeEventListener("click", onClick);
      modalClose.removeEventListener("click", onClose);
      modal.removeEventListener("click", outsideClick);
      closeModal();
    }

    function outsideClick(event) {
      if (event.target === modal) {
        onClose();
      }
    }

    modalBody.addEventListener("click", onClick);
    modalClose.addEventListener("click", onClose);
    modal.addEventListener("click", outsideClick);
  });
}

function pickManageActionModal(id) {
  return new Promise((resolve) => {
    openModal(
      `Manage ID ${id}`,
      `
      <div class="editor-modal-list">
        <button class="editor-modal-item" data-manage="merge" type="button">Merge into another ID</button>
        <button class="editor-modal-item" data-manage="rename" type="button">Create new ID (rename global)</button>
      </div>
      `
    );

    const onClick = (event) => {
      const btn = event.target.closest("[data-manage]");
      if (!btn) return;
      const value = btn.dataset.manage || "";
      cleanup();
      resolve(value || null);
    };

    const onClose = () => {
      cleanup();
      resolve(null);
    };

    function cleanup() {
      modalBody.removeEventListener("click", onClick);
      modalClose.removeEventListener("click", onClose);
      modal.removeEventListener("click", outsideClick);
      closeModal();
    }

    function outsideClick(event) {
      if (event.target === modal) onClose();
    }

    modalBody.addEventListener("click", onClick);
    modalClose.addEventListener("click", onClose);
    modal.addEventListener("click", outsideClick);
  });
}

function maxId() {
  const ids = allGlobalIds().map((g) => g.id);
  return ids.length ? Math.max(...ids) : 0;
}

function getImageViewport() {
  if (!state.image || !state.imageLoaded) {
    return null;
  }

  const imageWidth = state.image.naturalWidth || state.image.width;
  const imageHeight = state.image.naturalHeight || state.image.height;
  if (!imageWidth || !imageHeight) {
    return null;
  }

  const scale = Math.min(canvas.width / imageWidth, canvas.height / imageHeight);
  const drawWidth = imageWidth * scale;
  const drawHeight = imageHeight * scale;
  const offsetX = (canvas.width - drawWidth) / 2;
  const offsetY = (canvas.height - drawHeight) / 2;

  return { imageWidth, imageHeight, scale, drawWidth, drawHeight, offsetX, offsetY };
}

function canvasToImage(pos, clampToImage = false) {
  const vp = getImageViewport();
  if (!vp) return null;

  let x = (pos.x - vp.offsetX) / vp.scale;
  let y = (pos.y - vp.offsetY) / vp.scale;

  if (clampToImage) {
    x = Math.max(0, Math.min(vp.imageWidth, x));
    y = Math.max(0, Math.min(vp.imageHeight, y));
    return { x, y };
  }

  if (x < 0 || y < 0 || x > vp.imageWidth || y > vp.imageHeight) {
    return null;
  }

  return { x, y };
}

function imageRectToCanvas(rect) {
  const vp = getImageViewport();
  if (!vp) return null;

  return {
    x: vp.offsetX + rect.x * vp.scale,
    y: vp.offsetY + rect.y * vp.scale,
    w: rect.w * vp.scale,
    h: rect.h * vp.scale,
  };
}

function getCanvasPos(event) {
  const rect = canvas.getBoundingClientRect();
  return {
    x: ((event.clientX - rect.left) / rect.width) * canvas.width,
    y: ((event.clientY - rect.top) / rect.height) * canvas.height,
  };
}

function hitTest(x, y) {
  const boxes = currentBoxes();
  for (let i = boxes.length - 1; i >= 0; i -= 1) {
    const b = boxes[i];
    if (x >= b.x && x <= b.x + b.w && y >= b.y && y <= b.y + b.h) {
      return b;
    }
  }
  return null;
}

function loadCurrentImage() {
  const frame = currentFrameName();
  if (!frame) return;
  const img = new Image();
  img.crossOrigin = "anonymous";
  img.onload = () => {
    state.image = img;
    state.imageLoaded = true;
    drawCanvas();
  };
  img.onerror = () => {
    state.imageLoaded = false;
    drawCanvas();
  };
  img.src = `/correct/frame_image?img_dir=${encodeURIComponent(state.imgDir)}&filename=${encodeURIComponent(frame)}`;
}

function drawCanvas() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#000000";
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  const vp = getImageViewport();
  if (state.image && state.imageLoaded && vp) {
    ctx.drawImage(state.image, vp.offsetX, vp.offsetY, vp.drawWidth, vp.drawHeight);
  }

  prevBoxes().forEach((b) => {
    const c = imageRectToCanvas(b);
    if (!c) return;
    ctx.strokeStyle = "rgba(245, 158, 11, 0.55)";
    ctx.lineWidth = 2;
    ctx.setLineDash([4, 3]);
    ctx.strokeRect(c.x, c.y, c.w, c.h);
    ctx.setLineDash([]);
    ctx.fillStyle = "rgba(245, 158, 11, 0.75)";
    ctx.font = "11px Segoe UI";
    ctx.fillText(`${b.class_name} ${b.id}`, c.x + 3, c.y - 4);
  });

  currentBoxes().forEach((b) => {
    const c = imageRectToCanvas(b);
    if (!c) return;
    const selected = b.id === state.selectedId;
    ctx.strokeStyle = selected ? "#ffe066" : "#00e5ff";
    ctx.lineWidth = 2;
    if (selected) {
      ctx.shadowColor = "rgba(255, 224, 102, 0.55)";
      ctx.shadowBlur = 8;
    }
    ctx.strokeRect(c.x, c.y, c.w, c.h);
    ctx.shadowBlur = 0;

    ctx.fillStyle = selected ? "rgba(255, 224, 102, 0.88)" : "rgba(0, 229, 255, 0.88)";
    const txt = `${b.class_name} ${b.id}`;
    ctx.font = "11px Segoe UI";
    const tw = ctx.measureText(txt).width;
    ctx.fillRect(c.x, c.y - 16, tw + 7, 16);
    ctx.fillStyle = "#eaf4ff";
    ctx.fillText(txt, c.x + 3, c.y - 4);
  });

  if (state.drawing) {
    const d = state.drawing;
    const c = imageRectToCanvas(d);
    if (!c) return;
    ctx.strokeStyle = "#00e5ff";
    ctx.setLineDash([6, 3]);
    ctx.strokeRect(c.x, c.y, c.w, c.h);
    ctx.setLineDash([]);
  }
}

function renderLists() {
  const globals = allGlobalIds();
  const locals = currentBoxes();
  const prev = prevBoxes();

  globalIdsBox.innerHTML = globals
    .map((g) => `<button class="id-row ${g.id === state.selectedId ? "active" : ""}" data-id="${g.id}"><span>#${g.id}</span><span>${g.class_name}</span></button>`)
    .join("") || '<p class="empty">Aucun ID</p>';

  localIdsBox.innerHTML = locals
    .map((l) => `<button class="id-row ${l.id === state.selectedId ? "active" : ""}" data-id="${l.id}"><span>#${l.id}</span><span>${l.class_name}</span></button>`)
    .join("") || '<p class="empty">Aucun ID local</p>';

  const localSet = new Set(locals.map((l) => l.id));
  const missing = prev.filter((p) => !localSet.has(p.id));
  missingIdsBox.innerHTML = missing
    .map((m) => `<button class="id-row warn" data-missing="${m.id}"><span>#${m.id}</span><span>${m.class_name}</span></button>`)
    .join("") || '<p class="empty">Aucun missing ID</p>';

  const frame = currentFrame();
  frameLabel.textContent = frame
    ? `Frame: ${frame.index} (${state.frameIndex + 1}/${state.frames.length})`
    : "Frame: -";
}

function openContextMenu(x, y, id) {
  menu.innerHTML = `
    <button data-action="pullback">PULLBACK (Copy to Previous Frame)</button>
    <button data-action="manage">MANAGE / MERGE...</button>
    <button data-action="change_class">CHANGE CLASS</button>
    <hr />
    <button data-action="delete_frame">DELETE (Frame)</button>
    <button class="danger" data-action="delete_global">DELETE (Global)</button>
    <hr />
    <button class="accent" data-action="stationary">STATIONARY (Apply to All Frames)</button>
    <button class="accent" data-action="mark_exited">MARK AS EXITED</button>
  `;
  menu.dataset.id = String(id);
  menu.style.left = `${x}px`;
  menu.style.top = `${y}px`;
  menu.classList.remove("hidden");
}

function closeContextMenu() {
  menu.classList.add("hidden");
  menu.innerHTML = "";
  delete menu.dataset.id;
}

async function deleteId(id, scope) {
  const ok = await confirmModal("Suppression", `Supprimer ID ${id} (${scope}) ?`, "Supprimer");
  if (!ok) return;

  pushUndo();
  if (scope === "frame") {
    applyCurrentBoxes(currentBoxes().filter((b) => b.id !== id));
  } else {
    Object.keys(state.boxesByFrame).forEach((k) => {
      state.boxesByFrame[k] = (state.boxesByFrame[k] || []).filter((b) => b.id !== id);
      state.modifiedFrames.add(k);
    });
    setDirtyFlag();
    renderLists();
    drawCanvas();
  }

  await apiJson("/correct/delete_id", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      segment,
      frame: currentFrameName(),
      id,
      scope,
      base_dir: baseDir,
      output_dir: outputDir || undefined,
    }),
  });
  showToast(`ID ${id} supprime (${scope})`, "success");
}

async function changeClass(id) {
  const before = allGlobalIds().find((g) => g.id === id);
  const cls = await pickClassModal(before ? before.class_name : CLASSES[0]);
  if (!cls) return;

  pushUndo();
  Object.keys(state.boxesByFrame).forEach((k) => {
    state.boxesByFrame[k] = (state.boxesByFrame[k] || []).map((b) => (b.id === id ? { ...b, class_name: cls } : b));
    state.modifiedFrames.add(k);
  });
  setDirtyFlag();
  renderLists();
  drawCanvas();

  await apiJson("/correct/change_class", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ segment, id, new_class: cls, base_dir: baseDir, output_dir: outputDir || undefined }),
  });
  showToast(`Classe de ID ${id} mise a jour`, "success");
}

async function mergeIds(sourceId) {
  const targetId = await pickMergeTargetModal(sourceId);
  if (!Number.isFinite(targetId) || targetId === sourceId) return;

  pushUndo();
  Object.keys(state.boxesByFrame).forEach((k) => {
    state.boxesByFrame[k] = (state.boxesByFrame[k] || []).map((b) => (b.id === sourceId ? { ...b, id: targetId } : b));
    state.modifiedFrames.add(k);
  });
  setDirtyFlag();
  renderLists();
  drawCanvas();

  await apiJson("/correct/merge_ids", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      segment,
      source_id: sourceId,
      target_id: targetId,
      base_dir: baseDir,
      output_dir: outputDir || undefined,
    }),
  });
  showToast(`ID ${sourceId} fusionne vers ${targetId}`, "success");
}

async function manageId(id) {
  const action = await pickManageActionModal(id);
  if (!action) return;

  if (action === "merge") {
    await mergeIds(id);
    return;
  }

  if (action === "rename") {
    const nextId = maxId() + 1;
    const ok = await confirmModal("Create new ID", `Renommer globalement ID ${id} vers ${nextId} ?`, "Appliquer");
    if (!ok) return;

    pushUndo();
    Object.keys(state.boxesByFrame).forEach((k) => {
      state.boxesByFrame[k] = (state.boxesByFrame[k] || []).map((b) => (b.id === id ? { ...b, id: nextId } : b));
      state.modifiedFrames.add(k);
    });
    state.selectedId = nextId;
    setDirtyFlag();
    renderLists();
    drawCanvas();
    showToast(`ID ${id} renomme vers ${nextId}`, "success");
  }
}

function pullbackToPrevious(id) {
  if (state.frameIndex === 0) {
    showToast("Pas de frame precedente", "info");
    return;
  }

  const curr = currentBoxes().find((b) => b.id === id);
  if (!curr) return;

  const prevFrame = state.frames[state.frameIndex - 1]?.filename;
  if (!prevFrame) return;

  pushUndo();
  const prev = state.boxesByFrame[prevFrame] || [];
  const exists = prev.some((b) => b.id === id);
  const updated = exists
    ? prev.map((b) => (b.id === id ? { ...curr } : b))
    : [...prev, { ...curr }];

  state.boxesByFrame[prevFrame] = updated;
  state.modifiedFrames.add(prevFrame);
  setDirtyFlag();
  renderLists();
  drawCanvas();
  showToast(`ID ${id} copie vers frame precedente`, "success");
}

function applyStationary(id) {
  const curr = currentBoxes().find((b) => b.id === id);
  if (!curr) return;

  pushUndo();
  Object.keys(state.boxesByFrame).forEach((frame) => {
    const boxes = state.boxesByFrame[frame] || [];
    const hasId = boxes.some((b) => b.id === id);
    if (!hasId) return;
    state.boxesByFrame[frame] = boxes.map((b) => (b.id === id ? { ...b, x: curr.x, y: curr.y, w: curr.w, h: curr.h } : b));
    state.modifiedFrames.add(frame);
  });
  setDirtyFlag();
  renderLists();
  drawCanvas();
  showToast(`ID ${id} applique en stationary`, "success");
}

function markAsExited(id) {
  pushUndo();
  for (let i = state.frameIndex; i < state.frames.length; i += 1) {
    const frame = state.frames[i]?.filename;
    if (!frame) continue;
    const boxes = state.boxesByFrame[frame] || [];
    const next = boxes.filter((b) => b.id !== id);
    if (next.length !== boxes.length) {
      state.boxesByFrame[frame] = next;
      state.modifiedFrames.add(frame);
    }
  }
  setDirtyFlag();
  renderLists();
  drawCanvas();
  showToast(`ID ${id} marque comme sorti`, "success");
}

function autoFillMissing(id) {
  const previous = prevBoxes().find((b) => b.id === id);
  if (!previous) return;
  pushUndo();
  applyCurrentBoxes([...currentBoxes(), { ...previous }]);
  showToast(`ID ${id} auto-fill`, "info");
}

function undo() {
  const last = state.undo.pop();
  if (!last) return;
  state.boxesByFrame[last.frame] = structuredClone(last.boxes);
  state.modifiedFrames.add(last.frame);
  setDirtyFlag();
  renderLists();
  drawCanvas();
}

async function saveAll() {
  const frames = Array.from(state.modifiedFrames);
  if (!frames.length) return;

  saveBtn.disabled = true;
  saveBtn.textContent = "Saving...";
  try {
    for (const frame of frames) {
      await apiJson("/correct/save_frame", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          segment,
          frame,
          boxes: state.boxesByFrame[frame] || [],
          base_dir: baseDir,
          output_dir: outputDir || undefined,
        }),
      });
    }
    state.modifiedFrames.clear();
    setDirtyFlag();
    document.body.classList.add("export-success");
    window.setTimeout(() => document.body.classList.remove("export-success"), 1300);
    showToast(`Finalized and exported to ${outputDir}`, "success");
  } catch (err) {
    showToast(`Save failed: ${err.message}`, "error");
  } finally {
    saveBtn.textContent = "Save";
    saveBtn.disabled = false;
  }
}

function gotoFrame(index) {
  state.frameIndex = Math.max(0, Math.min(state.frames.length - 1, index));
  state.selectedId = null;
  setMode("Select");
  renderLists();
  loadCurrentImage();
}

async function rejectFrame() {
  const ok = await confirmModal("Reject frame", "Vider toutes les boxes de la frame courante ?", "Reject");
  if (!ok) return;
  pushUndo();
  applyCurrentBoxes([]);
  showToast("Frame rejetee", "info");
}

function acceptFrame() {
  if (state.frameIndex < state.frames.length - 1) gotoFrame(state.frameIndex + 1);
}

canvas.addEventListener("mousedown", (event) => {
  const canvasPos = getCanvasPos(event);
  const imgPos = canvasToImage(canvasPos);
  const hit = imgPos ? hitTest(imgPos.x, imgPos.y) : null;

  if (event.button === 2) {
    event.preventDefault();
    if (imgPos && hit) {
      state.selectedId = hit.id;
      setMode("Select");
      renderLists();
      drawCanvas();
    }
    return;
  }

  if (event.button !== 0) return;
  if (!imgPos) return;

  if (hit) {
    state.selectedId = hit.id;
    setMode(`Re-draw ID ${hit.id}`);
    renderLists();
    drawCanvas();
    return;
  }

  state.selectedId = null;
  setMode("Draw");
  state.drawing = { x: imgPos.x, y: imgPos.y, w: 0, h: 0, sx: imgPos.x, sy: imgPos.y };
  drawCanvas();
});

canvas.addEventListener("mousemove", (event) => {
  const canvasPos = getCanvasPos(event);
  const imgPos = canvasToImage(canvasPos, true);
  if (!imgPos) return;

  if (state.drawing) {
    const x = Math.min(state.drawing.sx, imgPos.x);
    const y = Math.min(state.drawing.sy, imgPos.y);
    const w = Math.abs(imgPos.x - state.drawing.sx);
    const h = Math.abs(imgPos.y - state.drawing.sy);
    state.drawing = { ...state.drawing, x, y, w, h };
    drawCanvas();
    return;
  }

  if (state.dragging) {
    const target = currentBoxes().find((b) => b.id === state.dragging.id);
    if (!target) return;
    const dx = imgPos.x - state.dragging.sx;
    const dy = imgPos.y - state.dragging.sy;
    const nextX = state.dragging.ox + dx;
    const nextY = state.dragging.oy + dy;

    applyCurrentBoxes(
      currentBoxes().map((b) => (b.id === state.dragging.id ? { ...b, x: nextX, y: nextY } : b))
    );
  }
});

canvas.addEventListener("mouseup", async (event) => {
  if (state.dragging) {
    state.dragging = null;
    return;
  }

  if (!state.drawing) return;

  const d = state.drawing;
  state.drawing = null;
  if (d.w < 6 || d.h < 6) {
    setMode("Select");
    drawCanvas();
    return;
  }

  const cls = await pickClassModal(CLASSES[0]);
  if (!cls) {
    setMode("Select");
    drawCanvas();
    return;
  }

  pushUndo();
  const id = maxId() + 1;
  applyCurrentBoxes([...currentBoxes(), { id, class_name: cls, x: d.x, y: d.y, w: d.w, h: d.h }]);
  state.selectedId = id;
  setMode(`Re-draw ID ${id}`);
});

canvas.addEventListener("contextmenu", (event) => {
  event.preventDefault();
  const canvasPos = getCanvasPos(event);
  const imgPos = canvasToImage(canvasPos);
  const hit = imgPos ? hitTest(imgPos.x, imgPos.y) : null;
  if (!hit) {
    closeContextMenu();
    return;
  }
  state.selectedId = hit.id;
  renderLists();
  drawCanvas();
  openContextMenu(event.clientX, event.clientY, hit.id);
});

menu.addEventListener("click", async (event) => {
  const btn = event.target.closest("button");
  if (!btn) return;
  const id = Number(menu.dataset.id || "");
  if (!Number.isFinite(id)) return;

  const action = btn.dataset.action;
  closeContextMenu();
  try {
    if (action === "pullback") pullbackToPrevious(id);
    if (action === "manage") await manageId(id);
    if (action === "delete_frame") await deleteId(id, "frame");
    if (action === "delete_global") await deleteId(id, "global");
    if (action === "change_class") await changeClass(id);
    if (action === "merge") await mergeIds(id);
    if (action === "stationary") applyStationary(id);
    if (action === "mark_exited") markAsExited(id);
  } catch (err) {
    window.alert(err.message);
  }
});

window.addEventListener("click", (event) => {
  if (!event.target.closest("#editor-menu")) {
    closeContextMenu();
  }
});

globalIdsBox.addEventListener("click", (event) => {
  const row = event.target.closest(".id-row");
  if (!row) return;
  state.selectedId = Number(row.dataset.id || "");
  setMode(`Re-draw ID ${state.selectedId}`);
  renderLists();
  drawCanvas();
});

globalIdsBox.addEventListener("contextmenu", (event) => {
  const row = event.target.closest(".id-row");
  if (!row) return;
  event.preventDefault();
  const id = Number(row.dataset.id || "");
  if (!Number.isFinite(id)) return;
  state.selectedId = id;
  renderLists();
  drawCanvas();
  openContextMenu(event.clientX, event.clientY, id);
});

localIdsBox.addEventListener("click", (event) => {
  const row = event.target.closest(".id-row");
  if (!row) return;
  state.selectedId = Number(row.dataset.id || "");
  setMode(`Re-draw ID ${state.selectedId}`);
  renderLists();
  drawCanvas();
});

localIdsBox.addEventListener("contextmenu", (event) => {
  const row = event.target.closest(".id-row");
  if (!row) return;
  event.preventDefault();
  const id = Number(row.dataset.id || "");
  if (!Number.isFinite(id)) return;
  state.selectedId = id;
  renderLists();
  drawCanvas();
  openContextMenu(event.clientX, event.clientY, id);
});

missingIdsBox.addEventListener("click", (event) => {
  const row = event.target.closest(".id-row");
  if (!row) return;
  const id = Number(row.dataset.missing || "");
  autoFillMissing(id);
});

firstBtn.addEventListener("click", () => gotoFrame(0));
prevBtn.addEventListener("click", () => gotoFrame(state.frameIndex - 1));
nextBtn.addEventListener("click", () => gotoFrame(state.frameIndex + 1));
lastBtn.addEventListener("click", () => gotoFrame(state.frames.length - 1));
rejectBtn.addEventListener("click", () => {
  rejectFrame();
});
acceptBtn.addEventListener("click", acceptFrame);
undoBtn.addEventListener("click", undo);
saveBtn.addEventListener("click", saveAll);

window.addEventListener("keydown", (event) => {
  if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) return;
  if (event.ctrlKey && event.key.toLowerCase() === "z") {
    event.preventDefault();
    undo();
    return;
  }
  if (event.key === "ArrowLeft") gotoFrame(state.frameIndex - 1);
  if (event.key === "ArrowRight") gotoFrame(state.frameIndex + 1);
  if (event.key.toLowerCase() === "a") acceptFrame();
  if (event.key.toLowerCase() === "d") rejectFrame();
});

if (backLink) {
  backLink.addEventListener("click", async (event) => {
    if (!state.modifiedFrames.size) return;
    event.preventDefault();
    const ok = await confirmModal(
      "Quitter l'editeur",
      "Tu as des modifications non sauvegardees. Quitter quand meme ?",
      "Quitter"
    );
    if (ok) {
      window.location.href = backLink.getAttribute("href") || "/front/corrector";
    }
  });
}

window.addEventListener("beforeunload", (event) => {
  if (!state.modifiedFrames.size) return;
  event.preventDefault();
  event.returnValue = "";
});

window.addEventListener("resize", () => {
  drawCanvas();
});

async function init() {
  if (!segment || !baseDir) {
    window.alert("Segment/base_dir manquant");
    window.location.href = "/front/corrector";
    return;
  }

  segmentLabel.textContent = `Segment: ${segment}`;

  const framesData = await apiJson(
    `/correct/frames?segment=${encodeURIComponent(segment)}&base_dir=${encodeURIComponent(baseDir)}${outputDir ? `&output_dir=${encodeURIComponent(outputDir)}` : ""}`
  );
  const trajData = await apiJson(
    `/correct/trajectories?segment=${encodeURIComponent(segment)}&base_dir=${encodeURIComponent(baseDir)}${outputDir ? `&output_dir=${encodeURIComponent(outputDir)}` : ""}`
  );

  state.frames = framesData.frames || [];
  state.imgDir = framesData.img_dir || "";
  state.boxesByFrame = {};

  (trajData.trajectories || []).forEach((entry) => {
    state.boxesByFrame[entry.frame] = structuredClone(entry.boxes || []);
  });

  setMode("Select");
  setDirtyFlag();
  renderLists();
  loadCurrentImage();
}

init().catch((err) => {
  showToast(`Init error: ${err.message}`, "error");
});
