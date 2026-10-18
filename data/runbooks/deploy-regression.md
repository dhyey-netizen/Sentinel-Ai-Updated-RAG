# Error spike after a deployment

## Symptoms
The error rate rises sharply shortly after a release, with the same exception repeated, for example
a NullPointerException in one method. Infrastructure metrics such as database pool usage are
normal. The first errors appear minutes after the deployment line in the logs.

## Diagnosis
Compare the time of the first error with the deployment time. Read the stack trace or error
message to find the failing method and the input that triggers it, such as a null value. Review
what changed in the release for that code path and check whether the failing input is new or newly
reachable. Confirm that all instances run the new version.

## Remediation
Roll back to the previous release if the impact is high, then fix forward with a test that covers
the failing input. Add null handling or validation at the failing point. Consider a canary or staged
rollout for similar changes in future.
