# conftest.py — root-level pytest configuration for the email service
#
# Placing conftest.py here (alongside pytest.ini) guarantees that the project
# root (/app inside the container) is inserted into sys.path before any test
# module is collected, regardless of whether tests/ has an __init__.py.
# This makes `from app.main import app` and `from core.config import settings`
# importable without a PYTHONPATH env variable in the Docker run command.
import sys
import os

# Ensure the project root is at the front of sys.path
sys.path.insert(0, os.path.dirname(__file__))
