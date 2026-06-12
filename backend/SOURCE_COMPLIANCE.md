# Source Compliance

## RemoteOK (Phase 1's only source)

Data is fetched from the public RemoteOK API at `https://remoteok.com/api` with an honest `User-Agent` (`REMOTEOK_USER_AGENT`, default `job-market-intelligence/1.0`). The adapter does not impersonate a browser, respects HTTP 429 by aborting the run, and stores the original RemoteOK URL with every job.

### Usage requirements

1. **Attribution required.** Any public display of RemoteOK-derived jobs must credit RemoteOK as the source.
2. **Link back required.** Any public display must link back to the original RemoteOK job URL (stored in `jobs.source_url`).
3. **No logo use.** Do not use the RemoteOK logo unless explicit permission is granted by RemoteOK.
4. **Raw record retention.** The original source record is preserved in `jobs.raw_payload` for auditability.

## Sources excluded from Phase 1

- Kaggle datasets, static CSVs, or any manually curated production records (production data must come from live or recently collected postings)
- Browser-automation or Playwright scraping of sites without APIs
- Any source whose terms of service prohibit programmatic collection
- Multi-source ingestion in general (explicitly out of Phase 1 scope)

Test fixtures are allowed only inside tests; they never enter production tables.

## Checklist for evaluating future sources

Before adding a source, confirm:

- [ ] The source offers a public API or explicitly permits programmatic access
- [ ] Terms of service allow storage and redistribution of posting metadata
- [ ] Attribution and link-back requirements are understood and implementable
- [ ] Rate limits are documented and the adapter can respect them (429 handling, backoff)
- [ ] An honest User-Agent identifying this project can be sent
- [ ] Personally identifying information in postings can be avoided or handled lawfully
- [ ] A stable, unique source URL exists per posting (required for deduplication)
- [ ] Logo/trademark usage rules are clear
