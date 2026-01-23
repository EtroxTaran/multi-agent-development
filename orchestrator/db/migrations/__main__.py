"""Entry point for running migrations as a module.

Usage:
    python -m orchestrator.db.migrations migrate --project my-app
    python -m orchestrator.db.migrations rollback --project my-app
    python -m orchestrator.db.migrations status --project my-app
    python -m orchestrator.db.migrations create add_new_feature
"""

from .cli import main

if __name__ == "__main__":
    main()
