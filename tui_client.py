import urwid
import collections
import random
import requests
import argparse

SERVER_URL = "http://localhost:5000"
FILE_ID = "default"  # will be overridden by --file_id

class Graph:
    """
    Store node coordinates once we compute them.
    edges: list of (source, target)
    nodes: dict of node_id => (x, y)
    """
    def __init__(self):
        self.nodes = {}
        self.edges = []
        self.current_node = None
        self.selected_edge = None

    def add_node(self, node_id):
        self.nodes[node_id] = (None, None)  # Coordinates set later

    def add_edge(self, source_id, target_id):
        self.edges.append((source_id, target_id))

    def set_current_node(self, node_id):
        if node_id not in self.nodes:
            raise ValueError(f"Node {node_id} not in graph.")
        self.current_node = node_id

def build_adjacency_list(edges):
    children_map = collections.defaultdict(list)
    parents_map = collections.defaultdict(list)
    for src, dst in edges:
        children_map[src].append(dst)
        parents_map[dst].append(src)
    return children_map, parents_map

def layout_balanced_tree(graph, root, x=0, y=0, x_spacing=3, y_spacing=2):
    """
    Recursively position nodes in a simple 'layered' tree layout.
    """
    children_map, _ = build_adjacency_list(graph.edges)
    children = children_map[root]
    # Sort children so layout is reproducible
    children.sort()

    if not children:
        graph.nodes[root] = (x, y)
        return 1

    total_width = 0
    child_positions = []
    for child in children:
        subtree_width = layout_balanced_tree(
            graph, child,
            x=x + total_width,
            y=y + y_spacing,
            x_spacing=x_spacing,
            y_spacing=y_spacing
        )
        child_center_x = total_width + subtree_width / 2
        child_positions.append((child, child_center_x))
        total_width += subtree_width + x_spacing

    total_width -= x_spacing  # remove trailing spacing
    if total_width < 1:
        total_width = 1

    leftmost_center = child_positions[0][1]
    rightmost_center = child_positions[-1][1]
    parent_center_x = (leftmost_center + rightmost_center) / 2
    abs_x = x + parent_center_x

    graph.nodes[root] = (abs_x, y)
    return total_width

def choose_edge_char(r1, c1, r2, c2):
    if r1 == r2:
        return "-"
    elif c1 == c2:
        return "|"
    else:
        dy = r2 - r1
        dx = c2 - c1
        # positive slope => '\\', negative slope => '/'
        return "\\" if (dy * dx > 0) else "/"

def draw_line(canvas, r1, c1, r2, c2, char, height, width):
    # Bresenham-ish line
    x1, y1 = c1, r1
    x2, y2 = c2, r2
    dx = abs(x2 - x1)
    sx = 1 if x1 < x2 else -1
    dy = -abs(y2 - y1)
    sy = 1 if y1 < y2 else -1
    err = dx + dy

    while True:
        if 0 <= y1 < height and 0 <= x1 < width:
            canvas[y1][x1] = char
        if x1 == x2 and y1 == y2:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x1 += sx
        if e2 <= dx:
            err += dx
            y1 += sy

def build_full_canvas(graph: Graph, selected_edge=None):
    """
    Return a 2D array of characters representing the ASCII layout
    of the entire graph.
    """
    xs = [pos[0] for pos in graph.nodes.values()]
    ys = [pos[1] for pos in graph.nodes.values()]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    # Add some padding
    width = int((max_x - min_x + 1) * 2 + 4)
    height = int((max_y - min_y + 1) * 2 + 4)

    canvas = [[" " for _ in range(width)] for _ in range(height)]

    def to_canvas_coords(x, y):
        # scale x,y => row,col
        col = int((x - min_x) * 2)
        row = int((y - min_y) * 2)
        return (row, col)

    # Draw edges
    for (src, dst) in graph.edges:
        x1, y1 = graph.nodes[src]
        x2, y2 = graph.nodes[dst]
        r1, c1 = to_canvas_coords(x1, y1)
        r2, c2 = to_canvas_coords(x2, y2)
        is_selected = (selected_edge == (src, dst))
        edge_char = '*' if is_selected else choose_edge_char(r1, c1, r2, c2)
        draw_line(canvas, r1, c1, r2, c2, edge_char, height, width)

    # Draw nodes
    for node_id, (x, y) in graph.nodes.items():
        r, c = to_canvas_coords(x, y)
        if 0 <= r < height and 0 <= c < width:
            canvas[r][c] = "x" if node_id == graph.current_node else "o"

    return canvas

def crop_canvas_around_current_node(canvas, graph, desired_width, desired_height):
    """
    Extract a (desired_height x desired_width) subregion of 'canvas',
    centered around the current node 'x' if possible.
    """
    full_height = len(canvas)
    full_width = len(canvas[0]) if full_height > 0 else 0

    # Find 'x' in the canvas
    row_center, col_center = None, None
    for r in range(full_height):
        for c in range(full_width):
            if canvas[r][c] == 'x':
                row_center, col_center = r, c
                break
        if row_center is not None:
            break

    if row_center is None or col_center is None:
        # fallback to top-left
        row_center, col_center = 0, 0

    # clamp the desired size
    if desired_width > full_width:
        desired_width = full_width
    if desired_height > full_height:
        desired_height = full_height

    # center subregion
    row_top = row_center - desired_height // 2
    col_left = col_center - desired_width // 2

    max_row_top = full_height - desired_height
    max_col_left = full_width - desired_width
    if row_top < 0:
        row_top = 0
    elif row_top > max_row_top:
        row_top = max_row_top

    if col_left < 0:
        col_left = 0
    elif col_left > max_col_left:
        col_left = max_col_left

    cropped_rows = []
    for r in range(row_top, row_top + desired_height):
        row_slice = canvas[r][col_left:col_left + desired_width]
        cropped_rows.append("".join(row_slice))

    return "\n".join(cropped_rows)

def fetch_and_build_graph():
    """
    Fetch the current graph from /api/graph for the chosen FILE_ID
    and build a Graph() object we can render with ASCII art.
    """
    resp = requests.get(f"{SERVER_URL}/api/graph?file_id={FILE_ID}")
    if resp.status_code != 200:
        raise RuntimeError(f"Failed to fetch graph: {resp.status_code} {resp.text}")
    data = resp.json()  # { "nodes": { "node_id": {...}, ... }, "current_node_id": "..." }

    g = Graph()

    # 1) Create all nodes in the local TUI structure
    for node_id in data["nodes"].keys():
        g.add_node(node_id)

    # 2) Create edges from each node to its children
    for node_id, info in data["nodes"].items():
        for child_id in info["children"]:
            g.add_edge(node_id, child_id)

    # 3) Pick a "root" for the layout algorithm
    #    If there's a "root" node, we use that. Otherwise, we use current_node_id.
    root_id = "root" if "root" in data["nodes"] else data["current_node_id"]

    # Layout the nodes for ASCII display
    layout_balanced_tree(g, root_id, x=0, y=0, x_spacing=4, y_spacing=3)

    # 4) Mark the server's current node as TUI current node
    g.set_current_node(data["current_node_id"])

    return g

def navigate_to_node(graph, navigate_to_node_id, change_node_id):
    """
    1) Send a request to /api/navigate for FILE_ID
    2) Update our local Graph's current node
    """
    try:
        # Tell the server we want to navigate
        payload = {
            "file_id": FILE_ID,
            "target_node_id": change_node_id,
            "current_node_id": navigate_to_node_id
        }
        requests.post(f"{SERVER_URL}/api/navigate", json=payload)
    except requests.RequestException as e:
        print(f"[TUI] Error navigating to {change_node_id}: {e}")
        return

    graph.set_current_node(navigate_to_node_id)

def main():
    # Parse --file_id from command line (default: "default")
    parser = argparse.ArgumentParser()
    parser.add_argument("--file_id", default="default", help="File ID to visualize")
    args = parser.parse_args()

    global FILE_ID
    FILE_ID = args.file_id

    try:
        g = fetch_and_build_graph()
    except RuntimeError as e:
        print(f"Error initializing TUI: {e}")
        return

    # Build adjacency maps for quick navigation
    children_map, parents_map = build_adjacency_list(g.edges)
    child_selection_map = collections.defaultdict(int)

    text_widget = urwid.Text("", align='left')
    fill = urwid.Filler(text_widget, valign='top')

    def update_view():
        cur = g.current_node
        c_idx = child_selection_map[cur]
        if children_map[cur]:
            c_idx %= len(children_map[cur])
            child_selection_map[cur] = c_idx
            child_id = children_map[cur][c_idx]
            g.selected_edge = (cur, child_id)
        else:
            g.selected_edge = None

        full_canvas = build_full_canvas(g, selected_edge=g.selected_edge)
        # Attempt to use the terminal size (or fallback to some minimal)
        cols, rows = loop.screen.get_cols_rows()
        view_width = max(20, cols - 2)
        view_height = max(10, rows - 2)

        ascii_art = crop_canvas_around_current_node(full_canvas, g, view_width, view_height)
        text_widget.set_text(ascii_art)

    def handle_input(key):
        if key in ('q', 'Q', 'esc'):
            raise urwid.ExitMainLoop()

        cur = g.current_node

        if key == 'left':
            if children_map[cur]:
                c_idx = child_selection_map[cur]
                c_idx = (c_idx - 1) % len(children_map[cur])
                child_selection_map[cur] = c_idx

        elif key == 'right':
            if children_map[cur]:
                c_idx = child_selection_map[cur]
                c_idx = (c_idx + 1) % len(children_map[cur])
                child_selection_map[cur] = c_idx

        elif key == 'down':
            if children_map[cur]:
                c_idx = child_selection_map[cur]
                next_node = children_map[cur][c_idx]
                navigate_to_node(g, next_node, next_node)  # going down => '+'

        elif key == 'up':
            # If multiple parents, we just pick the first (or you can cycle)
            if parents_map[cur]:
                parent = parents_map[cur][0]
                navigate_to_node(g, parent, cur)  # going up => '-'
                # Also set parent's child_selection index so that up-down toggles effectively
                if cur in children_map[parent]:
                    idx = children_map[parent].index(cur)
                    child_selection_map[parent] = idx

        update_view()

    loop = urwid.MainLoop(fill, unhandled_input=handle_input)
    update_view()
    loop.run()

if __name__ == "__main__":
    main()