"""
Pytest configuration and fixtures for Auth Service tests.
"""

import os
import tempfile
from pathlib import Path

import pytest

from src.jwt_handler import JWTHandler

# RSA-2048 test key pair (for testing only - do not use in production)
_TEST_RSA_PRIVATE_KEY = """-----BEGIN PRIVATE KEY-----
MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQCUUU9NoYWHrJXD
lix5s+XrxHVvl2a+SwvuLtyM/H3IKC658hUM2IxzF/2u16QoV6snMdPSciSdP5D9
K4N4XkfhHixpUAq+FxZxTERgIIYLw2aWEtLGTS3jsiGJ9X94PZ0iVF6/Cv/kqZqv
AO+J4Z3OvJHy2MpK/C95ot95u0ChSfUcxSnkWMt3PkWEUlcs1Adg7s/Uv+q3mBaR
tatYeRJEdgd2JEqTYPrp2ZJcJQbtaVhS4JQbFXYOAp35Tl+XLS012yUSjCgRdd43
SrV+NbsVPO0H7oE3wkB5SqaKUqJN/t9TLh4hb8e2quFF0qKx5uWQbfyI3dHiAV/u
z63VDQXfAgMBAAECggEAAUk0FGACXQsA6zFuW4JxWeTZ8npo6IexJ+ZojyFD+Ja+
0r89Bwpf1kJLNskXaUaT+1ED8rRFwsZhpsWfXfgG2qELO8Ev6G9aXctVfVKK3hl2
8ud9iwPxoFuMlKwUdi/7degSQHORhNx4CjP0/CvynFMnj+ghuqi1inIALnlZYIyc
Aa6evJq5TbUHKme7iiwPsrStKifzepcXoPYMSn0tJdDDU0FwV4aAoU56wZhXVh7J
TSYmiEwYkxccMWdsWjsmPxTbQ1K+wmeZtJ6QY4Hn7LJ49yZtTUM9mFJNosjcrGUy
0KvrDOtjFaaTXJ09ZxUi8wOWnimd5Emcdzd9zrHA8QKBgQDFid5av6kCZ9BYn9WE
G0vGI+UDnftAJ7eJK4BdR/bVpnN34Um6JeYYf0F5iG4OHIepZuKdtCc5xCbBSgL2
qcfkXdJ6gu3Q1EbXsV8fVuUg419ySR82p0BFT+bcBaeDbpDl4XwG70mf2oWmJJvH
XUNBk2erJgW1mNZhXK0QagQCKwKBgQDANk+kvhv0HeWsRZjh1CPLp8t7pRhtv0aS
yBF/4Zfs+kIfPc7U37vkARI2OldXOAwX37ls8IJRFDzl9tni7QT08REfBEBkvMVz
wJFTvlv4olF3nIsCBOZpsDGNKCLOAyEKH0TjQhIhYqfttB2enUgedtNS5mSM9f6A
2daqP+HVHQKBgQC1d5Lh0QIE6LOYRrTSGHVCv4TKDt5aMGJFy8Wva8XQvYmDzl15
eQlo5baTXAamRgVGVPLHp1EFmzFzDXete4jbPGl4DEFGP0wZJ6NX2e7BiL8M8SmQ
fpLnWaCd7T/W2MKZu8vBXx9Gj2uJlkXZHs8DNdPdgR9rlM0UQhvmYU3vYwKBgDuP
mNZf4qGeshDT8C/qYL023aMO4acAYooRXPrXmRBh7CNqL7FfMwXQHyiWo4HvaC/t
r7PGQ1uEfep0t8fN0n9kQ/3sf1e39yeLQH1Gu5EsGzqJU7nocs3FP1WSXlagOZi9
X8dcLeoSfB74dUU1T6fBAnLp2bakc5zR4+cVrJExAoGAZ0Kn2+E15XDdKn/enbL2
xP0jNzJcfL1oTPD0zslzuPDjUqL4t/SVtqx44deb/5ekGxrx0W4QyU4Cylq0u/g/
/ovWkOG6oHTiTyXna2+M7Z94xPkBwLrYdUutscif/4lhOC6Rchxzz+LLhq1yPKEy
BDZtj5c1i4uGEEcpRK18++k=
-----END PRIVATE KEY-----"""

_TEST_RSA_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAlFFPTaGFh6yVw5YsebPl
68R1b5dmvksL7i7cjPx9yCguufIVDNiMcxf9rtekKFerJzHT0nIknT+Q/SuDeF5H
4R4saVAKvhcWcUxEYCCGC8NmlhLSxk0t47IhifV/eD2dIlRevwr/5KmarwDvieGd
zryR8tjKSvwveaLfebtAoUn1HMUp5FjLdz5FhFJXLNQHYO7P1L/qt5gWkbWrWHkS
RHYHdiRKk2D66dmSXCUG7WlYUuCUGxV2DgKd+U5fly0tNdslEowoEXXeN0q1fjW7
FTztB+6BN8JAeUqmilKiTf7fUy4eIW/HtqrhRdKiseblkG38iN3R4gFf7s+t1Q0F
3wIDAQAB
-----END PUBLIC KEY-----"""


@pytest.fixture
def temp_key_dir() -> Path:
    """Create a temporary directory with RSA keys for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        key_dir = Path(tmpdir)
        (key_dir / "private.pem").write_text(_TEST_RSA_PRIVATE_KEY)
        (key_dir / "public.pem").write_text(_TEST_RSA_PUBLIC_KEY)
        yield key_dir


@pytest.fixture
def rsa_key_paths(temp_key_dir: Path) -> tuple[str, str]:
    """Return (private_path, public_path) for temporary RSA key files."""
    return str(temp_key_dir / "private.pem"), str(temp_key_dir / "public.pem")


@pytest.fixture
def jwt_handler(rsa_key_paths: tuple[str, str]) -> JWTHandler:
    """Create a JWTHandler with RS256 for testing."""
    private_path, public_path = rsa_key_paths
    return JWTHandler(
        private_key_path=private_path,
        public_key_path=public_path,
        access_token_expire_minutes=15,
        refresh_token_expire_days=7,
    )


@pytest.fixture(autouse=True)
def setup_test_env() -> None:
    """Set up test environment variables."""
    os.environ.setdefault("SERVICE_NAME", "auth-test")
    os.environ.setdefault("GRPC_PORT", "50059")
    os.environ.setdefault("REDIS_HOST", "localhost")
    os.environ.setdefault("REDIS_PORT", "6379")
    os.environ.setdefault("USER_SERVICE_HOST", "localhost")
    os.environ.setdefault("USER_SERVICE_PORT", "50058")
    os.environ.setdefault("JWT_PRIVATE_KEY_PATH", "infra/keys/jwt-private.pem")
    os.environ.setdefault("JWT_PUBLIC_KEY_PATH", "infra/keys/jwt-public.pem")
    os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "15")
    os.environ.setdefault("REFRESH_TOKEN_EXPIRE_DAYS", "7")
    os.environ.setdefault("CONSUL_ENABLED", "false")
