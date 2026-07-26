"""Shared orchestration for profile-level McNemar analyses."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from .statistics import ASYMPTOTIC_THRESHOLD, run_mcnemar


EXPERIMENTAL_PROFILES = [
    "elder_text_heavy",
    "elder_zoom_heavy",
    "elder_combo_max",
    "elder_combo_rtl",
    "colorblind_deuteranomaly",
]

FLOOR_ACC_THRESHOLD = 50.0


@dataclass(frozen=True)
class AnalysisRecord:
    """All computed values for one profile comparison."""

    profile: str
    a: int
    b: int
    c: int
    d: int
    result: dict

    @property
    def total(self) -> int:
        return self.a + self.b + self.c + self.d

    @property
    def first_accuracy(self) -> float:
        return ((self.a + self.b) / self.total * 100) if self.total > 0 else 0.0

    @property
    def second_accuracy(self) -> float:
        return ((self.a + self.c) / self.total * 100) if self.total > 0 else 0.0

    @property
    def discordant_pairs(self) -> int:
        return self.b + self.c

    @property
    def floor_limited(self) -> bool:
        return self.first_accuracy < FLOOR_ACC_THRESHOLD

    @property
    def test_short(self) -> str:
        if self.discordant_pairs == 0:
            return "N/A"
        if self.discordant_pairs >= ASYMPTOTIC_THRESHOLD:
            return "Asymptotic"
        return "Exact Binom."


def analyze_profiles(
    pairs: object,
    profiles: Iterable[str],
    contingency_function: Callable[[object, str], tuple[int, int, int, int]],
) -> list[AnalysisRecord]:
    """Compute a single reusable analysis record for each requested profile."""
    records = []
    for profile in profiles:
        a, b, c, d = contingency_function(pairs, profile)
        records.append(AnalysisRecord(profile, a, b, c, d, run_mcnemar(b, c)))
    return records


def cross_file_profiles(pairs: dict[str, dict[str, tuple[int, int]]]) -> list[str]:
    """Return legacy-order profiles that occur in paired cross-file data."""
    profiles_present = set()
    for profile_scores in pairs.values():
        profiles_present.update(profile_scores.keys())
    return [profile for profile in EXPERIMENTAL_PROFILES if profile in profiles_present]
