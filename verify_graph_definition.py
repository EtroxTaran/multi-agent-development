import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, "/home/etrox/workspace/conductor")

from orchestrator.orchestrator import Orchestrator


def verify_definition():
    try:
        # Mock project dir
        project_dir = Path("/home/etrox/workspace/conductor/projects/test_project")
        project_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(project_dir, console_output=False)

        # We don't need real DB for this method as it uses create_workflow_graph() which doesn't touch DB unless running
        # actually create_workflow_graph takes a checkpointer, but get_workflow_definition handles it.

        definition = orchestrator.get_workflow_definition()

        print(f"Nodes found: {len(definition['nodes'])}")
        router_nodes = [n for n in definition["nodes"] if n["type"] == "router"]
        print(f"Router nodes found: {len(router_nodes)}")
        for r in router_nodes:
            print(f" - {r['id']}")

        print(f"\nEdges found: {len(definition['edges'])}")
        router_edges = [e for e in definition["edges"] if "router" in e["source"]]
        print(f"Edges starting from routers: {len(router_edges)}")
        for e in router_edges[:5]:
            print(f" - {e['source']} -> {e['target']} (Label: {e.get('data', {}).get('label')})")

    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    verify_definition()
