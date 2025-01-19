import uuid
from flask import Flask, request, jsonify

app = Flask(__name__)

# In-memory graph data structure
# 'pending_changes' is a queue (FIFO) of dicts: [ {"node_id": ..., "delta": ...}, ... ]
graph = {
    "nodes": {
        "root": {
            "id": "root",
            "delta": None,      # The snapshot of the file at the root, optional
            "parents": [],
            "children": []
        }
    },
    "current_node_id": "root",
    "pending_changes": []
}


@app.route("/api/nodes", methods=["POST"])
def add_node():
    """
    Endpoint for the VS Code extension to POST new deltas when a new change is created.
    JSON payload example:
    {
       "parent_node_id": "some_node_id",
       "delta": { ... }  // or "delta": "some textual change"
    }
    """
    data = request.json
    parent_id = data.get("parent_node_id")
    delta = data.get("delta")

    if not parent_id or delta is None:
        return jsonify({"error": "parent_node_id and delta are required"}), 400

    if parent_id not in graph["nodes"]:
        return jsonify({"error": f"Parent node {parent_id} does not exist"}), 404

    # Generate a unique ID for the new node
    new_node_id = str(uuid.uuid4())

    # Create the node
    graph["nodes"][new_node_id] = {
        "id": new_node_id,
        "delta": delta,
        "parents": [parent_id],
        "children": []
    }

    # Link from parent
    graph["nodes"][parent_id]["children"].append(new_node_id)
    graph["current_node_id"] = new_node_id

    return jsonify({
        "message": "Node created successfully",
        "node_id": new_node_id
    }), 201


@app.route("/api/graph", methods=["GET"])
def get_graph():
    """
    Endpoint for TUI to GET the entire graph (or you can filter as needed).
    Returns the nodes and which node is currently 'active'.
    """
    return jsonify({
        "nodes": graph["nodes"],
        "current_node_id": graph["current_node_id"]
    }), 200


@app.route("/api/navigate", methods=["POST"])
def navigate_node():
    """
    Called by the TUI when the user navigates to a different node.
    JSON payload example:
    {
      "target_node_id": "some_node_id"
    }

    The server will:
      1. Update `current_node_id` to `target_node_id`.
      2. Enqueue a new pending change (node_id + delta).
    """
    data = request.json
    current_node_id = data.get("current_node_id")
    change_node_id = data.get("target_node_id")
    if current_node_id == change_node_id:
        mode = "apply"
    else:
        mode = "revert"

    if not change_node_id:
        return jsonify({"error": "target_node_id is required"}), 400

    if change_node_id not in graph["nodes"]:
        return jsonify({"error": f"Node {change_node_id} does not exist"}), 404

    # Update current node
    graph["current_node_id"] = current_node_id

    node_delta = graph["nodes"][change_node_id]["delta"]
    # Enqueue a pending change
    change = {
        "node_id": change_node_id,
        "delta": node_delta,
        "mode": mode,
    }
    graph["pending_changes"].append(change)

    return jsonify({
        "message": f"Current node changed to {change_node_id}. Delta queued for extension."
    }), 200


@app.route("/api/poll_changes", methods=["GET"])
def poll_changes():
    """
    Called by the VS Code extension to retrieve ALL pending changes.
    Returns a JSON array of all pending changes, oldest (first enqueued) first.
    Example response:
    [
      { "node_id": "node1", "delta": ... },
      { "node_id": "node2", "delta": ... },
      ...
    ]
    If empty, returns [].
    """
    return jsonify(graph["pending_changes"]), 200


@app.route("/api/ack_changes", methods=["POST"])
def ack_changes():
    """
    Called by the VS Code extension after it has successfully applied
    some (or all) pending changes.
    JSON payload example:
    {
      "node_ids": ["...", "...", ...]
    }

    The server verifies these node_ids match the front of the queue in order.
    If they match, remove them from 'pending_changes'. If not, return an error.
    """
    data = request.json
    ack_node_ids = data.get("node_ids")

    if not ack_node_ids or not isinstance(ack_node_ids, list):
        return jsonify({"error": "node_ids (list) is required"}), 400

    # We'll remove from the front of the list as many as match in order.
    pending = graph["pending_changes"]
    
    if len(ack_node_ids) > len(pending):
        return jsonify({
            "error": "More node_ids acknowledged than are pending"
        }), 400

    # Check each ack_node_id against the pending list in order
    for i, node_id in enumerate(ack_node_ids):
        if pending[i]["node_id"] != node_id:
            return jsonify({
                "error": f"Mismatch at index {i}. "
                         f"Pending node_id={pending[i]['node_id']} but ack={node_id}"
            }), 400

    # If all matched, pop them from the front
    # Slicing approach: keep the remainder from the end
    graph["pending_changes"] = pending[len(ack_node_ids):]

    return jsonify({
        "message": "Acknowledged changes successfully.",
        "remaining_pending_count": len(graph["pending_changes"])
    }), 200


if __name__ == "__main__":
    # Run the Flask development server. 
    # For production, consider using a production WSGI server like gunicorn.
    app.run(host="0.0.0.0", port=5000, debug=True)