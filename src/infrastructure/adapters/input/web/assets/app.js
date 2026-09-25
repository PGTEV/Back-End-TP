const fileInput = document.querySelector("#file-input");
const fileLabel = document.querySelector("#file-label");
const dropzone = document.querySelector("#dropzone");
const processButton = document.querySelector("#process-button");
const queryForm = document.querySelector("#query-form");
const statusPanel = document.querySelector("#status-panel");
const statusTitle = document.querySelector("#status-title");
const statusMessage = document.querySelector("#status-message");
const results = document.querySelector("#results");

let selectedFile = null;

function setFile(file) {
  selectedFile = file || null;
  processButton.disabled = !selectedFile;
  fileLabel.textContent = selectedFile ? selectedFile.name : "Arrastra tu PDF aquí";
}

fileInput.addEventListener("change", () => setFile(fileInput.files[0]));
["dragenter", "dragover"].forEach(event => dropzone.addEventListener(event, e => {
  e.preventDefault();
  dropzone.classList.add("dragging");
}));
["dragleave", "drop"].forEach(event => dropzone.addEventListener(event, e => {
  e.preventDefault();
  dropzone.classList.remove("dragging");
}));
dropzone.addEventListener("drop", event => setFile(event.dataTransfer.files[0]));

function showStatus(title, message, error = false) {
  statusTitle.textContent = title;
  statusMessage.textContent = message;
  statusPanel.classList.remove("hidden");
  statusPanel.classList.toggle("error", error);
  if (!error) results.classList.add("hidden");
  statusPanel.scrollIntoView({ behavior: "smooth", block: "center" });
}

function hideStatus() {
  statusPanel.classList.add("hidden");
  statusPanel.classList.remove("error");
}

function messageFrom(payload, fallback) {
  const detail = payload?.detail;
  if (typeof detail === "string") return detail;
  if (detail?.mensaje) return detail.mensaje;
  if (Array.isArray(detail)) return detail.map(item => item.msg).join(". ");
  return fallback;
}

function renderResult(data) {
  document.querySelector("#result-file").textContent = data.nombre_archivo;
  document.querySelector("#result-id").textContent = data.id;
  document.querySelector("#result-count").textContent = data.documentos.length;
  document.querySelector("#result-date").textContent = new Date(data.creado_en).toLocaleString("es-PE", { timeZone: "UTC" });
  const state = document.querySelector("#result-state");
  state.textContent = data.estado;
  state.classList.toggle("bad", data.estado !== "PROCESADO");

  const container = document.querySelector("#documents");
  container.replaceChildren();
  if (!data.documentos.length) {
    const empty = document.createElement("p");
    empty.textContent = data.error || "El expediente no contiene documentos procesados.";
    container.append(empty);
  }
  data.documentos.forEach((documento, index) => {
    const article = document.createElement("article");
    article.className = "document";
    const fields = Object.entries(documento.campos || {}).map(([key, value]) => `${key.toUpperCase()}: ${value}`).join(" · ") || "Sin campos adicionales";
    article.innerHTML = `
      <span class="doc-type">${escapeHtml(documento.tipo)}</span>
      <div><h3>Documento ${index + 1}</h3><p>${escapeHtml(fields)}</p></div>
      <div class="doc-meta">Página ${documento.paginas.join(", ")}<br>${escapeHtml(documento.metodo_extraccion)}</div>`;
    container.append(article);
  });
  hideStatus();
  results.classList.remove("hidden");
  results.scrollIntoView({ behavior: "smooth", block: "start" });
}

function escapeHtml(value) {
  const node = document.createElement("div");
  node.textContent = String(value ?? "");
  return node.innerHTML;
}

async function request(url, options, fallback) {
  const response = await fetch(url, options);
  const payload = await response.json();
  if (!response.ok) throw new Error(messageFrom(payload, fallback));
  return payload;
}

processButton.addEventListener("click", async () => {
  if (!selectedFile) return;
  if (selectedFile.type !== "application/pdf" && !selectedFile.name.toLowerCase().endsWith(".pdf")) {
    showStatus("Archivo no válido", "Selecciona un documento en formato PDF.", true);
    return;
  }
  const form = new FormData();
  form.append("archivo", selectedFile);
  processButton.disabled = true;
  showStatus("Procesando expediente", "Extrayendo texto y clasificando las páginas. Esto puede tardar unos segundos.");
  try {
    renderResult(await request("/api/expedientes", { method: "POST", body: form }, "No se pudo procesar el expediente."));
  } catch (error) {
    showStatus("No se pudo completar", error.message, true);
  } finally {
    processButton.disabled = false;
  }
});

queryForm.addEventListener("submit", async event => {
  event.preventDefault();
  const id = document.querySelector("#dossier-id").value.trim();
  showStatus("Buscando expediente", "Consultando la información guardada.");
  try {
    renderResult(await request(`/api/expedientes/${encodeURIComponent(id)}`, {}, "No se encontró el expediente."));
  } catch (error) {
    showStatus("Consulta sin resultado", error.message, true);
  }
});

fetch("/health")
  .then(response => response.ok ? response.json() : Promise.reject())
  .then(() => {
    const badge = document.querySelector("#health");
    badge.className = "health online";
    badge.querySelector("b").textContent = "Servicio activo";
  })
  .catch(() => {
    const badge = document.querySelector("#health");
    badge.className = "health offline";
    badge.querySelector("b").textContent = "Sin conexión";
  });
