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


def layout_balanced_tree(graph, root, x=0, y=0, 
                         x_spacing=3, y_spacing=2):
    children_map, _ = build_adjacency_list(graph.edges)
    children = children_map[root]
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

    # Remove the trailing spacing
    total_width -= x_spacing
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
        return "\\" if (dy * dx > 0) else "/"


def draw_line(canvas, r1, c1, r2, c2, char, height, width):
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


### NEW OR MODIFIED CODE ###
def build_full_canvas(graph: Graph, selected_edge=None):
    """
    Instead of returning a single string, build and return
    the 2D array (list of lists of single characters) for
    the entire graph bounding box.
    """
    xs = [pos[0] for pos in graph.nodes.values()]
    ys = [pos[1] for pos in graph.nodes.values()]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    # Padding
    width = int((max_x - min_x + 1) * 2 + 4)
    height = int((max_y - min_y + 1) * 2 + 4)

    # Create blank canvas
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
        is_selected = (selected_edge == (src, dst))
        edge_char = '*' if is_selected else choose_edge_char(r1, c1, r2, c2)
        draw_line(canvas, r1, c1, r2, c2, edge_char, height, width)

    # Draw nodes
    for node_id, (x, y) in graph.nodes.items():
        r, c = to_canvas_coords(x, y)
        if 0 <= r < height and 0 <= c < width:
            canvas[r][c] = "x" if node_id == graph.current_node else "o"

    return canvas


### NEW OR MODIFIED CODE ###
def crop_canvas_around_current_node(canvas, graph, desired_width, desired_height):
    """
    Safely slice out a subregion of size (desired_height x desired_width)
    from 'canvas', centered around the 'x' node if possible.
    """
    full_height = len(canvas)
    full_width = len(canvas[0]) if full_height > 0 else 0

    # Find 'x' in the canvas (the current node's position)
    row_center, col_center = None, None
    for r in range(full_height):
        for c in range(full_width):
            if canvas[r][c] == 'x':
                row_center, col_center = r, c
                break
        if row_center is not None:
            break

    if row_center is None or col_center is None:
        # Fallback if no 'x' was found:
        row_center, col_center = 0, 0

    # 1) Clamp the desired view size if it's bigger than the entire canvas
    if desired_width > full_width:
        desired_width = full_width
    if desired_height > full_height:
        desired_height = full_height

    # 2) Attempt to center (row_center, col_center) in that subregion
    row_top = row_center - desired_height // 2
    col_left = col_center - desired_width // 2

    # 3) Clamp row_top/col_left so subregion is fully within the canvas
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

    # 4) Build the cropped ASCII
    cropped_rows = []
    for r in range(row_top, row_top + desired_height):
        row_slice = canvas[r][col_left:col_left + desired_width]
        cropped_rows.append("".join(row_slice))

    return "\n".join(cropped_rows)



def create_example_graph():
    g = Graph()
    for node_id in ["n0", "n1", "n2", "n3", "n4", "n5", "n6"]:
        g.add_node(node_id)

    g.add_edge("n0", "n1")
    g.add_edge("n1", "n2")
    g.add_edge("n1", "n3")
    g.add_edge("n1", "n4")
    g.add_edge("n2", "n5")
    g.add_edge("n2", "n6")

    layout_balanced_tree(g, "n0", x=0, y=0, x_spacing=4, y_spacing=3)
    g.set_current_node("n0")
    return g

def create_larger_example_graph():
    g = Graph()
    num_nodes = 20
    for i in range(num_nodes):
        g.add_node(f"n{i}")

    random.seed(42)
    queue = [0]
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

    layout_balanced_tree(g, root="n0", x_spacing=4, y_spacing=3)
    g.set_current_node("n0")
    return g


def main():
    # g = create_example_graph()
    g = create_larger_example_graph()

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

        ### NEW OR MODIFIED CODE ###
        # Instead of rendering a single full string, build the full canvas,
        # then crop around the current node based on the terminal size
        # (or you can pick a fixed size, e.g., 30x15)
        full_canvas = build_full_canvas(g, selected_edge=g.selected_edge)

        # 1) Build the full canvas
        # Get terminal size (cols, rows)
        cols, rows = loop.screen.get_cols_rows()

        # Subtract a margin if you need to account for borders or other widgets
        view_width = max(20, cols - 2)
        view_height = max(10, rows - 2)

        # Now safely crop around the current node:
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
                g.set_current_node(next_node)
        elif key == 'up':
            if parents_map[cur]:
                parent = parents_map[cur][0]
                g.set_current_node(parent)
                if cur in children_map[parent]:
                    idx = children_map[parent].index(cur)
                    child_selection_map[parent] = idx

        update_view()

    loop = urwid.MainLoop(fill, unhandled_input=handle_input)
    update_view()  # initial render
    loop.run()


if __name__ == "__main__":
    main()