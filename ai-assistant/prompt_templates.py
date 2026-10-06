"""Reusable wording templates for deterministic assistant responses."""

ESTIMATE_DISCLAIMER = (
    "This is an automated estimate, not an official warning or a substitute for "
    "instructions from local emergency services."
)

RISK_SUMMARY_TEMPLATE = "{hazard} risk is {risk_band} (score {risk_score}/100)."

SCENARIO_SUMMARY_TEMPLATE = (
    "In scenario '{scenario_name}', estimated risk changes from {baseline_score} "
    "to {scenario_score} ({score_change:+.2f} points)."
)

FEATURE_POSITIVE_TEMPLATE = "{feature} is a factor associated with increased estimated risk."
FEATURE_NEGATIVE_TEMPLATE = "{feature} is associated with a lower model estimate; it does not remove the hazard."
