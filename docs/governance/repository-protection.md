# Repository protection proposal

Inspection date: **2026-10-04**. Applies to `ThePolarisLab/Polaris-Lab`; supports [PROJECT_STATE](../../PROJECT_STATE.md). This is a proposal, not an applied settings change.

## Observed state

GitHub main branch API reported `protected: false`, enforcement off and no required checks. Repository ruleset enumeration returned an empty list. This does not verify unrelated organization policies or administration-only settings. Passing CI therefore does not currently enforce merge discipline.

Security Gate previously ran on PRs to main but pushed only to the stale `phase1/security-gate` branch. This PR changes its push trigger to main and gives all three jobs unique Security Gate names. Tests/build commands and test credentials remain unchanged.

## Recommended checks

After this PR's successful CI establishes the emitted check names, require:

- `Security Gate / Backend security tests`
- `Security Gate / TypeScript tests`
- `Security Gate / Frontend tests and build`

These are the exact job names defined by this PR and run on every PR to main. Select the GitHub Actions source when configuring requirements. `test-typescript-core` from Polaris TypeScript CI also runs for every PR but duplicates the root test suite; requiring both adds little assurance. It may remain informational for least-cost protection.

Database Gate's `SQLite migration lifecycle` and `PostgreSQL migration compatibility` should also gate schema-impacting merges. **Do not require them globally with the current path filters:** a skipped workflow can leave required checks pending. A separate reviewed trigger/aggregate-gate change must provide an always-reported migration decision before enabling them as universal required checks. PostgreSQL 16 CI also does not prove PostgreSQL 18 production compatibility; validate that version gap separately without migrating production here.

Backend Tests, PGE-008 runtime, QuickBooks and Outlook workflows are path-filtered and/or overlap other suites. Keep relevant results in PR review rather than blindly requiring all workflow names. The old generic `Frontend tests and build` name also appears in Database Gate; Security Gate names are now distinct to avoid ambiguous requirements. Inspect existing `feature/**` push triggers and duplicated suites before any future cost-reduction changes; they are not altered here.

## Least-cost proposal

For this currently public repository, GitHub Free supports protected branches. Use one main protection rule (or an equivalent ruleset), require PRs and the three always-run Security Gate checks, block force pushes/deletion, and resolve review conversations. Require independent approval where a second maintainer is available; avoid an approval rule that permanently blocks a sole maintainer. Decide administrator bypass explicitly and document any emergency bypass with follow-up review.

Do not buy a plan solely for this baseline or change repository visibility to obtain protection. If the repository becomes private, verify the applicable plan's protection support before relying on it. Keep settings changes separately authorized/reviewed and record their effective date/check names after application.

References: [GitHub protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches), [required-check troubleshooting](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/troubleshooting-required-status-checks).
