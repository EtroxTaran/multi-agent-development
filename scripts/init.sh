#!/bin/bash
# Meta-Architect Init Script
# Usage: ./scripts/init.sh [project-name] [--type node-api|react-tanstack|java-spring|nx-fullstack]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== Meta-Architect Init ===${NC}"

# Check prerequisites
check_prereqs() {
    echo -e "\n${YELLOW}Checking prerequisites...${NC}"

    local missing=0

    # Python
    if command -v python3 &> /dev/null; then
        echo -e "  ${GREEN}✓${NC} Python3: $(python3 --version)"
    else
        echo -e "  ${RED}✗${NC} Python3 not found"
        missing=1
    fi

    # Virtual environment
    if [ -d "$ROOT_DIR/.venv" ]; then
        echo -e "  ${GREEN}✓${NC} Virtual environment exists"
    else
        echo -e "  ${YELLOW}→${NC} Creating virtual environment..."
        python3 -m venv "$ROOT_DIR/.venv"
        echo -e "  ${GREEN}✓${NC} Virtual environment created"
    fi

    # Dependencies
    if "$ROOT_DIR/.venv/bin/pip" show langgraph &> /dev/null; then
        echo -e "  ${GREEN}✓${NC} Dependencies installed"
    else
        echo -e "  ${YELLOW}→${NC} Installing dependencies..."
        "$ROOT_DIR/.venv/bin/pip" install -r "$ROOT_DIR/requirements.txt" -q
        echo -e "  ${GREEN}✓${NC} Dependencies installed"
    fi

    # Claude CLI
    if command -v claude &> /dev/null; then
        echo -e "  ${GREEN}✓${NC} Claude CLI: $(which claude)"
    else
        echo -e "  ${RED}✗${NC} Claude CLI not found (needed for planning/implementation)"
        missing=1
    fi

    # Cursor CLI
    if command -v cursor-agent &> /dev/null; then
        echo -e "  ${GREEN}✓${NC} Cursor CLI: $(which cursor-agent)"
    else
        echo -e "  ${YELLOW}!${NC} Cursor CLI not found (optional, for validation)"
    fi

    # Gemini CLI
    if command -v gemini &> /dev/null; then
        echo -e "  ${GREEN}✓${NC} Gemini CLI: $(which gemini)"
    else
        echo -e "  ${YELLOW}!${NC} Gemini CLI not found (optional, for validation)"
    fi

    if [ $missing -eq 1 ]; then
        echo -e "\n${RED}Missing required prerequisites. Please install them first.${NC}"
        exit 1
    fi

    echo -e "\n${GREEN}All prerequisites satisfied!${NC}"
}

# Create project
create_project() {
    local name="$1"
    local type="${2:-node-api}"

    echo -e "\n${YELLOW}Creating project: ${name} (type: ${type})${NC}"

    "$ROOT_DIR/.venv/bin/python" "$ROOT_DIR/scripts/create-project.py" "$name" --type "$type" --force

    echo -e "\n${GREEN}Project created at: ${ROOT_DIR}/projects/${name}${NC}"
    echo -e "${YELLOW}→ Edit projects/${name}/PRODUCT.md with your feature specification${NC}"
}

# Run workflow
run_workflow() {
    local name="$1"

    echo -e "\n${YELLOW}Running workflow for: ${name}${NC}"

    "$ROOT_DIR/.venv/bin/python" -m orchestrator --project "$name" --use-langgraph --start
}

# Show help
show_help() {
    echo "
Usage: ./scripts/init.sh [command] [options]

Commands:
  check                     Check prerequisites only
  create <name> [--type T]  Create a new project
  run <name>                Run workflow for a project
  new <name> [--type T]     Create project and open PRODUCT.md for editing

Project Types:
  node-api        Hono + Prisma + PostgreSQL (default)
  react-tanstack  React 19 + TanStack + Shadcn
  java-spring     Spring Boot 3 + Gradle
  nx-fullstack    Nx monorepo

Examples:
  ./scripts/init.sh check
  ./scripts/init.sh create my-api --type node-api
  ./scripts/init.sh run my-api
  ./scripts/init.sh new my-feature --type react-tanstack
"
}

# Parse arguments
PROJECT_NAME=""
PROJECT_TYPE="node-api"
COMMAND="${1:-check}"

case "$COMMAND" in
    check)
        check_prereqs
        ;;
    create)
        shift
        PROJECT_NAME="$1"
        shift || true
        while [[ $# -gt 0 ]]; do
            case "$1" in
                --type|-t) PROJECT_TYPE="$2"; shift 2 ;;
                *) shift ;;
            esac
        done
        if [ -z "$PROJECT_NAME" ]; then
            echo -e "${RED}Error: Project name required${NC}"
            show_help
            exit 1
        fi
        check_prereqs
        create_project "$PROJECT_NAME" "$PROJECT_TYPE"
        ;;
    run)
        shift
        PROJECT_NAME="$1"
        if [ -z "$PROJECT_NAME" ]; then
            echo -e "${RED}Error: Project name required${NC}"
            show_help
            exit 1
        fi
        check_prereqs
        run_workflow "$PROJECT_NAME"
        ;;
    new)
        shift
        PROJECT_NAME="$1"
        shift || true
        while [[ $# -gt 0 ]]; do
            case "$1" in
                --type|-t) PROJECT_TYPE="$2"; shift 2 ;;
                *) shift ;;
            esac
        done
        if [ -z "$PROJECT_NAME" ]; then
            echo -e "${RED}Error: Project name required${NC}"
            show_help
            exit 1
        fi
        check_prereqs
        create_project "$PROJECT_NAME" "$PROJECT_TYPE"
        echo -e "\n${BLUE}Opening PRODUCT.md for editing...${NC}"
        echo -e "${YELLOW}After editing, run: ./scripts/init.sh run ${PROJECT_NAME}${NC}\n"
        ${EDITOR:-nano} "$ROOT_DIR/projects/$PROJECT_NAME/PRODUCT.md"
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
