"""Test settings module that boots example_project's demo app under pytest.

Imports example_project.settings and overrides DATABASES to point at the
testcontainers Postgres instance from tests/settings.py.
"""

import sys
from pathlib import Path

# Add example_project/ to path so `import demo` and `import example_project`
# both resolve.
EXAMPLE_DIR = Path(__file__).resolve().parent.parent / "example_project"
sys.path.insert(0, str(EXAMPLE_DIR))

# Eager import to populate everything from example_project.settings.
from example_project.settings import *  # noqa: F401, F403, E402

# But override the database to use the same testcontainers Postgres that
# tests/settings.py spun up — DO NOT spin up a second container.
from tests.settings import DATABASES  # noqa: E402, F401

DEBUG = False
