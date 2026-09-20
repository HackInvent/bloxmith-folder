# -----------------------------------------------------------------------------
# Role: Represents and safely manages one server-side working directory.
# File Name: block.py
# Author: Alexandre EL
# Email: alex@hackinvent.com
# Created Date: 2026-07-23
# -----------------------------------------------------------------------------

from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any
import os

from bloxsmith_app.block_api import (
    BlockDefinition,
    BlockRuntimeContext,
    BlockRuntimeOutput,
    BlockRuntimeResult,
    DIRECTORY_PATH,
    render_inspector_template,
    render_node_card_template,
    render_path_browser_control,
)


MAX_FOLDER_UPLOAD_BYTES = 50 * 1024 * 1024


class FolderBlockError(ValueError):
    """Raised when a Folder operation violates its configured root contract."""


# Functional behavior:
# FB1 - Resolve and validate the configured directory, then emit its absolute directory/path value.
# FB2 - List files and child directories without allowing navigation above the configured root.
# FB3 - Create child directories inside the configured root only.
# FB4 - Store browser uploads atomically inside the current explorer directory.
# FB5 - Reject traversal, absolute relative targets, symbolic links, unsafe names, and implicit overwrite.
# FB6 - Render block-owned node card, modal, inspector, and read/write explorer assets.
# FB7 - Execute through the same generic block contract in centralized and zeromq_active modes.
class FolderBlock(BlockDefinition):
    """Autonomous source block for one bounded read/write directory."""

    kind = "folder"

    def render_node_card(self, *, node: dict[str, Any], payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Render the configured directory in the block-owned canvas card."""

        configured_path = self._configured_path(node)
        label = Path(configured_path).name if configured_path else "Aucun répertoire"
        return render_node_card_template(
            block=self,
            node=node,
            node_classes=["folder-node"],
            replacements={
                "title": node.get("title") or self.default_title(),
                "path": configured_path or "Répertoire non configuré",
                "path_label": label or configured_path,
            },
        )

    def render_modal(self, *, node: dict[str, Any], payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Render the large read/write explorer and directory configuration tabs."""

        configured_path = self._configured_path(node)
        template = (self.directory / "block_modal.html").read_text(encoding="utf-8")
        template = template.replace(
            "{{ path_browser_html }}",
            self._path_browser(configured_path, input_id=f"{node.get('id') or 'folder'}ModalPath"),
        ).replace("{{ configured_path }}", escape(configured_path or "Non configuré"))
        html = self._render_generic_modal_template(template=template, node=node, payload=payload or {})
        return {
            "html": html,
            "context": {
                "node_id": str(node.get("id") or ""),
                "node_kind": self.kind,
                "path": configured_path,
            },
        }

    def render_inspector_panel(self, *, node: dict[str, Any], payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Render the block-owned inspector with root selection and fixed ports."""

        configured_path = self._configured_path(node)
        template = (self.directory / "inspector_panel.html").read_text(encoding="utf-8")
        html = render_inspector_template(
            template=template.replace(
                "{{ path_browser_html }}",
                self._path_browser(configured_path, input_id=f"{node.get('id') or 'folder'}InspectorPath"),
            ),
            node={**node, "type": self.kind, "kind": self.kind},
            payload=payload,
            replacements={
                "add_input_disabled": "disabled",
                "add_output_disabled": "disabled",
            },
            show_duplicate=False,
        )
        return {
            "html": html,
            "context": {
                "node_id": str(node.get("id") or ""),
                "full_panel": True,
                "path": configured_path,
            },
        }

    def handle_ui_request(
        self,
        *,
        node: dict[str, Any],
        route: str,
        method: str,
        values: dict[str, Any],
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Handle explorer listing and bounded filesystem mutations.

        Args:
            node: Serialized Folder node whose config defines the root.
            route: Block-local explorer operation.
            method: HTTP method used by the generic adapter.
            values: Relative path and operation-specific values.
            payload: Framework context containing the application root.
        """

        if str(method or "").upper() != "POST":
            raise FolderBlockError("folder_method_not_allowed")
        root = self._root_from_node(node, payload)
        normalized_route = str(route or "").strip("/")
        relative_path = str(values.get("relative_path") or "")
        if normalized_route == "explorer/list":
            return self._listing(root, relative_path)
        if normalized_route == "explorer/create-directory":
            current = self._resolve_relative(root, relative_path, require_exists=True, require_directory=True)
            name = self._safe_entry_name(values.get("name"))
            target = self._resolve_relative(root, self._join_relative(relative_path, name), require_exists=False)
            if target.exists():
                raise FolderBlockError("folder_entry_exists")
            target.mkdir()
            return {"ok": True, "message": f"Folder created: {name}", "listing": self._listing(root, self._relative(root, current))}
        raise FolderBlockError(f"folder_route_unknown:{normalized_route or '-'}")

    def handle_ui_upload(
        self,
        *,
        node: dict[str, Any],
        action: str,
        values: dict[str, Any],
        filename: str,
        content: bytes,
        content_type: str = "",
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Store one browser upload atomically under the configured root.

        Args:
            node: Serialized Folder node defining the explorer root.
            action: Must be ``upload_file``.
            values: Current relative directory and overwrite confirmation.
            filename: Browser-provided base file name.
            content: Raw uploaded bytes.
            content_type: Informational browser MIME type.
            payload: Framework context containing the application root.
        """

        if str(action or "") != "upload_file":
            raise FolderBlockError("folder_upload_action_unknown")
        if len(content) > MAX_FOLDER_UPLOAD_BYTES:
            raise FolderBlockError("folder_upload_too_large")
        root = self._root_from_node(node, payload)
        current_relative = str(values.get("relative_path") or "")
        current = self._resolve_relative(root, current_relative, require_exists=True, require_directory=True)
        safe_name = self._safe_entry_name(filename)
        target = self._resolve_relative(root, self._join_relative(current_relative, safe_name), require_exists=False)
        overwrite = self._as_bool(values.get("overwrite"))
        if target.exists() and not overwrite:
            raise FolderBlockError("folder_entry_exists")
        if target.exists() and not target.is_file():
            raise FolderBlockError("folder_upload_target_not_file")

        temporary_path: Path | None = None
        try:
            with NamedTemporaryFile(prefix=".bloxsmith-upload-", dir=current, delete=False) as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
                temporary_path = Path(stream.name)
            os.replace(temporary_path, target)
            temporary_path = None
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

        return {
            "ok": True,
            "message": f"File imported: {safe_name}",
            "file": {
                "name": safe_name,
                "relative_path": self._relative(root, target),
                "size": len(content),
                "content_type": str(content_type or "application/octet-stream"),
            },
            "listing": self._listing(root, self._relative(root, current)),
        }

    def preview_received(self, *, node: Any, **runtime_services: Any) -> str:
        """Return the configured folder path for worker previews."""

        config = getattr(node, "config", {}) if isinstance(getattr(node, "config", {}), dict) else {}
        return str(config.get("path") or "").strip() or "répertoire non configuré"

    def execute_runtime(self, context: BlockRuntimeContext) -> BlockRuntimeResult:
        """Validate and emit the configured directory path in either runtime mode."""

        try:
            root = self.resolve_root(context.config.get("path"), context.root_dir)
        except (FolderBlockError, OSError) as exc:
            message = str(exc)
            return BlockRuntimeResult(
                status="failed",
                outputs=[],
                logs=[f"[folder-error] {context.node_id}: {message}"],
                error=message,
                exit_code=1,
                last_message=message,
                worker_received="-",
            )
        absolute_path = str(root)
        outputs = [
            BlockRuntimeOutput(
                port_id=int(getattr(port, "id", 0) or 0),
                port_name=str(getattr(port, "name", "") or ""),
                value=absolute_path,
                content_type=DIRECTORY_PATH,
            )
            for port in context.output_ports
        ]
        writable = os.access(root, os.W_OK)
        return BlockRuntimeResult(
            status="success",
            outputs=outputs,
            logs=[f"[folder] {context.node_id} -> {absolute_path}"],
            last_message=absolute_path,
            content_type=DIRECTORY_PATH,
            worker_received=absolute_path,
            metadata={"folder": {"path": absolute_path, "readable": os.access(root, os.R_OK), "writable": writable}},
        )

    def resolve_root(self, raw_path: Any, root_dir: Path | str) -> Path:
        """Resolve one configured path and require an existing directory."""

        cleaned = str(raw_path or "").strip()
        if not cleaned:
            raise FolderBlockError("folder_path_required")
        path = Path(cleaned).expanduser()
        if not path.is_absolute():
            path = Path(root_dir) / path
        try:
            resolved = path.resolve(strict=True)
        except FileNotFoundError as exc:
            raise FolderBlockError(f"folder_not_found:{cleaned}") from exc
        if not resolved.is_dir():
            raise FolderBlockError(f"folder_path_not_directory:{cleaned}")
        return resolved

    def _root_from_node(self, node: dict[str, Any], payload: dict[str, Any] | None) -> Path:
        """Resolve the UI root from durable node config, never from request values."""

        request = payload if isinstance(payload, dict) else {}
        root_dir = request.get("root_dir") or Path(".")
        return self.resolve_root(self._configured_path(node), root_dir)

    def _configured_path(self, node: dict[str, Any]) -> str:
        """Return the durable Folder path from one serialized node."""

        config = node.get("config") if isinstance(node.get("config"), dict) else {}
        return str(config.get("path") or "").strip()

    def _path_browser(self, value: str, *, input_id: str) -> str:
        """Render the shared directory picker used to configure the explorer root."""

        return render_path_browser_control(
            input_id=input_id,
            label="Répertoire racine",
            value=value,
            placeholder="/chemin/du/repertoire",
            input_attrs='data-block-config-field="path" data-folder-path',
            select_mode="directory",
            status="Choisissez le répertoire qui délimitera l’explorateur.",
            use_current_label="Utiliser comme racine",
        )

    def _listing(self, root: Path, relative_path: str) -> dict[str, Any]:
        """Return one safe explorer listing relative to the configured root."""

        current = self._resolve_relative(root, relative_path, require_exists=True, require_directory=True)
        entries: list[dict[str, Any]] = []
        skipped_symlinks = 0
        for child in current.iterdir():
            try:
                if child.is_symlink():
                    skipped_symlinks += 1
                    continue
                is_directory = child.is_dir()
                is_file = child.is_file()
                if not is_directory and not is_file:
                    continue
                resolved = child.resolve(strict=True)
                self._ensure_within_root(root, resolved)
                stat = resolved.stat()
            except (FolderBlockError, OSError):
                continue
            entries.append(
                {
                    "name": child.name,
                    "kind": "directory" if is_directory else "file",
                    "relative_path": self._relative(root, resolved),
                    "size": None if is_directory else int(stat.st_size),
                    "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                    "hidden": child.name.startswith("."),
                }
            )
        entries.sort(key=lambda entry: (entry["kind"] != "directory", str(entry["name"]).casefold()))
        current_relative = self._relative(root, current)
        return {
            "ok": True,
            "root_path": str(root),
            "current_path": current_relative,
            "at_root": current == root,
            "parent_path": self._relative(root, current.parent) if current != root else "",
            "breadcrumbs": self._breadcrumbs(current_relative),
            "entries": entries,
            "entry_count": len(entries),
            "skipped_symlinks": skipped_symlinks,
            "writable": os.access(current, os.W_OK),
        }

    def _resolve_relative(
        self,
        root: Path,
        relative_path: Any,
        *,
        require_exists: bool,
        require_directory: bool = False,
    ) -> Path:
        """Resolve a client-relative target while rejecting traversal and symlinks."""

        cleaned = str(relative_path or "").strip()
        path = Path(cleaned) if cleaned else Path()
        if path.is_absolute() or any(part == ".." for part in path.parts):
            raise FolderBlockError("folder_path_outside_root")
        parts = [part for part in path.parts if part not in {"", "."}]
        candidate = root
        for part in parts:
            candidate = candidate / part
            if candidate.is_symlink():
                raise FolderBlockError("folder_symlink_forbidden")
        try:
            resolved = candidate.resolve(strict=require_exists)
        except FileNotFoundError as exc:
            raise FolderBlockError("folder_entry_not_found") from exc
        self._ensure_within_root(root, resolved)
        if require_exists and not resolved.exists():
            raise FolderBlockError("folder_entry_not_found")
        if require_directory and not resolved.is_dir():
            raise FolderBlockError("folder_entry_not_directory")
        return resolved

    @staticmethod
    def _ensure_within_root(root: Path, target: Path) -> None:
        """Reject any canonical target that is not the root or one of its descendants."""

        if target != root and root not in target.parents:
            raise FolderBlockError("folder_path_outside_root")

    @staticmethod
    def _safe_entry_name(value: Any) -> str:
        """Validate one direct child name without silently rewriting it."""

        name = str(value or "").strip()
        if (
            not name
            or name in {".", ".."}
            or "/" in name
            or "\\" in name
            or "\x00" in name
            or any(ord(character) < 32 for character in name)
            or len(name.encode("utf-8")) > 255
        ):
            raise FolderBlockError("folder_entry_name_invalid")
        return name

    @staticmethod
    def _relative(root: Path, target: Path) -> str:
        """Return a POSIX relative path, using an empty string for the root."""

        relative = target.relative_to(root)
        return "" if relative == Path(".") else relative.as_posix()

    @staticmethod
    def _join_relative(parent: str, name: str) -> str:
        """Join one validated child name to a relative explorer path."""

        return (Path(str(parent or "")) / name).as_posix()

    @staticmethod
    def _breadcrumbs(relative_path: str) -> list[dict[str, str]]:
        """Build a root-relative breadcrumb trail for the explorer modal."""

        items = [{"label": "Racine", "path": ""}]
        current = Path()
        for part in Path(relative_path).parts:
            if part in {"", "."}:
                continue
            current /= part
            items.append({"label": part, "path": current.as_posix()})
        return items

    @staticmethod
    def _as_bool(value: Any) -> bool:
        """Normalize a UI boolean used for overwrite confirmation."""

        if isinstance(value, bool):
            return value
        return str(value or "").strip().lower() in {"1", "true", "yes", "on"}
