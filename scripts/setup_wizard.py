#!/usr/bin/env python3
"""
Conductor Setup Wizard
Interactively configures the Conductor environment.
"""

import os
import sys
from pathlib import Path

# Colors
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"


def input_with_default(prompt, default):
    """Get input with a default value."""
    user_input = input(f"{prompt} [{default}]: ")
    return user_input.strip() or default


def main():
    print(f"{BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}")
    print(f"{BLUE}           Conductor Configuration Wizard{RESET}")
    print(f"{BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}")
    print("\nLet's configure your environment.\n")

    # defaults
    default_backend_port = "8080"
    default_projects_dir = "/home/etrox/workspace/conductor-projects"

    # 1. Backend Port
    backend_port = input_with_default("Frontend/Backend Port", default_backend_port)

    # 2. Projects Directory
    projects_dir = input_with_default("Projects Directory", default_projects_dir)

    # Expand user/vars
    projects_path = Path(os.path.expandvars(os.path.expanduser(projects_dir))).resolve()

    # Verify/Create Projects Directory
    if not projects_path.exists():
        print(f"\n{YELLOW}Directory {projects_path} does not exist.{RESET}")
        create = input("Create it? [Y/n]: ").strip().lower()
        if create in ("", "y", "yes"):
            try:
                projects_path.mkdir(parents=True, exist_ok=True)
                print(f"{GREEN}Created directory: {projects_path}{RESET}")
            except Exception as e:
                print(f"{YELLOW}Error creating directory: {e}{RESET}")
                sys.exit(1)
        else:
            print("Exiting.")
            sys.exit(1)
    else:
        print(f"{GREEN}Directory exists: {projects_path}{RESET}")

    # 3. API Keys (Optional)
    print("\nAPI Keys (Press Enter to skip if configured elsewhere)")
    openai_key = input("OpenAI API Key: ").strip()
    anthropic_key = input("Anthropic API Key: ").strip()

    # Write to .env
    backend_dir = Path(__file__).parent.parent / "dashboard" / "backend"
    env_file = backend_dir / ".env"

    # Ensure backend dir exists (sanity check)
    if not backend_dir.exists():
        print(f"{YELLOW}Warning: Backend directory not found at {backend_dir}{RESET}")

    print(f"\nWriting configuration to {env_file}...")

    env_lines = [
        "# Server Configuration",
        f"PORT={backend_port}",
        "NODE_ENV=development",
        "",
        "# Orchestrator API",
        "ORCHESTRATOR_API_URL=http://localhost:8090",
        "",
        "# Projects Configuration",
        f"PROJECTS_DIR={projects_path}",
        "",
        "# CORS",
        f"CORS_ORIGINS=http://localhost:3000,http://localhost:{backend_port}",
        "",
        "# AI Providers",
    ]

    if openai_key:
        env_lines.append(f"OPENAI_API_KEY={openai_key}")
    if anthropic_key:
        env_lines.append(f"ANTHROPIC_API_KEY={anthropic_key}")

    try:
        with open(env_file, "w") as f:
            f.write("\n".join(env_lines) + "\n")
        print(f"{GREEN}Configuration saved!{RESET}")
    except Exception as e:
        print(f"{YELLOW}Error writing .env file: {e}{RESET}")
        sys.exit(1)

    print(f"\n{BLUE}Setup complete! You can now run 'scripts/start-dashboard.sh'{RESET}")


if __name__ == "__main__":
    main()
