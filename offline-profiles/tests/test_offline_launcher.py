import subprocess

import pytest

from lumen import offline_launcher
from lumen.offline_profiles import OfflineProfileDB


@pytest.mark.parametrize("offline", [True, False])
def test_launch_passes_offline_mode_through_command_building(
    tmp_path, monkeypatch, offline
):
    version = "1.21.1"
    version_directory = tmp_path / "versions" / version
    version_directory.mkdir(parents=True)
    (version_directory / f"{version}.json").write_text("{}")
    profiles = OfflineProfileDB(tmp_path / "profiles.json")
    profile = profiles.add_profile("Player")
    java_options = []
    process_options = []

    monkeypatch.setattr(
        offline_launcher,
        "ensure_java",
        lambda *args, **kwargs: java_options.append(kwargs["offline"]) or "java",
    )
    monkeypatch.setattr(
        offline_launcher.minecraft_launcher_lib.command,
        "get_minecraft_command",
        lambda *args: ["java", "Minecraft"],
    )

    class Process:
        stdout = None

    monkeypatch.setattr(
        offline_launcher.subprocess,
        "Popen",
        lambda command, **kwargs: process_options.append((command, kwargs)) or Process(),
    )

    class Thread:
        def __init__(self, **kwargs):
            pass

        def start(self):
            pass

    monkeypatch.setattr(offline_launcher.threading, "Thread", Thread)
    launcher = offline_launcher.OfflineLauncher(tmp_path, profiles)

    result = launcher.launch(version, profile=profile, offline=offline)

    assert isinstance(result, Process)
    assert java_options == [offline]
    assert process_options[0][0] == ["java", "Minecraft"]
    assert process_options[0][1]["stdin"] == subprocess.DEVNULL
