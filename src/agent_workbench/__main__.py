"""Allow ``python -m agent_workbench``."""

import sys

from agent_workbench.interfaces.cli import main

if __name__ == "__main__":
    sys.exit(main())
