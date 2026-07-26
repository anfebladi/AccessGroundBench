"""Console and CSV rendering for McNemar analysis records."""

from .service import AnalysisRecord, FLOOR_ACC_THRESHOLD
from .statistics import ALPHA


def format_report(record: AnalysisRecord) -> str:
    """Format a baseline-versus-profile result as the legacy readable block."""
    return _format_comparison_report(
        record,
        header_lines=[f"  Profile: {record.profile}  vs.  baseline"],
        first_accuracy_label="Baseline Accuracy",
        second_accuracy_label="Experimental Accuracy",
        first_accuracy_gap=5,
        second_accuracy_gap=1,
        second_pass_label="Exp. PASS",
        second_fail_label="Exp. FAIL",
        first_pass_label="Baseline PASS",
        first_fail_label="Baseline FAIL",
        conclusion_lines=_standard_conclusion(record),
    )


def format_cross_report(record: AnalysisRecord) -> str:
    """Format a cross-file comparison result as the legacy readable block."""
    return _format_comparison_report(
        record,
        header_lines=[f"  Profile: {record.profile}", "  Vision-only vs. Vision + A11y Tree"],
        first_accuracy_label="Vision-only Accuracy",
        second_accuracy_label="With Tree Accuracy",
        first_accuracy_gap=2,
        second_accuracy_gap=4,
        second_pass_label="Tree PASS",
        second_fail_label="Tree FAIL",
        first_pass_label="Vision-only PASS",
        first_fail_label="Vision-only FAIL",
        conclusion_lines=_cross_conclusion(record),
    )


def standard_csv_header() -> list[str]:
    """Return the legacy standard-analysis CSV header."""
    return [
        "Profile", "Total_Pairs", "Both_Pass_a", "Broke_It_b",
        "Fluke_Recovery_c", "Both_Fail_d", "Discordant_Pairs",
        "Baseline_Acc", "Exp_Acc", "Test_Used", "Statistic", "P_Value",
        "Significant", "Floor_Limited",
    ]


def cross_csv_header() -> list[str]:
    """Return the legacy cross-file CSV header."""
    return [
        "Profile", "Total_Pairs", "Both_Pass_a", "Tree_Hurt_b",
        "Tree_Helped_c", "Both_Fail_d", "Discordant_Pairs",
        "VisionOnly_Acc", "WithTree_Acc", "Test_Used", "Statistic",
        "P_Value", "Significant",
    ]


def standard_csv_row(record: AnalysisRecord) -> list[object]:
    """Render one legacy standard-analysis CSV row."""
    return _common_csv_row(record) + ["Yes" if record.floor_limited else "No"]


def cross_csv_row(record: AnalysisRecord) -> list[object]:
    """Render one legacy cross-file CSV row."""
    return _common_csv_row(record)


def format_standard_summary(model_name: str, records: list[AnalysisRecord]) -> str:
    """Render the legacy standard-analysis summary table."""
    return _format_summary(
        title=f"  Summary for {model_name}",
        first_heading="Base Acc",
        second_heading="Exp Acc",
        records=records,
        floor_aware=True,
    )


def format_cross_summary(records: list[AnalysisRecord]) -> str:
    """Render the legacy cross-file summary table."""
    return _format_summary(
        title="  Cross-File Summary: Vision-only vs. Vision + A11y Tree",
        first_heading="Vis Acc",
        second_heading="Tree Acc",
        records=records,
        floor_aware=False,
    )


def _format_comparison_report(
    record: AnalysisRecord,
    *,
    header_lines: list[str],
    first_accuracy_label: str,
    second_accuracy_label: str,
    first_accuracy_gap: int,
    second_accuracy_gap: int,
    second_pass_label: str,
    second_fail_label: str,
    first_pass_label: str,
    first_fail_label: str,
    conclusion_lines: list[str],
) -> str:
    lines = ["", "=" * 60, *header_lines, "=" * 60, "", "  Accuracies:"]
    lines.extend([
        f"    {first_accuracy_label}:{' ' * first_accuracy_gap}{record.first_accuracy:.1f}% ({record.a + record.b}/{record.total})",
        f"    {second_accuracy_label}:{' ' * second_accuracy_gap}{record.second_accuracy:.1f}% ({record.a + record.c}/{record.total})",
        "",
        f"  2x2 Contingency Matrix (n={record.total} paired elements):",
        "  +---------------------+--------------+--------------+",
        f"  |                     | {second_pass_label:<12} | {second_fail_label:<12} |",
        "  +---------------------+--------------+--------------+",
        f"  | {first_pass_label:<19} |  a = {record.a:<7} |  b = {record.b:<7} |",
        f"  | {first_fail_label:<19} |  c = {record.c:<7} |  d = {record.d:<7} |",
        "  +---------------------+--------------+--------------+",
        "",
        f"  Discordant pairs: b + c = {record.discordant_pairs}",
        f"  Test selected:    {record.result['test']}",
    ])

    if record.result["statistic"] is not None:
        lines.append(f"  chi2 statistic:   {record.result['statistic']:.4f}")

    lines.extend([f"  p-value:          {record.result['p_value']:.6f}", "", *conclusion_lines, ""])
    return "\n".join(lines)


def _standard_conclusion(record: AnalysisRecord) -> list[str]:
    lines = []
    if record.floor_limited:
        lines.extend([
            f"  Floor check:      FLOOR-LIMITED (baseline acc {record.first_accuracy:.1f}% "
            f"< {FLOOR_ACC_THRESHOLD:.0f}%; only {record.a + record.b}/{record.total} targets "
            "could show degradation)",
            "",
        ])

    if record.result["p_value"] < ALPHA:
        lines.append(
            f"  >> REJECT H0 (p < {ALPHA}): The accessibility layout modifications "
            f"caused a STATISTICALLY SIGNIFICANT alteration in VLM grounding "
            f"performance for profile '{record.profile}'."
        )
    elif record.floor_limited:
        lines.append(
            f"  >> INCONCLUSIVE (p >= {ALPHA}, FLOOR EFFECT): Baseline accuracy is "
            f"only {record.first_accuracy:.1f}%, so most targets already fail before any "
            f"distortion. This test CANNOT detect degradation here and is NOT "
            f"evidence of resilience for profile '{record.profile}'."
        )
    else:
        lines.append(
            f"  >> FAIL TO REJECT H0 (p >= {ALPHA}): The model demonstrated "
            f"spatial localization RESILIENCE. Performance differences fall within "
            f"random statistical noise for profile '{record.profile}'."
        )
    return lines


def _cross_conclusion(record: AnalysisRecord) -> list[str]:
    if record.result["p_value"] < ALPHA:
        return [
            f"  >> REJECT H0 (p < {ALPHA}): Tree injection caused a "
            f"STATISTICALLY SIGNIFICANT change in VLM grounding "
            f"performance for profile '{record.profile}'."
        ]
    return [
        f"  >> FAIL TO REJECT H0 (p >= {ALPHA}): Tree injection did NOT "
        f"significantly alter VLM grounding performance for "
        f"profile '{record.profile}'. Differences fall within random noise."
    ]


def _common_csv_row(record: AnalysisRecord) -> list[object]:
    return [
        record.profile, record.total, record.a, record.b, record.c, record.d,
        record.discordant_pairs,
        f"{record.first_accuracy:.1f}%",
        f"{record.second_accuracy:.1f}%",
        record.result["test"],
        record.result["statistic"] if record.result["statistic"] is not None else "",
        record.result["p_value"],
        "Yes" if record.result["p_value"] < ALPHA else "No",
    ]


def _format_summary(
    *,
    title: str,
    first_heading: str,
    second_heading: str,
    records: list[AnalysisRecord],
    floor_aware: bool,
) -> str:
    lines = [
        "\n" + "=" * 80,
        title,
        "=" * 80,
        f"  {'Profile':<20} {first_heading:>9} {second_heading:>9} {'b+c':>5}  {'Test':<15}  {'p-value':>10}  {'Result'}",
        f"  {'-' * 20} {'-' * 9} {'-' * 9} {'-' * 5}  {'-' * 15}  {'-' * 10}  {'-' * 12}",
    ]
    for record in records:
        if record.result["p_value"] < ALPHA:
            verdict = "SIGNIFICANT"
        elif floor_aware and record.floor_limited:
            verdict = "Inconclusive (floor)"
        else:
            verdict = "Not Sig."
        lines.append(
            f"  {record.profile:<20} {record.first_accuracy:>8.1f}% {record.second_accuracy:>8.1f}% "
            f"{record.discordant_pairs:>5}  {record.test_short:<15}  "
            f"{record.result['p_value']:>10.6f}  {verdict}"
        )
    return "\n".join(lines)
