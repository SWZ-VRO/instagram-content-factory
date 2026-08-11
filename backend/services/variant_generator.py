"""
Runs the transform catalog (transforms.py) against one probed master file,
keeping whichever outputs pass QC. Pure filesystem/ffmpeg work -- no DB
access here; backend/services/master_import.py is the orchestrator that
persists results.
"""
from dataclasses import dataclass, field
from pathlib import Path

from backend.core.config import settings
from backend.services import qc, transforms
from backend.services.ffmpeg_runner import FFmpegError, ProbeResult, run_ffmpeg


@dataclass
class GeneratedVariant:
    index: int
    transform_name: str
    filepath: Path
    probe: ProbeResult


@dataclass
class VariantGenerationResult:
    successes: list[GeneratedVariant] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)  # "{transform_name}: {reason}"


def generate_variants(
    master_filepath: Path, master_probe: ProbeResult, *, master_code: str, output_dir: Path
) -> VariantGenerationResult:
    """
    Tries each transform in backend.services.transforms.REGISTRY (exactly
    MAX_VARIANTS entries) in order and keeps the ones that succeed and pass
    QC. A single transform failing (e.g. an edge-case source resolution)
    never aborts the others -- the master only fails overall if fewer than
    MIN_VARIANTS succeed (checked by the caller).
    """
    successes: list[GeneratedVariant] = []
    failures: list[str] = []

    catalog = transforms.REGISTRY[: settings.MAX_VARIANTS]
    for i, spec in enumerate(catalog, start=1):
        variant_code = f"{master_code}_V{i:02d}"
        output_path = output_dir / f"{variant_code}.mp4"
        try:
            plan = spec.build(master_probe)
            args = transforms.build_ffmpeg_args(master_filepath, plan)
            run_ffmpeg(args, output_path=output_path)

            result = qc.check_variant_output(output_path)
            if not result.passed:
                output_path.unlink(missing_ok=True)
                failures.append(f"{spec.name}: {'; '.join(result.reasons)}")
                continue

            successes.append(
                GeneratedVariant(index=i, transform_name=spec.name, filepath=output_path, probe=result.probe)
            )
        except FFmpegError as exc:
            output_path.unlink(missing_ok=True)
            failures.append(f"{spec.name}: {exc}")

    return VariantGenerationResult(successes=successes, failures=failures)
