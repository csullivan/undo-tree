import urwid
import collections

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
    Return a dict: node -> list of children
    Also returns a dict: node -> list of parents
    For a tree-like DAG, each node has at most 1 parent 
    (or 0 if root).
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

    Returns the 'width' of the entire subtree for root,
    so that the caller can place subtrees next to each other
    if needed.
    """
    children_map, _ = build_adjacency_list(graph.edges)
    children = children_map[root]
    children.sort()  # optional stable ordering by ID

    # If no children, just place the node at (x, y)
    if not children:
        graph.nodes[root] = (x, y)
        # minimal width = 1 'unit' for this leaf
        return 1

    # Otherwise, layout each child subtree
    total_width = 0
    child_positions = []  # store (child_id, subtree_center_x)
    for child in children:
        # place this child subtree at the *current* x offset
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

    # Remove trailing extra spacing:
    total_width -= x_spacing
    if total_width < 1:
        total_width = 1

    # Now, place 'root' so it is centered above its children
    leftmost_center = child_positions[0][1]
    rightmost_center = child_positions[-1][1]
    parent_center_x = (leftmost_center + rightmost_center) / 2
    # The absolute X for the parent is x + parent_center_x
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


def render_graph_as_ascii(graph: Graph):
    """
    Convert the graph into a 2D ASCII art string.
    Each node = 'o' or 'x' if it's current_node.
    """
    # Find min/max x/y
    xs = [pos[0] for pos in graph.nodes.values()]
    ys = [pos[1] for pos in graph.nodes.values()]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    # Add some padding around bounding box
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
        char = choose_edge_char(r1, c1, r2, c2)
        draw_line(canvas, r1, c1, r2, c2, char, height, width)

    # Place nodes
    for node_id, (x, y) in graph.nodes.items():
        r, c = to_canvas_coords(x, y)
        if 0 <= r < height and 0 <= c < width:
            canvas[r][c] = "x" if node_id == graph.current_node else "o"

    return "\n".join("".join(row) for row in canvas)


def create_example_graph():
    """
    Create a simple tree-like DAG:
    
       n0
        \
         n1
         /|\
        n2 n3 n4

    We'll designate n0 as the root.
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
    layout_balanced_tree(g, root,
                         x=0, y=0, 
                         x_spacing=4,   # horizontal spacing
                         y_spacing=3)   # vertical spacing

    g.set_current_node("n0")  # highlight the root for demo
    return g


def main():
    g = create_example_graph()

    ascii_art = render_graph_as_ascii(g)
    text_widget = urwid.Text(ascii_art, align='left')
    fill = urwid.Filler(text_widget, valign='top')

    def handle_input(key):
        if key in ('q', 'Q', 'esc'):
            raise urwid.ExitMainLoop()
        # Arrow-key navigation goes here

    loop = urwid.MainLoop(fill, unhandled_input=handle_input)
    loop.run()


if __name__ == "__main__":
    main()