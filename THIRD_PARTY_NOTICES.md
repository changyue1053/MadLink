# Third-party boundaries

The root MIT LICENSE applies to independently written MadLink first-party source,
tests and documentation in this snapshot. It does not relicense external projects,
standards, system libraries, compilers or generated dependency artifacts.
No third-party implementation source, MadObs headers, binary dependency, build output,
test certificate/private key or raw test log is included in this repository.

This snapshot contains optional adapter source, but the default core does not
compile or install either adapter. No dependency or platform package is shipped
here.

## Optional libcurl WSS adapter

- curl/libcurl: copyright Daniel Stenberg and contributors; upstream `curl` license
  (MIT-inspired, not identical to MIT): https://curl.se/docs/copyright.html
- OpenSSL 3.x, used by the tested system libcurl: Apache License 2.0. Prior releases
  have different terms: https://openssl-library.org/source/license/index.html
- A system libcurl can bring additional dependencies with distinct licenses. The
  tested system build included, among others, GnuTLS in its dependency graph. This
  notice is not an exhaustive binary distribution SBOM. Review the actual resolved
  dependency versions, licensing, source/notice obligations and shipping method
  before distributing a binary bundle. These dependencies are not bundled here.

## Optional MadObs API-only adapter

Public API source: https://github.com/changyue1053/MadObs/tree/79fd8ced44a18bca574598ff683cd706ded16a60
The adapter was developed against this exact public revision's observer/privacy API.
The original API headers and their terms remain upstream, and are not vendored here.
No upstream licensing grant is inferred from public visibility, nor from MadLink's
MIT license. Confirm applicable MadObs permission/terms before redistributing its
headers, runtime or a bundle containing them. The test script requires separately
provided pinned API headers and does not download them automatically.

## Public standards and documentation

The optional transport refers to WebSocket RFC 6455, TLS
documentation and official libcurl API documentation. External documents retain their respective rights. This
snapshot does not include copies of those standards or upstream implementation code.
