from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Position:
    id: Optional[int]
    network: str
    dex: str
    pair: str
    lower_price: float
    upper_price: float
    token0_amount: float
    token1_amount: float
    fees_token0: float = 0.0
    fees_token1: float = 0.0
    wallet_address: Optional[str] = None
    last_price: float = 0.0
    initial_price: float = 0.0
    goal: str = 'maximize_fees'
    target_token: str = ''
    target_amount: float = 0.0
    fees_token0_total: float = 0.0
    fees_token1_total: float = 0.0
    liquidity: float = 0.0
    is_public: bool = False
    owner_id: str = "admin"
    status: str = "active"
    token0_current: float = 0.0
    token1_current: float = 0.0

    @property
    def base_symbol(self) -> str:
        return self.pair.split('/')[0] if '/' in self.pair else self.pair

    @property
    def quote_symbol(self) -> str:
        return self.pair.split('/')[1] if '/' in self.pair else 'USDC'

    @property
    def current_value(self) -> float:
        if self.last_price:
            return self.token0_amount * self.last_price + self.token1_amount
        return 0.0

    def to_dict(self):
        return {
            "id": self.id,
            "network": self.network,
            "dex": self.dex,
            "pair": self.pair,
            "lower_price": self.lower_price,
            "upper_price": self.upper_price,
            "token0_amount": self.token0_amount,
            "token1_amount": self.token1_amount,
            "fees_token0": self.fees_token0,
            "fees_token1": self.fees_token1,
            "wallet_address": self.wallet_address,
            "last_price": self.last_price,
            "initial_price": self.initial_price,
            "goal": self.goal,
            "target_token": self.target_token,
            "target_amount": self.target_amount,
            "fees_token0_total": self.fees_token0_total,
            "fees_token1_total": self.fees_token1_total,
            "liquidity": self.liquidity,
            "is_public": self.is_public,
            "owner_id": self.owner_id,
            "status": self.status,
            "token0_current": self.token0_current,
            "token1_current": self.token1_current,
        }

    @classmethod
    def from_tuple(cls, row):
        """Named column access — safe against ALTER TABLE column order changes."""
        def _f(val, default=0.0):
            try:
                return float(val) if val is not None else default
            except (ValueError, TypeError):
                return default

        def _s(val, default=''):
            return str(val) if val is not None else default

        return cls(
            id=row['id'],
            network=_s(row['network']),
            dex=_s(row['dex']),
            pair=_s(row['pair']),
            lower_price=_f(row['lower_price']),
            upper_price=_f(row['upper_price']),
            token0_amount=_f(row['token0_amount']),
            token1_amount=_f(row['token1_amount']),
            fees_token0=_f(row['fees_token0']),
            fees_token1=_f(row['fees_token1']),
            wallet_address=_s(row['wallet_address'], None),
            last_price=_f(row['last_price'] if 'last_price' in row.keys() else 0),
            initial_price=_f(row['initial_price'] if 'initial_price' in row.keys() else 0),
            goal=_s(row['goal'] if 'goal' in row.keys() else 'maximize_fees', 'maximize_fees'),
            target_token=_s(row['target_token'] if 'target_token' in row.keys() else ''),
            target_amount=_f(row['target_amount'] if 'target_amount' in row.keys() else 0),
            fees_token0_total=_f(row['fees_token0_total'] if 'fees_token0_total' in row.keys() else row['fees_token0']),
            fees_token1_total=_f(row['fees_token1_total'] if 'fees_token1_total' in row.keys() else row['fees_token1']),
            liquidity=_f(row['liquidity'] if 'liquidity' in row.keys() else 0),
            is_public=bool(row['is_public']) if 'is_public' in row.keys() else False,
            owner_id=_s(row['owner_id'] if 'owner_id' in row.keys() else 'admin', 'admin'),
            status=_s(row['status'] if 'status' in row.keys() else 'active', 'active'),
            token0_current=_f(row['token0_current'] if 'token0_current' in row.keys() else row['token0_amount']),
            token1_current=_f(row['token1_current'] if 'token1_current' in row.keys() else row['token1_amount']),
        )
