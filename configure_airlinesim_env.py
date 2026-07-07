#!/usr/bin/env python3
"""
Find and save the AirlineSim airline name and game world as environment values.

Environment variables:
  AIRLINESIM_AIRLINE_NAME
  AIRLINESIM_GAME_WORLD

The variables are set for this script process. On Windows, the permanent option
also uses `setx`, which affects future terminals.
"""

from __future__ import annotations

import os
import platform
import re
import subprocess
from difflib import SequenceMatcher
from pathlib import Path


AIRLINE_ENV = "AIRLINESIM_AIRLINE_NAME"
WORLD_ENV = "AIRLINESIM_GAME_WORLD"
MIN_MATCH_SCORE = 0.50
SKIP_DIRS = {".git", ".agents", ".codex", "__pycache__"}
IGNORED_AIRLINE_NAMES = {"AS Route Map", "Load monitoring"}


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def is_airport_code(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Z0-9]{3}", value.strip()))


def iter_available_files(root: Path):
    for path in root.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.is_file():
            yield path


def parse_airlinesim_name(name: str):
    match = re.match(r"^(.+?) _ (.+?) _ AirlineSim(?:\.html)?$", name, flags=re.IGNORECASE)
    if not match:
        return None
    return clean_text(match.group(1)), clean_text(match.group(2))


def add_candidate(candidates: dict[str, set[str]], airline: str, source: str) -> None:
    if not airline:
        return
    if airline in IGNORED_AIRLINE_NAMES or is_airport_code(airline):
        return
    candidates.setdefault(airline, set()).add(source)


def read_small_text(path: Path) -> str:
    try:
        raw = path.read_bytes()
    except OSError:
        return ""
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def discover_airlines_and_worlds(root: Path):
    airlines: dict[str, set[str]] = {}
    worlds: dict[str, set[str]] = {}

    for path in iter_available_files(root):
        parsed = parse_airlinesim_name(path.name)
        if parsed:
            first, world = parsed
            add_candidate(airlines, first, str(path))
            worlds.setdefault(world, set()).add(str(path))

        if path.suffix.lower() not in {".html", ".htm", ".md", ".txt", ".py"}:
            continue

        text = read_small_text(path)
        for title in re.findall(r"<title>\s*(.*?)\s*</title>", text, flags=re.IGNORECASE | re.DOTALL):
            parts = [clean_text(part) for part in re.split(r"\s*\|\s*", title)]
            if len(parts) >= 3 and parts[-1].lower() == "airlinesim":
                add_candidate(airlines, parts[0], f"{path} <title>")
                worlds.setdefault(parts[1], set()).add(f"{path} <title>")

    return airlines, worlds


def match_score(query: str, candidate: str) -> float:
    query_norm = query.casefold().strip()
    candidate_norm = candidate.casefold().strip()
    if not query_norm or not candidate_norm:
        return 0.0
    ratio = SequenceMatcher(None, query_norm, candidate_norm).ratio()
    if query_norm in candidate_norm:
        ratio = max(ratio, len(query_norm) / len(candidate_norm))
    if candidate_norm in query_norm:
        ratio = max(ratio, len(candidate_norm) / len(query_norm))
    return ratio


def choose_airline(airlines: dict[str, set[str]]) -> str | None:
    requested = input("Airline name: ").strip()
    scored = sorted(
        ((match_score(requested, airline), airline) for airline in airlines),
        reverse=True,
    )
    if not scored or scored[0][0] <= MIN_MATCH_SCORE:
        print(f"Error: no airline match above {int(MIN_MATCH_SCORE * 100)}%.")
        return None

    score, airline = scored[0]
    print(f"Best match: {airline} ({score:.0%})")
    answer = input("Is this correct? [y/N]: ").strip().casefold()
    if answer not in {"y", "yes"}:
        print("Cancelled.")
        return None
    return airline


def choose_world(worlds: dict[str, set[str]]) -> str | None:
    names = sorted(worlds)
    if not names:
        print("Error: no AirlineSim game world found.")
        return None
    if len(names) == 1:
        print(f"Game world: {names[0]}")
        return names[0]

    print("Available game worlds:")
    for index, name in enumerate(names, start=1):
        print(f"  {index}. {name}")

    choice = input("Choose game world number: ").strip()
    if not choice.isdigit() or not 1 <= int(choice) <= len(names):
        print("Error: invalid game world choice.")
        return None
    return names[int(choice) - 1]


def save_permanently(name: str, value: str) -> bool:
    if platform.system().lower() == "windows":
        try:
            subprocess.run(["setx", name, value], check=True)
        except (OSError, subprocess.CalledProcessError) as exc:
            print(f"Error: failed to permanently save {name}: {exc}")
            return False
        return True

    profile = Path.home() / ".profile"
    line = f'export {name}="{value}"\n'
    try:
        existing = profile.read_text(encoding="utf-8") if profile.exists() else ""
        if f"export {name}=" not in existing:
            with profile.open("a", encoding="utf-8") as output:
                output.write(line)
        else:
            print(f"Skipped permanent save for {name}; it already exists in {profile}.")
    except OSError as exc:
        print(f"Error: failed to update {profile}: {exc}")
        return False
    return True


def print_current_terminal_commands(airline: str, world: str) -> None:
    airline_value = airline.replace("'", "''")
    world_value = world.replace("'", "''")
    print("To set these for the current PowerShell terminal, run:")
    print(f"$env:{AIRLINE_ENV} = '{airline_value}'")
    print(f"$env:{WORLD_ENV} = '{world_value}'")


def main() -> int:
    root = Path(__file__).resolve().parent
    airlines, worlds = discover_airlines_and_worlds(root)

    airline = choose_airline(airlines)
    if not airline:
        return 1

    world = choose_world(worlds)
    if not world:
        return 1

    os.environ[AIRLINE_ENV] = airline
    os.environ[WORLD_ENV] = world

    print(f"Set {AIRLINE_ENV}={airline}")
    print(f"Set {WORLD_ENV}={world}")
    print_current_terminal_commands(airline, world)

    answer = input("Save permanently for future terminals? [y/N]: ").strip().casefold()
    if answer in {"y", "yes"}:
        ok_airline = save_permanently(AIRLINE_ENV, airline)
        ok_world = save_permanently(WORLD_ENV, world)
        if ok_airline and ok_world:
            print("Saved permanently. Open a new terminal before running the other scripts.")
        else:
            return 1
    else:
        print("Permanent save skipped.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
