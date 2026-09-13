#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# Role: Verifies Folder block runtime, explorer, upload, and UI behavior.
# File Name: F5.33_folder_block.py
# Author: Alexandre EL
# Email: alex@hackinvent.com
# Created Date: 2026-07-23
# -----------------------------------------------------------------------------

'''F5.33 - Folder autonomous block regression coverage.'''

# Test cases:
# - FB1 - Resolve an existing directory and emit one absolute directory/path value.
# - FB2/FB5 - List descendants while rejecting traversal, absolute targets, and symbolic links.
# - FB3/FB5 - Create safe child directories under the configured root.
# - FB4/FB5 - Upload files atomically and require explicit overwrite confirmation.
# - FB6 - Render block-owned modal, inspector, node card, and explorer assets.
# - FB7 - Execute Folder -> Directory List -> Display in centralized and zeromq_active modes.

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import json
import sys
import uuid

ROOT_DIR = Path(__file__).resolve().parents[3]
TESTS_DIR = ROOT_DIR / "tests"
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from ui_smoke_common import (  # noqa: E402
    create_run_api,
    data_edge,
    display_node,
    expect,
    graph_payload,
    isolated_server,
    wait_for_run_terminal,
)

from blocs.folder.block import FolderBlock, FolderBlockError  # noqa: E402
from bloxsmith_app.block_runtime import BlockRuntimeContext  # noqa: E402
from bloxsmith_app.block_ui import render_block_inspector_panel, render_block_modal, render_block_node_card  # noqa: E402


def folder_node(path: str, *, node_id: str = "folder-1") -> dict:
    '''Return one serializable Folder node for UI and runtime checks.'''

    return {
        "id": node_id,
        "kind": "folder",
        "title": "Working Folder",
        "position": {"x": 100, "y": 120},
        "inputs": [],
        "outputs": [
            {
                "id": 1,
                "name": "path",
                "title": "Path",
                "emits": ["directory/path", "message/*"],
                "multiplicity": "many",
            }
        ],
        "config": {"path": path},
    }


def directory_list_node() -> dict:
    '''Return a Directory List node consuming the Folder output contract.'''

    return {
        "id": "directory-list-1",
        "kind": "directory_list",
        "title": "Files",
        "position": {"x": 420, "y": 120},
        "inputs": [
            {
                "id": 1,
                "name": "folder",
                "title": "Folder",
                "accepts": ["directory/path", "file/path", "message/*", "application/json"],
                "multiplicity": "many",
                "required": False,
                "execution_requirement": "required_for_execution",
            }
        ],
        "outputs": [
            {
                "id": 1,
                "name": "liste",
                "title": "Files",
                "emits": ["application/json", "message/*"],
                "multiplicity": "many",
            }
        ],
        "config": {"folder_path": "", "pattern": "*", "recursive": False},
    }


def direct_context(path: str, root_dir: Path) -> BlockRuntimeContext:
    '''Build the generic runtime context used by direct Folder execution.'''

    return BlockRuntimeContext(
        run_id="folder-unit-run",
        node_id="folder-unit",
        kind="folder",
        title="Folder Unit",
        config={"path": path},
        inputs={},
        input_content_types={},
        input_message="",
        input_ports=(),
        output_ports=(SimpleNamespace(id=1, name="path"),),
        root_dir=root_dir,
    )


def assert_folder_error(callable_value, expected_code: str) -> None:
    '''Assert that a bounded explorer operation fails with a stable code.'''

    try:
        callable_value()
    except FolderBlockError as exc:
        expect(expected_code in str(exc), f"Erreur Folder attendue: {expected_code}; reçue: {exc}")
        return
    raise AssertionError(f"FolderBlockError attendu: {expected_code}")


def test_direct_runtime_and_ui() -> None:
    '''TC1/TC5 - Validate runtime path emission, failures, and block-owned UI.'''

    block = FolderBlock()
    with TemporaryDirectory(prefix="bloxsmith-folder-unit-") as temp_dir:
        base = Path(temp_dir)
        root = base / "root"
        root.mkdir()
        regular_file = base / "not-a-directory.txt"
        regular_file.write_text("x", encoding="utf-8")

        result = block.execute_runtime(direct_context(str(root), base))
        expect(result.status == "success", "Folder doit réussir avec un dossier existant.")
        expect(result.outputs[0].value == str(root.resolve()), "Folder doit émettre le chemin absolu.")
        expect(result.outputs[0].content_type == "directory/path", "Folder doit émettre directory/path.")

        relative = block.execute_runtime(direct_context("root", base))
        expect(relative.status == "success", "Folder doit résoudre un chemin relatif depuis root_dir.")
        expect(relative.outputs[0].value == str(root.resolve()), "Résolution relative Folder incorrecte.")

        missing = block.execute_runtime(direct_context(str(base / "missing"), base))
        expect(missing.status == "failed" and "folder_not_found" in str(missing.error), "Dossier absent non signalé.")
        invalid = block.execute_runtime(direct_context(str(regular_file), base))
        expect(
            invalid.status == "failed" and "folder_path_not_directory" in str(invalid.error),
            "Un fichier ne doit pas être accepté comme Folder.",
        )

        node = folder_node(str(root))
        modal_html = str(render_block_modal("folder", {"node": node, "runtime": {}}).get("html") or "")
        inspector_html = str(render_block_inspector_panel("folder", {"node": node}).get("html") or "")
        card_html = str(render_block_node_card("folder", {"node": node}).get("html") or "")
        modal_css = (ROOT_DIR / "blocs" / "folder" / "assets" / "css" / "block_modal.css").read_text(encoding="utf-8")
        modal_js = (ROOT_DIR / "blocs" / "folder" / "assets" / "js" / "block_modal.js").read_text(encoding="utf-8")
        expect("data-folder-list" in modal_html, "Le modal Folder doit posséder l’explorateur autonome.")
        expect("Ajouter des fichiers" in modal_html, "Le modal Folder doit exposer l’upload.")
        expect("Actions" not in modal_html, "Le modal Folder ne doit pas afficher une colonne d'actions.")
        expect(
            "explorer/rename" not in modal_js and "explorer/delete" not in modal_js,
            "Le JavaScript Folder ne doit plus exposer renommer ou supprimer.",
        )
        expect('data-block-config-field="path"' in modal_html, "Le modal doit exposer la racine durable.")
        expect('data-block-config-field="path"' in inspector_html, "L’inspector doit exposer la racine durable.")
        expect(root.name in card_html and "__path" not in card_html, "La node-card Folder doit afficher la racine.")
        expect(
            '.folder-modal-panel[data-folder-panel="content"]:not([hidden])' in modal_css
            and ".folder-modal-panel[hidden]" in modal_css,
            "Les panneaux inactifs du modal Folder doivent rester masqués.",
        )
        expect(
            "grid-template-rows: auto auto minmax(0, 1fr);" in modal_css
            and "grid-template-rows: auto auto auto auto minmax(0, 1fr);" in modal_css
            and ".folder-list {\n  min-height: 0;" in modal_css,
            "The Folder list must remain bounded and scrollable inside the modal.",
        )


def test_bounded_explorer_and_upload() -> None:
    '''TC2/TC3/TC4 - Validate bounded read/write explorer operations.'''

    block = FolderBlock()
    with TemporaryDirectory(prefix="bloxsmith-folder-scope-") as temp_dir:
        base = Path(temp_dir)
        root = base / "root"
        outside = base / "outside"
        root.mkdir()
        outside.mkdir()
        (root / "alpha.txt").write_text("alpha", encoding="utf-8")
        (root / "nested").mkdir()
        (root / "nested" / "child.txt").write_text("child", encoding="utf-8")
        (outside / "secret.txt").write_text("secret", encoding="utf-8")
        node = folder_node(str(root))
        payload = {"root_dir": base}

        listing = block.handle_ui_request(node=node, route="explorer/list", method="POST", values={"relative_path": ""}, payload=payload)
        expect([entry["name"] for entry in listing["entries"]] == ["nested", "alpha.txt"], "Tri Folder incorrect.")
        nested_listing = block.handle_ui_request(node=node, route="explorer/list", method="POST", values={"relative_path": "nested"}, payload=payload)
        expect(nested_listing.get("at_root") is False, "Un sous-dossier ne doit pas être marqué comme racine.")
        expect(nested_listing.get("parent_path") == "", "Le parent d’un enfant direct doit pointer vers la racine.")

        created = block.handle_ui_request(
            node=node,
            route="explorer/create-directory",
            method="POST",
            values={"relative_path": "", "name": "created"},
            payload=payload,
        )
        expect((root / "created").is_dir() and created.get("ok") is True, "Création de dossier Folder échouée.")
        for removed_route in ("explorer/rename", "explorer/delete"):
            assert_folder_error(
                lambda removed_route=removed_route: block.handle_ui_request(
                    node=node,
                    route=removed_route,
                    method="POST",
                    values={"relative_path": "created"},
                    payload=payload,
                ),
                f"folder_route_unknown:{removed_route}",
            )

        uploaded = block.handle_ui_upload(
            node=node,
            action="upload_file",
            values={"relative_path": "created", "overwrite": False},
            filename="note.txt",
            content=b"first",
            content_type="text/plain",
            payload=payload,
        )
        expect(uploaded.get("file", {}).get("size") == 5, "Metadata upload Folder incorrecte.")
        expect((root / "created" / "note.txt").read_bytes() == b"first", "Contenu uploadé incorrect.")
        expect(not list((root / "created").glob(".bloxsmith-upload-*")), "Le fichier temporaire atomique doit disparaître.")

        assert_folder_error(
            lambda: block.handle_ui_upload(
                node=node,
                action="upload_file",
                values={"relative_path": "created", "overwrite": False},
                filename="note.txt",
                content=b"second",
                payload=payload,
            ),
            "folder_entry_exists",
        )
        block.handle_ui_upload(
            node=node,
            action="upload_file",
            values={"relative_path": "created", "overwrite": True},
            filename="note.txt",
            content=b"second",
            payload=payload,
        )
        expect((root / "created" / "note.txt").read_bytes() == b"second", "Écrasement confirmé non appliqué.")

        for unsafe_path in ("../outside", str(outside.resolve())):
            assert_folder_error(
                lambda unsafe_path=unsafe_path: block.handle_ui_request(
                    node=node,
                    route="explorer/list",
                    method="POST",
                    values={"relative_path": unsafe_path},
                    payload=payload,
                ),
                "folder_path_outside_root",
            )
        assert_folder_error(
            lambda: block.handle_ui_upload(
                node=node,
                action="upload_file",
                values={"relative_path": ""},
                filename="../escape.txt",
                content=b"blocked",
                payload=payload,
            ),
            "folder_entry_name_invalid",
        )
        link = root / "outside-link"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError:
            link = None
        if link is not None:
            listing = block.handle_ui_request(node=node, route="explorer/list", method="POST", values={"relative_path": ""}, payload=payload)
            expect(listing.get("skipped_symlinks") == 1, "Les symlinks doivent être masqués dans Folder.")
            assert_folder_error(
                lambda: block.handle_ui_request(
                    node=node,
                    route="explorer/list",
                    method="POST",
                    values={"relative_path": "outside-link"},
                    payload=payload,
                ),
                "folder_symlink_forbidden",
            )


def multipart_upload(server, node: dict, *, filename: str, content: bytes) -> dict:
    '''Upload one file through the public generic block multipart endpoint.'''

    boundary = f"----bloxsmith-folder-{uuid.uuid4().hex}"
    payload = json.dumps({"node": node, "action": "upload_file", "values": {"relative_path": "", "overwrite": False}})
    body = b"".join(
        [
            f"--{boundary}\r\n".encode(),
            b'Content-Disposition: form-data; name="payload"\r\n',
            b"Content-Type: application/json\r\n\r\n",
            payload.encode("utf-8"),
            b"\r\n",
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode(),
            b"Content-Type: text/plain\r\n\r\n",
            content,
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
    )
    request = Request(
        f"{server.base_url}/api/blocks/folder/ui-upload",
        data=body,
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urlopen(request, timeout=10) as response:
        expect(response.status == 201, "L’endpoint multipart Folder doit répondre 201.")
        return json.loads(response.read().decode("utf-8"))


def test_http_upload_and_runtime_modes() -> None:
    '''TC4/TC6 - Validate generic multipart dispatch and both graph runtimes.'''

    with isolated_server() as server:
        root = server.root_dir / "folder-fixture"
        root.mkdir()
        (root / "one.txt").write_text("one", encoding="utf-8")
        node = folder_node(str(root))
        uploaded = multipart_upload(server, node, filename="from-browser.txt", content=b"browser")
        expect(uploaded.get("ok") is True, "L’upload multipart Folder doit réussir.")
        expect((root / "from-browser.txt").read_bytes() == b"browser", "L’endpoint doit écrire dans la racine Folder.")

        invalid_payload = json.dumps({"node": node, "values": {"relative_path": "../"}}).encode("utf-8")
        invalid_request = Request(
            f"{server.base_url}/api/blocks/folder/explorer/list",
            data=invalid_payload,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            urlopen(invalid_request, timeout=10)
        except HTTPError as exc:
            error_payload = json.loads(exc.read().decode("utf-8"))
            expect(exc.code == 400, "Une traversée Folder doit répondre HTTP 400.")
            expect("folder_path_outside_root" in str(error_payload.get("error")), "Erreur HTTP Folder non structurée.")
        else:
            raise AssertionError("La traversée HTTP Folder aurait dû être refusée.")

        document = graph_payload(
            "F5 Folder runtime",
            [node, directory_list_node(), display_node("display-1", "Display", 760, 120)],
            [
                data_edge("edge-folder-list", "folder-1", 1, "directory-list-1", 1),
                data_edge("edge-list-display", "directory-list-1", 1, "display-1", 1),
            ],
        )
        for runtime_mode in ("centralized", "zeromq_active"):
            created = create_run_api(server, document, runtime_mode=runtime_mode)
            run = wait_for_run_terminal(server, str(created.get("run_id") or ""), timeout_sec=25)
            expect(run.get("status") == "success", f"Le run Folder {runtime_mode} doit réussir.")
            folder_output = run.get("output_values", {}).get("folder-1:1", {})
            expect(folder_output.get("value") == str(root.resolve()), f"Sortie Folder incorrecte en {runtime_mode}.")
            expect(folder_output.get("content_type") == "directory/path", f"Type Folder incorrect en {runtime_mode}.")
            list_output = run.get("output_values", {}).get("directory-list-1:1", {}).get("value")
            expect(len(json.loads(list_output or "[]")) == 2, f"Directory List ne consomme pas Folder en {runtime_mode}.")
            if runtime_mode == "zeromq_active":
                expect(
                    run.get("results", {}).get("folder-1", {}).get("transport") == "zeromq_active",
                    "Folder doit être exécuté via le worker actif générique.",
                )


def main() -> None:
    test_direct_runtime_and_ui()
    test_bounded_explorer_and_upload()
    test_http_upload_and_runtime_modes()
    print("[ok] F5.33_folder_block")


if __name__ == "__main__":
    main()
