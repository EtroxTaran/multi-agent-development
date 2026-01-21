#!/bin/bash
# Meta-Architect Init Script
# Usage: ./scripts/init.sh [command] [project-name]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== Meta-Architect ===${NC}"

# Check prerequisites
check_prereqs() {
    echo -e "\n${YELLOW}Checking prerequisites...${NC}"

    local missing=0

    # Python
    if command -v python3 &> /dev/null; then
        echo -e "  ${GREEN}+${NC} Python3: $(python3 --version)"
    else
        echo -e "  ${RED}x${NC} Python3 not found"
        missing=1
    fi

    # Virtual environment
    if [ -d "$ROOT_DIR/.venv" ]; then
        echo -e "  ${GREEN}+${NC} Virtual environment exists"
    else
        echo -e "  ${YELLOW}>${NC} Creating virtual environment..."
        python3 -m venv "$ROOT_DIR/.venv"
        echo -e "  ${GREEN}+${NC} Virtual environment created"
    fi

    # Dependencies
    if "$ROOT_DIR/.venv/bin/pip" show langgraph &> /dev/null; then
        echo -e "  ${GREEN}+${NC} Dependencies installed"
    else
        echo -e "  ${YELLOW}>${NC} Installing dependencies..."
        "$ROOT_DIR/.venv/bin/pip" install -r "$ROOT_DIR/requirements.txt" -q
        echo -e "  ${GREEN}+${NC} Dependencies installed"
    fi

    # Claude CLI
    if command -v claude &> /dev/null; then
        echo -e "  ${GREEN}+${NC} Claude CLI: $(which claude)"
    else
        echo -e "  ${RED}x${NC} Claude CLI not found (needed for planning/implementation)"
        missing=1
    fi

    # Cursor CLI
    if command -v cursor-agent &> /dev/null; then
        echo -e "  ${GREEN}+${NC} Cursor CLI: $(which cursor-agent)"
    else
        echo -e "  ${YELLOW}!${NC} Cursor CLI not found (optional, for validation)"
    fi

    # Gemini CLI
    if command -v gemini &> /dev/null; then
        echo -e "  ${GREEN}+${NC} Gemini CLI: $(which gemini)"
    else
        echo -e "  ${YELLOW}!${NC} Gemini CLI not found (optional, for validation)"
    fi

    if [ $missing -eq 1 ]; then
        echo -e "\n${RED}Missing required prerequisites. Please install them first.${NC}"
        exit 1
    fi

    echo -e "\n${GREEN}All prerequisites satisfied!${NC}"
}

# Validate project name to prevent path traversal attacks
validate_project_name() {
    local name="$1"

    # Reject names with path traversal patterns
    if [[ "$name" == *".."* ]] || [[ "$name" == "/"* ]] || [[ "$name" == "~"* ]]; then
        echo -e "${RED}Error: Invalid project name '$name' - path traversal not allowed${NC}"
        exit 1
    fi

    # Reject names with slashes
    if [[ "$name" == *"/"* ]]; then
        echo -e "${RED}Error: Invalid project name '$name' - slashes not allowed${NC}"
        exit 1
    fi

    # Only allow alphanumeric, underscore, and hyphen
    if ! [[ "$name" =~ ^[a-zA-Z0-9_-]+$ ]]; then
        echo -e "${RED}Error: Project name must be alphanumeric (with _ or - allowed): '$name'${NC}"
        exit 1
    fi

    # Limit length
    if [ ${#name} -gt 64 ]; then
        echo -e "${RED}Error: Project name too long (max 64 chars): '$name'${NC}"
        exit 1
    fi
}

# Initialize project structure
init_project() {
    local name="$1"

    # Validate project name first
    validate_project_name "$name"

    local project_dir="$ROOT_DIR/projects/$name"

    echo -e "\n${YELLOW}Initializing project: ${name}${NC}"

    if [ -d "$project_dir" ]; then
        echo -e "${RED}Error: Project '$name' already exists${NC}"
        exit 1
    fi

    # Create project structure
    mkdir -p "$project_dir"
    mkdir -p "$project_dir/Documents"
    mkdir -p "$project_dir/.workflow/phases"

    # Create initial config
    cat > "$project_dir/.project-config.json" << EOF
{
  "project_name": "$name",
  "created_at": "$(date -Iseconds)"
}
EOF

    echo -e "\n${GREEN}Project initialized at: ${project_dir}${NC}"
    echo -e "\n${YELLOW}Next steps:${NC}"
    echo -e "  1. Add your Documents/ folder with product vision and architecture docs"
    echo -e "  2. Add context files (CLAUDE.md, GEMINI.md, .cursor/rules)"
    echo -e "  3. Create PRODUCT.md with feature specification"
    echo -e "  4. Run: ./scripts/init.sh run $name"
}

# List projects
list_projects() {
    echo -e "\n${YELLOW}Projects:${NC}"

    local projects_dir="$ROOT_DIR/projects"
    if [ ! -d "$projects_dir" ]; then
        echo -e "  No projects directory found"
        return
    fi

    local found=0
    for project in "$projects_dir"/*/; do
        if [ -d "$project" ]; then
            local name=$(basename "$project")
            if [ "$name" != "." ] && [ "$name" != ".." ]; then
                found=1
                echo -e "  ${BLUE}${name}${NC}"

                # Check for files
                local docs=""
                [ -d "$project/Documents" ] && docs="Documents "
                [ -f "$project/PRODUCT.md" ] && docs="${docs}PRODUCT.md "
                [ -f "$project/CLAUDE.md" ] && docs="${docs}CLAUDE.md "
                [ -f "$project/GEMINI.md" ] && docs="${docs}GEMINI.md "
                [ -d "$project/.cursor" ] && docs="${docs}.cursor "

                if [ -n "$docs" ]; then
                    echo -e "    Has: $docs"
                fi
            fi
        fi
    done

    if [ $found -eq 0 ]; then
        echo -e "  No projects found. Initialize one with: ./scripts/init.sh init <name>"
    fi
}

# Run workflow
run_workflow() {
    local name="$1"
    local project_path="$2"
    local parallel_workers="$3"

    # Build the command arguments
    local cmd_args=""

    if [ -n "$project_path" ]; then
        # External project mode
        if [ ! -d "$project_path" ]; then
            echo -e "${RED}Error: Project path '$project_path' not found${NC}"
            exit 1
        fi
        echo -e "\n${YELLOW}Running workflow for external project: ${project_path}${NC}"
        cmd_args="--project-path $project_path"
    else
        # Nested project mode
        local project_dir="$ROOT_DIR/projects/$name"
        if [ ! -d "$project_dir" ]; then
            echo -e "${RED}Error: Project '$name' not found${NC}"
            echo -e "Available projects:"
            list_projects
            exit 1
        fi
        echo -e "\n${YELLOW}Running workflow for: ${name}${NC}"
        cmd_args="--project $name"
    fi

    # Add parallel workers if specified
    if [ -n "$parallel_workers" ]; then
        echo -e "${BLUE}Parallel workers: ${parallel_workers}${NC}"
        export PARALLEL_WORKERS="$parallel_workers"
    fi

    "$ROOT_DIR/.venv/bin/python" -m orchestrator $cmd_args --use-langgraph --start
}

# Show status
show_status() {
    local name="$1"

    echo -e "\n${YELLOW}Status for: ${name}${NC}"

    "$ROOT_DIR/.venv/bin/python" -m orchestrator --project "$name" --status
}

# Show help
show_help() {
    echo "
Usage: ./scripts/init.sh [command] [options]

Commands:
  check           Check prerequisites only
  init <name>     Initialize a new project directory
  list            List all projects
  run <name>      Run workflow for a project
  run --path <path>        Run workflow for external project
  run <name> --parallel N  Run with N parallel workers
  status <name>   Show workflow status for a project

Options:
  --path <path>   Use external project directory instead of projects/<name>
  --parallel <N>  Enable parallel worker execution with N workers (experimental)

Workflow:
  1. Initialize a project:    ./scripts/init.sh init my-project
  2. Add your documents:      Place files in projects/my-project/Documents/
  3. Add context files:       Add CLAUDE.md, GEMINI.md, .cursor/rules
  4. Create PRODUCT.md:       Define your feature specification
  5. Run the workflow:        ./scripts/init.sh run my-project

Examples:
  ./scripts/init.sh check
  ./scripts/init.sh init my-api
  ./scripts/init.sh list
  ./scripts/init.sh run my-api
  ./scripts/init.sh run --path ~/repos/my-project
  ./scripts/init.sh run my-api --parallel 3
  ./scripts/init.sh status my-api
"
}

# Parse arguments
COMMAND="${1:-help}"

case "$COMMAND" in
    check)
        check_prereqs
        ;;
    init)
        shift
        PROJECT_NAME="$1"
        if [ -z "$PROJECT_NAME" ]; then
            echo -e "${RED}Error: Project name required${NC}"
            show_help
            exit 1
        fi
        check_prereqs
        init_project "$PROJECT_NAME"
        ;;
    list)
        list_projects
        ;;
    run)
        shift
        PROJECT_NAME=""
        PROJECT_PATH=""
        PARALLEL_WORKERS=""

        # Parse run arguments
        while [ $# -gt 0 ]; do
            case "$1" in
                --path)
                    shift
                    PROJECT_PATH="$1"
                    ;;
                --parallel)
                    shift
                    PARALLEL_WORKERS="$1"
                    ;;
                -*)
                    echo -e "${RED}Error: Unknown option: $1${NC}"
                    show_help
                    exit 1
                    ;;
                *)
                    if [ -z "$PROJECT_NAME" ]; then
                        PROJECT_NAME="$1"
                    fi
                    ;;
            esac
            shift
        done

        # Validate arguments
        if [ -z "$PROJECT_NAME" ] && [ -z "$PROJECT_PATH" ]; then
            echo -e "${RED}Error: Project name or --path required${NC}"
            show_help
            exit 1
        fi

        check_prereqs
        run_workflow "$PROJECT_NAME" "$PROJECT_PATH" "$PARALLEL_WORKERS"
        ;;
    status)
        shift
        PROJECT_NAME="$1"
        if [ -z "$PROJECT_NAME" ]; then
            echo -e "${RED}Error: Project name required${NC}"
            show_help
            exit 1
        fi
        show_status "$PROJECT_NAME"
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo -e "${RED}Unknown command: $COMMAND${NC}"
        show_help
        exit 1
        ;;
esac
