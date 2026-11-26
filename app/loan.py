"""The loan Samjho explains, and how close an answer has to be to count.

The sample is synthetic. A lender would load each borrower's own Key Fact Statement into the same shape.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Loan:
    loan_id: str
    lender: str
    sanctioned: int
    processing_fee: int
    insurance: int
    instalment: int
    frequency: str  # "weekly" or "monthly"
    instalments: int
    total_repayable: int
    apr_percent: float
    grievance_contact: str = "Lender's grievance officer"
    extra: dict = field(default_factory=dict)

    @property
    def deductions(self) -> int:
        return self.processing_fee + self.insurance

    @property
    def cash_in_hand(self) -> int:
        return self.sanctioned - self.deductions


SAMPLE_LOAN = Loan(
    loan_id="SAMPLE-JLG-50000",
    lender="Sample microfinance lender (synthetic)",
    sanctioned=50_000,
    processing_fee=1_000,
    insurance=590,
    instalment=1_095,
    frequency="weekly",
    instalments=52,
    total_repayable=56_940,
    apr_percent=32.8,
)

# The five facts a borrower must say back. Order is the order Samjho asks about missing ones.
FACTS = ("cash_in_hand", "deductions", "instalment", "frequency", "total")

# Relative tolerance: within green counts as understood; within amber is close and gets one gentle repair.
TOLERANCE = {
    "cash_in_hand": (0.03, 0.03),  # 50,000 for 48,410 is 3.3% off: that is the classic miss, so it is red
    "deductions": (0.10, 0.40),
    "instalment": (0.05, 0.12),  # "gyarah sau" (1,100) is green; "hazaar" (1,000) is amber
    "total": (0.03, 0.08),
}


def truth(loan: Loan, fact: str):
    return {
        "cash_in_hand": loan.cash_in_hand,
        "deductions": loan.deductions,
        "instalment": loan.instalment,
        "frequency": loan.frequency,
        "total": loan.total_repayable,
    }[fact]
