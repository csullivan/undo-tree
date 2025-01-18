import urwid

class Graph:
    """
    A simple DAG structure with nodes (having x,y coordinates)
    and edges (directed pairs).
    """
    def __init__(self):
        # List of node IDs => (x, y) positions
        self.nodes = {}
        # List of edges => (source_id, target_id)
        self.edges = []
        # Optionally track a "current node" to highlight
        self.current_node = None

    def add_node(self, node_id, x, y):
        self.nodes[node_id] = (x, y)

    def add_edge(self, source_id, target_id):
        self.edges.append((source_id, target_id))

    def set_current_node(self, node_id):
        if node_id in self.nodes:
            self.current_node = node_id
        else:
            raise ValueError(f"Node {node_id} does not exist.")

def create_example_graph():
    g = Graph()
    # Add nodes with (x, y) coordinates
    g.add_node("n0", 4, 0)   # top node
    g.add_node("n1", 4, 3)   # left
    g.add_node("n2", 4, 6)   # middle
    g.add_node("n3", 2, 6)   # right
    g.add_node("n4", 6, 6)   # far left
    
    g.add_edge("n0", "n1")
    g.add_edge("n1", "n2")
    g.add_edge("n1", "n3")
    g.add_edge("n1", "n4")

    # Optionally set current node:
    g.set_current_node("n0")

    return g

def draw_line(canvas, r1, c1, r2, c2, char, height, width):
    """
    Draw a line on the 2D 'canvas' from (r1, c1) to (r2, c2) using Bresenham's algorithm.
    'char' is the character to use for drawing.
    'height' and 'width' are the canvas boundaries.
    """
    # Convert to Bresenham's typical x,y naming
    # x => column, y => row
    x1, y1 = c1, r1
    x2, y2 = c2, r2
    
    dx = abs(x2 - x1)
    sx = 1 if x1 < x2 else -1
    dy = -abs(y2 - y1)
    sy = 1 if y1 < y2 else -1
    err = dx + dy

    while True:
        # Draw only if in bounds
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

def choose_edge_char(r1, c1, r2, c2):
    if r1 == r2:
        return "-"
    elif c1 == c2:
        return "|"
    else:
        # slope-based guess
        dy = r2 - r1
        dx = c2 - c1
        if dy * dx > 0:
            return "\\"
        else:
            return "/"
        
def render_graph_as_ascii(graph: Graph):
    # 1) Determine bounding box
    xs = [pos[0] for pos in graph.nodes.values()]
    ys = [pos[1] for pos in graph.nodes.values()]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    # Add some padding
    width = (max_x - min_x + 1) * 2 + 3
    height = (max_y - min_y + 1) * 2 + 3
    canvas = [[" " for _ in range(width)] for _ in range(height)]

    def to_canvas_coords(x, y):
        # Expand x and y into row,col with spacing
        col = (x - min_x) * 2
        row = (y - min_y) * 2
        return (row, col)

    for (src, dst) in graph.edges:
        x1, y1 = graph.nodes[src]
        x2, y2 = graph.nodes[dst]
        r1, c1 = to_canvas_coords(x1, y1)
        r2, c2 = to_canvas_coords(x2, y2)

        # Choose an ASCII char based on slope
        char = choose_edge_char(r1, c1, r2, c2)
        draw_line(canvas, r1, c1, r2, c2, char, height, width)

    # Place nodes
    for node_id, (x, y) in graph.nodes.items():
        r, c = to_canvas_coords(x, y)
        if 0 <= r < height and 0 <= c < width:
            canvas[r][c] = "x" if node_id == graph.current_node else "o"

    # Convert to string
    lines = ["".join(row) for row in canvas]
    return "\n".join(lines)

def main():
    # Build the graph
    g = create_example_graph()

    # Initial rendering
    ascii_art = render_graph_as_ascii(g)

    # Create a Text widget to display it
    text_widget = urwid.Text(ascii_art, align='left')

    # A simple filler to hold that text
    fill = urwid.Filler(text_widget, valign='top')

    # Main event loop
    def handle_input(key):
        if key in ('q', 'Q', 'esc'):
            raise urwid.ExitMainLoop()
        # You could handle arrow keys here later:
        # if key == 'up':
        #     # move current node to something else
        #     # update text_widget.set_text(render_graph_as_ascii(g))
        #     pass

    loop = urwid.MainLoop(fill, unhandled_input=handle_input)
    loop.run()

if __name__ == "__main__":
    main()