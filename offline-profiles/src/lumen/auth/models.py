from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class Account:
    username: str
    uuid: str
    kind: str                                   # "microsoft" | "offline"
    access_token: str = field(default="0", repr=False)   # never printed
