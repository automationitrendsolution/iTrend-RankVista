"""Populate the configured MongoDB with realistic development data.
Refuses to run unless --force is given, so a populated database is never touched."""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from django.core.management.base import BaseCommand, CommandError
from pymongo import UpdateOne

from apps.common.mongo import get_collection, ping
from apps.common.schema import ASINS, KEYWORDS, PROJECTS, RANKINGS, ensure_indexes

MARKETS = ["US", "US", "US", "UK", "DE", "CA"]

PRODUCT_LINES = [
    ("Snow Cover Kw Analysis", "Windshield Snow Cover", "snow cover", ["car windshield snow cover", "windshield cover for ice and snow", "snow cover for car windshield", "frost cover windshield", "winter windshield cover"]),
    ("Pivot & Squeegee", "Extendable Snow Brush", "snow brush", ["car scraper snow brush", "snow brush for suv", "snow scraper for suv", "extendable snow brush", "ice scraper extendable"]),
    ("Custom Sunshade Fitment", "Custom Fit Sun Shade", "sunshade", ["custom fit windshield sun shade", "sunshade for truck", "car sun shade front windshield", "foldable sunshade", "reflective sun shade"]),
    ("Handheld Fan US", "Portable Handheld Fan", "handheld fan", ["handheld fan portable", "mini fan rechargeable", "personal fan handheld", "battery operated fan", "usb handheld fan"]),
    ("Steering Wheel Cover", "Premium Steering Cover", "steering wheel cover", ["steering wheel cover leather", "steering wheel cover for women", "universal steering wheel cover", "car steering cover", "anti slip steering cover"]),
    ("Rollershade Track", "Retractable Roller Shade", "roller shade", ["car window roller shade", "retractable sun shade", "side window shade", "baby car window shade", "magnetic window shade"]),
    ("Medium Choice KW Analysis", "All-Weather Floor Liner", "floor mats", ["all weather floor mats", "car floor liners", "rubber floor mats for suv", "custom fit floor mats", "3d floor mats"]),
    ("Snowbrush Pro", "Heavy Duty Snowbrush", "snowbrush", ["heavy duty snow brush", "snow broom for car", "telescoping snow brush", "snow removal tool car", "foam snow brush"]),
]

MODIFIERS = ["", " for car", " for suv", " for truck", " heavy duty", " premium", " 2 pack",
             " universal", " waterproof", " with strap", " large", " compact", " winter",
             " front windshield", " magnetic", " foldable", " reusable", " extra thick"]


class Command(BaseCommand):
    help = "Seed the MongoDB database with representative demo data for development."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--force", action="store_true", help="Required when data already exists.")
        parser.add_argument("--projects", type=int, default=24, help="Number of projects to create.")
        parser.add_argument("--days", type=int, default=45, help="Days of ranking history.")
        parser.add_argument("--seed", type=int, default=20260904, help="Deterministic RNG seed.")

    def handle(self, *args, **options) -> None:
        if not ping():
            raise CommandError("MongoDB is unreachable. Check MONGODB_URI in your .env.")

        existing = get_collection(PROJECTS).estimated_document_count()
        if existing and not options["force"]:
            raise CommandError(
                f"{existing} projects already exist. Re-run with --force to add demo data."
            )

        rng = random.Random(options["seed"])
        ensure_indexes()

        projects_col = get_collection(PROJECTS)
        asins_col = get_collection(ASINS)
        keywords_col = get_collection(KEYWORDS)
        rankings_col = get_collection(RANKINGS)

        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        history_days = options["days"]
        total_keywords = 0
        total_observations = 0

        for index in range(options["projects"]):
            base_name, product_title, _, seed_keywords = PRODUCT_LINES[index % len(PRODUCT_LINES)]
            suffix = "" if index < len(PRODUCT_LINES) else f" Set {index // len(PRODUCT_LINES) + 1}"
            project_id = 70001 + index
            market = MARKETS[index % len(MARKETS)]
            asin_count = rng.randint(2, 9)
            asins = [self._asin(rng) for _ in range(asin_count)]
            primary = asins[0]

            projects_col.update_one(
                {"project_id": project_id},
                {
                    "$set": {
                        "project_id": project_id,
                        "name": f"{base_name}{suffix}",
                        "name_lower": f"{base_name}{suffix}".lower(),
                        "marketplace": market,
                        "primary_asin": primary,
                        "image_url": "",
                        "status": "active",
                        "owner_id": None,
                        "tags": [],
                        "created_at": today - timedelta(days=rng.randint(60, 400)),
                        "updated_at": today,
                        "last_opened_at": today - timedelta(hours=rng.randint(1, 720)),
                    }
                },
                upsert=True,
            )

            project_keyword_total = 0
            for position, asin in enumerate(asins):
                keyword_count = rng.randint(18, 55)
                asins_col.update_one(
                    {"project_id": project_id, "asin": asin},
                    {
                        "$set": {
                            "project_id": project_id,
                            "asin": asin,
                            "title": f"{product_title} - {market} Variant {position + 1}",
                            "image_url": "",
                            "marketplace": market,
                            "brand": "iTrend Labs",
                            "price": round(rng.uniform(12.99, 89.99), 2),
                            "is_primary": position == 0,
                            "status": "active" if position < asin_count - 1 else "paused",
                            "tracked_keyword_count": keyword_count,
                            "created_at": today - timedelta(days=rng.randint(30, 300)),
                            "updated_at": today,
                        }
                    },
                    upsert=True,
                )

                keywords = self._keywords(rng, seed_keywords, keyword_count)
                project_keyword_total += len(keywords)
                total_keywords += len(keywords)

                keyword_ops: list[UpdateOne] = []
                ranking_ops: list[UpdateOne] = []

                for keyword in keywords:
                    baseline = rng.choice([4, 7, 9, 12, 18, 26, 41, 68, 120])
                    drift = rng.uniform(-0.35, 0.35)
                    tracked_from = rng.randint(0, max(0, history_days - 12))
                    current = baseline
                    sales = rng.choice([0, 0, 0, 1, 2, 3, 5, 6, 11, 13])

                    for offset in range(history_days):
                        day = today - timedelta(days=history_days - 1 - offset)
                        if offset < tracked_from:
                            continue
                        current = max(1, min(305, int(current + drift * rng.uniform(-6, 6))))
                        rank = current if rng.random() > 0.06 else -1
                        ranking_ops.append(
                            UpdateOne(
                                {
                                    "project_id": project_id,
                                    "asin": asin,
                                    "keyword_lower": keyword.lower(),
                                    "date": day,
                                },
                                {
                                    "$set": {
                                        "project_id": project_id,
                                        "asin": asin,
                                        "keyword": keyword,
                                        "keyword_lower": keyword.lower(),
                                        "date": day,
                                        "rank": rank,
                                        "is_amazon_choice": rank > 0 and rank <= 3 and rng.random() < 0.15,
                                        "is_sponsored": rng.random() < 0.08,
                                        "page": max(1, (rank // 48) + 1) if rank > 0 else 0,
                                    }
                                },
                                upsert=True,
                            )
                        )
                        total_observations += 1

                    keyword_ops.append(
                        UpdateOne(
                            {
                                "project_id": project_id,
                                "asin": asin,
                                "keyword_lower": keyword.lower(),
                            },
                            {
                                "$set": {
                                    "project_id": project_id,
                                    "asin": asin,
                                    "keyword": keyword,
                                    "keyword_lower": keyword.lower(),
                                    "search_volume": rng.randint(120, 48000),
                                    "kw_sales": sales,
                                    "sales_trend_pct": round(rng.uniform(-80, 1300), 1) if sales else 0.0,
                                    "conversion_pct": round(rng.uniform(0, 26), 1) if sales else 0.0,
                                    "is_tracked": True,
                                    "current_rank": current if current > 0 else None,
                                    "best_rank": max(1, current - rng.randint(0, 8)),
                                    "created_at": today - timedelta(days=history_days),
                                    "updated_at": today,
                                }
                            },
                            upsert=True,
                        )
                    )

                if keyword_ops:
                    keywords_col.bulk_write(keyword_ops, ordered=False)
                for chunk_start in range(0, len(ranking_ops), 2000):
                    rankings_col.bulk_write(ranking_ops[chunk_start : chunk_start + 2000], ordered=False)

            projects_col.update_one(
                {"project_id": project_id},
                {"$set": {"asin_count": asin_count, "keyword_count": project_keyword_total}},
            )
            self.stdout.write(f"  seeded project {project_id}: {base_name}{suffix}")

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {options['projects']} projects, {total_keywords} keywords, "
                f"{total_observations} rank observations."
            )
        )

    def _asin(self, rng: random.Random) -> str:
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ0123456789"
        return "B0" + "".join(rng.choice(alphabet) for _ in range(8))

    def _keywords(self, rng: random.Random, seeds: list[str], count: int) -> list[str]:
        """Expand seed phrases with modifiers into a unique keyword set."""
        produced: list[str] = []
        seen: set[str] = set()
        while len(produced) < count:
            phrase = (rng.choice(seeds) + rng.choice(MODIFIERS)).strip()
            if phrase not in seen:
                seen.add(phrase)
                produced.append(phrase)
            elif len(seen) > count * 3:
                break
        return produced
