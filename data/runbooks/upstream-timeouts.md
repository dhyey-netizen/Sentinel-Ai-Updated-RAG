# Upstream dependency timeouts

## Symptoms
Calls to an external or internal service such as a payment gateway time out: "upstream
payment-gateway timed out after 10000ms", often with retry attempts logged. A circuit breaker may
report a high failure rate. Our own database and pool look healthy.

## Diagnosis
Check the upstream provider's status page and your own network path to it. Look at whether all
requests to that dependency fail or only some, and when failures began. Review retry settings:
repeated retries can multiply load and extend the outage. Check whether the circuit breaker opened
and whether callers have a sensible fallback or error message.

## Remediation
Confirm with the upstream owner whether they have an incident. Tune timeouts and retry backoff so
retries do not amplify load. Make sure the circuit breaker opens quickly and that users see a
clear failure rather than a long hang. Consider queueing work for later where the business allows
it.
