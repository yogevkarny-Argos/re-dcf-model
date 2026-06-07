"""
debt.py — Full debt stack: acquisition loan, construction loan, refi, exit payoff.
Each loan produces a month-by-month balance, interest, and payment schedule.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .assumptions import Assumptions


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class LoanMonth:
    month: int
    beginning_balance: float
    draw: float               # new principal drawn this month
    interest: float
    principal: float          # scheduled principal repayment
    payment: float            # total cash out (interest + principal)
    ending_balance: float
    is_io: bool               # True = interest-only period


@dataclass
class DebtMonth:
    month: int
    acq_loan: LoanMonth
    const_loan: LoanMonth
    refi_loan: LoanMonth
    total_debt_service: float        # acq + refi payments (not const — capitalize)
    total_interest_expense: float    # all loans
    total_balance: float
    refi_net_proceeds: float         # positive in refi month only
    payoff_amount: float             # non-zero in exit month only


# ---------------------------------------------------------------------------
# Amortization helpers
# ---------------------------------------------------------------------------

def _monthly_payment(balance: float, monthly_rate: float, n_payments: int) -> float:
    """Standard P&I payment for remaining balance and periods."""
    if monthly_rate == 0:
        return balance / n_payments if n_payments > 0 else 0.0
    return balance * (monthly_rate * (1 + monthly_rate) ** n_payments) / \
           ((1 + monthly_rate) ** n_payments - 1)


def _build_loan_schedule(
    initial_balance: float,
    annual_rate: float,
    io_months: int,
    amort_years: int,
    term_months: int,
    start_month: int,
    total_months: int,
    payoff_month: Optional[int] = None,
) -> List[LoanMonth]:
    """
    Build a full amortization schedule from start_month to total_months.
    Returns a list indexed by absolute month (0-based).
    Months before start_month are zero-balance placeholders.
    """
    monthly_rate = annual_rate / 12.0
    amort_payments = amort_years * 12

    schedule: List[LoanMonth] = []
    balance = 0.0

    for m in range(total_months):
        if m < start_month:
            schedule.append(LoanMonth(m, 0, 0, 0, 0, 0, 0, False))
            continue

        if m == start_month:
            balance = initial_balance

        if payoff_month is not None and m == payoff_month:
            # Full payoff — payment=0 so DCF doesn't double-count vs. sale proceeds
            schedule.append(LoanMonth(m, balance, 0, 0, 0, 0.0, 0.0, False))
            balance = 0.0
            continue

        if balance <= 0:
            schedule.append(LoanMonth(m, 0, 0, 0, 0, 0, 0, False))
            continue

        rel = m - start_month  # months since loan origination
        interest = balance * monthly_rate

        if rel < io_months:
            # Interest-only
            principal = 0.0
            payment   = interest
            is_io     = True
        else:
            months_in_amort = rel - io_months
            remaining = amort_payments - months_in_amort
            if remaining <= 0:
                # Balloon / maturity
                principal = balance
                payment   = interest + principal
                is_io     = False
            else:
                payment   = _monthly_payment(balance, monthly_rate, remaining)
                principal = payment - interest
                is_io     = False

        # Guard against float rounding causing negative principal
        principal = max(0.0, min(principal, balance))
        end_bal   = balance - principal

        schedule.append(LoanMonth(
            month=m,
            beginning_balance=balance,
            draw=0.0,
            interest=interest,
            principal=principal,
            payment=payment,
            ending_balance=end_bal,
            is_io=is_io,
        ))
        balance = end_bal

    return schedule


# ---------------------------------------------------------------------------
# Construction loan schedule
# ---------------------------------------------------------------------------

def _build_const_schedule(
    draws_by_month: List[float],   # equity-adjusted total draw per month
    annual_rate: float,
    total_months: int,
    payoff_month: Optional[int],
) -> List[LoanMonth]:
    """
    Construction loan: interest accrues on drawn balance only.
    No principal repayment until payoff.
    """
    schedule: List[LoanMonth] = []
    balance = 0.0
    monthly_rate = annual_rate / 12.0

    for m in range(total_months):
        draw     = draws_by_month[m] if m < len(draws_by_month) else 0.0
        interest = balance * monthly_rate

        if payoff_month is not None and m == payoff_month and balance > 0:
            # Payment=0 — payoff captured in refi/sale proceeds in DCF
            schedule.append(LoanMonth(m, balance, 0, 0, 0, 0.0, 0.0, True))
            balance = 0.0
            continue

        end_bal = balance + draw  # interest capitalized (added to balance)
        # In a construction loan, interest is typically capitalized or paid from reserve
        # We capitalize here (most common); set to paid-current by adjusting payment below
        payment = 0.0  # interest capitalized = no cash payment during construction
        end_bal = balance + draw + interest  # capitalize interest

        schedule.append(LoanMonth(
            month=m,
            beginning_balance=balance,
            draw=draw,
            interest=interest,
            principal=0.0,
            payment=payment,
            ending_balance=end_bal,
            is_io=True,
        ))
        balance = end_bal

    return schedule


# ---------------------------------------------------------------------------
# Main debt engine
# ---------------------------------------------------------------------------

def compute_debt(
    a: "Assumptions",
    const_loan_draws: List[float],    # from capex engine: const_loan_draw per month
    stabilization_month: int,
    noi_by_month: List[float],        # for refi sizing
) -> List[DebtMonth]:
    total_months = a.timeline.hold_months + 1
    exit_month   = a.exit.exit_month

    # -----------------------------------------------------------------------
    # Acquisition Loan
    # -----------------------------------------------------------------------
    acq  = a.acq_loan
    acq_amount = a.acquisition.purchase_price * acq.ltv_or_ltc if acq.include else 0.0
    acq_rate   = acq.interest_rate

    # Refi payoff month for acq loan
    refi_payoff_acq = None
    if a.refi.include:
        refi_month = a.refi.trigger_month if a.refi.trigger_month else stabilization_month
        refi_payoff_acq = refi_month
    else:
        refi_payoff_acq = exit_month

    acq_schedule = _build_loan_schedule(
        initial_balance=acq_amount,
        annual_rate=acq_rate,
        io_months=acq.io_period_months,
        amort_years=acq.amortization_years,
        term_months=acq.term_months,
        start_month=0,
        total_months=total_months,
        payoff_month=refi_payoff_acq,
    ) if acq.include else [LoanMonth(m, 0, 0, 0, 0, 0, 0, False) for m in range(total_months)]

    # -----------------------------------------------------------------------
    # Construction Loan
    # -----------------------------------------------------------------------
    const = a.const_loan
    const_payoff_month = refi_month if a.refi.include else exit_month

    const_schedule = _build_const_schedule(
        draws_by_month=const_loan_draws,
        annual_rate=const.interest_rate,
        total_months=total_months,
        payoff_month=const_payoff_month,
    ) if const.include else [LoanMonth(m, 0, 0, 0, 0, 0, 0, False) for m in range(total_months)]

    # -----------------------------------------------------------------------
    # Refi Loan
    # -----------------------------------------------------------------------
    refi_schedule = [LoanMonth(m, 0, 0, 0, 0, 0, 0, False) for m in range(total_months)]
    refi_net_proceeds = [0.0] * total_months

    if a.refi.include:
        refi_m = refi_month
        # Size refi on trailing NOI at refi month
        noi_at_refi = noi_by_month[refi_m] * 12 if refi_m < len(noi_by_month) else 0.0
        market_cap   = a.market.market_cap_rate_going_in
        refi_value   = noi_at_refi / market_cap if market_cap > 0 else 0.0
        refi_amount  = refi_value * a.refi.ltv
        # Payoffs
        acq_bal_at_refi   = acq_schedule[refi_m].beginning_balance if refi_m < len(acq_schedule) else 0.0
        const_bal_at_refi = const_schedule[refi_m].beginning_balance if refi_m < len(const_schedule) else 0.0
        total_payoff      = acq_bal_at_refi + const_bal_at_refi
        refi_costs        = refi_amount * a.refi.origination_fee_pct + a.refi.refi_costs_fixed
        net_proceeds      = refi_amount - total_payoff - refi_costs

        refi_net_proceeds[refi_m] = max(0.0, net_proceeds)

        refi_schedule_full = _build_loan_schedule(
            initial_balance=refi_amount,
            annual_rate=a.refi.interest_rate,
            io_months=a.refi.io_period_months,
            amort_years=a.refi.amortization_years,
            term_months=a.refi.term_months,
            start_month=refi_m,
            total_months=total_months,
            payoff_month=exit_month,
        )
        refi_schedule = refi_schedule_full

    # -----------------------------------------------------------------------
    # Assemble DebtMonth
    # -----------------------------------------------------------------------
    results: List[DebtMonth] = []

    for m in range(total_months):
        al = acq_schedule[m]
        cl = const_schedule[m]
        rl = refi_schedule[m]

        # Debt service = cash paid (acq + refi; const is capitalized)
        ds = al.payment + rl.payment

        # Payoff at exit
        payoff = 0.0
        if m == exit_month:
            refi_bal = rl.beginning_balance
            acq_bal  = al.beginning_balance  # should be 0 if refi happened
            payoff   = refi_bal + acq_bal

        results.append(DebtMonth(
            month=m,
            acq_loan=al,
            const_loan=cl,
            refi_loan=rl,
            total_debt_service=ds,
            total_interest_expense=al.interest + cl.interest + rl.interest,
            total_balance=al.ending_balance + cl.ending_balance + rl.ending_balance,
            refi_net_proceeds=refi_net_proceeds[m],
            payoff_amount=payoff,
        ))

    return results
