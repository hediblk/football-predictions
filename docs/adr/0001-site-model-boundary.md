---
status: accepted
date: 2026-10-13
---

# Keep the site and forecast model in one repository with a checked data boundary

Keep the model and site in one repository with separate checks and a validated JSON publishing boundary. Splitting repositories would add daily data delivery and coordination work; keeping one repository allows changes to the exporter and its consumers to be reviewed together. This decision covers roadmap item 5, excluding the repository rename.

## Boundary

- Keep `src/standing_prediction/`, `packages/`, and `site/` in place. `scripts/build_site_data.py` remains the adapter from forecast outputs to published site data; the browser consumes JSON without running or reimplementing the forecasting model.
- Give model checks, published-data validation, and daily refresh/publication separate workflow responsibilities. Shared adapter, schema, and dependency changes run the relevant checks on both sides. Pull-request checks use frozen inputs and require no provider credentials or live football APIs. Small production refactors that simplify these boundaries or make computations directly testable are in scope.
- Keep the current daily schedule and manual refresh. A model-only change is checked immediately and reaches published forecasts through the next refresh.

## Safeguards

- Run the existing Python tests and fixed-input, fixed-date, fixed-seed numerical regressions for domestic and Champions League forecasting. Use the same pinned runtime dependencies in CI and daily refresh. Compare match probabilities and season/tournament outcomes with explicit tolerances; exclude generation timestamps and paths. Intentional changes require an explained baseline update in the same review. [Numerical protection](../numerical-protection.md) defines coverage, tolerances, provenance, temporal checks, and the baseline review procedure.
- Define reusable JSON schemas for every published data family and independently check the adapter's output and complete published dataset. The [data contract](../site-data-contract.md) defines field meanings, units, optional data, consistency, rounding budgets, and compatibility. Model tests alone do not validate the exporter.
- Allow compatible extra fields and the existing optional fields and fallback files. Removing or renaming consumed fields, changing units, or changing required shapes requires a coordinated producer/consumer change that also handles retained competition data and older history. Start with one current contract rather than multiple API versions.
- Omit automated browser checks from this work. Concentrate the automated publication gate on valid model outputs and exported data; frontend JavaScript, interactions, and rendering receive manual review. Static hosting still runs client-side code, so data validity does not guarantee a functioning rendered site. This is a deliberate coverage trade-off.
- Preserve partial refreshes: if one competition fails, retain its last published data and update successful competitions. All-six failure remains a failed refresh. Reject an invalid combined dataset and leave the deployed site in place.
- Validate the exact immutable site artifact that is deployed, including daily refreshes whose bot commits do not trigger another workflow. Contract failures block publication. CI reports checks on pull requests; repository merge-protection settings are unchanged. Requiring merge checks needs a separate decision about the daily bot's direct commits to `main`.

## Documentation

Use `CONTEXT.md` for football terminology, `docs/adr/` for durable architectural decisions and their trade-offs, `ROADMAP.md` for pending work, `PLAN.md` for model design and experiment history, and the README for running and contributing to the project. Link between these sources rather than copying their content. Record later reversals in a superseding ADR.

## Consequences and scope

This provides independently checked areas within one repository, with shared checks at the publishing boundary. It does not create independently versioned products. The site still supports retained forecasts and optional data, so schemas must represent those states honestly rather than rejecting every missing value.

Numerical regressions detect unreviewed behavior changes; they do not establish forecast quality. Dependency updates can intentionally change fitted results and need the same baseline review. The current global freshness indicator can mask an older retained competition; changing that UI, asset cache versioning, new forecast features, folder migrations, and the repository rename remain outside this work.
