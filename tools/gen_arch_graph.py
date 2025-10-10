# tools/gen_arch_graph.py
import ast
import os

from graphviz import Digraph


def find_imports(root_dir="app"):
    edges = set()
    for dirpath, _, files in os.walk(root_dir):
        for f in files:
            if f.endswith(".py"):
                path = os.path.join(dirpath, f)
                module = path.replace("/", ".").removesuffix(".py")
                with open(path, encoding="utf-8") as fh:
                    try:
                        tree = ast.parse(fh.read())
                    except SyntaxError:
                        continue
                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom) and node.module:
                        dep = node.module
                        if dep.startswith("app."):
                            edges.add((module, dep))
    return edges


def draw_graph(edges, output="architecture.gv"):
    g = Digraph("WMS_Arch", format="png")
    g.attr("node", shape="box", style="rounded,filled", fillcolor="lightgrey")
    for src, dst in sorted(edges):
        g.edge(src, dst)
    g.render(output, view=False)
    print(f"Graph saved to {output}.png")


if __name__ == "__main__":
    edges = find_imports("app")
    draw_graph(edges)
