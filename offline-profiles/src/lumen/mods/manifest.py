"""Read fabric.mod.json and detect dependency/conflict problems before launch."""
from __future__ import annotations
import io, json, re, zipfile
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ModInfo:
    id: str
    version: str
    path: Path
    depends: dict = field(default_factory=dict)
    recommends: dict = field(default_factory=dict)
    breaks: dict = field(default_factory=dict)
    conflicts: dict = field(default_factory=dict)
    provides: list = field(default_factory=list)


@dataclass
class Issue:
    severity: str          # "error" | "warn"
    mod_id: str
    message: str


def read_fabric_mod(jar: Path) -> ModInfo | None:
    mods = _read_fabric_mod_tree(jar.read_bytes(), jar)
    return mods[0] if mods else None


def _read_fabric_mod_tree(payload: bytes, source: Path, depth: int = 0) -> list[ModInfo]:
    """Read a mod and its Fabric jar-in-jar modules."""
    if depth > 32:
        return []
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as z:
            j = json.loads(z.read("fabric.mod.json"))
            result = [ModInfo(
                j["id"], str(j.get("version", "0")), source,
                j.get("depends", {}) or {},
                j.get("recommends", {}) or {},
                j.get("breaks", {}) or {},
                j.get("conflicts", {}) or {},
                list(j.get("provides", []) or []),
            )]
            for nested in j.get("jars", []) or []:
                name = nested.get("file") if isinstance(nested, dict) else None
                if not name:
                    continue
                try:
                    child = z.read(name)
                except KeyError:
                    continue
                result.extend(_read_fabric_mod_tree(
                    child, Path(f"{source}!{name}"), depth + 1
                ))
            return result
    except (KeyError, json.JSONDecodeError, zipfile.BadZipFile, ValueError):
        return []

def _parts(v: str) -> list[int]:
    core = re.split(r"[-+]", v, maxsplit=1)[0]
    return [int(x) for x in re.findall(r"\d+", core)]


def _pad(p: list[int], n: int = 4) -> tuple[int, ...]:
    return tuple((p + [0] * n)[:n])


def _clause(version: str, clause: str) -> bool:
    clause = clause.strip()
    if clause in ("", "*"):
        return True
    m = re.match(r"^(>=|<=|>|<|=|~|\^)?\s*(.+)$", clause)
    op, ref = m.group(1) or "=", m.group(2)
    if re.search(r"[xX*]$", ref):                               # 1.21.x
        prefix = _parts(ref.rstrip("xX*."))
        return _parts(version)[:len(prefix)] == prefix
    v, r = _pad(_parts(version)), _pad(_parts(ref))
    if op == "=":  return v == r
    if op == ">=": return v >= r
    if op == "<=": return v <= r
    if op == ">":  return v > r
    if op == "<":  return v < r
    if op == "~":  return v >= r and v[:2] == r[:2]
    if op == "^":  return v >= r and (v[0] == r[0] if r[0] else v[:2] == r[:2])
    return False


def satisfies(version: str, rng) -> bool:
    """Fabric-style ranges: "*", ">=1.2 <2", or a list meaning OR. Pre-release tags ignored."""
    if isinstance(rng, list):
        return any(satisfies(version, r) for r in rng)
    return all(_clause(version, c) for c in str(rng).split())


def detect_conflicts(mods: list[ModInfo], mc_version: str, loader_version: str | None = None) -> list[Issue]:
    issues: list[Issue] = []
    provided: dict[str, str] = {"minecraft": mc_version}
    if loader_version:
        provided["fabricloader"] = loader_version
    seen: dict[str, ModInfo] = {}
    for m in mods:
        if m.id in seen:
            issues.append(Issue("error", m.id, f"Duplicate mod id in {seen[m.id].path.name} and {m.path.name}"))
        seen[m.id] = m
        provided[m.id] = m.version
        for alias in m.provides:
            provided.setdefault(alias, m.version)

    for m in mods:
        for dep, rng in m.depends.items():
            if dep == "java" or (dep == "fabricloader" and not loader_version):
                continue
            if dep not in provided:
                issues.append(Issue("error", m.id, f"requires '{dep}' {rng} but it is not installed"))
            elif not satisfies(provided[dep], rng):
                issues.append(Issue("error", m.id, f"requires {dep} {rng}, found {provided[dep]}"))
        for dep, rng in m.recommends.items():
            if dep not in provided:
                issues.append(Issue("warn", m.id, f"recommends '{dep}' {rng}"))
        for other, rng in m.breaks.items():
            if other in provided and satisfies(provided[other], rng):
                issues.append(Issue("error", m.id, f"is incompatible with {other} {provided[other]}"))
        for other, rng in m.conflicts.items():
            if other in provided and satisfies(provided[other], rng):
                issues.append(Issue("warn", m.id, f"may conflict with {other} {provided[other]}"))
    return issues


def scan_folder(mods_dir: Path) -> list[ModInfo]:
    found = []
    for jar in sorted(mods_dir.glob("*.jar")):
        found.extend(_read_fabric_mod_tree(jar.read_bytes(), jar))
    return found
