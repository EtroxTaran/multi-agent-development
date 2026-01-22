#!/bin/bash
# =============================================================================
# Meta-Architect Project Setup Script
# =============================================================================
#
# This script sets up meta-architect integration in any project directory.
#
# Usage:
#   curl -sL https://raw.githubusercontent.com/EtroxTaran/multi-agent-development/main/scripts/setup-project.sh | bash
#   ./meta-architect/scripts/setup-project.sh
#
# Options:
#   --skip-templates    Don't create starter templates
#   --branch <branch>   Use specific branch (default: main)
#   --help              Show help message
#
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
REPO_URL="https://github.com/EtroxTaran/multi-agent-development.git"
SUBMODULE_PATH="meta-architect"
DEFAULT_BRANCH="main"

# Parse arguments
SKIP_TEMPLATES=false
BRANCH="$DEFAULT_BRANCH"

while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-templates)
            SKIP_TEMPLATES=true
            shift
            ;;
        --branch)
            BRANCH="$2"
            shift 2
            ;;
        --help|-h)
            echo "Meta-Architect Project Setup"
            echo ""
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --skip-templates    Don't create starter templates"
            echo "  --branch <branch>   Use specific branch (default: main)"
            echo "  --help              Show this help message"
            echo ""
            echo "Run this script in your project root directory."
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

# =============================================================================
# Helper Functions
# =============================================================================

info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if file exists and don't overwrite
safe_create_file() {
    local filepath="$1"
    local content="$2"

    if [[ -f "$filepath" ]]; then
        warn "File already exists: $filepath (skipping)"
        return 1
    fi

    # Create directory if needed
    local dir=$(dirname "$filepath")
    if [[ ! -d "$dir" ]]; then
        mkdir -p "$dir"
    fi

    echo "$content" > "$filepath"
    success "Created: $filepath"
    return 0
}

# =============================================================================
# Step 1: Ensure we're in a git repository
# =============================================================================

info "Checking git repository..."

if [[ ! -d ".git" ]]; then
    info "Not a git repository. Initializing..."
    git init
    success "Initialized git repository"
else
    success "Git repository found"
fi

# =============================================================================
# Step 2: Add meta-architect as submodule
# =============================================================================

info "Setting up meta-architect submodule..."

if [[ -d "$SUBMODULE_PATH" ]]; then
    if [[ -f "$SUBMODULE_PATH/.git" ]] || [[ -d "$SUBMODULE_PATH/.git" ]]; then
        success "meta-architect submodule already exists"
    else
        warn "Directory '$SUBMODULE_PATH' exists but is not a submodule"
        warn "Please remove it or use a different path"
        exit 1
    fi
else
    info "Adding meta-architect submodule from $REPO_URL (branch: $BRANCH)..."
    git submodule add -b "$BRANCH" "$REPO_URL" "$SUBMODULE_PATH"
    git submodule update --init --recursive
    success "Added meta-architect submodule"
fi

# =============================================================================
# Step 3: Create starter templates (if not skipped)
# =============================================================================

if [[ "$SKIP_TEMPLATES" == "false" ]]; then
    info "Creating starter templates..."

    # Check if templates exist in submodule
    TEMPLATE_DIR="$SUBMODULE_PATH/templates/project"

    if [[ -d "$TEMPLATE_DIR" ]]; then
        # Copy from submodule templates

        # PRODUCT.md
        if [[ -f "$TEMPLATE_DIR/PRODUCT.md.template" ]] && [[ ! -f "PRODUCT.md" ]]; then
            cp "$TEMPLATE_DIR/PRODUCT.md.template" "PRODUCT.md"
            success "Created: PRODUCT.md"
        elif [[ -f "PRODUCT.md" ]]; then
            warn "File already exists: PRODUCT.md (skipping)"
        fi

        # CLAUDE.md
        if [[ -f "$TEMPLATE_DIR/CLAUDE.md.template" ]] && [[ ! -f "CLAUDE.md" ]]; then
            cp "$TEMPLATE_DIR/CLAUDE.md.template" "CLAUDE.md"
            success "Created: CLAUDE.md"
        elif [[ -f "CLAUDE.md" ]]; then
            warn "File already exists: CLAUDE.md (skipping)"
        fi

        # GEMINI.md
        if [[ -f "$TEMPLATE_DIR/GEMINI.md.template" ]] && [[ ! -f "GEMINI.md" ]]; then
            cp "$TEMPLATE_DIR/GEMINI.md.template" "GEMINI.md"
            success "Created: GEMINI.md"
        elif [[ -f "GEMINI.md" ]]; then
            warn "File already exists: GEMINI.md (skipping)"
        fi

        # .cursor/rules
        if [[ -f "$TEMPLATE_DIR/cursor-rules.template" ]] && [[ ! -f ".cursor/rules" ]]; then
            mkdir -p ".cursor"
            cp "$TEMPLATE_DIR/cursor-rules.template" ".cursor/rules"
            success "Created: .cursor/rules"
        elif [[ -f ".cursor/rules" ]]; then
            warn "File already exists: .cursor/rules (skipping)"
        fi

        # QUICKSTART.md
        if [[ -f "$TEMPLATE_DIR/QUICKSTART.md.template" ]] && [[ ! -f "QUICKSTART.md" ]]; then
            cp "$TEMPLATE_DIR/QUICKSTART.md.template" "QUICKSTART.md"
            success "Created: QUICKSTART.md"
        elif [[ -f "QUICKSTART.md" ]]; then
            warn "File already exists: QUICKSTART.md (skipping)"
        fi

    else
        warn "Template directory not found: $TEMPLATE_DIR"
        warn "Creating minimal templates inline..."

        # Create minimal PRODUCT.md template
        if [[ ! -f "PRODUCT.md" ]]; then
            cat > "PRODUCT.md" << 'PRODUCT_EOF'
# Feature Name
[Your feature name here - 5-100 characters]

## Summary
[Brief description - 50-500 characters]

## Problem Statement
[Why this feature is needed - minimum 100 characters]

## Acceptance Criteria
- [ ] Criterion 1
- [ ] Criterion 2
- [ ] Criterion 3

## Example Inputs/Outputs

### Example 1
```json
// Input
{}
// Output
{}
```

### Example 2
```json
// Input
{}
// Output
{}
```

## Technical Constraints
[Performance, security, compatibility requirements]

## Testing Strategy
[How to test this feature]

## Definition of Done
- [ ] All acceptance criteria met
- [ ] Tests passing
- [ ] Code reviewed
- [ ] Documentation updated
- [ ] No security issues
PRODUCT_EOF
            success "Created: PRODUCT.md"
        fi

        # Create minimal CLAUDE.md template
        if [[ ! -f "CLAUDE.md" ]]; then
            cat > "CLAUDE.md" << 'CLAUDE_EOF'
# Project Context for Claude

## Project Overview
[Brief description of what this project does]

## Tech Stack
- Language: [e.g., TypeScript, Python]
- Framework: [e.g., Next.js, FastAPI]
- Testing: [e.g., Jest, Pytest]

## Coding Standards
- [Your coding conventions]

## File Structure
```
src/
tests/
```

## TDD Requirements
- Write failing tests first
- Implement minimal code to pass
- Refactor while green

## Important Notes
- [Project-specific gotchas]
CLAUDE_EOF
            success "Created: CLAUDE.md"
        fi
    fi
fi

# =============================================================================
# Step 4: Create convenience scripts
# =============================================================================

info "Creating convenience scripts..."

# run-workflow.sh
if [[ ! -f "run-workflow.sh" ]]; then
    cat > "run-workflow.sh" << 'RUN_EOF'
#!/bin/bash
# Run meta-architect workflow on this project
set -e
cd "$(dirname "$0")"

if [[ ! -d "meta-architect" ]]; then
    echo "Error: meta-architect submodule not found"
    echo "Run: git submodule update --init --recursive"
    exit 1
fi

./meta-architect/scripts/init.sh run --path "$(pwd)"
RUN_EOF
    chmod +x "run-workflow.sh"
    success "Created: run-workflow.sh"
else
    warn "File already exists: run-workflow.sh (skipping)"
fi

# update-meta-architect.sh
if [[ ! -f "update-meta-architect.sh" ]]; then
    cat > "update-meta-architect.sh" << 'UPDATE_EOF'
#!/bin/bash
# Update meta-architect submodule to latest
set -e
cd "$(dirname "$0")"

if [[ ! -d "meta-architect" ]]; then
    echo "Error: meta-architect submodule not found"
    exit 1
fi

echo "Updating meta-architect submodule..."
cd meta-architect
git fetch origin
git checkout main
git pull origin main
cd ..

git add meta-architect
echo ""
echo "Updated meta-architect to latest."
echo "Run 'git commit -m \"Update meta-architect\"' to save the update."
UPDATE_EOF
    chmod +x "update-meta-architect.sh"
    success "Created: update-meta-architect.sh"
else
    warn "File already exists: update-meta-architect.sh (skipping)"
fi

# =============================================================================
# Step 5: Symlink .claude for skills access
# =============================================================================

info "Setting up Claude skills..."

if [[ -d "$SUBMODULE_PATH/.claude" ]]; then
    if [[ -L ".claude" ]]; then
        success "Symlink .claude already exists"
    elif [[ -d ".claude" ]]; then
        warn "Directory .claude already exists (not symlinking)"
        warn "To use /orchestrate, manually symlink: ln -s meta-architect/.claude .claude"
    else
        ln -s "$SUBMODULE_PATH/.claude" ".claude"
        success "Created symlink: .claude -> $SUBMODULE_PATH/.claude"
    fi
else
    warn "meta-architect/.claude not found - skills won't be available"
fi

# =============================================================================
# Step 6: Update .gitignore
# =============================================================================

info "Checking .gitignore..."

GITIGNORE_ADDITIONS=$(cat << 'GITIGNORE_EOF'

# =============================================================================
# Meta-Architect
# =============================================================================
# Workflow state is regenerated during each run
.workflow/

# Symlink to submodule (don't commit - each clone recreates it)
.claude
GITIGNORE_EOF
)

if [[ ! -f ".gitignore" ]]; then
    echo "$GITIGNORE_ADDITIONS" > ".gitignore"
    success "Created: .gitignore"
elif ! grep -q "Meta-Architect Workflow State" ".gitignore" 2>/dev/null; then
    echo "$GITIGNORE_ADDITIONS" >> ".gitignore"
    success "Updated: .gitignore with meta-architect entries"
else
    warn ".gitignore already has meta-architect entries (skipping)"
fi

# =============================================================================
# Step 7: Create .workflow directory
# =============================================================================

info "Setting up workflow directory..."

if [[ ! -d ".workflow" ]]; then
    mkdir -p ".workflow"
    success "Created: .workflow/"
else
    warn "Directory already exists: .workflow/"
fi

# =============================================================================
# Step 8: Create Documents directory
# =============================================================================

info "Setting up Documents directory..."

if [[ ! -d "Documents" ]]; then
    mkdir -p "Documents"
    # Create a placeholder README
    cat > "Documents/README.md" << 'DOCS_README_EOF'
# Project Documents

Add your project documentation here:

- **product-vision.md** - What you're building and why
- **architecture.md** - Technical design decisions
- **api-spec.md** - API contracts (if applicable)
- **requirements.md** - Detailed requirements

Claude will read these during `/discover` to understand your project.
DOCS_README_EOF
    success "Created: Documents/"
else
    warn "Directory already exists: Documents/"
fi

# =============================================================================
# Complete!
# =============================================================================

echo ""
echo "============================================================================="
echo -e "${GREEN}╔═══════════════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                    Meta-Architect Setup Complete!                         ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BLUE}What is this?${NC}"
echo "  A multi-agent AI development system. Claude is your Tech Lead with"
echo "  access to Cursor (security) and Gemini (architecture) for code review."
echo ""
echo -e "${BLUE}Project structure:${NC}"
echo "  $(pwd)/"
echo "  ├── meta-architect/      # AI orchestration (submodule)"
echo "  ├── Documents/           # Your project docs (add here)"
echo "  ├── CLAUDE.md            # Claude's context (EDIT THIS)"
echo "  ├── QUICKSTART.md        # Getting started guide"
echo "  └── .claude/             # AI skills (symlinked)"
echo ""
echo -e "${BLUE}How it works:${NC}"
echo ""
echo "  ┌─────────────────────────────────────────────────────────────┐"
echo "  │               Claude (Tech Lead)                            │"
echo "  │    • Coordinates workflow    • Implements code              │"
echo "  │    • Breaks down tasks       • Ensures quality              │"
echo "  └─────────────────────────────────────────────────────────────┘"
echo "                              │"
echo "          ┌───────────────────┼───────────────────┐"
echo "          ▼                   ▼                   ▼"
echo "  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐"
echo "  │ Cursor Agent  │  │ Gemini Agent  │  │ Worker Claude │"
echo "  │ (Security)    │  │ (Architecture)│  │ (Tasks)       │"
echo "  └───────────────┘  └───────────────┘  └───────────────┘"
echo ""
echo -e "${BLUE}Recommended workflow:${NC}"
echo ""
echo "  1. Add docs to Documents/ (product vision, architecture, etc.)"
echo ""
echo "  2. Edit CLAUDE.md with your tech stack and coding standards"
echo ""
echo "  3. Start Claude:"
echo -e "     ${GREEN}claude${NC}"
echo ""
echo "  4. Use these commands in order:"
echo ""
echo -e "     ${GREEN}/discover${NC}  → Claude reads your docs, creates PRODUCT.md"
echo -e "     ${GREEN}/plan${NC}      → Creates task breakdown, you approve"
echo -e "     ${GREEN}/task T1${NC}   → Implements first task with TDD"
echo -e "     ${GREEN}/task T2${NC}   → Continue through all tasks..."
echo -e "     ${GREEN}/status${NC}    → Check progress anytime"
echo ""
echo -e "${BLUE}Quick start (if you already know what to build):${NC}"
echo ""
echo "  1. Create PRODUCT.md with your feature spec"
echo -e "  2. Run: ${GREEN}claude${NC}"
echo -e "  3. Use: ${GREEN}/plan${NC} → approve → ${GREEN}/task T1${NC}"
echo ""
echo -e "${BLUE}Files to read:${NC}"
echo "  • QUICKSTART.md           - Full getting started guide"
echo "  • CLAUDE.md               - Claude's context (customize this!)"
echo "  • meta-architect/docs/    - Detailed documentation"
echo ""
echo -e "${YELLOW}Tip:${NC} The better you fill out CLAUDE.md, the better Claude performs!"
echo ""
echo "═══════════════════════════════════════════════════════════════════════════"
