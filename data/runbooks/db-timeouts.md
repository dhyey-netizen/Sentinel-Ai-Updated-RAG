# Database query timeouts

## Symptoms
Queries fail with "SQL timeout: statement exceeded 5000ms". Errors concentrate on one or a few
statements. The connection pool itself is healthy, with idle connections available.

## Diagnosis
Identify the slow statement from the error text and check the slow query log. Look for full table
scans, missing indexes, large row counts examined, lock waits and recent data growth. Check whether
the timeouts started after a schema change, a deploy that altered the query, or a batch job
running at the same time. Compare the query plan with a known good one.

## Remediation
Add or fix the missing index, rewrite the query to examine fewer rows, or add pagination. Review
the query plan before and after a change. If a batch job competes for the same tables, reschedule
it. Raising the statement timeout only hides the problem and should not be the first step.
