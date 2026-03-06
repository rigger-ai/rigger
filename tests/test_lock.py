"""Tests for rigger._lock — lock file mechanism."""

import json
import os
import platform
from unittest.mock import patch

import pytest

from rigger._lock import (
    LOCK_FILE,
    HarnessAlreadyRunning,
    LockInfo,
    acquire_lock,
    harness_lock,
    release_lock,
)
from rigger._schema import HARNESS_DIR


class TestAcquireRelease:
    def test_acquire_creates_lock_file(self, tmp_path):
        info = acquire_lock(tmp_path)
        lock_path = tmp_path / HARNESS_DIR / LOCK_FILE
        assert lock_path.exists()
        data = json.loads(lock_path.read_text())
        assert data["pid"] == os.getpid()
        assert data["hostname"] == platform.node()
        assert data["instance_id"] == info.instance_id

    def test_release_removes_lock_file(self, tmp_path):
        info = acquire_lock(tmp_path)
        lock_path = tmp_path / HARNESS_DIR / LOCK_FILE
        assert lock_path.exists()
        release_lock(tmp_path, info)
        assert not lock_path.exists()

    def test_release_checks_instance_id(self, tmp_path):
        info = acquire_lock(tmp_path)
        wrong_info = LockInfo(
            pid=info.pid,
            timestamp=info.timestamp,
            instance_id="wrong_id",
            hostname=info.hostname,
        )
        release_lock(tmp_path, wrong_info)
        # Lock file should still exist (not released)
        assert (tmp_path / HARNESS_DIR / LOCK_FILE).exists()

    def test_release_noop_if_no_lock(self, tmp_path):
        info = LockInfo(
            pid=os.getpid(),
            timestamp=0.0,
            instance_id="abc",
            hostname=platform.node(),
        )
        release_lock(tmp_path, info)  # Should not raise

    def test_lock_info_fields(self, tmp_path):
        info = acquire_lock(tmp_path)
        assert info.pid == os.getpid()
        assert info.hostname == platform.node()
        assert len(info.instance_id) == 32  # UUID hex
        assert info.timestamp > 0


class TestConcurrentAcquisition:
    def test_live_pid_raises(self, tmp_path):
        acquire_lock(tmp_path)
        with pytest.raises(HarnessAlreadyRunning, match="Another harness instance"):
            acquire_lock(tmp_path)

    def test_different_host_raises(self, tmp_path):
        acquire_lock(tmp_path)
        # Overwrite lock file to simulate different host
        lock_path = tmp_path / HARNESS_DIR / LOCK_FILE
        data = json.loads(lock_path.read_text())
        data["hostname"] = "remote-server"
        lock_path.write_text(json.dumps(data))
        with pytest.raises(HarnessAlreadyRunning, match="different host"):
            acquire_lock(tmp_path)


class TestStaleLock:
    def test_dead_pid_acquires(self, tmp_path):
        # Create a lock with a definitely-dead PID
        info = acquire_lock(tmp_path)
        lock_path = tmp_path / HARNESS_DIR / LOCK_FILE
        data = json.loads(lock_path.read_text())
        data["pid"] = 999999999  # Almost certainly dead
        lock_path.write_text(json.dumps(data))

        with patch("rigger._lock._pid_alive", return_value=False):
            new_info = acquire_lock(tmp_path)
        assert new_info.pid == os.getpid()
        assert new_info.instance_id != info.instance_id


class TestForceOverride:
    def test_force_overrides_live_lock(self, tmp_path):
        old_info = acquire_lock(tmp_path)
        new_info = acquire_lock(tmp_path, force=True)
        assert new_info.instance_id != old_info.instance_id
        data = json.loads((tmp_path / HARNESS_DIR / LOCK_FILE).read_text())
        assert data["instance_id"] == new_info.instance_id


class TestContextManager:
    def test_acquires_and_releases(self, tmp_path):
        lock_path = tmp_path / HARNESS_DIR / LOCK_FILE
        with harness_lock(tmp_path) as info:
            assert lock_path.exists()
            assert info.pid == os.getpid()
        assert not lock_path.exists()

    def test_releases_on_exception(self, tmp_path):
        lock_path = tmp_path / HARNESS_DIR / LOCK_FILE
        with pytest.raises(ValueError, match="boom"):  # noqa: PT012, SIM117
            with harness_lock(tmp_path):
                assert lock_path.exists()
                raise ValueError("boom")
        assert not lock_path.exists()

    def test_nested_raises(self, tmp_path):
        with harness_lock(tmp_path), pytest.raises(HarnessAlreadyRunning):
            acquire_lock(tmp_path)


class TestCorruptLock:
    def test_corrupt_json_treated_as_absent(self, tmp_path):
        harness_dir = tmp_path / HARNESS_DIR
        harness_dir.mkdir(parents=True)
        (harness_dir / LOCK_FILE).write_text("not valid json")
        # Should acquire successfully (corrupt = absent)
        info = acquire_lock(tmp_path)
        assert info.pid == os.getpid()

    def test_missing_fields_treated_as_absent(self, tmp_path):
        harness_dir = tmp_path / HARNESS_DIR
        harness_dir.mkdir(parents=True)
        (harness_dir / LOCK_FILE).write_text(json.dumps({"pid": 1}))
        info = acquire_lock(tmp_path)
        assert info.pid == os.getpid()


class TestAtomicWrite:
    def test_no_temp_files_left(self, tmp_path):
        info = acquire_lock(tmp_path)
        harness_dir = tmp_path / HARNESS_DIR
        tmp_files = list(harness_dir.glob(".tmp_*"))
        assert tmp_files == []
        release_lock(tmp_path, info)
