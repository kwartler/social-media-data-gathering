"""Point the app's hidden folder at a throwaway directory, so running the tests
never creates or changes ~/.social_media_data_gathering on the tester's machine.
Runs before any test module imports smdg.config."""
import os
import tempfile

_home = tempfile.mkdtemp(prefix="smdg-test-home-")
os.environ["HOME"] = _home
os.environ["USERPROFILE"] = _home  # Windows
