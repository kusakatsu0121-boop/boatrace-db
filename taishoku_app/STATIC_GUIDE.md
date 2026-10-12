# Free instant guide

`docs/taishoku-guide/` is an additive, client-only procedure guide for GitHub Pages.
It offers contact details, documents to prepare, and words to use at the counter.
It does not calculate benefits or determine eligibility. It has no submissions,
PDF, approval queue, AI/API, database, analytics, cookies, or browser storage.
Answers remain in page memory and reset on page show. CSP prohibits connections
and form submissions. All displayed content is authored constant text using
textContent; unknown options fall back to the unknown path.

The existing Tally/Render/Neon service, calculations, secret links and stored
reports are untouched. This guide can be published without deploying Render.
Keep that separate service's billing and eventual retirement as a separate task.

## Publish

The public repository's existing main-branch Pages workflow publishes all `docs`.
The guide lives at `/boatrace-db/taishoku-guide/`; it does not replace the racer
directory or change its workflow. Four static files total under 40 KB. Public
repository Pages and standard hosted Actions are free; no larger runner is used.
Do not add paid services or external requests.

## Verify

`node taishoku_app/tests/static_guide.test.mjs`

Serve `docs` with a static server and open `/taishoku-guide/`. Verify five cases:
ordinary retirement, sick leave, planned retirement with illness, disputed reason,
and all unknown. Check mobile at 320/390 px, keyboard focus, correction, reload,
no external requests, and no local/session storage. The supplied test covers all
512 option combinations and the sickness application/receiving branches.

## Sources checked 2026-10-12

- Hello Work: https://www.hellowork.mhlw.go.jp/insurance/insurance_procedure.html
- Hello Work (inability to work / extension): https://www.hellowork.mhlw.go.jp/insurance/insurance_basicbenefit.html
- Kyokai Kenpo (sickness): https://www.kyoukaikenpo.or.jp/faq/benefit/002/
- Kyokai Kenpo (insurance options): https://www.kyoukaikenpo.or.jp/faq/voluntary_continuation/001/
- Japan Pension Service: https://www.nenkin.go.jp/service/kokunen/kanyu/20140710-03.html
- Pages: https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages
- Actions: https://docs.github.com/en/billing/concepts/product-billing/github-actions

No monetary rates, age-specific unemployment entitlement, or waiting-period
calculations are included. Any future rule or deadline additions require official
source verification; preserve the existing calculation engine independently.
