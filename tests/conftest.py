# Shared fixtures for the test suite.
#
# The suite is fully offline and deterministic: every Gemini call is mocked and
# every vector-store call (Qdrant + the ONNX embedding model) is patched out, so no
# network, API key, model download, or on-disk index is ever touched.
import pytest

from src.state import SafetyAudit, UserProfile
from tests.helpers import make_extraction


@pytest.fixture
def extraction_factory():
    """Expose `make_extraction` as a fixture for tests that prefer injection."""
    return make_extraction


@pytest.fixture
def base_profile() -> UserProfile:
    return UserProfile(skin_type="dry", age=30, goals=["hydration"])


@pytest.fixture
def empty_audit() -> SafetyAudit:
    return SafetyAudit()
