import os
import sys
from pathlib import Path

# Ensure the root project directory is on sys.path so modules like config and services can be imported
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

# Import the initialized Flask WSGI application
from app import app
