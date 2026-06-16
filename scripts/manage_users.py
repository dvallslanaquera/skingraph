"""Manage user skincare profiles in the local SQLite store.

Usage:
    poetry run python scripts/manage_users.py list
    poetry run python scripts/manage_users.py show <user_id>
    poetry run python scripts/manage_users.py delete <user_id>
    poetry run python scripts/manage_users.py seed
    poetry run python scripts/manage_users.py add --name Aiko --skin-type oily \\
        --age 29 --goals "fine lines,hydration" --pregnant \\
        --conditions rosacea --sun-damage moderate --routine-time minimal \\
        --fitzpatrick 3 --undertone asian --devices --budget 75

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
        fitzpatrick=args.fitzpatrick,
        skin_undertone=args.undertone,
        goals=_csv(args.goals),
        is_pregnant=args.pregnant,
        skin_conditions=_csv(args.conditions),
        sun_damage_history=args.sun_damage,
        routine_time=args.routine_time,
        consider_devices=args.devices,
        budget=args.budget,
    )
    uid = user_store.save_user(profile, name=args.name)
    print(f"Added user '{args.name or '(unnamed)'}' with id: {uid}")


# A few contrasting personas so you can see the coach change its advice.
_SEED_PERSONAS = [
    ("Aiko", UserProfile(
        skin_type="combination", age=32, gender="female",
        fitzpatrick=3, skin_undertone="asian",
        goals=["dullness", "fine lines", "dryness/dehydration"], is_pregnant=False,
        skin_conditions=[], sun_damage_history="mild",
        routine_time="moderate", consider_devices=True, budget=75)),
    ("Haruto", UserProfile(
        skin_type="oily", age=24, gender="male",
        fitzpatrick=4, skin_undertone="asian",
        goals=["acne", "blackheads/whiteheads", "enlarged pores"], is_pregnant=False,
        skin_conditions=["acne"], sun_damage_history="none",
        routine_time="minimal", consider_devices=False, budget=25)),
    ("Mei", UserProfile(
        skin_type="sensitive", age=29, gender="female",
        fitzpatrick=2, skin_undertone="asian",
        goals=["redness", "dryness/dehydration"], is_pregnant=True,
        skin_conditions=["rosacea", "eczema"], sun_damage_history="none",
        routine_time="moderate", consider_devices=False, budget=75)),
    ("Yuki", UserProfile(
        skin_type="dry", age=52, gender="female",
        fitzpatrick=2, skin_undertone="asian",
        goals=["deep wrinkles", "hyperpigmentation", "sagging skin"], is_pregnant=False,
        skin_conditions=["hyperpigmentation"], sun_damage_history="severe",
        routine_time="extensive", consider_devices=True, budget=250)),
]

# Routine products for each persona. Intentionally includes conflict-prone
# combinations (Retinol + Ascorbic Acid, BHA + AHA over-exfoliation) so the
# auditor and coach nodes have real signals to fire on.
_SEED_ROUTINES = {
    # Aiko — combination skin, brightening + anti-aging focus.
    # CONFLICT: Rohto Melano CC (Ascorbic Acid, PM) + DHC Retinol Cream (Retinol, PM)
    "Aiko": [
        {
            "brand": "Hada Labo",
            "product_name": "Gokujyun Hyaluronic Acid Lotion (AM+PM)",
            "ingredients": [
                "Water", "Butylene Glycol", "Glycerin", "Sodium Hyaluronate",
                "Hyaluronic Acid", "Hydroxyethylcellulose", "Citric Acid",
                "Sodium Citrate", "Methylparaben",
            ],
            "is_quasi_drug": False,
        },
        {
            "brand": "Rohto",
            "product_name": "Melano CC Vitamin C Intensive Spot Essence (PM)",
            "ingredients": [
                "Water", "Ascorbic Acid", "Dipropylene Glycol", "Isopropanol",
                "Polyethylene Glycol 400", "dl-alpha-Tocopherol", "Citric Acid",
                "Sodium Citrate",
            ],
            "is_quasi_drug": True,
        },
        {
            # Retinol conflicts with Ascorbic Acid above when used same night
            "brand": "DHC",
            "product_name": "Retinol Night Cream (PM)",
            "ingredients": [
                "Water", "Glycerin", "Dimethicone", "Cyclopentasiloxane", "Retinol",
                "Cetyl Alcohol", "Niacinamide", "BHT", "Phenoxyethanol",
            ],
            "is_quasi_drug": False,
        },
    ],

    # Haruto — oily/acne-prone, budget, minimal routine.
    # CONFLICT: Salicylic Acid (BHA) in toner + Glycolic Acid (AHA) in peeling lotion
    #           = overexfoliation risk; two BHA products = redundancy.
    "Haruto": [
        {
            "brand": "Biore",
            "product_name": "UV Aqua Rich Watery Essence SPF50+ (AM)",
            "ingredients": [
                "Water", "Alcohol", "Ethylhexyl Methoxycinnamate",
                "Diethylamino Hydroxybenzoyl Hexyl Benzoate",
                "Bis-Ethylhexyloxyphenol Methoxyphenyl Triazine",
                "Glycerin", "Dimethicone", "Carbomer", "Methylparaben",
            ],
            "is_quasi_drug": False,
        },
        {
            "brand": "Mentholatum",
            "product_name": "Acnes Medicated Serum Toner (AM+PM)",
            "ingredients": [
                "Water", "Butylene Glycol", "Salicylic Acid", "Niacinamide",
                "Dipotassium Glycyrrhizate", "Methylparaben",
            ],
            "is_quasi_drug": True,
        },
        {
            # Salicylic Acid again = redundant BHA on top of Acnes toner
            "brand": "Rohto",
            "product_name": "Acnes Creamy Wash (PM)",
            "ingredients": [
                "Water", "Myristic Acid", "Potassium Hydroxide", "Glycerin",
                "Salicylic Acid", "Dipotassium Glycyrrhizate", "Panthenol",
                "Methylparaben",
            ],
            "is_quasi_drug": True,
        },
        {
            # AHA + BHA same PM routine = over-exfoliation burden
            "brand": "Hada Labo",
            "product_name": "Koi-Gokujyun Alpha Lotion (PM)",
            "ingredients": [
                "Water", "Glycerin", "Butylene Glycol", "Sodium Hyaluronate",
                "Glycolic Acid", "Lactic Acid", "Citric Acid", "Niacinamide",
                "Methylparaben",
            ],
            "is_quasi_drug": False,
        },
        {
            "brand": "Kose",
            "product_name": "Softymo Speedy Cleansing Oil (PM)",
            "ingredients": [
                "Liquid Paraffin", "PEG-8 Glyceryl Isostearate",
                "Isopropyl Myristate", "PEG-20 Glyceryl Triisostearate",
                "Squalane", "Tocopherol", "Methylparaben",
            ],
            "is_quasi_drug": False,
        },
    ],

    # Mei — sensitive + pregnant; single ultra-gentle product, no actives.
    "Mei": [
        {
            "brand": "Hada Labo",
            "product_name": "Gokujyun Premium Moist Lotion (AM+PM)",
            "ingredients": [
                "Water", "Butylene Glycol", "Glycerin", "Sodium Hyaluronate",
                "Hydroxyethylcellulose", "Citric Acid", "Sodium Citrate",
                "Methylparaben",
            ],
            "is_quasi_drug": False,
        },
    ],

    # Yuki — dry, 52, anti-aging + brightening, severe sun damage.
    # CONFLICT: Ascorbic Acid (Melano CC, PM) + Retinol (DHC Cream, PM)
    "Yuki": [
        {
            "brand": "Anessa",
            "product_name": "Perfect UV Sunscreen Skincare Milk SPF50+ PA++++ (AM)",
            "ingredients": [
                "Water", "Ethylhexyl Methoxycinnamate",
                "Diethylamino Hydroxybenzoyl Hexyl Benzoate",
                "Alcohol", "Glycerin", "Titanium Dioxide", "Zinc Oxide",
                "Niacinamide", "Dimethicone", "Methylparaben",
            ],
            "is_quasi_drug": False,
        },
        {
            "brand": "Rohto",
            "product_name": "Melano CC Vitamin C Intensive Spot Essence (PM)",
            "ingredients": [
                "Water", "Ascorbic Acid", "Dipropylene Glycol", "Isopropanol",
                "dl-alpha-Tocopherol", "Citric Acid", "Sodium Citrate",
            ],
            "is_quasi_drug": True,
        },
        {
            # Retinol conflicts with Ascorbic Acid above; heavy active for dry skin
            "brand": "DHC",
            "product_name": "Retinol Night Cream (PM)",
            "ingredients": [
                "Water", "Glycerin", "Dimethicone", "Cyclopentasiloxane", "Retinol",
                "Cetyl Alcohol", "Niacinamide", "BHT", "Phenoxyethanol",
            ],
            "is_quasi_drug": False,
        },
    ],
}


def cmd_seed(_args):
    print("Seeding dummy personas:")
    for name, profile in _SEED_PERSONAS:
        uid = user_store.save_user(profile, name=name)
        print(f"  {uid}  {name}  ({profile.skin_type}, goals={profile.goals})")
        for prod in _SEED_ROUTINES.get(name, []):
            pid = user_store.add_routine_product(
                uid,
                prod["brand"],
                prod["product_name"],
                prod["ingredients"],
                prod.get("is_quasi_drug"),
            )
            print(f"    + {prod['brand']} — {prod['product_name']}  [{pid}]")


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
    p_add.add_argument("--gender", choices=["male", "female", "other"])
    p_add.add_argument("--fitzpatrick", type=int, choices=[1, 2, 3, 4, 5, 6],
                       help="Fitzpatrick phototype 1 (I) to 6 (VI)")
    p_add.add_argument("--undertone", choices=["asian", "non_asian"])
    p_add.add_argument("--goals", help="Comma-separated, e.g. 'fine lines,redness'")
    p_add.add_argument("--pregnant", action="store_true")
    p_add.add_argument("--conditions", help="Comma-separated, e.g. rosacea,eczema")
    p_add.add_argument("--sun-damage", choices=["none", "mild", "moderate", "severe"])
    p_add.add_argument("--routine-time", choices=["minimal", "moderate", "extensive"])
    p_add.add_argument("--devices", action="store_true",
                       help="Open to devices / at-home treatments")
    p_add.add_argument("--budget", type=int, help="Monthly budget in USD (0–250+)")
    p_add.set_defaults(func=cmd_add)

    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    args.func(args)
