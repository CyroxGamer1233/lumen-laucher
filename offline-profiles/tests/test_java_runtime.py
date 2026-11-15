import subprocess
from types import SimpleNamespace

from lumen import java_runtime


def test_java_version_parser_handles_legacy_and_modern_formats(monkeypatch):
    results = iter([
        subprocess.CompletedProcess([], 0, "", 'java version "1.8.0_402"'),
        subprocess.CompletedProcess([], 0, "", 'openjdk version "21.0.2"'),
    ])
    monkeypatch.setattr(java_runtime.subprocess, "run", lambda *args, **kwargs: next(results))

    assert java_runtime.java_major_version("java8") == 8
    assert java_runtime.java_major_version("java21") == 21


def test_uses_matching_mojang_runtime_instead_of_wrong_system_java(tmp_path, monkeypatch):
    managed = tmp_path / "java-17"
    managed.touch()
    runtime = SimpleNamespace(
        get_version_runtime_information=lambda version, directory: {
            "name": "java-runtime-gamma",
            "javaMajorVersion": 17,
        },
        get_executable_path=lambda name, directory: str(managed),
        install_jvm_runtime=lambda name, directory: (_ for _ in ()).throw(
            AssertionError("an installed matching runtime must be reused")
        ),
    )
    monkeypatch.setattr(java_runtime, "minecraft_launcher_lib", SimpleNamespace(runtime=runtime))

    assert java_runtime.ensure_java("1.20.1", tmp_path, offline=True) == str(managed)


def test_offline_launch_refuses_incompatible_system_java(tmp_path, monkeypatch):
    runtime = SimpleNamespace(
        get_version_runtime_information=lambda version, directory: {
            "name": "java-runtime-gamma",
            "javaMajorVersion": 17,
        },
        get_executable_path=lambda name, directory: None,
        install_jvm_runtime=lambda name, directory: (_ for _ in ()).throw(
            AssertionError("offline launch must not download Java")
        ),
    )
    monkeypatch.setattr(java_runtime, "minecraft_launcher_lib", SimpleNamespace(runtime=runtime))
    monkeypatch.setattr(java_runtime, "find_java", lambda *args, **kwargs: None)

    try:
        java_runtime.ensure_java("1.20.1", tmp_path, offline=True)
        raise AssertionError("incompatible/missing Java must stop an offline launch")
    except RuntimeError as error:
        assert "Java 17" in str(error)
        assert "install this version's runtime" in str(error)
