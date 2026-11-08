"""Allow ``python -m agent_workspace``."""

import sys

from agent_workspace.interfaces.cli import main

if __name__ == "__main__":
    sys.exit(main())
