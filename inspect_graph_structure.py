import sys

# Add project root to path
sys.path.insert(0, "/home/etrox/workspace/conductor")

from orchestrator.langgraph.workflow import create_workflow_graph


def inspect_graph():
    try:
        graph = create_workflow_graph()
        drawable = graph.get_graph()

        print(f"Nodes: {list(drawable.nodes.keys())}")
        print("\nEdges:")
        for edge in drawable.edges:
            print(f"Source: {edge.source}, Target: {edge.target}")
            if hasattr(edge, "conditional") and edge.conditional:
                print(f"  Conditional: {edge.conditional}")
            if hasattr(edge, "data"):
                print(f"  Data: {edge.data}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    inspect_graph()
