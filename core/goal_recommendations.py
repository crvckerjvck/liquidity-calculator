"""
core/goal_recommendations.py
Goal-based recommendation engine for the LP Tracker.
Each goal type produces targeted, actionable suggestions.
"""
from typing import Optional


GOAL_LABELS = {
    'preserve_asset':   'Сохранить актив',
    'accumulate_stable': 'Накопить стейблы',
    'maximize_fees':    'Максимум комиссий',
    'hedge':            'Хедж',
    'balanced':         'Балансировка',
}


def get_goal_recommendation(
    pos: dict,
    current0: float,
    current1: float,
    current_price: float,
) -> dict:
    """
    Возвращает рекомендацию на основе цели позиции.

    Args:
        pos: dict-like запись позиции из БД (или Position.to_dict())
        current0: текущее кол-во token0 в пуле (из V3 math)
        current1: текущее кол-во token1 в пуле (из V3 math)
        current_price: текущая цена token0 в USD

    Returns:
        {
          action: str,
          message: str,
          severity: 'info' | 'warning' | 'critical',
          suggested_range: (float, float) | None,
        }
    """
    goal          = pos.get('goal', 'maximize_fees')
    target_token  = pos.get('target_token', '') or ''
    target_amount = float(pos.get('target_amount') or 0)
    lower         = float(pos.get('lower_price') or 0)
    upper         = float(pos.get('upper_price') or 0)
    fees0         = float(pos.get('fees_token0') or 0)
    fees1         = float(pos.get('fees_token1') or 0)
    pair          = pos.get('pair', '')

    base_sym  = pair.split('/')[0] if '/' in pair else pair
    quote_sym = pair.split('/')[1] if '/' in pair else 'USDC'

    in_range = lower <= current_price <= upper if upper > lower else False
    near_upper = upper > 0 and (upper - current_price) / upper < 0.05
    near_lower = lower > 0 and (current_price - lower) / lower < 0.05

    # ─── Determine current position of base token ───────────────────────────
    # token0 = base (e.g. SOL, ETH), token1 = quote (e.g. USDC)
    # "target_token" could be either base or quote symbol
    if target_token.upper() == base_sym.upper():
        current_target = current0
        fees_target = fees0
        fees_other = fees1
        other_sym = quote_sym
    else:
        current_target = current1
        fees_target = fees1
        fees_other = fees0
        other_sym = base_sym

    # ─── GOAL: preserve_asset ───────────────────────────────────────────────
    if goal == 'preserve_asset' and target_amount > 0:
        deficit = target_amount - current_target
        deficit_pct = deficit / target_amount * 100 if target_amount > 0 else 0

        # Range boundaries warning (takes priority)
        if near_upper and in_range:
            new_lower = current_price * 0.9
            new_upper = current_price * 1.5
            return {
                'action': 'SHIFT_RANGE_UP',
                'message': (
                    f'⚠️ Цена близка к верхней границе (5%). '
                    f'{base_sym} будет конвертироваться в {quote_sym}. '
                    f'Рекомендуется сдвинуть диапазон вверх: [{new_lower:,.2f} – {new_upper:,.2f}].'
                ),
                'severity': 'warning',
                'suggested_range': (new_lower, new_upper),
            }

        if near_lower and in_range:
            new_lower = current_price * 0.6
            new_upper = current_price * 1.1
            return {
                'action': 'EXPAND_RANGE_DOWN',
                'message': (
                    f'ℹ️ Цена близка к нижней границе. '
                    f'Позиция будет конвертирована в {base_sym} (для цели это безопасно), '
                    f'но комиссии прекратятся. Можно расширить диапазон вниз: [{new_lower:,.2f} – {new_upper:,.2f}].'
                ),
                'severity': 'info',
                'suggested_range': (new_lower, new_upper),
            }

        # Target deviation
        if deficit > 0 and deficit_pct > 2:
            new_lower = current_price * 0.9
            new_upper = current_price * 1.5
            msg = (
                f'❗ Не хватает {deficit:.4g} {target_token} до цели '
                f'({current_target:.4g} из {target_amount:.4g}, -{deficit_pct:.1f}%). '
                f'Цена выросла → {base_sym} конвертируется. '
                f'Рекомендуется сдвинуть диапазон вверх [{new_lower:,.2f} – {new_upper:,.2f}] '
                f'или купить {target_token} на комиссии в {quote_sym}.'
            )
            return {'action': 'SHIFT_RANGE_UP', 'message': msg, 'severity': 'warning',
                    'suggested_range': (new_lower, new_upper)}

        if deficit < 0 and abs(deficit_pct) > 2:
            surplus = abs(deficit)
            return {
                'action': 'TAKE_SURPLUS',
                'message': (
                    f'✅ Избыток: у вас на {surplus:.4g} {target_token} больше цели '
                    f'({current_target:.4g}). Можно вывести излишек в {quote_sym} '
                    f'или реинвестировать для усиления дохода.'
                ),
                'severity': 'info',
                'suggested_range': None,
            }

        # Fee suggestions
        if fees0 > 0 or fees1 > 0:
            fee_val_t = fees_target
            fee_val_o = fees_other
            if fee_val_t * current_price > 5 or fee_val_o > 5:
                return {
                    'action': 'ADD_FEES',
                    'message': (
                        f'💰 Накоплены комиссии: {fees0:.4g} {base_sym} + {fees1:.4g} {quote_sym}. '
                        f'Реинвестируйте {target_token} для приближения к цели {target_amount:.4g}.'
                    ),
                    'severity': 'info',
                    'suggested_range': None,
                }

        return {
            'action': 'HOLD',
            'message': f'✅ Позиция в норме. {current_target:.4g} {target_token} ({deficit_pct:+.1f}% к цели {target_amount:.4g}).',
            'severity': 'info',
            'suggested_range': None,
        }

    # ─── GOAL: accumulate_stable ─────────────────────────────────────────────
    if goal == 'accumulate_stable':
        # Price growing: pool auto-converts to stable — good
        if near_upper and in_range:
            return {
                'action': 'HOLD',
                'message': f'📈 Цена растёт → позиция конвертирует {base_sym} в {quote_sym}. Всё идёт по плану.',
                'severity': 'info',
                'suggested_range': None,
            }

        # Price falling: pool accumulates base, bad for this goal
        if near_lower and in_range:
            new_lower = current_price * 0.95
            new_upper = current_price * 2.0
            return {
                'action': 'SHIFT_RANGE_UP',
                'message': (
                    f'📉 Цена падает → позиция накапливает {base_sym}, а не {quote_sym}. '
                    f'Рекомендуется сдвинуть диапазон выше: [{new_lower:,.2f} – {new_upper:,.2f}].'
                ),
                'severity': 'warning',
                'suggested_range': (new_lower, new_upper),
            }

        if fees1 > 10:
            return {
                'action': 'WITHDRAW_FEES',
                'message': f'💰 Есть {fees1:.2f} {quote_sym} комиссий. Вывод соответствует вашей цели накопления стейблов.',
                'severity': 'info',
                'suggested_range': None,
            }

        return {
            'action': 'HOLD',
            'message': f'✅ Накоплено {current1:.2f} {quote_sym} в пуле + {fees1:.2f} {quote_sym} комиссий.',
            'severity': 'info',
            'suggested_range': None,
        }

    # ─── GOAL: maximize_fees ─────────────────────────────────────────────────
    if goal == 'maximize_fees':
        if not in_range:
            return {
                'action': 'SHIFT_RANGE',
                'message': f'🚫 Цена вне диапазона — комиссии не начисляются. Сдвиньте диапазон к текущей цене.',
                'severity': 'critical',
                'suggested_range': (current_price * 0.85, current_price * 1.15),
            }

        if near_upper or near_lower:
            mid = current_price
            new_lower = mid * 0.85
            new_upper = mid * 1.15
            return {
                'action': 'CENTER_RANGE',
                'message': f'⚡ Цена у границы. Для максимума комиссий держите диапазон ±15% от текущей цены: [{new_lower:,.2f} – {new_upper:,.2f}].',
                'severity': 'warning',
                'suggested_range': (new_lower, new_upper),
            }

        total_fees_val = fees0 * current_price + fees1
        if total_fees_val > 20:
            return {
                'action': 'REINVEST',
                'message': f'💰 Накоплено ~${total_fees_val:.0f} комиссий. Реинвестируйте для роста доли в пуле.',
                'severity': 'info',
                'suggested_range': None,
            }

        return {
            'action': 'HOLD',
            'message': '✅ Диапазон активен, комиссии собираются. Продолжайте.',
            'severity': 'info',
            'suggested_range': None,
        }

    # ─── GOAL: hedge ─────────────────────────────────────────────────────────
    if goal == 'hedge':
        if current_price < lower:
            return {
                'action': 'HOLD',
                'message': f'🛡 Хедж сработал: позиция конвертирована в {quote_sym}. Ждите стабилизации перед ребалансировкой.',
                'severity': 'info',
                'suggested_range': None,
            }
        if near_upper:
            return {
                'action': 'SHIFT_RANGE_UP',
                'message': f'⚠️ Цена у верхней границы хеджа. Сдвиньте диапазон вверх для поддержания защиты.',
                'severity': 'warning',
                'suggested_range': (current_price * 0.9, current_price * 1.5),
            }
        return {
            'action': 'HOLD',
            'message': '🛡 Хедж активен. Позиция защищена.',
            'severity': 'info',
            'suggested_range': None,
        }

    # ─── GOAL: balanced / default ────────────────────────────────────────────
    if not in_range:
        return {
            'action': 'SHIFT_RANGE',
            'message': '🚫 Цена вне диапазона — комиссии не начисляются. Ребалансируйте.',
            'severity': 'critical',
            'suggested_range': (current_price * 0.85, current_price * 1.15),
        }

    if near_upper or near_lower:
        return {
            'action': 'REBALANCE',
            'message': f'⚠️ Цена близка к границе диапазона. Рассмотрите ребалансировку для сохранения доходности.',
            'severity': 'warning',
            'suggested_range': (current_price * 0.85, current_price * 1.15),
        }

    return {
        'action': 'HOLD',
        'message': '✅ Позиция в диапазоне. Комиссии начисляются.',
        'severity': 'info',
        'suggested_range': None,
    }
