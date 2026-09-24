# Folder Block

<!-- block-metadata:start -->
[![Block version: 0.1.0](https://img.shields.io/badge/block-0.1.0-blue)](model.json)
[![BloxSmith compatibility: 1.0.9](https://img.shields.io/badge/BloxSmith-1.0.9-brightgreen)](compatibility.json)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)

Verified BloxSmith versions: **1.0.9** (bundled-block tests; see [test evidence](compatibility.json)).
<!-- block-metadata:end -->


## Role

`folder` represents one server-side working directory and emits its absolute path. Its modal also provides a read/write explorer constrained to that configured directory.

## Ports

- Inputs: none.
- Outputs:
  - `path` (`id: 1`): absolute directory path emitted as `directory/path` and `message/*`.

## Configuration

- `path`: directory root. Relative values are resolved from the application working root; the shared path browser normally stores an absolute server path.

The configured path is both the runtime value and the security boundary of the explorer. Navigating inside the modal never changes this output path.

## Runtime Behavior

The block validates that `path` exists and is a directory, then emits its resolved absolute path on every output. Missing paths and regular files fail with a structured block error. The same `execute_runtime()` contract is used by One Shot Simulation (`centralized`) and Active Runtime (`zeromq_active`).

## Read/Write Explorer

The modal opens on the **Contents** tab and lists descendants of the configured root with name, type, size, and modification date. It supports:

- navigation inside child directories and back to the configured root;
- creating a child directory;
- uploading one or more browser files, including drag and drop;
- refreshing the listing.

The modal header and explorer controls remain visible while large directory listings scroll inside the bounded file table.

When the current server directory is not writable, the modal remains usable for navigation but disables creation and upload controls and marks the view as read-only.

Filesystem changes are immediate and do not mutate the blueprint. Changing the configured root remains a normal block configuration edit and must be applied explicitly.

## Security Boundary

Explorer requests carry only paths relative to the configured root. `block.py` resolves and validates every target again on the server. It rejects:

- absolute explorer paths;
- `..` traversal;
- path separators in entry names;
- symbolic links and paths that resolve outside the root;
- uploads larger than 50 MiB;
- implicit overwrites unless the user confirms replacement.

The explorer manipulates the server filesystem, while uploads originate from the browser workstation. Existing files and directories cannot be renamed or deleted from this modal.

## UI Ownership

The node card, inspector, modal, CSS, and JavaScript live in this package. The shared framework only mounts the surfaces, provides the path picker, and transports JSON or multipart requests through generic block UI interfaces.

## Compatibility policy

[compatibility.json](compatibility.json) records HackInvent's verified BloxSmith versions and test evidence. Only the versions listed above have been verified, using the block-owned suites in a **bundled-block test installation**. This is not a certification of managed-package installation, every browser/OS, or live provider availability. Other framework versions are unverified, not necessarily incompatible.

The block-version badge follows `model.json`, not a published Git tag. `unversioned` means that no block release version is declared; no number is inferred from the framework version. The framework still uses `model.json` for its runtime/install contract; the tester-owned JSON does not replace it. Official integration tests run in the private `bloxmith-blocs` workspace. Test helpers and the proprietary framework are not bundled in this public block repository.

## Properties ergonomics

Modal and inspector styles are owned by this package and scoped to its exact
release. Forms adapt to narrow panels, checkboxes stay beside their labels, and
long values do not widen the inspector. Existing labels are associated with
controls; keyboard navigation complements the block’s own tab handlers.
These presentation helpers do not change port bindings, authored settings,
runtime behavior or the block’s original surface cleanup.
