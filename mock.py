import time
import requests

SERVER_URL = "http://localhost:5000"

def create_node(parent_id, delta):
    """
    Helper function to create a new node in the server's graph.
    Returns the new node's ID.
    """
    payload = {
        "parent_node_id": parent_id,
        "delta": delta
    }
    resp = requests.post(f"{SERVER_URL}/api/nodes", json=payload)
    if resp.status_code != 201:
        print(f"Error creating node (parent={parent_id}, delta={delta}): {resp.text}")
        return None
    data = resp.json()
    print(f"Created node {data['node_id']} with delta: {delta}")
    return data["node_id"]

def poll_and_apply_changes():
    """
    Polls the server for all pending changes. If any are found, we simulate
    "applying" them (just printing to console), then acknowledge them.
    """
    resp = requests.get(f"{SERVER_URL}/api/poll_changes")
    if resp.status_code == 200:
        changes = resp.json()  # Should be a list of { "node_id": ..., "delta": ... }
        if not changes:
            # No pending changes, do nothing
            return
        # Simulate applying each change
        node_ids = []
        for ch in changes:
            node_id = ch["node_id"]
            delta = ch["delta"]
            mode = ch["mode"]
            # Simulate "applying" the delta in the editor
            print(f"[Extension] {mode.capitalize()}ing change for node {node_id} with delta: {delta}")
            node_ids.append(node_id)

        # Acknowledge them all at once
        ack_payload = {
            "node_ids": node_ids
        }
        ack_resp = requests.post(f"{SERVER_URL}/api/ack_changes", json=ack_payload)
        if ack_resp.status_code == 200:
            print(f"[Extension] Acknowledged changes: {node_ids}")
        else:
            print(f"Error acknowledging changes: {ack_resp.text}")
    elif resp.status_code == 204:
        # 204 means no pending changes (some servers might just return an empty list with 200)
        return
    else:
        print(f"Unexpected status polling changes: {resp.status_code} {resp.text}")

def main():
    # 1) Check current graph
    graph_resp = requests.get(f"{SERVER_URL}/api/graph")
    if graph_resp.status_code != 200:
        print(f"Error fetching graph: {graph_resp.text}")
        return

    graph_data = graph_resp.json()
    # By default, the server code has a "root" node with ID "root".
    # We'll attach our new nodes to "root" or to one another in sequence.

    root_id = "root"

    # 2) Create an initial snapshot from root
    n1 = create_node(root_id, "Hello World!")
    # 3) Create subsequent nodes
    n2 = create_node(n1, " How")
    n3 = create_node(n2, " are")
    n4 = create_node(n3, " you?")
    n5 = create_node(n2, " do")
    n6 = create_node(n5, " you")
    n7 = create_node(n6, " like")
    n8 = create_node(n7, " your")
    n9 = create_node(n8, " tea?")
    print("\n--- Finished creating sample nodes. ---\n")

    # 4) Start polling loop
    print("[Extension] Starting to poll for pending changes...")
    try:
        while True:
            poll_and_apply_changes()
            # Sleep a bit between polls
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n[Extension] Stopped polling. Exiting...")

if __name__ == "__main__":
    main()

