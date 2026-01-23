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
        "$ROOT_DIR/.venv/bin/pip" install -e "$ROOT_DIR" -q
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
    local autonomous="$4"

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

    # Add autonomous mode if specified
    if [ "$autonomous" = "true" ]; then
        echo -e "${BLUE}Autonomous mode: enabled (no human consultation)${NC}"
        cmd_args="$cmd_args --autonomous"
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
# Database management
db_start() {
    echo -e "\n${YELLOW}Starting SurrealDB...${NC}"

    if ! command -v docker &> /dev/null; then
        echo -e "${RED}Error: Docker not found. Please install Docker first.${NC}"
        exit 1
    fi

    cd "$ROOT_DIR"

    if docker ps --format '{{.Names}}' | grep -q "conductor-surrealdb"; then
        echo -e "${GREEN}SurrealDB is already running${NC}"
    else
        docker-compose up -d
        echo -e "${GREEN}SurrealDB started${NC}"
    fi

    # Wait for health
    echo -e "${YELLOW}Waiting for SurrealDB to be ready...${NC}"
    for i in {1..30}; do
        if curl -s http://localhost:8001/health > /dev/null 2>&1; then
            echo -e "${GREEN}SurrealDB is ready!${NC}"
            return 0
        fi
        sleep 1
    done

    echo -e "${RED}SurrealDB failed to start. Check: docker logs conductor-surrealdb${NC}"
    exit 1
}

db_stop() {
    echo -e "\n${YELLOW}Stopping SurrealDB...${NC}"
    cd "$ROOT_DIR"
    docker-compose down
    echo -e "${GREEN}SurrealDB stopped${NC}"
}

db_status() {
    echo -e "\n${YELLOW}SurrealDB Status:${NC}"

    if docker ps --format '{{.Names}}' | grep -q "conductor-surrealdb"; then
        echo -e "  ${GREEN}+${NC} Container: running"

        if curl -s http://localhost:8001/health > /dev/null 2>&1; then
            echo -e "  ${GREEN}+${NC} Health: healthy"
        else
            echo -e "  ${RED}x${NC} Health: unhealthy"
        fi

        # Show data directory size
        local data_size=$(du -sh "$ROOT_DIR/data/surrealdb" 2>/dev/null | cut -f1)
        echo -e "  ${BLUE}i${NC} Data size: ${data_size:-N/A}"
    else
        echo -e "  ${RED}x${NC} Container: not running"
        echo -e "  ${BLUE}>${NC} Start with: ./scripts/init.sh db start"
    fi
}

show_help() {
    echo "
Usage: ./scripts/init.sh [command] [options]

Commands:
  check           Check prerequisites only
  db start        Start local SurrealDB (Docker)
  db stop         Stop local SurrealDB
  db status       Show SurrealDB status
  init <name>     Initialize a new project directory
  list            List all projects
  run <name>      Run workflow for a project
  run --path <path>        Run workflow for external project
  run <name> --parallel N  Run with N parallel workers
  run <name> --autonomous  Run fully autonomously without human consultation
  status <name>   Show workflow status for a project

Options:
  --path <path>     Use external project directory instead of projects/<name>
  --parallel <N>    Enable parallel worker execution with N workers (experimental)
  --autonomous      Run fully autonomously without pausing for human input
                    (default: interactive mode with human consultation)

Quick Start:
  1. Start the database:      ./scripts/init.sh db start
  2. Initialize a project:    ./scripts/init.sh init my-project
  3. Add your documents:      Place files in projects/my-project/Docs/
  4. Create PRODUCT.md:       Define your feature specification
  5. Run the workflow:        ./scripts/init.sh run my-project

Examples:
  ./scripts/init.sh db start
  ./scripts/init.sh check
  ./scripts/init.sh init my-api
  ./scripts/init.sh list
  ./scripts/init.sh run my-api
  ./scripts/init.sh run my-api --autonomous
  ./scripts/init.sh run --path ~/repos/my-project
  ./scripts/init.sh run my-api --parallel 3
  ./scripts/init.sh run my-api --autonomous --parallel 3
  ./scripts/init.sh status my-api
"
}

# Parse arguments
COMMAND="${1:-help}"

case "$COMMAND" in
    check)
        check_prereqs
        ;;
    db)
        shift
        DB_CMD="${1:-status}"
        case "$DB_CMD" in
            start)
                db_start
                ;;
            stop)
                db_stop
                ;;
            status)
                db_status
                ;;
            *)
                echo -e "${RED}Unknown db command: $DB_CMD${NC}"
                echo "Usage: ./scripts/init.sh db [start|stop|status]"
                exit 1
                ;;
        esac
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
        AUTONOMOUS="false"

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
                --autonomous)
                    AUTONOMOUS="true"
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
        run_workflow "$PROJECT_NAME" "$PROJECT_PATH" "$PARALLEL_WORKERS" "$AUTONOMOUS"
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
