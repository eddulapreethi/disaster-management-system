import argparse
import sys

from sqlalchemy import select

from app.database.database import SessionLocal, create_tables
from app.models.user import User


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Grant reviewer access to an existing DisasterGuard account."
    )
    parser.add_argument("email", help="Email address of the existing account to promote.")
    args = parser.parse_args(argv)
    email = args.email.strip().lower()
    if not email:
        parser.error("email must not be blank")

    create_tables()
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            print("No account with that email exists; create the account before promotion.", file=sys.stderr)
            return 1
        if user.role == "reviewer":
            print("Account already has reviewer access.")
            return 0
        user.role = "reviewer"
        db.commit()
        print(f"Reviewer access granted to existing account id {user.id}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
