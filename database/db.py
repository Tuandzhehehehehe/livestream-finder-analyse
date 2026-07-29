"""
database/db.py — Database Engine & Table Schema Definitions
============================================================
Chứa toàn bộ schema cho hai database của hệ thống:

  [livestream.db]  — Dữ liệu livestream events (crawl & phân tích)
    • livestreams

  [channel_info.db] — Thông tin kênh / creator (xếp hạng & đề xuất theo khu vực)
    • channel_profiles
    • follower_snapshots
"""

import os
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv
# pyrefly: ignore [missing-import]
from sqlalchemy import (
    create_engine, MetaData, Table, Column,
    Integer, BigInteger, String, Text, Float, DateTime, JSON,
    UniqueConstraint, func,
)

load_dotenv()

# ── Engine: livestream.db ──────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///livestream.db")
engine       = create_engine(DATABASE_URL)
metadata     = MetaData()

# ── Table: livestreams ─────────────────────────────────────────────────────────
livestreams = Table(
    "livestreams",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("title", String, nullable=False),
    Column("platform", String),
    Column("description", Text),
    Column("url", String, unique=True),
    Column("keyword", String),
    Column("status", String),
    Column("start_time", String),
    Column("scheduled_start_time", String),
    Column("actual_start_time", String),
    Column("actual_end_time", String),
    Column("score", Integer, default=0),
    Column("priority", String),
    Column("interaction_tip", Text),
    Column("industry", String),
    Column("language", String),
    Column("buyer_persona", String),
    Column("suggested_comment", Text),
    Column("created_at", DateTime, server_default=func.now()),
)

metadata.create_all(engine)

# ── Engine: channel_info.db ───────────────────────────────────────────────────
_CHANNEL_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "channel_info.db",
)
channel_engine   = create_engine(f"sqlite:///{_CHANNEL_DB_PATH}", echo=False)
channel_metadata = MetaData()

# ── Table: channel_profiles ────────────────────────────────────────────────────
channel_profiles = Table(
    "channel_profiles",
    channel_metadata,

    # ── Identity ──────────────────────────────────────────────────────────────
    Column("id",           Integer, primary_key=True, autoincrement=True),
    Column("platform",     String(32),  nullable=False),          # youtube | tiktok
    Column("channel_id",   String(256), nullable=False),          # platform-native ID
    Column("channel_url",  String(512), nullable=False, unique=True),
    Column("username",     String(256)),                          # @handle / unique_id
    Column("channel_name", String(512)),                          # display name

    # ── Audience ──────────────────────────────────────────────────────────────
    Column("follower_count",  BigInteger, default=0),             # latest snapshot
    Column("growth_7d_pct",   Float),                             # % change 7 days
    Column("growth_30d_pct",  Float),                             # % change 30 days

    # ── Activity ──────────────────────────────────────────────────────────────
    Column("total_livestreams",     Integer, default=0),
    Column("broadcast_freq_weekly", Float),                       # avg lives/week
    Column("last_live_at",          String(64)),                  # ISO-8601
    Column("avg_viewers",           Integer),

    # ── Content ───────────────────────────────────────────────────────────────
    Column("category",    String(256)),
    Column("language",    String(16)),
    Column("description", Text),
    Column("is_verified", Integer, default=0),                    # 0/1

    # ── Location ──────────────────────────────────────────────────────────────
    Column("location_raw", String(512)),                          # raw string from platform
    Column("country",      String(128)),                          # VN / TH / US …
    Column("region_tag",   String(64)),                           # VN-HN / VN-HCM / TH-BKK …
    Column("timezone",     String(64)),

    # ── Seller / Creator info ─────────────────────────────────────────────────
    # Stored as JSON blob:
    # {
    #   "is_seller": true,   "shop_name": "...", "shop_url": "...",
    #   "brand_name": "...", "links": [...],     "contact_email": "..."
    # }
    Column("seller_info", JSON),

    # ── Activity history ──────────────────────────────────────────────────────
    # JSON list of recent live events:
    # [{"title": "...", "started_at": "...", "viewers": 123, "duration_min": 45}, ...]
    Column("activity_history", JSON),

    # ── Scoring ──────────────────────────────────────────────────────────────────
    Column("cas",              Float),                               # Channel Attraction Score [0–100]
    Column("cas_computed_at",  DateTime),                            # khi nào CAS được tính lại lần cuối

    # ── Meta ─────────────────────────────────────────────────────────────────────
    Column("channel_created_at", String(64)),                     # when channel was created
    Column("crawled_at",  DateTime, server_default=func.now()),
    Column("updated_at",  DateTime, server_default=func.now(), onupdate=func.now()),

    UniqueConstraint("platform", "channel_id", name="uq_platform_channel"),
)

# ── Table: follower_snapshots ──────────────────────────────────────────────────
follower_snapshots = Table(
    "follower_snapshots",
    channel_metadata,

    Column("id",             Integer, primary_key=True, autoincrement=True),
    Column("channel_url",    String(512), nullable=False),        # FK-like ref to channel_profiles
    Column("platform",       String(32),  nullable=False),
    Column("follower_count", BigInteger,  nullable=False),
    Column("snapped_at",     DateTime, server_default=func.now()),

    UniqueConstraint("channel_url", "snapped_at", name="uq_snapshot"),
)

channel_metadata.create_all(channel_engine)