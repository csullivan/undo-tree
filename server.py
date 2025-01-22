import uuid
from flask import Flask, request, jsonify

app = Flask(__name__)

# A global dictionary of file_id -> graph data.
# Example structure:
# graphs["default"] = {
#    "nodes": {
#       "root": { "id": "root", "delta": None, "parents": [], "children": [] }
#    },
#    "current_node_id": "root",
#    "pending_changes": []
# }
graphs = {}

def get_or_init_file_graph(file_id: str):
    """
    Retrieve the graph for the given file_id, or initialize it if it doesn't exist.
    This ensures each file_id has its own independent graph state.
    """
    if file_id not in graphs:
        # Initialize a new graph with a 'root' node
        graphs[file_id] = {
            "nodes": {
                "root": {
                    "id": "root",
                    "delta": None,
                    "parents": [],
                    "children": []
                }
            },
            "current_node_id": "root",
            "pending_changes": []
        }
    return graphs[file_id]

@app.route("/api/nodes", methods=["POST"])
def add_node():
    """
    Endpoint for the VS Code extension (or any client) to POST new deltas.
    Expects JSON payload like:
    {
       "file_id": "some_file.txt",
       "parent_node_id": "some_node_id",
       "delta": { ... }  or "delta": "some textual change"
    }
    """
    data = request.json
    file_id = data.get("file_id", "default")  # fallback if not provided
    parent_id = data.get("parent_node_id")
    delta = data.get("delta")

    if not parent_id or delta is None:
        return jsonify({"error": "parent_node_id and delta are required"}), 400

    graph_data = get_or_init_file_graph(file_id)

    if parent_id not in graph_data["nodes"]:
        return jsonify({"error": f"Parent node {parent_id} does not exist"}), 404

    # Generate a unique ID for the new node
    new_node_id = str(uuid.uuid4())

    # Create the node
    graph_data["nodes"][new_node_id] = {
        "id": new_node_id,
        "delta": delta,
        "parents": [parent_id],
        "children": []
    }

    # Link from parent
    graph_data["nodes"][parent_id]["children"].append(new_node_id)
    # Optionally update current_node_id to the newly created node
    graph_data["current_node_id"] = new_node_id

    return jsonify({
        "message": f"Node {new_node_id} created successfully in file {file_id}",
        "node_id": new_node_id
    }), 201

@app.route("/api/graph", methods=["GET"])
def get_graph():
    """
    Endpoint to GET the entire graph for a given file_id.
    Usage: GET /api/graph?file_id=my_file.txt
    Returns the nodes and which node is currently 'active'.
    """
    file_id = request.args.get("file_id", "default")
    graph_data = get_or_init_file_graph(file_id)

    return jsonify({
        "nodes": graph_data["nodes"],
        "current_node_id": graph_data["current_node_id"]
    }), 200

@app.route("/api/navigate", methods=["POST"])
def navigate_node():
    """
    Called by the TUI (or other client) to navigate the graph.
    JSON payload example:
    {
      "file_id": "my_file.txt",
      "current_node_id": "some_current_node",
      "target_node_id": "some_other_node"
    }

    We either "apply" or "revert" based on whether current_node_id == target_node_id or not.

    The server:
      - sets graph_data["current_node_id"] = current_node_id
      - enqueues a pending change referencing 'target_node_id' for the extension to process.
    """
    data = request.json
    file_id = data.get("file_id", "default")
    current_node_id = data.get("current_node_id")
    change_node_id = data.get("target_node_id")

    graph_data = get_or_init_file_graph(file_id)

    if not change_node_id:
        return jsonify({"error": "target_node_id is required"}), 400
    if change_node_id not in graph_data["nodes"]:
        return jsonify({"error": f"Node {change_node_id} does not exist"}), 404
    if current_node_id not in graph_data["nodes"]:
        return jsonify({"error": f"Current node {current_node_id} does not exist"}), 404

    # Decide if we are applying or reverting
    if current_node_id == change_node_id:
        mode = "apply"
        node_id = change_node_id
    else:
        mode = "revert"
        node_id = current_node_id

    # Update the current node
    graph_data["current_node_id"] = current_node_id

    node_delta = graph_data["nodes"][change_node_id]["delta"]
    # Enqueue a pending change
    change = {
        "node_id": node_id,
        "delta": node_delta,
        "mode": mode,
    }
    graph_data["pending_changes"].append(change)

    return jsonify({
        "message": f"[{file_id}] Current node set to {current_node_id}. Delta from {change_node_id} queued for extension.",
        "mode": mode
    }), 200

@app.route("/api/poll_changes", methods=["GET"])
def poll_changes():
    """
    Called by the editor extension to retrieve ALL pending changes for a file.
    Example: GET /api/poll_changes?file_id=my_file.txt
    Returns a JSON array of all pending changes, oldest first.
    If empty, returns [].
    """
    file_id = request.args.get("file_id", "default")
    graph_data = get_or_init_file_graph(file_id)
    return jsonify(graph_data["pending_changes"]), 200

@app.route("/api/ack_changes", methods=["POST"])
def ack_changes():
    """
    Called by the editor extension after it has applied some (or all) pending changes.
    JSON example:
    {
      "file_id": "my_file.txt",
      "node_ids": ["...", "...", ...]
    }

    The server verifies these node_ids match the front of the queue in order.
    If they match, remove them. Otherwise, return an error.
    """
    data = request.json
    file_id = data.get("file_id", "default")
    ack_node_ids = data.get("node_ids")

    graph_data = get_or_init_file_graph(file_id)
    pending = graph_data["pending_changes"]

    if not ack_node_ids or not isinstance(ack_node_ids, list):
        return jsonify({"error": "node_ids (list) is required"}), 400

    if len(ack_node_ids) > len(pending):
        return jsonify({
            "error": "More node_ids acknowledged than are pending"
        }), 400

    # Check each ack_node_id against the queue in order
    for i, node_id in enumerate(ack_node_ids):
        if pending[i]["node_id"] != node_id:
            return jsonify({
                "error": f"Mismatch at index {i}: "
                         f"pending node_id={pending[i]['node_id']} but ack={node_id}"
            }), 400

    # Remove the acknowledged subset from the front of the queue
    graph_data["pending_changes"] = pending[len(ack_node_ids):]

    return jsonify({
        "message": f"Acknowledged changes for file {file_id}.",
        "remaining_pending_count": len(graph_data["pending_changes"])
    }), 200


if __name__ == "__main__":
    # For production, use a proper WSGI server like gunicorn.
    app.run(host="0.0.0.0", port=5000, debug=True)