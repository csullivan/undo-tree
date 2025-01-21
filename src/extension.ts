import * as vscode from 'vscode';
import fetch from 'node-fetch';  // If you're on Node 18+ with ESM, you can use globalThis.fetch.
import { diff_match_patch, DIFF_INSERT, DIFF_DELETE, patch_obj } from 'diff-match-patch';

const isOptInOnly = true; // Set to true to make tracking opt-in, false to track all files

const SERVER_URL = "http://localhost:5000"; // or use a setting or environment variable

console.log(`[Extension] Hello from undo-tree!`);

interface PendingChange {
    node_id: string;
    delta: string; // This will be the patch text from diff_match_patch.patch_toText(...)
    mode: string;  // "apply" or "revert" or your custom modes
}

interface FileState {
    fileId: string;
    content: string;           // The local content snapshot
    parentNodeId: string;      // The current node in the server’s graph
    lastDeltaSendTime?: number;
    pendingDelta?: string;
    sendTimer?: NodeJS.Timeout;
}

// Keep track of open file states
const fileStates = new Map<string, FileState>();

// How often (in ms) we poll the server for incoming changes
const POLL_INTERVAL = 300;
// How long (in ms) after typing stops do we consider a "batch" of edits done?
// TODO(csullivan): Consider eventually changing this to measure a batch as a
// period of changes made over a short interval
const DELTA_BATCH_INTERVAL = 1000;

// Create a single instance of diff_match_patch to use everywhere
const dmp = new diff_match_patch();

export function activate(context: vscode.ExtensionContext) {
    console.log(`[Extension] Activated!`);

    // Register the 'enableTracking' command
    const enableTrackingCommand = vscode.commands.registerCommand('undoTreeExtension.enableTracking', async () => {
        const editor = vscode.window.activeTextEditor;
        if (!editor) {
            vscode.window.showInformationMessage('No active editor found.');
            return;
        }

        const doc = editor.document;
        if (doc.uri.scheme !== 'file') {
            vscode.window.showInformationMessage('Only file-based documents are supported.');
            return;
        }

        const fileName = doc.fileName;
        if (fileStates.has(fileName)) {
            vscode.window.showInformationMessage('Undo Tree Tracking is already enabled for this file.');
            return;
        }

        await initializeFileState(doc);
        vscode.window.showInformationMessage(`Undo Tree Tracking enabled for ${fileName}.`);

        // Run the specified command in a new terminal
        const fileId = fileStates.get(fileName)?.fileId;
        if (fileId) {
            const terminal = vscode.window.createTerminal(`UndoTree-${fileId}`);
            terminal.show();
            // TODO(csullivan): Make this configurable
            const command = `/home/scratch.chrsullivan_gpu/projects/undo-tree/venv-undo-tree/bin/python /home/scratch.chrsullivan_gpu/projects/undo-tree/tui_client.py --file_id ${fileId}`;
            terminal.sendText(command);
        }
    });
    context.subscriptions.push(enableTrackingCommand);

    // 1) Poll the server on an interval
    const poller = setInterval(() => {
        // For each open file, poll for changes
        for (const state of fileStates.values()) {
            pollAndApplyChanges(state).catch(err =>
                console.error("[Extension] Error polling for changes:", err)
            );
        }
    }, POLL_INTERVAL);
    context.subscriptions.push({ dispose: () => clearInterval(poller) });

    // 2) On opening a text document, initialize our state
    if (!isOptInOnly) { // Only initialize automatically if not in opt-in mode
        vscode.workspace.onDidOpenTextDocument(doc => {
            if (doc.uri.scheme === 'file') {
                initializeFileState(doc);
            }
        }, null, context.subscriptions);

        // Also initialize state for already-open documents
        vscode.workspace.textDocuments.forEach(doc => {
            if (doc.uri.scheme === 'file') {
                initializeFileState(doc);
            }
        });
    }

    // 3) Listen for text changes
    vscode.workspace.onDidChangeTextDocument(event => {
        if (event.document.uri.scheme !== 'file') {
            return;
        }
        const doc = event.document;
        const state = fileStates.get(doc.fileName);
        if (!state) {
            return;
        }

        // Store the *entire* new text in pendingDelta for now,
        // but we'll compute and send a patch in sendDeltaToServer below.
        state.pendingDelta = doc.getText();

        // Reset or start our batch-timer
        if (state.sendTimer) {
            clearTimeout(state.sendTimer);
        }
        state.sendTimer = setTimeout(() => {
            sendDeltaToServer(state).catch(err =>
                console.error("[Extension] Error sending delta to server:", err)
            );
        }, DELTA_BATCH_INTERVAL);
    }, null, context.subscriptions);

    // 4) Cleanup on close if desired
    vscode.workspace.onDidCloseTextDocument(doc => {
        const state = fileStates.get(doc.fileName);
        if (state?.sendTimer) {
            clearTimeout(state.sendTimer);
        }
        fileStates.delete(doc.fileName);
    }, null, context.subscriptions);
}

export function deactivate() {
    console.log("[Extension] Deactivated.");
}

/**
 * Initialize FileState for a newly opened text document.
 * - Snapshots content
 * - Ensures a graph (or node) for this file is created on the server
 */
async function initializeFileState(doc: vscode.TextDocument) {
    const fileName = doc.fileName;
    if (fileStates.has(fileName)) {
        return;
    }

    const content = doc.getText();
    const fileId = fileName;  // For real usage, sanitize or customize this ID

    try {
        // Example: ensure the server has a graph for fileId
        const graphResp = await fetch(`${SERVER_URL}/api/graph?file_id=${encodeURIComponent(fileId)}`);
        if (graphResp.status !== 200) {
            console.error(`[Extension] Error fetching/creating graph for ${fileId}:`, await graphResp.text());
            return;
        }

        // A simple assumption: the server can give us a 'root' or we define it:
        const parentNodeId = "root";

        // (Optional) Create an initial snapshot node from 'root'
        // So that there is a distinct node representing the initial file contents
        const nodeId = await createNodeOnServer(fileId, parentNodeId, content, /*isFullContent*/ true);
        if (!nodeId) {
            console.error("[Extension] Could not create initial node for file:", fileId);
            return;
        }

        const fileState: FileState = {
            fileId,
            content,
            parentNodeId: nodeId,
        };
        fileStates.set(fileName, fileState);
        console.log(`[Extension] Initialized file state for '${fileName}'. Node = ${nodeId}`);
    } catch (err) {
        console.error("[Extension] Error initializing file state:", err);
    }
}

/**
 * Sends any pending changes as a diff/patch to the server,
 * then updates our local state accordingly.
 */
async function sendDeltaToServer(state: FileState) {
    const oldText = state.content;
    const newText = state.pendingDelta;
    // If no change or no new text, bail out
    if (!newText || newText === oldText) {
        return;
    }

    // 1. Create a patch from old to new using diff-match-patch
    const patchList = dmp.patch_make(oldText, newText);
    const patchText = dmp.patch_toText(patchList);
    if (!patchText) {
        return;
    }

    // 2. Send this patch to the server
    const newNodeId = await createNodeOnServer(state.fileId, state.parentNodeId, patchText);
    if (!newNodeId) {
        console.error("[Extension] createNodeOnServer failed");
        return;
    }

    // 3. Update local state
    state.parentNodeId = newNodeId;
    state.content = newText;
    state.pendingDelta = undefined;
    console.log(`[Extension] Updated parent node for file '${state.fileId}' to ${newNodeId}`);
}

/**
 * Create a node on the server, posting either a patch delta or (optionally)
 * a full snapshot if isFullContent is true.
 *
 * The server needs to understand which is which. One approach is to have a
 * boolean flag or different fields. For demonstration, we're sending:
 *   delta: The patch (or full text)
 *   is_full_content: optional boolean
 */
async function createNodeOnServer(
    fileId: string, 
    parentNodeId: string, 
    deltaOrContent: string, 
    isFullContent: boolean = false
): Promise<string | null> {
    const payload = {
        file_id: fileId,
        parent_node_id: parentNodeId,
        delta: deltaOrContent,
        is_full_content: isFullContent
    };

    const resp = await fetch(`${SERVER_URL}/api/nodes`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });

    if (resp.status === 201) {
        const data = await resp.json();
        console.log(`[Extension] Created node ${data.node_id} (isFullContent=${isFullContent})`);
        return data.node_id;
    } else {
        console.error("[Extension] Error creating node:", await resp.text());
        return null;
    }
}

/**
 * Called periodically to poll the server for changes (patches).
 * If the server returns a patch with mode="revert", it means
 * "this is the forward patch from A->B, but we want to revert B->A".
 */
async function pollAndApplyChanges(state: FileState) {
    const url = `${SERVER_URL}/api/poll_changes?file_id=${encodeURIComponent(state.fileId)}`;
    const resp = await fetch(url);
    if (resp.status !== 200) {
        console.error(`[Extension] Unexpected status polling changes: ${resp.status} -`, await resp.text());
        return;
    }

    const changes: PendingChange[] = await resp.json();
    if (!changes || changes.length === 0) {
        return; // No changes
    }

    const nodeIds: string[] = [];
    for (const ch of changes) {
        // ch.delta is the forward patch text from A->B
        const forwardPatchList: (new () => patch_obj)[] = dmp.patch_fromText(ch.delta);

        let newText = state.content;

        if (ch.mode === "apply") {
            // Normal forward apply: patch_apply( forward, oldText = A ) => B
            const [appliedText, results] = dmp.patch_apply(forwardPatchList, state.content);
            newText = appliedText;

        } else if (ch.mode === "revert") {
            // The server only has the forward patch (A->B),
            // but we want to go from B->A. Invert the patch first.
            const reversedPatchList = invertPatch(forwardPatchList);

            // Now apply the reversed patch to the local content (which is B)
            const [appliedText, results] = dmp.patch_apply(reversedPatchList as unknown as (new () => patch_obj)[], state.content);
            newText = appliedText;

        } else {
            console.log(`[Extension] Unhandled change mode: ${ch.mode}`);
            continue;
        }

        // If we got new text from the patch, replace in the editor
        if (newText !== state.content) {
            const textEditor = await getOpenTextEditor(state.fileId);
            if (textEditor) {
                await replaceAllText(textEditor, newText);
                state.content = newText;
            }
        }

        // Update our notion of "current node" to the server's node
        nodeIds.push(ch.node_id);
        state.parentNodeId = ch.node_id;
    }

    // Acknowledge the changes so the server knows we're up to date
    const ackResp = await fetch(`${SERVER_URL}/api/ack_changes`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            file_id: state.fileId,
            node_ids: nodeIds
        })
    });

    if (ackResp.status === 200) {
        console.log(`[Extension] Acknowledged changes: ${nodeIds.join(", ")}`);
    } else {
        console.error("[Extension] Error acknowledging changes:", await ackResp.text());
    }
}

/**
 * Invert (reverse) a forward patch (A -> B) into its opposite (B -> A).
 *
 * Diff-match-patch doesn't provide a built-in "reverse patch" function,
 * so we manually:
 *   - swap DIFF_INSERT <-> DIFF_DELETE
 *   - swap patch_obj.start1 <-> patch_obj.start2
 *   - swap patch_obj.length1 <-> patch_obj.length2
 *   - reverse the order of patch objects
 */
function invertPatch(forwardPatchList: (new () => patch_obj)[]): patch_obj[] {
    // Deep-copy first, so we don't mutate the original patch
    const reversed = dmp.patch_deepCopy(forwardPatchList) as unknown as patch_obj[];

    // Reverse the order of patches because the last patch in A->B
    // should be the first to apply in B->A
    reversed.reverse();

    // Now invert each patch's diffs and swap patch metadata
    for (const patch of reversed) {
        // Swap the patch range fields
        const tmpStart = patch.start1;
        patch.start1 = patch.start2;
        patch.start2 = tmpStart;

        const tmpLength = patch.length1;
        patch.length1 = patch.length2;
        patch.length2 = tmpLength;

        // Invert each diff inside the patch
        for (const diff of patch.diffs) {
            if (diff[0] === DIFF_INSERT) {
                diff[0] = DIFF_DELETE;
            } else if (diff[0] === DIFF_DELETE) {
                diff[0] = DIFF_INSERT;
            }
            // DIFF_EQUAL remains the same
        }
    }
    return reversed;
}

/**
 * Return an open TextEditor for the given fileId (assumed = fileName)
 */
async function getOpenTextEditor(fileId: string): Promise<vscode.TextEditor | undefined> {
    for (const ed of vscode.window.visibleTextEditors) {
        if (ed.document.fileName === fileId) {
            return ed;
        }
    }
    return undefined;
}

/**
 * Replace all text in the given TextEditor with newContent.
 */
async function replaceAllText(editor: vscode.TextEditor, newContent: string) {
    const doc = editor.document;
    const fullRange = new vscode.Range(
        doc.positionAt(0),
        doc.positionAt(doc.getText().length)
    );

    await editor.edit(editBuilder => {
        editBuilder.replace(fullRange, newContent);
    });
}