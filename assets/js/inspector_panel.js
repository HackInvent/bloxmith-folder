/**
 * Role: Mounts the Folder inspector surface while shared helpers own path browsing.
 * File Name: inspector_panel.js
 * Author: Alexandre EL
 * Email: alex@hackinvent.com
 * Created Date: 2026-07-23
 */

/** Keep Folder inspector behavior block-owned without duplicating path-browser logic. */
export function mount(root) {
  root.dataset.folderInspectorMounted = "true";
}
