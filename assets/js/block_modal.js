/**
 * Role: Mounts the Folder block read/write explorer modal.
 * File Name: block_modal.js
 * Author: Alexandre EL
 * Email: alex@hackinvent.com
 * Created Date: 2026-07-23
 */
const FOLDER_ERROR_MESSAGES = Object.freeze({
  folder_path_required: "Configurez d’abord un répertoire racine.",
  folder_not_found: "Le répertoire configuré est introuvable.",
  folder_path_not_directory: "Le chemin configuré n’est pas un répertoire.",
  folder_path_outside_root: "Cette opération sortirait du répertoire racine.",
  folder_symlink_forbidden: "Les liens symboliques ne sont pas accessibles dans cet explorateur.",
  folder_entry_not_found: "L’élément demandé est introuvable.",
  folder_entry_not_directory: "L’élément demandé n’est pas un dossier.",
  folder_entry_name_invalid: "Le nom saisi n’est pas valide.",
  folder_entry_exists: "Un élément porte déjà ce nom.",
  folder_upload_too_large: "Le fichier dépasse la limite de 50 Mio.",
  folder_upload_target_not_file: "La destination de l’import n’est pas un fichier.",
  folder_upload_action_unknown: "L’action d’import demandée n’est pas prise en charge.",
});

/** Update the explorer status line without replacing the mounted modal. */
function setStatus(root, message, isError = false) {
  const element = root.querySelector("[data-folder-status]");
  if (!element) return;
  element.textContent = message;
  element.classList.toggle("is-error", Boolean(isError));
}

/** Return one backend Folder error as a concise user-facing message. */
function formatError(error) {
  const raw = String(error?.message || error || "Erreur inconnue");
  const separator = raw.indexOf(":");
  const code = separator >= 0 ? raw.slice(0, separator) : raw;
  const detail = separator >= 0 ? raw.slice(separator + 1) : "";
  const message = FOLDER_ERROR_MESSAGES[code] || raw;
  return detail && FOLDER_ERROR_MESSAGES[code] ? `${message} (${detail})` : message;
}

/** Format one byte count for the explorer table. */
function formatSize(value) {
  if (value === null || value === undefined) return "—";
  const units = ["o", "Ko", "Mo", "Go"];
  let size = Number(value) || 0;
  let index = 0;
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024;
    index += 1;
  }
  return `${size.toLocaleString("fr-FR", { maximumFractionDigits: index ? 1 : 0 })} ${units[index]}`;
}

/** Format one ISO timestamp for the current browser locale. */
function formatDate(value) {
  const date = new Date(String(value || ""));
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString("fr-FR");
}

/** Activate exactly one Folder modal tab and its matching panel. */
function setActiveTab(root, name) {
  for (const button of root.querySelectorAll("[data-folder-tab]")) {
    const active = button.dataset.folderTab === name;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-selected", active ? "true" : "false");
  }
  for (const panel of root.querySelectorAll("[data-folder-panel]")) {
    const active = panel.dataset.folderPanel === name;
    panel.classList.toggle("is-active", active);
    panel.hidden = !active;
  }
}

/** Render root-relative breadcrumbs; every target remains server-validated. */
function renderBreadcrumbs(root, state) {
  const mount = root.querySelector("[data-folder-breadcrumbs]");
  if (!mount) return;
  mount.replaceChildren();
  for (const [index, entry] of state.breadcrumbs.entries()) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "folder-breadcrumb";
    button.textContent = entry.label || "Racine";
    button.addEventListener("click", () => void loadListing(root, state.api, state, entry.path || ""));
    mount.append(button);
    if (index < state.breadcrumbs.length - 1) {
      const separator = document.createElement("span");
      separator.textContent = "/";
      separator.setAttribute("aria-hidden", "true");
      mount.append(separator);
    }
  }
}

/** Filter hidden entries locally without changing the backend listing. */
function visibleEntries(root, state) {
  const showHidden = root.querySelector("[data-folder-show-hidden]")?.checked === true;
  return state.entries.filter((entry) => showHidden || !entry.hidden);
}

/** Render the current explorer listing. */
function renderEntries(root, state) {
  const mount = root.querySelector("[data-folder-list]");
  if (!mount) return;
  mount.replaceChildren();
  const entries = visibleEntries(root, state);
  if (!entries.length) {
    const empty = document.createElement("div");
    empty.className = "folder-list-empty";
    empty.textContent = state.entries.length ? "Aucun élément visible." : "Ce dossier est vide.";
    mount.append(empty);
    return;
  }
  for (const entry of entries) {
    const row = document.createElement("div");
    row.className = "folder-list-row";
    row.dataset.folderEntry = entry.relative_path || "";
    row.setAttribute("role", "row");

    const nameCell = document.createElement("div");
    nameCell.className = "folder-name-cell";
    nameCell.setAttribute("role", "cell");
    const icon = document.createElement("span");
    icon.className = "folder-entry-icon";
    window.CWIcons?.setIcon?.(icon, entry.kind === "directory" ? "folder" : "fileText");
    const name = document.createElement(entry.kind === "directory" ? "button" : "span");
    if (name instanceof HTMLButtonElement) {
      name.type = "button";
      name.className = "folder-entry-link";
      name.addEventListener("click", () => void loadListing(root, state.api, state, entry.relative_path || ""));
    } else {
      name.className = "folder-entry-name";
    }
    name.textContent = entry.name || "";
    name.title = entry.name || "";
    nameCell.append(icon, name);

    const type = document.createElement("span");
    type.setAttribute("role", "cell");
    type.textContent = entry.kind === "directory" ? "Dossier" : "Fichier";
    const size = document.createElement("span");
    size.setAttribute("role", "cell");
    size.textContent = formatSize(entry.size);
    const modified = document.createElement("span");
    modified.setAttribute("role", "cell");
    modified.textContent = formatDate(entry.modified_at);
    row.append(nameCell, type, size, modified);
    mount.append(row);
  }
}

/** Apply an authoritative backend listing to the mounted explorer state. */
function applyListing(root, state, payload) {
  const listing = payload?.listing || payload || {};
  state.currentPath = String(listing.current_path || "");
  state.parentPath = String(listing.parent_path || "");
  state.atRoot = listing.at_root === true;
  state.entries = Array.isArray(listing.entries) ? listing.entries : [];
  state.breadcrumbs = Array.isArray(listing.breadcrumbs) ? listing.breadcrumbs : [];
  state.writable = listing.writable !== false;
  const parent = root.querySelector("[data-folder-action='parent']");
  if (parent) parent.disabled = state.atRoot;
  for (const selector of ["[data-folder-action='choose-files']", "[data-folder-action='create-directory']", "[data-folder-new-directory]"]) {
    const control = root.querySelector(selector);
    if (control) control.disabled = !state.writable;
  }
  const dropzone = root.querySelector("[data-folder-dropzone]");
  if (dropzone) dropzone.setAttribute("aria-disabled", state.writable ? "false" : "true");
  const rootLabel = root.querySelector("[data-folder-root-label]");
  if (rootLabel) {
    rootLabel.textContent = listing.root_path || "Non configuré";
    rootLabel.title = listing.root_path || "";
  }
  renderBreadcrumbs(root, state);
  renderEntries(root, state);
  const suffix = listing.skipped_symlinks ? ` · ${listing.skipped_symlinks} lien(s) symbolique(s) masqué(s)` : "";
  const access = state.writable ? "" : " · lecture seule";
  setStatus(root, `${state.entries.length} élément(s)${suffix}${access}.`);
}

/** Load one root-relative directory through the generic block request API. */
async function loadListing(root, api, state, relativePath = state.currentPath) {
  setStatus(root, "Chargement du contenu...");
  try {
    const result = await api.blockRequest("explorer/list", { payload: { values: { relative_path: relativePath || "" } } });
    applyListing(root, state, result);
  } catch (error) {
    state.entries = [];
    state.breadcrumbs = [];
    renderEntries(root, state);
    renderBreadcrumbs(root, state);
    setStatus(root, `Exploration impossible : ${formatError(error)}`, true);
  }
}

/** Execute one block-owned filesystem mutation and apply its returned listing. */
async function mutate(root, api, state, route, values) {
  setStatus(root, "Modification en cours...");
  try {
    const result = await api.blockRequest(route, { payload: { values } });
    applyListing(root, state, result);
    if (result.message) setStatus(root, result.message);
    return result;
  } catch (error) {
    setStatus(root, `Modification impossible : ${formatError(error)}`, true);
    throw error;
  }
}

/** Upload one browser file, requiring confirmation before replacement. */
async function uploadOne(root, api, state, file, overwrite = false) {
  const form = new FormData();
  form.set("file", file, file.name);
  try {
    const result = await api.blockRequest("ui-upload", {
      method: "POST",
      formData: form,
      payload: {
        action: "upload_file",
        values: { relative_path: state.currentPath, overwrite },
      },
    });
    applyListing(root, state, result);
    setStatus(root, result.message || `Fichier importé : ${file.name}`);
  } catch (error) {
    if (!overwrite && String(error.message || "").includes("folder_entry_exists")) {
      const replace = window.confirm(`Le fichier « ${file.name} » existe déjà. Le remplacer ?`);
      if (replace) return uploadOne(root, api, state, file, true);
    }
    setStatus(root, `Import impossible : ${formatError(error)}`, true);
    throw error;
  }
}

/** Upload selected files sequentially so status and overwrite prompts remain deterministic. */
async function uploadFiles(root, api, state, files) {
  for (const file of Array.from(files || [])) {
    await uploadOne(root, api, state, file).catch(() => undefined);
  }
}

/**
 * Mount the autonomous Folder modal explorer.
 *
 * @param {HTMLElement} root - Mounted Folder modal root.
 * @param {object} api - Generic block UI API including JSON and multipart requests.
 */
export function mount(root, api) {
  const state = { api, currentPath: "", parentPath: "", atRoot: true, entries: [], breadcrumbs: [], writable: false };
  const uploadInput = root.querySelector("[data-folder-upload-input]");
  const dropzone = root.querySelector("[data-folder-dropzone]");

  root.addEventListener("click", (event) => {
    const target = event.target instanceof Element ? event.target : null;
    const tab = target?.closest("[data-folder-tab]")?.dataset.folderTab;
    if (tab) {
      setActiveTab(root, tab);
      if (tab === "content") void loadListing(root, api, state);
      return;
    }
    const action = target?.closest("[data-folder-action]")?.dataset.folderAction;
    if (action === "refresh") void loadListing(root, api, state);
    if (action === "parent" && !state.atRoot) void loadListing(root, api, state, state.parentPath);
    if (action === "choose-files") uploadInput?.click();
    if (action === "create-directory") {
      const input = root.querySelector("[data-folder-new-directory]");
      const name = String(input?.value || "").trim();
      if (!name) return;
      void mutate(root, api, state, "explorer/create-directory", { relative_path: state.currentPath, name }).then(() => {
        if (input) input.value = "";
      });
    }
  });

  root.querySelector("[data-folder-show-hidden]")?.addEventListener("change", () => renderEntries(root, state));
  uploadInput?.addEventListener("change", () => {
    void uploadFiles(root, api, state, uploadInput.files).finally(() => { uploadInput.value = ""; });
  });
  for (const name of ["dragenter", "dragover"]) {
    dropzone?.addEventListener(name, (event) => {
      event.preventDefault();
      dropzone.classList.add("is-dragover");
    });
  }
  for (const name of ["dragleave", "drop"]) {
    dropzone?.addEventListener(name, (event) => {
      event.preventDefault();
      dropzone.classList.remove("is-dragover");
    });
  }
  dropzone?.addEventListener("drop", (event) => {
    if (!state.writable) {
      setStatus(root, "Ce dossier est en lecture seule.", true);
      return;
    }
    void uploadFiles(root, api, state, event.dataTransfer?.files || []);
  });
  setActiveTab(root, "content");
  void loadListing(root, api, state, "");
}
