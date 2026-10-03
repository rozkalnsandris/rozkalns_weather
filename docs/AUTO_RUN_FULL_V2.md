# AUTO-RUN FULL v2

Activate only with:

```text
AUTO-RUN FULL rozkalns_weather #<issue>
```

The explicit command authorizes the named issue's source work and canonical PR through CI/review convergence and guarded merge under `.github/auto-run-full-v2.json`.

It never grants secrets, Cloudflare/network, DB/schema/data, host/systemd or other non-standard LIVE authority.

No project-local controller issue, queue or receipt state machine is required for normal operation.
