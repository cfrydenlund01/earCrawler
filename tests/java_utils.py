import re
import subprocess
from typing import Optional


def get_java_major_version() -> Optional[int]:
    """Return the installed Java major version, or None if unavailable."""
    try:
        proc = subprocess.run(
            ["java", "-version"], capture_output=True, text=True, check=False
        )
    except OSError:
        return None
    out = proc.stderr or proc.stdout
    if not out:
        return None
    first_line = out.splitlines()[0]
    match = re.search(r"\"(\d+)(?:\.(\d+))?", first_line)
    if not match:
        return None
    major = int(match.group(1))
    if major == 1 and match.group(2):
        major = int(match.group(2))
    return major


JAVA_VERSION = get_java_major_version()
JAVA_VERSION_OK = JAVA_VERSION is not None and JAVA_VERSION >= 17
