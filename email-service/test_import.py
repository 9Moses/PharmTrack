import sys
import os

print("Initial sys.path:", sys.path)
try:
    from app.main import app
    print("SUCCESS: Imported app.main")
except Exception as e:
    print("FAILED:", type(e).__name__, e)
