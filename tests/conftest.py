import os
import sys
from dataclasses import dataclass as original_dataclass, field

# Ensure the repo root is on PYTHONPATH so packages import cleanly in tests
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
print("DEBUG: Original sys.path:", sys.path)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
    print("DEBUG: ROOT added to sys.path. Current sys.path:", sys.path)
else:
    print("DEBUG: ROOT already in sys.path. Current sys.path:", sys.path)

# Add explicit check for stagewarden module availability
try:
    import stagewarden
    print("DEBUG: Successfully imported stagewarden.")
except ModuleNotFoundError as e:
    print(f"DEBUG: Failed to import stagewarden: {e}", file=sys.stderr)

# Add explicit check for dataclasses and a tracer decorator
try:
    print("DEBUG: Attempting to import dataclass...")
    from dataclasses import dataclass as imported_dataclass, field
    print("DEBUG: Successfully imported dataclass and field from dataclasses.")

    # Define a wrapper decorator that logs before and after calling the real dataclass
    def trace_dataclass(cls):
        print(f"DEBUG: Decorating class: {cls.__name__}")
        # Call the original dataclass decorator
        decorated_cls = imported_dataclass(cls)
        print(f"DEBUG: Successfully decorated class: {cls.__name__}")
        return decorated_cls

    # Replace the builtin dataclass with our traced version
    __builtins__[dataclass] = trace_dataclass
    print("DEBUG: Monkey-patched __builtins__.dataclass for tracing.")

except ImportError:
    print("DEBUG: Could not import dataclass. Python version might be too old (< 3.7).")
except Exception as e:
    print(f"DEBUG: An unexpected error occurred during dataclass setup: {e}", file=sys.stderr)


