# Mac ARM publisher admission probe candidate (not a native build)

This independent metadata-only workflow reuses the reviewed Linux probe at
public commit `f361a4c1d27eab51d709ac28d686be953fb44c68`, tree
`e1f4c28da50c4854e5a5f3312d11b7147ca25239` (identical local parent
`31e543785adbed544a8d3e77f281cac99231d24b`). That Linux route failed; this is
not a retry presented as success or evidence that a Mac route will work.

Only new workflow `.github/workflows/ohos-mac-arm-publisher-probe.yml` is used.
Its push trigger requires exact branch
`checkpoint/madlink-ohos-api20-mac-arm-publisher-probe` AND its own workflow
path changed. It has `permissions: {}`, no checkout, actions, credentials,
secrets, uploads, installs or user-computer interaction. Other existing source,
Linux probe and native/receipt acceptance files remain unchanged.

The runner is GitHub-hosted `macos-15`, documented as ARM64 for public repos:
https://docs.github.com/en/actions/reference/runners/github-hosted-runners
Before any Python/network step, `/usr/bin/uname -s` must be Darwin and
`/usr/bin/uname -m` must be arm64. Otherwise emit only the fixed host failure
label and fail; the label alone is not treated as architecture proof.

The only network operations, direct HTTPS with certificate verification and
redirect/proxy fallback disabled, are:

- GET exact official URL
  `https://repo.huaweicloud.com/openharmony/os/6.0-Release/L2-SDK-MAC-M1-PUBLIC.tar.gz.sha256`
  with bounded 66-byte read to require precisely the locked 64 lowercase hex
  plus LF: `d4b0c942cbc8dfc7f28f49c0f33648f332d43c3a51399f2463655c2ef1f2c659`.
- HEAD exact same archive URL without `.sha256`, requiring Content-Length
  `1288449769`, status 200, identity encoding and archive MIME. It never reads
  the archive body. No SDK download, extraction, execution or terms acceptance.

The 15-second per-socket and two-minute whole-job bounds, fixed failure reasons,
no retries and no raw response/exception logging match the Linux reviewed logic.
Each workflow holds its single complete inline runtime source. No repository
helper is fetched or executed; local mocks load precisely that inline source.

Eight Mac-probe offline mock tests pass, including HTML/nonhex/extra bytes,
checksum mismatch, redirects, wrong length/type/status/encoding and exact
host guard/trigger/pins. The eight unchanged Linux-probe tests also pass;
YAML/embedded Bash syntax was checked. No live local publisher probe was run,
no owner Mac was used, and this candidate has not been pushed or run on GitHub.
A future PASS proves only this runner's metadata-route admission, not archive
integrity, native receipt, compiler/linker support or target execution.
