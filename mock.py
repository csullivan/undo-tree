import time
import requests
import sys

SERVER_URL = "http://localhost:5000"

def create_node(file_id, parent_id, delta):
    """
    Helper function to create a new node in the server's graph for file_id.
    """
    payload = {
        "file_id": file_id,
        "parent_node_id": parent_id,
        "delta": delta
    }
    resp = requests.post(f"{SERVER_URL}/api/nodes", json=payload)
    if resp.status_code != 201:
        print(f"Error creating node (parent={parent_id}, delta={delta}): {resp.text}")
        return None
    data = resp.json()
    print(f"Created node {data['node_id']} with delta: {delta} in file {file_id}")
    return data["node_id"]

def poll_and_apply_changes(file_id):
    """
    Polls the server for all pending changes in file_id.
    Simulates applying them, then acknowledges them in bulk.
    """
    resp = requests.get(f"{SERVER_URL}/api/poll_changes?file_id={file_id}")
    if resp.status_code == 200:
        changes = resp.json()  # list of { "node_id": ..., "delta": ..., "mode": ... }
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

        ack_payload = { "file_id": file_id, "node_ids": node_ids }
        ack_resp = requests.post(f"{SERVER_URL}/api/ack_changes", json=ack_payload)
        if ack_resp.status_code == 200:
            print(f"[Extension] Acknowledged changes: {node_ids}")
        else:
            print(f"[Extension] Error acknowledging changes: {ack_resp.text}")
    else:
        print(f"[Extension] Unexpected status polling changes: {resp.status_code} {resp.text}")

def main():
    file_id = "example.txt"
    if len(sys.argv) > 1:
        file_id = sys.argv[1]  # e.g. python mock_editor.py my_file_id.txt

    # 1) Check or init the graph
    graph_resp = requests.get(f"{SERVER_URL}/api/graph?file_id={file_id}")
    if graph_resp.status_code != 200:
        print(f"Error fetching/creating graph for {file_id}: {graph_resp.text}")
        return

    # 2) Create some nodes
    root_id = "root"

    # 2) Create an initial snapshot from root
    n1 = create_node(file_id,root_id, "Hello World!")
    # 3) Create subsequent nodes
    n2 = create_node(file_id, n1, " How")
    n3 = create_node(file_id, n2, " are")
    n4 = create_node(file_id, n3, " you?")
    n5 = create_node(file_id, n2, " do")
    n6 = create_node(file_id, n5, " you")
    n7 = create_node(file_id, n6, " like")
    n8 = create_node(file_id, n7, " your")
    n9 = create_node(file_id, n8, " tea?")
    print("\n--- Finished creating sample nodes. ---\n")

    # 3) Start polling loop
    print("[Extension] Starting to poll for pending changes...")
    try:
        while True:
            poll_and_apply_changes(file_id)
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[Extension] Stopped polling. Exiting...")

if __name__ == "__main__":
    main()