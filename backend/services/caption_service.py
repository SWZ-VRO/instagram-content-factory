"""
Caption import (§11-13). Text is used exactly as provided -- no reformulation,
translation, hashtag/emoji injection. This module only parses/associates;
Phase 1 exposes it via POST /captions/import for CSV, matching §12's format.
"""
import csv
from io import StringIO

from sqlalchemy.orm import Session

from backend.models.caption import Caption
from backend.repositories import caption_repo, variant_repo


class CaptionImportError(Exception):
    pass


def import_captions_csv(db: Session, csv_text: str) -> list[Caption]:
    """
    Expects the exact format from §12:
        master_id,variant_id,caption
        MASTER_001,MASTER_001_V01,"Caption 01"
    `variant_id` here is the human-readable variant_code (e.g. MASTER_001_V01).
    Unknown variant codes are skipped and reported, not silently dropped.
    """
    reader = csv.DictReader(StringIO(csv_text))
    required = {"master_id", "variant_id", "caption"}
    if reader.fieldnames is None or not required.issubset(set(reader.fieldnames)):
        raise CaptionImportError(f"CSV must have columns {sorted(required)}, got {reader.fieldnames}")

    attached: list[Caption] = []
    errors: list[str] = []
    for row in reader:
        variant_code = row["variant_id"].strip()
        text = row["caption"]
        variant = variant_repo.get_by_code(db, variant_code)
        if variant is None:
            errors.append(f"unknown variant_id '{variant_code}', skipped")
            continue
        attached.append(caption_repo.attach(db, variant_id=variant.id, text=text, source="csv"))

    if errors:
        # Rows that matched a known variant were already attached/committed
        # above; we still surface the unmatched ones instead of failing
        # silently (§12 requires exact association, not best-effort).
        raise CaptionImportError(f"{len(attached)} caption(s) attached; unresolved rows: " + "; ".join(errors))
    return attached
