"""
Data models for DEX pool metadata.
"""

from dataclasses import dataclass


@dataclass
class Token:
    address: str
    name: str
    symbol: str
    decimals: int

    def __repr__(self) -> str:
        return self.symbol


@dataclass
class Pool:
    address: str
    token0: Token
    token1: Token

    @classmethod
    def from_dict(cls, data: dict) -> "Pool":
        return cls(
            address=data["pool_address"],
            token0=Token(
                address=data["token0_address"],
                name=data["token0_name"],
                symbol=data["token0_symbol"],
                decimals=data["token0_decimals"],
            ),
            token1=Token(
                address=data["token1_address"],
                name=data["token1_name"],
                symbol=data["token1_symbol"],
                decimals=data["token1_decimals"],
            ),
        )

    def __repr__(self) -> str:
        return f"{self.token0}/{self.token1}({self.address})"

    def __str__(self) -> str:
        return (
            f"{self.token0}/{self.token1}({self.address})\n"
            f"├─ {self.token0.name}\n"
            f"│    ├ {self.token0.symbol}\n"
            f"│    ├ {self.token0.address}\n"
            f"│    └ {self.token0.decimals}\n"
            f"└─ {self.token1.name}\n"
            f"     ├ {self.token1.symbol}\n"
            f"     ├ {self.token1.address}\n"
            f"     └ {self.token1.decimals}"
        )
