# Cache or Redis connectivity failures

## Symptoms
Errors such as "cache lookup failed: redis connection reset". Requests fall back to the database
and become slow. Failures are intermittent and may not match database health checks.

## Diagnosis
Check Redis availability, memory usage and eviction, connection limits and recent restarts or
failovers. Look at whether client connections are reused or reopened per request. Determine whether
cache failures and slow requests start at the same time, and whether the application treats a cache
miss as an error rather than falling back gracefully.

## Remediation
Make cache failures non-fatal in the application, with a short timeout and a database fallback.
Review the connection pool and keepalive settings of the Redis client. If memory pressure causes
resets, adjust sizing or the eviction policy after reviewing the workload.
