# Weather SIMPLE-DEPLOY v1 canary

Issue: `#142`

Status: **source adoption; one-time RPi5 cutover is not active and remains separately authorized**.

Weather is the first consumer/canary of the shared SIMPLE-DEPLOY v1 platform. Weather owns application-specific configuration only; it does not own the generic build/publish/deploy control plane.

## Frozen shared dependencies

- shared workflow/contract: `rozkalnsandris/ops-workflows@e05ed760791a127c7c9628696806ef39c9fe329c`;
- generic trusted RPi5 deployer source: `rozkalnsandris/RPi5_main@ff20fcf64ba62c95e5f15eeb481c3c66bb5c9708`.

Production callers must keep the shared workflow reference pinned to the full immutable SHA. The tracking comment `# v1.0.0` is Renovate/human metadata only; the SHA is the security identity.

## Weather consumer identity

- manifest: `.simple-deploy.json`;
- caller: `.github/workflows/simple-deploy.yml`;
- image: `ghcr.io/rozkalnsandris/rozkalns_weather`;
- architecture: `linux/arm64`;
- target alias: `rozkalns-weather-public-rpi5`;
- Compose project/file/service: `rozkalns-weather-public` / `deploy/docker-compose.public.yml` / `weather`;
- liveness/readiness: `/health` / `/ready`;
- persistent volume: `weather_data`;
- pull profile: `public-anonymous-pull`;
- runtime mode: `public-only`;
- database startup mode: `require-existing`.

The caller has only `contents: read` and `packages: write`. It has no self-hosted runner, SSH, host credential, root/sudo command, Docker socket authority or arbitrary runtime input.

## Ordinary release after one-time cutover

```text
merged Weather main SHA
-> immutable-pinned shared SIMPLE-DEPLOY caller
-> GitHub-hosted ARM64 build
-> GHCR exact-SHA image + immutable digest
-> :production discovery pointer
-> generic RPi5 allowlisted reconciler
-> freeze exact digest for attempt
-> docker compose pull weather
-> docker compose up -d --wait --wait-timeout <bounded> weather
-> /health + /ready
-> exact digest/source receipt
```

The `:production` tag is discovery only. The generic RPi5 deployer overlays the `weather` service with the frozen `image@sha256:...` reference before mutation. A pointer advance during an attempt waits for the next reconciliation.

`deploy/docker-compose.public.yml` contains image declarations and no RPi5 source build. Bootstrap/check/job services remain separate operations. When one of those services is deliberately run, its separately reviewed operation must bind an exact image digest; the mutable production pointer is not a data-operation authorization.

## Activation boundary

Merging Weather source adoption may publish the caller-bound GHCR image/pointer on later `main` pushes, but it does **not** install or enable the generic host deployer and does not activate the Weather target on RPi5. The first host cutover remains one separate exact LIVE authorization binding the reviewed RPi5 source, host `rpi5`, Weather target, installed artifacts, registry/Compose identities, baseline and verification.

Before target activation, the cutover must verify that `ghcr.io/rozkalnsandris/rozkalns_weather` is actually anonymous-pullable with no registry credentials. GitHub Actions publication with `GITHUB_TOKEN` is expected to link/inherit from the public repository, but actual package visibility remains a GitHub Packages setting and must be verified rather than inferred. If anonymous pull fails because visibility/access differs, STOP: changing package visibility or activating `private-read-only` auth requires a separate exact owner authorization and is not an automatic fallback.

Until that cutover succeeds, existing production runtime state is not inferred from source. After successful cutover, ordinary already-classified `AUTO_DEPLOY_SAFE` application releases may use the fixed platform path without a fresh per-release LIVE approval.

## Sensitive operations remain separate

Ordinary SIMPLE-DEPLOY excludes database/schema/data mutation, destructive recovery, secrets/credentials/permissions, Cloudflare/DNS/network mutation, private-provider activation and unrelated host control. In particular, first schema initialization, public corpus bootstrap/backfill, recurring-ingest first activation when it changes scheduler state, WeatherNext/private-home activation and destructive recovery remain separately reviewed operations.

`DATABASE_INIT_MODE=require-existing` and `weather_data` persistence are invariants of the ordinary application release. Application replacement never implies SQLite migration, restore, delete or backfill.

## Legacy control-plane evidence

The historical Weather broker/registration/operator/`ops-workflows#46` queue/JIT/Composite LIVE files and validators are retained only as legacy audit/regression evidence for the earlier first-rollout design. They are **superseded for ordinary application releases** and must not be interpreted as current prerequisites for SIMPLE-DEPLOY. No v11/v12 successor of that Weather-specific control plane should be created.
