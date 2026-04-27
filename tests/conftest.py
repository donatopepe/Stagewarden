import os
import sys
# Ensure the repo root is on PYTHONPATH so packages import cleanly in tests
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
print(f"DEBUG: PYTHONPATH set to: {sys.path}")
