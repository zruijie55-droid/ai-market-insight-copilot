# Changelog

## V1.2.0 - 2026-10-05

- Added monthly review-volume, negative-rate, and average-rating trends.
- Added brand-level feedback summaries and brand-by-negative-theme heatmaps.
- Added theme, sentiment, and brand filters for source-evidence review.
- Improved upload error recovery and source attribution.
- Added strict validation for configurable price-band boundaries.
- Improved standalone HTML reports, including inline Plotly assets and correct Markdown rendering.
- Added Streamlit Community Cloud configuration and GitHub Actions CI.
- Expanded the automated suite to 64 passing tests, including deployment-readiness checks.

## V1.1.1

- Fixed Streamlit `UploadedFile` handling for CSV and Excel.
- Fixed missing-review text validation and empty price-band report handling.
- Added explicit LLM call-budget enforcement and graceful fallback.
