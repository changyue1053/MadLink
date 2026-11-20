# Publisher route admission probe (candidate, NOT RUN on GitHub)

This is separate from SDK acquisition, receipts and native builds. Existing
OpenHarmony native acceptance code and its `provenance_verified`/manifest
requirements are unchanged. A PASS means only that this runner can obtain the
exact pinned checksum and plausible archive headers from the official endpoint.
It does not authenticate a downloaded archive, establish inner package layout,
review terms, derive an approved native receipt, install or execute any SDK.

## Network and execution scope

The self-contained workflow runs on Ubuntu 24.04 with `permissions: {}`. It has
no checkout, third-party actions, credentials, secrets, artifacts, package body,
archive extraction or user-computer interaction. The workflow contains the sole executable probe implementation. Offline tests
load this exact inline Python into a module (without executing main) and supply
mock responses. No repository source is fetched or checked out at runtime.

Only these two HTTPS requests are permitted, directly without proxies/redirects:

1. GET `https://repo.huaweicloud.com/openharmony/os/6.0-Release/ohos-sdk-windows_linux-public.tar.gz.sha256`
   reads at most 66 bytes to validate exactly 64 lowercase hex + LF (65 bytes)
   against `a315834ac133625efc912bd078f3e2b2550868d04aef1b5aa4f9679c8b3c9d8e`.
2. HEAD the identical archive URL without `.sha256`, never reading its body.
   Require HTTP 200, identity content encoding, exact Content-Length 2487576829,
   and archive MIME application/gzip, application/x-gzip or application/octet-stream.

Default HTTPS certificate validation is retained. Each open/read has a 15-second
socket timeout; the whole job is bounded by a two-minute workflow timeout.
Mismatch, HTML, redirects, non-200, wrong/missing length/type, encoding and
network failures all fail closed with fixed reason labels. Server headers,
exception contents and received bodies are never echoed. No retries, mirrors,
alternative URLs or signature/terms bypasses are attempted.

## Exact trigger and frozen review boundary

The only trigger is `push` to the exact branch
`checkpoint/madlink-ohos-api20-publisher-probe`, AND only when
`.github/workflows/ohos-publisher-probe.yml` is among changed paths. No
workflow_dispatch, pull_request, schedule, main/all-branch or tag trigger exists.
No push or network execution is performed while preparing this candidate.
The workflow itself is the complete reviewed runtime code; there is no checkout,
external action or fetched helper to drift from it. A later branch publication
requires the coordinator's approval; this document does not publish anything.

Source baseline: public MadLink commit
`5279d61453e008f626eba6d63586632eb42cb39e`, tree
`65e732b1ca77d55f7819b81f164c693dd6746fd5`; local equivalent parent
`753503da92a8bc742dfec2c025297d4dca3c3e36` has that identical tree.
The candidate adds only this document, the scoped workflow and offline test.
Existing SDK receipts, native acceptance and other workflows remain unchanged.

Eight local offline mock tests passed: canonical bounded requests, HTML/nonhex/
extra bytes, checksum mismatch, redirect refusal, HEAD size/type failures,
encoding/status failures and single-inline-source and exact trigger constraints. These mocks do not
prove any live publisher reachability. Earlier cloud checks returned HTML and
remain negative evidence; no simulated PASS is recorded as a network result.
