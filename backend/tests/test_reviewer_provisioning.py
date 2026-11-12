from types import SimpleNamespace

from app.scripts import provision_reviewer
from app.schemas.user import UserCreate


class FakeSession:
    def __init__(self, user):
        self.user = user
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def scalar(self, _query):
        return self.user

    def commit(self):
        self.committed = True


def test_public_registration_schema_does_not_accept_a_requested_reviewer_role() -> None:
    data = UserCreate.model_validate({
        "name": "New account",
        "email": "new@example.org",
        "password": "a-long-password",
        "role": "reviewer",
    })
    assert "role" not in data.model_dump()


def test_offline_provisioning_promotes_existing_account_only(monkeypatch, capsys) -> None:
    user = SimpleNamespace(id=12, email="reviewer@example.test", role="user")
    session = FakeSession(user)
    monkeypatch.setattr(provision_reviewer, "SessionLocal", lambda: session)
    monkeypatch.setattr(provision_reviewer, "create_tables", lambda: None)

    assert provision_reviewer.main(["REVIEWER@example.test"]) == 0
    assert user.role == "reviewer"
    assert session.committed is True
    assert "Reviewer access granted" in capsys.readouterr().out


def test_offline_provisioning_fails_when_account_does_not_exist(monkeypatch, capsys) -> None:
    session = FakeSession(None)
    monkeypatch.setattr(provision_reviewer, "SessionLocal", lambda: session)
    monkeypatch.setattr(provision_reviewer, "create_tables", lambda: None)

    assert provision_reviewer.main(["missing@example.test"]) == 1
    assert session.committed is False
    assert "No account" in capsys.readouterr().err
