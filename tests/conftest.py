import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
# isolate the audit DB used during tests
os.environ.setdefault("CLAIMGUARD_DB", str(Path(tempfile.mkdtemp()) / "test.db"))

import pytest  # noqa: E402

SAMPLES = ROOT / "data" / "sample_claims"


@pytest.fixture(scope="session")
def sample_files():
    def _get(claim_id: str):
        return sorted((SAMPLES / claim_id).glob("*.pdf"))
    return _get
