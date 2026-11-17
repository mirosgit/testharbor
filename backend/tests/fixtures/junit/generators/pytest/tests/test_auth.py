"""Sample suite used to generate real pytest JUnit XML for TestHarbor's import tests."""

import pytest


def test_login_C1():
    """Case id in the test name."""
    assert 1 + 1 == 2


@pytest.mark.case("C2")
def test_wrong_password():
    response = {"status": 200}
    assert response["status"] == 401, "expected 401 for a wrong password"


@pytest.mark.case("C3", "C4")
def test_lockout_and_unlock():
    assert True


@pytest.mark.case("C5")
@pytest.mark.parametrize("browser", ["chrome", "firefox"])
def test_logout(browser):
    assert browser == "chrome", f"logout button hidden in {browser}"


@pytest.mark.case("C6")
@pytest.mark.skip(reason="SSO provider not configured")
def test_sso_login():
    pass


def test_signup():
    """No case id: matched by automation_key."""
    assert "user@example.com".count("@") == 1


@pytest.fixture
def broken_db():
    raise ConnectionError("database is unavailable")


def test_profile_page(broken_db):
    """Errors in fixtures become <error> elements."""
