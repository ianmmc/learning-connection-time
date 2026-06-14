# Benchmark Report: openrouter:meta-llama/llama-3.3-70b-instruct:free
Run date: 2026-06-13T22:15:36
Districts tested: 1
Total extraction time: 64s (avg 64.0s/district)

## Summary

| Metric | Value |
|--------|-------|
| Overall accuracy | 0.0% |
| JSON parse success | 100.0% |
| Grade coverage rate | 0.0% |
| False positive rate | 0.0/district |
| Mean time/extraction | 64.0s |

## Per-District Scores

| District | State | Score | Max | Pct | Penalties | Notes |
|----------|-------|-------|-----|-----|-----------|-------|
| KIPP DC PCS | DC | 0 | 30 | 0.0% | extraction_error |  |

## Detailed Scoring

======================================================================
KIPP DC PCS (DC) - 1100031
======================================================================
Ground truth: 3 entries | Extracted: 0 | Matched: 0

Entry Scores:

Penalties:
  extraction_error: -5 (RateLimitError: Error code: 429 - {'error': {'message': 'Provider returned error', 'code': 429, 'metadata': {'raw': 'meta-llama/llama-3.3-70b-instruct:free is temporarily rate-limited upstream. Please retry shortly, or add your own key to accumulate your rate limits: https://openrouter.ai/settings/integrations', 'provider_name': 'Venice', 'is_byok': False, 'retry_after_seconds': 30, 'retry_after_seconds_raw': 29.423, 'headers': {'Retry-After': '30'}}}, 'user_id': 'user_3F6G2u57EqCPewKcTHYL5cGYfne'})

Total: 0 (entries) + -5 (penalties) = 0/30 (0.0%)