from sqlalchemy import *
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///livestream.db"
)

engine = create_engine(DATABASE_URL)

metadata = MetaData()

livestreams = Table(
    "livestreams",
    metadata,

    Column(
        "id",
        Integer,
        primary_key=True
    ),

    Column(
        "title",
        String,
        nullable=False
    ),

    Column(
        "platform",
        String
    ),

    Column(
        "description",
        Text
    ),

    Column(
        "url",
        String,
        unique=True
    ),

    Column(
        "keyword",
        String
    ),

    Column(
        "status",
        String
    ),

    Column(
        "start_time",
        String
    ),

    Column(
        "scheduled_start_time",
        String
    ),

    Column(
        "actual_start_time",
        String
    ),

    Column(
        "actual_end_time",
        String
    ),

    Column(
        "score",
        Integer,
        default=0
    ),

    Column(
        "priority",
        String
    ),

    Column(
        "interaction_tip",
        Text
    ),

    Column(
        "industry",
        String
    ),

    Column(
        "language",
        String
    ),

    Column(
        "buyer_persona",
        String
    ),

    Column(
        "suggested_comment",
        Text
    ),

    Column(
        "created_at",
        DateTime,
        server_default=func.now()
    ),
)

metadata.create_all(engine)