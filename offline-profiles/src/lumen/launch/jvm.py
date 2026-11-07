"""Safe JVM tuning. Only standard HotSpot flags; nothing that alters game behaviour."""
from __future__ import annotations


def total_ram_mb() -> int:
    try:
        import psutil
        return int(psutil.virtual_memory().total / 2**20)
    except Exception:
        return 8192


def pick_heap_mb(total_mb: int, profile: str, override: int | None = None) -> int:
    """Leave headroom for the OS, browser and the JVM's off-heap use."""
    if override:
        return max(1024, min(override, int(total_mb * 0.75)))
    share = {"low_end": 0.25, "balanced": 0.33, "high_end": 0.40}.get(profile, 0.33)
    cap = {"low_end": 3072, "balanced": 6144, "high_end": 10240}.get(profile, 6144)
    return max(1536, min(int(total_mb * share), cap))


def build_jvm_args(profile: str = "balanced", ram_mb: int | None = None,
                   total_mb: int | None = None, java_major: int = 21) -> list[str]:
    total = total_mb or total_ram_mb()
    heap = pick_heap_mb(total, profile, ram_mb)
    args = [f"-Xms{heap}M", f"-Xmx{heap}M"]        # fixed heap avoids resize stutter
    args += ["-XX:+UseG1GC", "-XX:+ParallelRefProcEnabled", "-XX:MaxGCPauseMillis=50"]
    if profile != "low_end":
        args += ["-XX:+UnlockExperimentalVMOptions", "-XX:G1NewSizePercent=20", "-XX:G1ReservePercent=20"]
    if profile == "high_end":
        args += ["-XX:+AlwaysPreTouch"]            # slower start, steadier frametimes
    args += ["-Dfile.encoding=UTF-8"]
    return args
