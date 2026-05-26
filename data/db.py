import os
import math
import secrets
import time
import functools
from datetime import datetime, date
from typing import Optional

import streamlit as st
from dotenv import load_dotenv
from postgrest._sync.client import SyncPostgrestClient as PostgrestClient

from models.position import Position

_DB_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_DB_DIR, '..'))
load_dotenv(os.path.join(_PROJECT_ROOT, '.env'))

SUPABASE_URL = os.getenv("SUPABASE_URL") or st.secrets.get("SUPABASE_URL")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY") or st.secrets.get("SUPABASE_SECRET_KEY")

if not SUPABASE_URL or not SUPABASE_SECRET_KEY:
    raise RuntimeError(
        "SUPABASE_URL and SUPABASE_SECRET_KEY must be set. "
        "Add them to .env file, environment variables, or Streamlit secrets."
    )

_api_url = SUPABASE_URL.rstrip('/') + '/rest/v1'
supabase = PostgrestClient(
    base_url=_api_url,
    headers={
        "apikey": SUPABASE_SECRET_KEY,
        "Authorization": f"Bearer {SUPABASE_SECRET_KEY}"
    }
)

def _now():
    return datetime.now().isoformat()

def supabase_db_retry(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        for attempt in range(3):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                print(f"Supabase error (attempt {attempt + 1}): {e}")
                time.sleep(1 * (attempt + 1))
        raise
    return wrapper

@supabase_db_retry
def initialize_database():
    try:
        supabase.table("positions").select("id").limit(1).execute()
    except Exception as e:
        print(f"Supabase connection check failed: {e}")
        raise

# ─── Position CRUD ───────────────────────────────────────────────────────────

def add_position(
    network: str, dex: str, pair: str,
    lower_price: float, upper_price: float,
    token0_amount: float, token1_amount: float,
    fees_token0: float = 0, fees_token1: float = 0,
    wallet_address: Optional[str] = None,
    initial_price: float = 0.0,
    goal: str = 'maximize_fees',
    target_token: str = '',
    target_amount: float = 0.0,
    liquidity: float = 0.0,
    is_public: bool = False,
    owner_id: str = "admin",
    status: str = "active",
    created_at: str = None,
):
    data = {
        "network": network,
        "dex": dex,
        "pair": pair,
        "lower_price": lower_price,
        "upper_price": upper_price,
        "token0_amount": token0_amount,
        "token1_amount": token1_amount,
        "fees_token0": fees_token0,
        "fees_token1": fees_token1,
        "wallet_address": wallet_address,
        "initial_price": initial_price,
        "goal": goal,
        "target_token": target_token,
        "target_amount": target_amount,
        "fees_token0_total": fees_token0,
        "fees_token1_total": fees_token1,
        "liquidity": liquidity,
        "is_public": int(is_public),
        "owner_id": owner_id,
        "status": status,
        "created_at": created_at,
        "token0_amount_initial": token0_amount,
        "token1_amount_initial": token1_amount,
        "token0_current": token0_amount,
        "token1_current": token1_amount,
    }
    supabase.table("positions").insert(data).execute()


def get_all_positions():
    result = supabase.table("positions").select("*").order("created_at", desc=True).execute()
    return result.data


def get_all_positions_objs():
    return [Position.from_tuple(row) for row in get_all_positions()]


def get_position_by_id(pos_id: int):
    result = supabase.table("positions").select("*").eq("id", pos_id).execute()
    if result.data:
        return result.data[0]
    return None


@supabase_db_retry
def update_position_price(pos_id: int, price: float):
    supabase.table("positions").update({
        "last_price": price,
        "last_updated": _now()
    }).eq("id", pos_id).execute()


def delete_position(pos_id: int):
    supabase.table("fees_log").delete().eq("position_id", pos_id).execute()
    supabase.table("positions").delete().eq("id", pos_id).execute()


def update_position_goal(pos_id: int, goal: str, target_token: str, target_amount: float):
    supabase.table("positions").update({
        "goal": goal,
        "target_token": target_token,
        "target_amount": target_amount,
        "last_updated": _now()
    }).eq("id", pos_id).execute()


@supabase_db_retry
def update_position_ranges(pos_id: int, lower: float, upper: float, initial_price: float, token0: float, token1: float, liquidity: float):
    supabase.table("positions").update({
        "lower_price": lower,
        "upper_price": upper,
        "initial_price": initial_price,
        "token0_amount": token0,
        "token1_amount": token1,
        "liquidity": liquidity,
        "last_updated": _now()
    }).eq("id", pos_id).execute()


@supabase_db_retry
def update_position_status(pos_id: int, status: str):
    supabase.table("positions").update({
        "status": status,
        "last_updated": _now()
    }).eq("id", pos_id).execute()


@supabase_db_retry
def update_position_date(pos_id: int, created_at: str):
    supabase.table("positions").update({
        "created_at": created_at,
        "last_updated": _now()
    }).eq("id", pos_id).execute()


@supabase_db_retry
def update_position_current_balances(pos_id: int, token0_current: float, token1_current: float):
    supabase.table("positions").update({
        "token0_current": token0_current,
        "token1_current": token1_current,
        "last_updated": _now()
    }).eq("id", pos_id).execute()


@supabase_db_retry
def update_v2_pool_status(pool_id: int, status: str):
    supabase.table("v2_pools").update({"status": status}).eq("id", pool_id).execute()


@supabase_db_retry
def update_v2_pool_balances(pool_id: int, token0_current: float, token1_current: float):
    supabase.table("v2_pools").update({
        "token0_current": token0_current,
        "token1_current": token1_current
    }).eq("id", pool_id).execute()


@supabase_db_retry
def update_custom_position_status(pos_id: int, status: str):
    supabase.table("custom_positions").update({"status": status}).eq("id", pos_id).execute()


# ─── Fee Logging ─────────────────────────────────────────────────────────────

@supabase_db_retry
def log_fees(pos_id: int, token0_amount: float, token1_amount: float, reinvested: bool = False,
             new_liquidity: float = 0.0, logged_at: str = None):
    log_entry = {
        "position_id": pos_id,
        "token0_amount": token0_amount,
        "token1_amount": token1_amount,
        "reinvested": 1 if reinvested else 0,
        "delta_liquidity": new_liquidity,
    }
    if logged_at:
        log_entry["logged_at"] = logged_at

    supabase.table("fees_log").insert(log_entry).execute()

    cur = supabase.table("positions").select("liquidity, fees_token0_total, fees_token1_total, fees_token0, fees_token1").eq("id", pos_id).execute()
    cur_data = cur.data[0] if cur.data else {}

    if reinvested:
        old_liquidity = float(cur_data.get("liquidity", 0) or 0)
        old_total0 = float(cur_data.get("fees_token0_total", 0) or 0)
        old_total1 = float(cur_data.get("fees_token1_total", 0) or 0)
        supabase.table("positions").update({
            "liquidity": old_liquidity + new_liquidity,
            "fees_token0": 0,
            "fees_token1": 0,
            "fees_token0_total": old_total0 + token0_amount,
            "fees_token1_total": old_total1 + token1_amount,
            "token0_current": None,
            "token1_current": None,
            "last_updated": _now()
        }).eq("id", pos_id).execute()
    else:
        old_fees0 = float(cur_data.get("fees_token0", 0) or 0)
        old_fees1 = float(cur_data.get("fees_token1", 0) or 0)
        old_total0 = float(cur_data.get("fees_token0_total", 0) or 0)
        old_total1 = float(cur_data.get("fees_token1_total", 0) or 0)
        supabase.table("positions").update({
            "fees_token0": old_fees0 + token0_amount,
            "fees_token1": old_fees1 + token1_amount,
            "fees_token0_total": old_total0 + token0_amount,
            "fees_token1_total": old_total1 + token1_amount,
            "last_updated": _now()
        }).eq("id", pos_id).execute()


@supabase_db_retry
def delete_fee_log(log_id: int):
    result = supabase.table("fees_log").select("position_id, token0_amount, token1_amount, reinvested, delta_liquidity").eq("id", log_id).execute()
    if not result.data:
        return

    log = result.data[0]
    pos_id = log["position_id"]
    reinvested_val = log["reinvested"]
    delta_l = log.get("delta_liquidity", 0) or 0

    if reinvested_val and delta_l:
        cur_del = supabase.table("positions").select("liquidity").eq("id", pos_id).execute()
        old_l = float(cur_del.data[0].get("liquidity", 0) or 0) if cur_del.data else 0
        supabase.table("positions").update({
            "liquidity": max(0, old_l - float(delta_l)),
            "fees_token0": 0,
            "fees_token1": 0,
            "token0_current": None,
            "token1_current": None,
            "last_updated": _now()
        }).eq("id", pos_id).execute()

    supabase.table("fees_log").delete().eq("id", log_id).execute()

    fees_data = supabase.table("fees_log").select("*").eq("position_id", pos_id).execute()
    new_curr0 = 0.0
    new_curr1 = 0.0
    new_total0 = 0.0
    new_total1 = 0.0
    for row in fees_data.data:
        t0 = float(row.get("token0_amount", 0) or 0)
        t1 = float(row.get("token1_amount", 0) or 0)
        is_reinv = row.get("reinvested", 0)
        new_total0 += t0
        new_total1 += t1
        if not is_reinv:
            new_curr0 += t0
            new_curr1 += t1

    supabase.table("positions").update({
        "fees_token0": new_curr0,
        "fees_token1": new_curr1,
        "fees_token0_total": new_total0,
        "fees_token1_total": new_total1,
        "last_updated": _now()
    }).eq("id", pos_id).execute()


@supabase_db_retry
def clear_all_fees(pos_id: int):
    supabase.table("fees_log").delete().eq("position_id", pos_id).execute()
    supabase.table("positions").update({
        "fees_token0": 0.0,
        "fees_token1": 0.0,
        "fees_token0_total": 0.0,
        "fees_token1_total": 0.0,
        "last_updated": _now()
    }).eq("id", pos_id).execute()


def get_fees_log(pos_id: int) -> list:
    result = supabase.table("fees_log").select("*").eq("position_id", pos_id).order("logged_at", desc=True).execute()
    return result.data


# ──��� Custom Positions CRUD ───────────────────────────────────────────────────

def add_custom_position(
    type: str, protocol: str, network: str,
    asset_deposited: str, amount_deposited: float,
    asset_borrowed: str = None, amount_borrowed: float = 0.0,
    liquidation_threshold: float = None, apy: float = None,
    notes: str = None, is_public: bool = False, created_at: str = None
):
    data = {
        "type": type,
        "protocol": protocol,
        "network": network,
        "asset_deposited": asset_deposited,
        "amount_deposited": amount_deposited,
        "asset_borrowed": asset_borrowed,
        "amount_borrowed": amount_borrowed if amount_borrowed else 0.0,
        "liquidation_threshold": liquidation_threshold,
        "apy": apy,
        "status": "active",
        "created_at": created_at,
        "notes": notes,
        "is_public": int(is_public),
        "initial_body_usd": amount_deposited,
        "current_body_usd": amount_deposited,
    }
    supabase.table("custom_positions").insert(data).execute()


def get_custom_positions(status_filter: str = None) -> list:
    query = supabase.table("custom_positions").select("*")
    if status_filter:
        query = query.eq("status", status_filter)
    result = query.order("created_at", desc=True).execute()
    return result.data


def update_custom_position(pos_id: int, **kwargs):
    if not kwargs:
        return
    supabase.table("custom_positions").update(kwargs).eq("id", pos_id).execute()


def soft_delete_custom_position(pos_id: int):
    update_custom_position(pos_id, status='closed', closed_at=datetime.now().strftime('%Y-%m-%d'))


def hard_delete_custom_position(pos_id: int):
    supabase.table("custom_positions").delete().eq("id", pos_id).execute()


def _recalc_actual_apy(initial_body: float, current_body: float, total_fees: float, created_at: str) -> float | None:
    if initial_body <= 0 or not created_at:
        return None
    try:
        created_date = datetime.strptime(created_at[:10], '%Y-%m-%d').date()
        days_active = (date.today() - created_date).days
    except (ValueError, TypeError):
        days_active = 0
    if days_active < 1:
        return None
    total_gain = (current_body - initial_body) + total_fees
    calc_apy = (total_gain / initial_body) * (365.0 / days_active) * 100.0
    return max(-100.0, min(500.0, calc_apy))


@supabase_db_retry
def update_custom_body(pos_id: int, current_body_usd: float):
    result = supabase.table("custom_positions").select("initial_body_usd, total_fees_usd, created_at").eq("id", pos_id).execute()
    if not result.data:
        return

    row = result.data[0]
    initial_body = float(row.get("initial_body_usd", 0) or 0.0)
    total_fees = float(row.get("total_fees_usd", 0) or 0.0)
    created_at_val = row.get("created_at", "")

    actual_apy = _recalc_actual_apy(initial_body, current_body_usd, total_fees, created_at_val)

    supabase.table("custom_positions").update({
        "current_body_usd": current_body_usd,
        "last_updated": _now(),
        "actual_apy": actual_apy
    }).eq("id", pos_id).execute()


@supabase_db_retry
def update_custom_fees(pos_id: int, total_fees_usd: float):
    result = supabase.table("custom_positions").select("initial_body_usd, current_body_usd, created_at").eq("id", pos_id).execute()
    if not result.data:
        return

    row = result.data[0]
    initial_body = float(row.get("initial_body_usd", 0) or 0.0)
    current_body = float(row.get("current_body_usd", 0) or 0.0)
    created_at_val = row.get("created_at", "")

    actual_apy = _recalc_actual_apy(initial_body, current_body, total_fees_usd, created_at_val)

    supabase.table("custom_positions").update({
        "total_fees_usd": total_fees_usd,
        "last_updated": _now(),
        "actual_apy": actual_apy
    }).eq("id", pos_id).execute()


# ─── V2 Pools CRUD ───────────────────────────────────────────────────────────

@supabase_db_retry
def add_v2_pool(
    network: str, dex: str, pair: str,
    token0_symbol: str, token1_symbol: str,
    token0_initial: float, token1_initial: float,
    initial_price: float, created_at: str,
    apy: float = None, goal: str = 'balanced',
    target_token: str = None, target_amount: float = None, is_public: bool = False
):
    data = {
        "network": network,
        "dex": dex,
        "pair": pair,
        "token0_symbol": token0_symbol,
        "token1_symbol": token1_symbol,
        "token0_initial": token0_initial,
        "token1_initial": token1_initial,
        "initial_price": initial_price,
        "created_at": created_at,
        "apy": apy,
        "goal": goal,
        "target_token": target_token,
        "target_amount": target_amount,
        "status": "active",
        "is_public": int(is_public),
        "token0_current": token0_initial,
        "token1_current": token1_initial,
    }
    supabase.table("v2_pools").insert(data).execute()


def get_v2_pools(status_filter: str = None) -> list:
    query = supabase.table("v2_pools").select("*")
    if status_filter:
        query = query.eq("status", status_filter)
    result = query.order("created_at", desc=True).execute()
    return result.data


@supabase_db_retry
def update_v2_pool(pool_id: int, **kwargs):
    if not kwargs:
        return
    supabase.table("v2_pools").update(kwargs).eq("id", pool_id).execute()


def soft_delete_v2_pool(pool_id: int):
    update_v2_pool(pool_id, status='closed', closed_at=datetime.now().strftime('%Y-%m-%d'))


def hard_delete_v2_pool(pool_id: int):
    supabase.table("v2_fees_log").delete().eq("v2_pool_id", pool_id).execute()
    supabase.table("v2_pools").delete().eq("id", pool_id).execute()


@supabase_db_retry
def log_v2_fees(pool_id: int, fee_token0: float, fee_token1: float, timestamp: str):
    supabase.table("v2_fees_log").insert({
        "v2_pool_id": pool_id,
        "timestamp": timestamp,
        "fee_token0": fee_token0,
        "fee_token1": fee_token1
    }).execute()

    cur_v2 = supabase.table("v2_pools").select("fees_token0_total, fees_token1_total").eq("id", pool_id).execute()
    v2_data = cur_v2.data[0] if cur_v2.data else {}
    old_v2_total0 = float(v2_data.get("fees_token0_total", 0) or 0)
    old_v2_total1 = float(v2_data.get("fees_token1_total", 0) or 0)

    supabase.table("v2_pools").update({
        "fees_token0_total": old_v2_total0 + fee_token0,
        "fees_token1_total": old_v2_total1 + fee_token1
    }).eq("id", pool_id).execute()


def get_v2_fees_log(pool_id: int) -> list:
    result = supabase.table("v2_fees_log").select("*").eq("v2_pool_id", pool_id).order("timestamp", desc=True).execute()
    return result.data


@supabase_db_retry
def clear_all_v2_fees(pool_id: int):
    supabase.table("v2_fees_log").delete().eq("v2_pool_id", pool_id).execute()
    supabase.table("v2_pools").update({
        "fees_token0_total": 0,
        "fees_token1_total": 0
    }).eq("id", pool_id).execute()


# ─── Public Visibility Functions ────────────────────────────────────────────

@supabase_db_retry
def get_all_public_positions():
    positions = supabase.table("positions").select("*").eq("is_public", 1).order("created_at", desc=True).execute()
    v2_pools = supabase.table("v2_pools").select("*").eq("is_public", 1).order("created_at", desc=True).execute()
    custom = supabase.table("custom_positions").select("*").eq("is_public", 1).eq("status", "active").order("created_at", desc=True).execute()
    return positions.data + v2_pools.data + custom.data


@supabase_db_retry
def get_public_v2_pools():
    result = supabase.table("v2_pools").select("*").eq("is_public", 1).order("created_at", desc=True).execute()
    return result.data


@supabase_db_retry
def get_public_custom_positions():
    result = supabase.table("custom_positions").select("*").eq("is_public", 1).eq("status", "active").order("created_at", desc=True).execute()
    return result.data


@supabase_db_retry
def update_position_visibility(pos_id: int, is_public: int):
    supabase.table("positions").update({"is_public": is_public}).eq("id", pos_id).execute()


@supabase_db_retry
def update_v2_pool_visibility(pool_id: int, is_public: int):
    supabase.table("v2_pools").update({"is_public": is_public}).eq("id", pool_id).execute()


@supabase_db_retry
def update_custom_visibility(cpos_id: int, is_public: int):
    supabase.table("custom_positions").update({"is_public": is_public}).eq("id", cpos_id).execute()


# ─── Auth Token Functions ────────────────────────────────────────────────────

def generate_auth_token() -> str:
    return secrets.token_urlsafe(32)


@supabase_db_retry
def save_auth_token(token: str, days_valid: int = 30):
    expires = int(time.time()) + days_valid * 86400
    supabase.table("auth_tokens").upsert({
        "token": token,
        "expires_at": expires
    }).execute()


def is_token_valid(token: str) -> bool:
    result = supabase.table("auth_tokens").select("expires_at").eq("token", token).execute()
    if result.data and result.data[0]["expires_at"] > int(time.time()):
        return True
    return False


@supabase_db_retry
def delete_auth_token(token: str):
    supabase.table("auth_tokens").delete().eq("token", token).execute()


@supabase_db_retry
def clear_all_auth_tokens():
    supabase.table("auth_tokens").delete().neq("token", "").execute()