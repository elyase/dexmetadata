"""
Data models for DEX pool metadata.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Token:
    address: str
    name: str
    symbol: str
    decimals: int

    def __repr__(self) -> str:
        return self.symbol or "Unknown"


@dataclass
class Pool:
    identifier: (
        str  # Unified identifier (address for regular pools, pool_id for Uniswap V4)
    )
    token0: Token
    token1: Token
    protocol: str = ""  # Protocol identifier (e.g., "Uniswap v4")
    is_valid: bool = True  # Field to indicate if the pool is valid

    @classmethod
    def from_dict(cls, data: dict) -> "Pool":
        # Check if invalid pool
        if not data.get("is_valid", True):
            return cls(
                identifier=data.get("identifier", "unknown"),
                token0=Token("", "", "", 0),
                token1=Token("", "", "", 0),
                protocol=data.get("protocol", ""),
                is_valid=False,
            )

        # Create tokens
        token0 = Token(
            address=data["token0_address"],
            name=data["token0_name"],
            symbol=data["token0_symbol"],
            decimals=data["token0_decimals"],
        )

        token1 = Token(
            address=data["token1_address"],
            name=data["token1_name"],
            symbol=data["token1_symbol"],
            decimals=data["token1_decimals"],
        )

        # Create pool
        return cls(
            identifier=data["identifier"],
            token0=token0,
            token1=token1,
            protocol=data.get("protocol", ""),
            is_valid=True,
        )

    def __repr__(self) -> str:
        """Return a programmer representation of the pool."""
        if not self.is_valid:
            return f"<Invalid Pool {self.identifier}>"

        protocol_str = f" {self.protocol}" if self.protocol else ""
        return f"{self.token0.symbol}/{self.token1.symbol}{protocol_str} ({self.identifier})"

    def __str__(self) -> str:
        """Return a human-readable representation of the pool."""
        if not self.is_valid:
            return f"Invalid Pool: {self.identifier}"

        protocol_str = f" {self.protocol}" if self.protocol else ""
        return (
            f"{self.token0.symbol}/{self.token1.symbol}{protocol_str} ({self.identifier})\n"
            f"├─ {self.token0.name}\n"
            f"│    ├ {self.token0.symbol}\n"
            f"│    ├ {self.token0.address}\n"
            f"│    └ {self.token0.decimals}\n"
            f"└─ {self.token1.name}\n"
            f"     ├ {self.token1.symbol}\n"
            f"     ├ {self.token1.address}\n"
            f"     └ {self.token1.decimals}"
        )
