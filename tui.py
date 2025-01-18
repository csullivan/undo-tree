import urwid
import collections
import random

class Graph:
    """
    For simplicity, store node coordinates once we compute them.
    edges: list of (source, target)
    nodes: dict of node_id => (x,y)
    """
    def __init__(self):
        self.nodes = {}
        self.edges = []
        self.current_node = None
        # We'll store an optional "selected_edge" to highlight
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
    """
    Return two dicts:
      children_map: node -> list of children
      parents_map: node -> list of parents
    """
    children_map = collections.defaultdict(list)
    parents_map = collections.defaultdict(list)
    for src, dst in edges:
        children_map[src].append(dst)
        parents_map[dst].append(src)
    return children_map, parents_map


def layout_balanced_tree(graph, root, x=0, y=0, 
                         x_spacing=3, y_spacing=2):
    """
    Recursively lay out the subtree rooted at 'root' in a 
    balanced, centered-above-children way.

    Returns the 'width' of the entire subtree for root.
    """
    # We rebuild adjacency inside because we may call this function recursively
    children_map, _ = build_adjacency_list(graph.edges)
    children = children_map[root]
    # Sorting children is optional, ensures stable ordering
    children.sort()

    # If no children, just place the node at (x, y)
    if not children:
        graph.nodes[root] = (x, y)
        return 1

    # Otherwise, layout each child subtree
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
        # The child's subtree center is total_width + (subtree_width/2)
        child_center_x = total_width + subtree_width / 2
        child_positions.append((child, child_center_x))
        total_width += subtree_width + x_spacing

    # Remove the trailing spacing:
    total_width -= x_spacing
    if total_width < 1:
        total_width = 1

    # Now place root so it's centered above its children
    leftmost_center = child_positions[0][1]
    rightmost_center = child_positions[-1][1]
    parent_center_x = (leftmost_center + rightmost_center) / 2
    abs_x = x + parent_center_x

    graph.nodes[root] = (abs_x, y)
    return total_width


def choose_edge_char(r1, c1, r2, c2):
    """
    Determine which ASCII char to use for a line step
    based on slope.
    """
    if r1 == r2:
        return "-"
    elif c1 == c2:
        return "|"
    else:
        dy = r2 - r1
        dx = c2 - c1
        # If slope is positive, use '\', else '/'
        return "\\" if (dy * dx > 0) else "/"


def draw_line(canvas, r1, c1, r2, c2, char, height, width):
    """
    Draw a Bresenham line on the canvas from (r1,c1) to (r2,c2).
    """
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


def render_graph_as_ascii(graph: Graph, selected_edge=None):
    """
    Convert the graph into a 2D ASCII art string.
    Each node = 'o' or 'x' if it's the current_node.
    If an edge == selected_edge, draw it with '*' instead of the normal ASCII chars.
    """
    # Find the bounding box (min_x, max_x, min_y, max_y)
    xs = [pos[0] for pos in graph.nodes.values()]
    ys = [pos[1] for pos in graph.nodes.values()]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    # Add some padding
    width = int((max_x - min_x + 1) * 2 + 4)
    height = int((max_y - min_y + 1) * 2 + 4)

    # Blank canvas
    canvas = [[" " for _ in range(width)] for _ in range(height)]

    def to_canvas_coords(x, y):
        col = int((x - min_x) * 2)
        row = int((y - min_y) * 2)
        return (row, col)

    # Draw edges
    for (src, dst) in graph.edges:
        x1, y1 = graph.nodes[src]
        x2, y2 = graph.nodes[dst]
        r1, c1 = to_canvas_coords(x1, y1)
        r2, c2 = to_canvas_coords(x2, y2)

        # Decide whether this edge is the "selected" edge
        is_selected = (selected_edge == (src, dst))
        if is_selected:
            # Draw with '*' (no slope shape)
            edge_char = '*'
        else:
            # Normal slope-based ASCII
            edge_char = choose_edge_char(r1, c1, r2, c2)

        draw_line(canvas, r1, c1, r2, c2, edge_char, height, width)

    # Place nodes
    for node_id, (x, y) in graph.nodes.items():
        r, c = to_canvas_coords(x, y)
        if 0 <= r < height and 0 <= c < width:
            # Mark current node with 'x', others with 'o'
            canvas[r][c] = "x" if node_id == graph.current_node else "o"

    return "\n".join("".join(row) for row in canvas)


def create_example_graph():
    """
    Create a sample tree-like DAG:
    
       n0
        \
         n1
         /|\
        n2 n3 n4
        /
       ...
    """
    g = Graph()
    for node_id in ["n0", "n1", "n2", "n3", "n4", "n5", "n6"]:
        g.add_node(node_id)

    g.add_edge("n0", "n1")
    g.add_edge("n1", "n2")
    g.add_edge("n1", "n3")
    g.add_edge("n1", "n4")
    g.add_edge("n2", "n5")
    g.add_edge("n2", "n6")

    # Lay it out
    root = "n0"
    layout_balanced_tree(g, root, x=0, y=0, x_spacing=4, y_spacing=3)

    # Current node is n0
    g.set_current_node("n0")
    return g

def create_larger_example_graph():
    """
    Create a deterministic "larger" DAG with 20 nodes (n0..n19).
    Each node has 1–5 children, with no merges (i.e., each node has at most one parent).
    Uses a fixed seed so you'll always get the same structure each run.
    """

    # We'll build a list of nodes first:
    g = Graph()
    num_nodes = 20
    for i in range(num_nodes):
        g.add_node(f"n{i}")

    # Use a BFS-like approach to assign children. 
    # Each node we pop can get 1..5 children, 
    # but we never reassign parents (no merges).
    random.seed(42)
    queue = [0]  # start from node index 0
    next_node = 1

    while queue and next_node < num_nodes:
        parent = queue.pop(0)
        children_count = random.randint(1, 5)
        for _ in range(children_count):
            if next_node < num_nodes:
                g.add_edge(f"n{parent}", f"n{next_node}")
                queue.append(next_node)
                next_node += 1
            else:
                break

    # For layout, treat n0 as the "root" 
    # (strictly speaking, it's the first node we assigned children from).
    layout_balanced_tree(g, root="n0", x_spacing=4, y_spacing=3)

    # Arbitrarily pick n0 as our initial "current_node."
    g.set_current_node("n0")
    return g


def main():
    g = create_example_graph()
    g = create_larger_example_graph()
    

    # Build adjacency lists so we can navigate
    children_map, parents_map = build_adjacency_list(g.edges)

    # Keep track of which child-index is selected for each node 
    # (so pressing Down goes to that child).
    # Left/Right will cycle through the available children.
    child_selection_map = collections.defaultdict(int)

    # A small utility to refresh the ASCII after each keypress
    def update_view():
        # Refresh the selected_edge in the graph object 
        # based on current_node and which child is chosen
        cur = g.current_node
        c_idx = child_selection_map[cur]
        if children_map[cur]:
            # Ensure c_idx is in range
            c_idx %= len(children_map[cur])
            child_selection_map[cur] = c_idx
            child_id = children_map[cur][c_idx]
            g.selected_edge = (cur, child_id)
        else:
            g.selected_edge = None

        ascii_art = render_graph_as_ascii(g, selected_edge=g.selected_edge)
        text_widget.set_text(ascii_art)

    # Initial render
    text_widget = urwid.Text(render_graph_as_ascii(g), align='left')
    fill = urwid.Filler(text_widget, valign='top')

    def handle_input(key):
        if key in ('q', 'Q', 'esc'):
            raise urwid.ExitMainLoop()

        cur = g.current_node

        # ---- Left/Right: pick which child to go down to ----
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

        # ---- Down: move to the selected child ----
        elif key == 'down':
            if children_map[cur]:
                c_idx = child_selection_map[cur]
                next_node = children_map[cur][c_idx]
                g.set_current_node(next_node)

        # ---- Up: move to the first parent (if any) ----
        elif key == 'up':
            if parents_map[cur]:
                # Just pick the first parent for simplicity
                parent = parents_map[cur][0]
                g.set_current_node(parent)
                # Optionally, set the parent's child_selection_map so that 
                # its selected child is "cur"
                if cur in children_map[parent]:
                    idx = children_map[parent].index(cur)
                    child_selection_map[parent] = idx

        update_view()

    loop = urwid.MainLoop(fill, unhandled_input=handle_input)
    loop.run()


if __name__ == "__main__":
    main()