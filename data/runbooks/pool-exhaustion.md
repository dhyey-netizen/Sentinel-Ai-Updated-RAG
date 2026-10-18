# Database connection pool exhaustion

## Symptoms
Requests fail or stall with messages such as "Connection is not available, request timed out
after 30000ms". Pool metrics show active connections equal to the maximum pool size, idle at zero
and a growing number of threads waiting. Latency rises on every endpoint that touches the database,
not just one.

## Diagnosis
Check how long individual connections are held: look for leak detection warnings and for the code
path named in them. Compare the number of waiting threads with the pool maximum over time. Find out
whether traffic rose or whether connections are being held longer than before (slow queries, a
transaction left open, a missing close in an error path). Trace one failing request end to end to
see where it waited for a connection.

## Remediation
Fix connection leaks first: make sure connections are returned in every code path, including
exceptions. Shorten transactions and move slow work outside them. Only after that consider raising
the pool maximum, and confirm the database can handle the extra connections. Consider a shorter
connection acquisition timeout so callers fail fast. A rolling restart only clears the symptom
temporarily.
