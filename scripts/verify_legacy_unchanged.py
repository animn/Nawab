"""Verify this additive phase did not silently alter the original Streamlit entrypoint."""
from pathlib import Path
import hashlib
import sys
path = Path(__file__).resolve().parents[1] / 'app.py'
expected_git_blob = '05280c2d73e3e913226bcb6181232f2f5d479434'
data = path.read_bytes()
actual = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
if actual != expected_git_blob:
    sys.exit('app.py differs from the reviewed feature-branch baseline; explicitly review this change.')
print('Legacy app.py matches the feature-branch baseline.')
