# Skills Discovery Skill

List all available skills in the meta-architect system.

## Usage

```
/skills
```

## Purpose

Help users and Claude discover what capabilities are available.

## Output

Displays:
- All available commands organized by category
- Brief descriptions of each
- Recommended workflow order
- Links to detailed documentation

## Categories

### Human-Guided Workflow
Commands for step-by-step development with user control:
- `/discover` - Understand project, create spec
- `/plan` - Create task breakdown
- `/task <id>` - Implement single task
- `/status` - Check progress

### Automated Workflow
Commands for hands-off execution:
- `/orchestrate` - Full automated workflow

### Agent Invocation
Commands to directly call agents:
- `/validate` - Plan validation
- `/verify` - Code review
- `/call-cursor` - Cursor agent
- `/call-gemini` - Gemini agent

### Utility
Support commands:
- `/skills` - This command
- `/phase-status` - Detailed status
- `/resolve-conflict` - Conflict resolution
- `/list-projects` - Project listing
- `/sync-rules` - Rule synchronization
- `/add-lesson` - Add lessons learned
