"""Manage user skincare profiles in the local SQLite store.

Usage:
    poetry run python scripts/manage_users.py list
    poetry run python scripts/manage_users.py show <user_id>
    poetry run python scripts/manage_users.py delete <user_id>
    poetry run python scripts/manage_users.py seed
    poetry run python scripts/manage_users.py add --name Aiko --skin-type oily \\
        --age 29 --goals brightening,hydration --pregnant \\
        --conditions rosacea --sun-damage moderate --routine-time minimal --budget budget

`seed` inserts a few diverse dummy personas (handy for testing how the coach
adapts its advice). Run `list` afterwards to see the generated ids.
"""
import argparse
import os
import sys

# Make `src` importable no matter where this script is launched from.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from src.state import UserProfile  # noqa: E402
from src import user_store  # noqa: E402


def _csv(value):
    return [v.strip() for v in value.split(",") if v.strip()] if value else []


def cmd_list(_args):
    users = user_store.list_users()
    if not users:
        print("No users yet. Try: poetry run python scripts/manage_users.py seed")
        return
    print(f"{len(users)} user(s):")
    for uid, name in users:
        print(f"  {uid}  {name or '(unnamed)'}")


def cmd_show(args):
    profile = user_store.get_user(args.user_id)
    if profile is None:
        print(f"No user found with id: {args.user_id}")
        sys.exit(1)
    print(f"User {args.user_id}:")
    for field, value in profile.model_dump().items():
        print(f"  {field:20} {value}")


def cmd_delete(args):
    if user_store.delete_user(args.user_id):
        print(f"Deleted {args.user_id}")
    else:
        print(f"No user found with id: {args.user_id}")
        sys.exit(1)


def cmd_add(args):
    profile = UserProfile(
        skin_type=args.skin_type,
        age=args.age,
        gender=args.gender,
        goals=_csv(args.goals),
        is_pregnant=args.pregnant,
        skin_conditions=_csv(args.conditions),
        sun_damage_history=args.sun_damage,
        routine_time=args.routine_time,
        budget=args.budget,
    )
    uid = user_store.save_user(profile, name=args.name)
    print(f"Added user '{args.name or '(unnamed)'}' with id: {uid}")


# A few contrasting personas so you can see the coach change its advice.
_SEED_PERSONAS = [
    ("Aiko", UserProfile(
        skin_type="combination", age=32, gender="female",
        goals=["brightening", "anti_aging", "hydration"], is_pregnant=False,
        skin_conditions=[], sun_damage_history="mild",
        routine_time="moderate", budget="mid-range")),
    ("Haruto", UserProfile(
        skin_type="oily", age=24, gender="male",
        goals=["acne_control"], is_pregnant=False,
        skin_conditions=["acne"], sun_damage_history="none",
        routine_time="minimal", budget="budget")),
    ("Mei", UserProfile(
        skin_type="sensitive", age=29, gender="female",
        goals=["barrier_repair", "hydration"], is_pregnant=True,
        skin_conditions=["rosacea", "eczema"], sun_damage_history="none",
        routine_time="moderate", budget="mid-range")),
    ("Yuki", UserProfile(
        skin_type="dry", age=52, gender="female",
        goals=["anti_aging", "brightening"], is_pregnant=False,
        skin_conditions=["hyperpigmentation"], sun_damage_history="severe",
        routine_time="extensive", budget="premium")),
]


def cmd_seed(_args):
    print("Seeding dummy personas:")
    for name, profile in _SEED_PERSONAS:
        uid = user_store.save_user(profile, name=name)
        print(f"  {uid}  {name}  ({profile.skin_type}, goals={profile.goals})")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage user skincare profiles.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List all users").set_defaults(func=cmd_list)
    sub.add_parser("seed", help="Insert diverse dummy personas").set_defaults(func=cmd_seed)

    p_show = sub.add_parser("show", help="Show one user's full profile")
    p_show.add_argument("user_id")
    p_show.set_defaults(func=cmd_show)

    p_del = sub.add_parser("delete", help="Delete a user")
    p_del.add_argument("user_id")
    p_del.set_defaults(func=cmd_delete)

    p_add = sub.add_parser("add", help="Add a user")
    p_add.add_argument("--name")
    p_add.add_argument("--skin-type", choices=["dry", "oily", "combination", "normal", "sensitive"])
    p_add.add_argument("--age", type=int)
    p_add.add_argument("--gender")
    p_add.add_argument("--goals", help="Comma-separated, e.g. brightening,hydration")
    p_add.add_argument("--pregnant", action="store_true")
    p_add.add_argument("--conditions", help="Comma-separated, e.g. rosacea,eczema")
    p_add.add_argument("--sun-damage", choices=["none", "mild", "moderate", "severe"])
    p_add.add_argument("--routine-time", choices=["minimal", "moderate", "extensive"])
    p_add.add_argument("--budget", choices=["budget", "mid-range", "premium"])
    p_add.set_defaults(func=cmd_add)

    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    args.func(args)
