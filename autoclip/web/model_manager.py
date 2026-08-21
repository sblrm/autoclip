"""Checksum-safe, user-triggered installation of pinned local model plans."""

from __future__ import annotations

import hashlib
import json
import shutil
import stat
import urllib.request
import zipfile
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

from autoclip.web.model_catalog import MODEL_PLANS, ModelPlan


class ModelInstallError(ValueError):
    """Base error for a model installation rejected by local verification."""


class UnknownModelPlan(ModelInstallError):
    pass


class ResearchAcknowledgementRequired(ModelInstallError):
    pass


class ModelChecksumError(ModelInstallError):
    pass


class ModelSizeError(ModelInstallError):
    pass


class UnsafeArchiveMember(ModelInstallError):
    pass


class ArchiveMemberMissing(ModelInstallError):
    pass


@dataclass(frozen=True)
class InstalledModel:
    plan: ModelPlan
    path: Path
    cached: bool


Downloader = Callable[[str], Iterable[bytes]]
Report = Callable[..., None]


def _urllib_downloader(url: str) -> Iterable[bytes]:
    """Yield an approved model URL in bounded chunks when a user requests it."""
    with urllib.request.urlopen(url) as response:  # noqa: S310 - URL is catalog-owned.
        while chunk := response.read(1024 * 1024):
            yield chunk


class ModelManager:
    """Installs only catalogued artifacts below one local models root."""

    def __init__(
        self,
        models_root: Path | None = None,
        *,
        downloader: Downloader | None = None,
        model_plans: Mapping[str, ModelPlan] | None = None,
    ) -> None:
        self.models_root = (models_root or Path.home() / ".autoclip" / "models").expanduser()
        self.downloader = downloader or _urllib_downloader
        self._model_plans = model_plans or MODEL_PLANS

    def is_installed(self, plan_id: str) -> bool:
        """Return whether a catalogued direct or archive model is verified locally."""
        try:
            plan = self._plan(plan_id)
            return self._is_valid(self._destination(plan), plan)
        except (ModelInstallError, OSError):
            return False

    def install(self, plan_id: str, acknowledged: bool, report: Report) -> InstalledModel:
        """Verify and atomically persist one server-selected catalog plan."""
        plan = self._plan(plan_id)
        if plan.research_only and not acknowledged:
            raise ResearchAcknowledgementRequired(
                f"research_acknowledgement_required: plan_id={plan.id}",
            )

        destination = self._destination(plan)
        if self._is_valid(destination, plan):
            report("model_cache_hit", plan.id)
            return InstalledModel(plan=plan, path=destination, cached=True)

        archive_path = self.models_root / f"{plan.id}.part"
        try:
            self._download_verified(plan, archive_path, report)
            if plan.archive_member is None:
                self._atomic_replace(archive_path, destination)
            else:
                self._extract_member_atomically(archive_path, plan, destination)
                self._write_archive_manifest(destination, plan)
            report("model_installed", plan.id)
            return InstalledModel(plan=plan, path=destination, cached=False)
        except Exception:
            if plan.archive_member is not None:
                self._remove_archive_install(destination)
            raise
        finally:
            archive_path.unlink(missing_ok=True)

    def _plan(self, plan_id: str) -> ModelPlan:
        try:
            return self._model_plans[plan_id]
        except KeyError as exc:
            raise UnknownModelPlan(f"unknown_model: plan_id={plan_id}") from exc

    def _destination(self, plan: ModelPlan) -> Path:
        relative = PurePosixPath(plan.destination_relative_path)
        windows_relative = PureWindowsPath(plan.destination_relative_path)
        if (
            relative.is_absolute()
            or windows_relative.is_absolute()
            or windows_relative.drive
            or ".." in relative.parts
            or ".." in windows_relative.parts
        ):
            raise UnsafeArchiveMember(f"unsafe_destination: {plan.destination_relative_path}")

        root = self.models_root.resolve()
        destination = (root / Path(*relative.parts)).resolve()
        if root != destination and root not in destination.parents:
            raise UnsafeArchiveMember(f"unsafe_destination: {plan.destination_relative_path}")
        return destination

    def _is_valid(self, destination: Path, plan: ModelPlan) -> bool:
        if not self._is_safe_regular_file(destination):
            return False
        if plan.archive_member is not None:
            return self._has_matching_archive_manifest(destination, plan)
        if destination.stat().st_size != plan.bytes:
            return False
        digest = hashlib.sha256()
        with destination.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest() == plan.sha256

    @staticmethod
    def _is_safe_regular_file(path: Path) -> bool:
        try:
            return not path.is_symlink() and stat.S_ISREG(path.lstat().st_mode)
        except OSError:
            return False

    @staticmethod
    def _manifest_path(destination: Path) -> Path:
        return destination.with_name(f"{destination.name}.autoclip.json")

    def _has_matching_archive_manifest(self, destination: Path, plan: ModelPlan) -> bool:
        manifest_path = self._manifest_path(destination)
        if not self._is_safe_regular_file(manifest_path):
            return False
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        return isinstance(manifest, dict) and all(
            manifest.get(field) == value
            for field, value in self._archive_manifest(plan, destination).items()
        )

    @staticmethod
    def _archive_manifest(plan: ModelPlan, destination: Path) -> dict[str, str | int]:
        extracted_bytes, extracted_sha256 = ModelManager._file_metadata(destination)
        return {
            "plan_id": plan.id,
            "source_url": plan.source_url,
            "archive_sha256": plan.sha256,
            "archive_bytes": plan.bytes,
            "destination_relative_path": plan.destination_relative_path,
            "extracted_bytes": extracted_bytes,
            "extracted_sha256": extracted_sha256,
        }

    def _write_archive_manifest(self, destination: Path, plan: ModelPlan) -> None:
        manifest_path = self._manifest_path(destination)
        temporary = manifest_path.with_name(f".{manifest_path.name}.{plan.id}.part")
        try:
            temporary.write_text(
                json.dumps(self._archive_manifest(plan, destination), sort_keys=True),
                encoding="utf-8",
            )
            self._atomic_replace(temporary, manifest_path)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

    def _remove_archive_install(self, destination: Path) -> None:
        destination.unlink(missing_ok=True)
        self._manifest_path(destination).unlink(missing_ok=True)

    @staticmethod
    def _file_metadata(path: Path) -> tuple[int, str]:
        digest = hashlib.sha256()
        total = 0
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                total += len(chunk)
                digest.update(chunk)
        return total, digest.hexdigest()

    def _download_verified(self, plan: ModelPlan, part_path: Path, report: Report) -> None:
        part_path.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        total = 0
        report("model_download_started", plan.id)
        try:
            with part_path.open("wb") as output:
                for chunk in self.downloader(plan.source_url):
                    if not isinstance(chunk, bytes):
                        raise ModelInstallError("invalid_download_chunk")
                    total += len(chunk)
                    if total > plan.bytes:
                        raise ModelSizeError(f"model_size_error: plan_id={plan.id}")
                    digest.update(chunk)
                    output.write(chunk)
            if digest.hexdigest() != plan.sha256:
                raise ModelChecksumError(f"model_checksum_error: plan_id={plan.id}")
            if total != plan.bytes:
                raise ModelSizeError(f"model_size_error: plan_id={plan.id}")
        except Exception:
            part_path.unlink(missing_ok=True)
            raise

    def _extract_member_atomically(self, archive_path: Path, plan: ModelPlan, destination: Path) -> None:
        assert plan.archive_member is not None
        self._validate_archive_member_name(plan.archive_member)
        output_part = destination.with_name(f".{destination.name}.{plan.id}.part")
        try:
            with zipfile.ZipFile(archive_path) as archive:
                names = archive.namelist()
                for name in names:
                    self._validate_archive_member_name(name)
                    info = archive.getinfo(name)
                    if stat.S_ISLNK(info.external_attr >> 16):
                        raise UnsafeArchiveMember(f"unsafe_archive_member: {name}")
                if plan.archive_member not in names:
                    raise ArchiveMemberMissing(f"archive_member_missing: {plan.archive_member}")
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(plan.archive_member) as source, output_part.open("wb") as output:
                    shutil.copyfileobj(source, output, length=1024 * 1024)
            self._atomic_replace(output_part, destination)
        except Exception:
            output_part.unlink(missing_ok=True)
            raise

    @staticmethod
    def _validate_archive_member_name(name: str) -> None:
        posix = PurePosixPath(name)
        windows = PureWindowsPath(name)
        if (
            not name
            or posix.is_absolute()
            or windows.is_absolute()
            or windows.drive
            or ".." in posix.parts
            or ".." in windows.parts
        ):
            raise UnsafeArchiveMember(f"unsafe_archive_member: {name}")

    @staticmethod
    def _atomic_replace(source: Path, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        source.replace(destination)
