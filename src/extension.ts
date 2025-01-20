import * as vscode from 'vscode';
import fetch from 'node-fetch';  // If you're on Node 18+ with ESM, you can use globalThis.fetch.

const SERVER_URL = "http://localhost:5000"; // or use a setting or environment variable

console.log(`[Extension] Hello from undo-tree!`);

interface PendingChange {
    node_id: string;
    delta: string;
    mode: string; // "apply", "insert", or "delete" - depends on your server logic
}

interface FileState {
    fileId: string;
    content: string;
    parentNodeId: string;      // track the "current" node in the server’s graph
    lastDeltaSendTime?: number;
    pendingDelta?: string;
    sendTimer?: NodeJS.Timeout;
}

const fileStates = new Map<string, FileState>();

// How often (in ms) we poll the server for incoming changes.
const POLL_INTERVAL = 300;
// How long (in ms) after typing stops do we consider a "batch" of edits done?
// TODO(csullivan): Consider eventually changing this to measure a batch as a
// period of changes made over a short interval
const DELTA_BATCH_INTERVAL = 1000;

export function activate(context: vscode.ExtensionContext) {
    console.log(`[Extension] Hello from activate!`);
    // Set up an interval to poll the server for changes to *any* open files.
    const poller = setInterval(() => {
        console.log(`[Extension] polling!`);
        for (const state of fileStates.values()) {
            pollAndApplyChanges(state).catch(err =>
                console.error("[Extension] Error polling for changes:", err)
            );
        }
    }, POLL_INTERVAL);

    context.subscriptions.push({ dispose: () => clearInterval(poller) });

    // When a text document is opened, we init its state (snapshot content).
    // This also covers newly opened or newly created documents.
    vscode.workspace.onDidOpenTextDocument(doc => {
        if (doc.uri.scheme === 'file') {
            initializeFileState(doc);
        }
    }, null, context.subscriptions);

    // If the extension is activated with a file already open, initialize for those
    vscode.workspace.textDocuments.forEach(doc => {
        if (doc.uri.scheme === 'file') {
            initializeFileState(doc);
        }
    });

    // Listen for text changes
    vscode.workspace.onDidChangeTextDocument(event => {
        if (event.document.uri.scheme !== 'file') {
            return;
        }
        const doc = event.document;
        const state = fileStates.get(doc.fileName);
        if (!state) {
            return;
        }

        // The easiest approach: store the entire new text as "pendingDelta".
        // A more advanced approach might compute a minimal diff from state.content to doc.getText().
        state.pendingDelta = doc.getText();

        // Restart the send timer to wait DELTA_BATCH_INTERVAL after last keystroke
        if (state.sendTimer) {
            clearTimeout(state.sendTimer);
        }
        state.sendTimer = setTimeout(() => {
            sendDeltaToServer(state).catch(err =>
                console.error("[Extension] Error sending delta to server:", err)
            );
        }, DELTA_BATCH_INTERVAL);
    }, null, context.subscriptions);

    // When the extension is deactivated or the file is closed, we might want to flush changes
    vscode.workspace.onDidCloseTextDocument(doc => {
        // If you want to handle closing logic, do it here
        const state = fileStates.get(doc.fileName);
        if (state?.sendTimer) {
            clearTimeout(state.sendTimer);
        }
        fileStates.delete(doc.fileName);
    }, null, context.subscriptions);
}

/**
 * Initializes our internal FileState for a newly opened text document.
 * 
 * 1. Takes an initial snapshot (content).
 * 2. Creates/ensures a graph on the server for this file.
 * 3. Creates a root node or fetches existing root node for that file.
 */
async function initializeFileState(doc: vscode.TextDocument) {
    const fileName = doc.fileName;
    if (fileStates.has(fileName)) {
        return; // Already initialized
    }

    const content = doc.getText();
    const fileId = fileName;  // For real usage, you might want to sanitize the file name or use an ID from config.

    try {
        // Step 1: Ensure the server has a graph for fileId (similar to `GET /api/graph?file_id=xyz`).
        // Minimal example - we'll just do a GET, ignoring details.
        const graphResp = await fetch(`${SERVER_URL}/api/graph?file_id=${encodeURIComponent(fileId)}`);
        if (graphResp.status !== 200) {
            console.error(`[Extension] Error fetching/creating graph for ${fileId}:`, await graphResp.text());
            return;
        }

        // For the sake of demonstration, we set the parentNodeId to "root".
        // In reality, you might parse the server response to find or create a real root node.
        const parentNodeId = "root";

        // Create an initial snapshot node from root if you want a distinct node for "initial content"
        const nodeId = await createNodeOnServer(fileId, parentNodeId, content);
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
 * Sends the current 'pendingDelta' to the server, if any, and updates local state.
 */
async function sendDeltaToServer(state: FileState) {
    if (!state.pendingDelta || state.pendingDelta === state.content) {
        // Nothing new or no changes
        return;
    }
    const delta = diffText(state.content, state.pendingDelta);
    if (!delta) {
        return;
    }

    // The current parent is the last node we created.
    const newNodeId = await createNodeOnServer(state.fileId, state.parentNodeId, delta);
    if (!newNodeId) {
        console.error("[Extension] createNodeOnServer failed");
        return;
    }

    // Update local state
    state.parentNodeId = newNodeId;
    state.content = state.pendingDelta;
    state.pendingDelta = undefined;
    console.log(`[Extension] Updated parent node for file '${state.fileId}' to ${newNodeId}`);
}

/**
 * A naive "diff" method. You can replace this with something more sophisticated.
 * Currently returns the entire new text if it's different, or empty if not.
 */
function diffText(oldText: string, newText: string): string {
    if (oldText === newText) {
        return "";
    }
    // Minimal approach: just return the entire new text
    return newText;
}

/**
 * Creates a new node on the server, similar to create_node(...) in client.py
 */
async function createNodeOnServer(fileId: string, parentNodeId: string, delta: string): Promise<string | null> {
    const payload = {
        file_id: fileId,
        parent_node_id: parentNodeId,
        delta
    };
    const resp = await fetch(`${SERVER_URL}/api/nodes`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
    if (resp.status === 201) {
        const data = await resp.json();
        console.log(`[Extension] Created node ${data.node_id} with delta: ${delta}`);
        return data.node_id;
    } else {
        console.error("[Extension] Error creating node:", await resp.text());
        return null;
    }
}

/**
 * Poll the server for all pending changes for a given file, apply them, and acknowledge them.
 */
async function pollAndApplyChanges(state: FileState) {
    const url = `${SERVER_URL}/api/poll_changes?file_id=${encodeURIComponent(state.fileId)}`;
    console.log(`[Extension] pollingAndApplyingChanges for ${encodeURIComponent(state.fileId)}`);

    const resp = await fetch(url);
    if (resp.status !== 200) {
        console.error(`[Extension] Unexpected status polling changes: ${resp.status} -`, await resp.text());
        return;
    }

    const changes: PendingChange[] = await resp.json();
    if (!changes || changes.length === 0) {
        // No changes pending
        return;
    }

    const nodeIds: string[] = [];
    for (const ch of changes) {
        // In a real scenario, you'd interpret ch.delta and ch.mode, then do actual edits in the open editor.
        // For simplicity, we will do "replace entire content" if mode === 'apply' or something similar.
        console.log(`[Extension] ${ch.mode}ing change for node ${ch.node_id} with delta: ${ch.delta}`);

        // Apply the change to the open document (if it's open)
        // We'll do a naive approach: set entire content = ch.delta
        // This is not always correct, but demonstrates the concept.
        const textEditor = await getOpenTextEditor(state.fileId);
        if (textEditor) {
            await replaceAllText(textEditor, ch.delta);
            // Update local content
            state.content = ch.delta;
        }

        nodeIds.push(ch.node_id);
        // Update the parent node id to the node we just applied so any 
        // future changes will be applied to this node.
        state.parentNodeId = ch.node_id;
    }

    // Acknowledge changes
    const ackPayload = {
        file_id: state.fileId,
        node_ids: nodeIds
    };
    const ackResp = await fetch(`${SERVER_URL}/api/ack_changes`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(ackPayload)
    });
    if (ackResp.status === 200) {
        console.log(`[Extension] Acknowledged changes: ${nodeIds.join(", ")}`);
    } else {
        console.error("[Extension] Error acknowledging changes:", await ackResp.text());
    }
}

/**
 * Helper to get the current open TextEditor for the given fileId.
 * We are using the assumption that `fileId === fileName` in this example.
 */
async function getOpenTextEditor(fileId: string): Promise<vscode.TextEditor | undefined> {
    const editors = vscode.window.visibleTextEditors;
    for (const ed of editors) {
        if (ed.document.fileName === fileId) {
            return ed;
        }
    }
    return undefined;
}

/**
 * Helper to replace all text in a given TextEditor with new content.
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

export function deactivate() {
    // Cleanup if necessary
    console.log("[Extension] Deactivated.");
}