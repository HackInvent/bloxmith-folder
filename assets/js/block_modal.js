/**
 * Role: Mounts the Folder block read/write explorer modal.
 * File Name: block_modal.js
 * Author: Alexandre EL
 * Email: alex@hackinvent.com
 * Created Date: 2026-07-23
 */
const FOLDER_ERROR_MESSAGES = Object.freeze({
  folder_path_required: "Configure a root directory first.",
  folder_not_found: "The configured directory cannot be found.",
  folder_path_not_directory: "The configured path is not a directory.",
  folder_path_outside_root: "This operation would leave the root directory.",
  folder_symlink_forbidden: "Symbolic links are not reachable in this explorer.",
  folder_entry_not_found: "The requested item cannot be found.",
  folder_entry_not_directory: "The requested item is not a folder.",
  folder_entry_name_invalid: "The name entered is not valid.",
  folder_entry_exists: "An item already has that name.",
  folder_upload_too_large: "The file exceeds the 50 MiB limit.",
  folder_upload_target_not_file: "The import destination is not a file.",
  folder_upload_action_unknown: "The requested import action is not supported.",
});

/**
 * Resolve one block text in the active language, from the catalog of the owning release.
 *
 * @param {HTMLElement} element - Element inside the mounted surface, carrying its release.
 * @param {string} key - Block catalog key.
 * @param {object} params - Placeholder values.
 * @param {string} fallback - Authored English text.
 * @returns {string} Localized text.
 */
function text(element, key, params, fallback) {
  const release = element?.closest?.("[data-block-release]")?.dataset?.blockRelease || "";
  return window.CWI18n?.t?.(key, params, fallback, release) ?? fallback;
}

/** Update the explorer status line without replacing the mounted modal. */
function setStatus(root, message, isError = false) {
  const element = root.querySelector("[data-folder-status]");
  if (!element) return;
  element.textContent = message;
  element.classList.toggle("is-error", Boolean(isError));
}

/** Return one backend Folder error as a concise user-facing message. */
function formatError(error) {
  const raw = String(error?.message || error || "Unknown error");
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
    button.textContent = entry.label || text(button, "block.folder.root_default_label", {}, "Root");
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
    empty.textContent = state.entries.length
      ? text(empty, "block.folder.no_visible_item", {}, "No visible item.")
      : text(empty, "block.folder.empty_folder", {}, "This folder is empty.");
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
    type.textContent = entry.kind === "directory"
      ? text(type, "block.folder.kind_directory", {}, "Folder")
      : text(type, "block.folder.kind_file", {}, "File");
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
    rootLabel.textContent = listing.root_path || text(rootLabel, "block.folder.not_configured", {}, "Not configured");
    rootLabel.title = listing.root_path || "";
  }
  renderBreadcrumbs(root, state);
  renderEntries(root, state);
  const suffix = listing.skipped_symlinks
    ? text(root, "block.folder.hidden_symlinks", { count: listing.skipped_symlinks },
           ` · ${listing.skipped_symlinks} hidden symbolic link(s)`)
    : "";
  const access = state.writable ? "" : text(root, "block.folder.read_only_suffix", {}, " · read only");
  setStatus(root, text(root, "block.folder.entries_count",
    { count: state.entries.length, suffix, access }, `${state.entries.length} item(s)${suffix}${access}.`));
}

/** Load one root-relative directory through the generic block request API. */
async function loadListing(root, api, state, relativePath = state.currentPath) {
  setStatus(root, text(root, "block.folder.loading_content", {}, "Loading the content..."));
  try {
    const result = await api.blockRequest("explorer/list", { payload: { values: { relative_path: relativePath || "" } } });
    applyListing(root, state, result);
  } catch (error) {
    state.entries = [];
    state.breadcrumbs = [];
    renderEntries(root, state);
    renderBreadcrumbs(root, state);
    setStatus(root, text(root, "block.folder.error_explore", { error: formatError(error) },
      `Browsing failed: ${formatError(error)}`), true);
  }
}

/** Execute one block-owned filesystem mutation and apply its returned listing. */
async function mutate(root, api, state, route, values) {
  setStatus(root, text(root, "block.folder.modifying", {}, "Change in progress..."));
  try {
    const result = await api.blockRequest(route, { payload: { values } });
    applyListing(root, state, result);
    if (result.message) setStatus(root, result.message);
    return result;
  } catch (error) {
    setStatus(root, text(root, "block.folder.error_modify", { error: formatError(error) },
      `Change failed: ${formatError(error)}`), true);
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
    setStatus(root, result.message || text(root, "block.folder.file_imported", { name: file.name },
      `File imported: ${file.name}`));
  } catch (error) {
    if (!overwrite && String(error.message || "").includes("folder_entry_exists")) {
      const replace = window.confirm(text(root, "block.folder.replace_confirm", { name: file.name },
        `The file "${file.name}" already exists. Replace it?`));
      if (replace) return uploadOne(root, api, state, file, true);
    }
    setStatus(root, text(root, "block.folder.error_import", { error: formatError(error) },
      `Import failed: ${formatError(error)}`), true);
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
      setStatus(root, text(root, "block.folder.read_only", {}, "This folder is read-only."), true);
      return;
    }
    void uploadFiles(root, api, state, event.dataTransfer?.files || []);
  });
  setActiveTab(root, "content");
  void loadListing(root, api, state, "");
}
