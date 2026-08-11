"""Script ponctuel : remplit demo.db avec quelques données d'exemple pour
que l'aperçu (/demo) ne soit pas vide. Ne touche jamais content/masters/
(pas de vrai ffmpeg ici) -- crée directement les lignes en base, comme le
ferait le pipeline normal, pour montrer à quoi ça ressemble une fois
rempli. À supprimer / ignorer une fois le vrai pipeline utilisé."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from backend.core.database import SessionLocal
from backend.models.account import Account
from backend.models.caption import Caption
from backend.models.enums import AccountStatus, ConnectionStatus, VariantStatus
from backend.models.master import Master
from backend.models.variant import Variant

db = SessionLocal()

accounts = [
    Account(username="ma_marque_mode", timezone="Europe/Paris", status=AccountStatus.ACTIVE,
            connection_status=ConnectionStatus.DISCONNECTED, daily_min_posts=2, daily_max_posts=4),
    Account(username="ma_marque_fitness", timezone="Europe/Paris", status=AccountStatus.ACTIVE,
            connection_status=ConnectionStatus.DISCONNECTED, daily_min_posts=1, daily_max_posts=3),
]
db.add_all(accounts)
db.commit()

master = Master(master_code="MASTER_001", filename="MASTER_001.mp4", filepath="content/archive/MASTER_001.mp4",
                 sha256="demo" + "0" * 60, duration_seconds=14.2)
db.add(master)
db.commit()

captions_text = [
    "Nouvelle collection dispo maintenant 🔥",
    "On a écouté vos retours, la voilà.",
    None,
    "Le detail qui change tout.",
    None,
]
for i, cap in enumerate(captions_text, start=1):
    v = Variant(
        master_id=master.id, variant_code=f"MASTER_001_V{i:02d}", filename=f"MASTER_001_V{i:02d}.mp4",
        filepath=f"content/variants/MASTER_001_V{i:02d}.mp4", sha256=f"demovariant{i:02d}" + "0" * 50,
        transform=["crop_center", "zoom_in", "reframe_vertical", "mirror_horizontal", "trim_skip_intro"][i - 1],
        duration_seconds=13.5,
        status=VariantStatus.AVAILABLE if cap else VariantStatus.MISSING_CAPTION,
    )
    db.add(v)
    db.commit()
    if cap:
        db.add(Caption(variant_id=v.id, text=cap, source="csv"))
        db.commit()

db.close()
print("Demo data seeded.")
