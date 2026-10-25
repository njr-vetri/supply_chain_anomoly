"""Local script to reset an admin user's password directly in the database."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add project root to path
root = Path(__file__).resolve().parents[1]
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from src.core.config import load_settings
from src.core.repository import Repository, UserRow
from src.security.auth import generate_temp_password, hash_password


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--company", default="local", help="Company ID (default: local)")
    parser.add_argument("--user", help="Username or email of admin (optional; defaults to first admin found)")
    parser.add_argument("--password", help="New password (optional; auto-generated if omitted)")
    args = parser.parse_args()

    settings = load_settings()
    repo = Repository(settings.storage.url, company_id=args.company)

    admin_user: UserRow | None = None
    if args.user:
        admin_user = repo.get_user_by_email_or_username(args.user)
        if not admin_user:
            print(f"Error: User '{args.user}' not found in company '{args.company}'.", file=sys.stderr)
            return 1
        if admin_user.role != "admin":
            print(f"Error: User '{args.user}' is not an admin (role is {admin_user.role}).", file=sys.stderr)
            return 1
    else:
        # Find first admin
        users = repo.list_users()
        admin_user = next((u for u in users if u.role == "admin"), None)
        if not admin_user:
            print(f"Error: No admin user found for company '{args.company}'.", file=sys.stderr)
            return 1

    new_pwd = args.password or generate_temp_password(16)
    admin_user.password_hash = hash_password(new_pwd)
    admin_user.failed_login_attempts = 0
    admin_user.locked_until = None
    admin_user.must_change_password = True
    repo.add(admin_user)

    print(f"Successfully reset admin password for company: {args.company}")
    print(f"  Username: {admin_user.username}")
    print(f"  Email:    {admin_user.email}")
    print(f"  Password: {new_pwd}")
    print("  Note: User will be required to change this password on next login.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
