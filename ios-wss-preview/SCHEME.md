# Closed stock Xcode scheme route (preview)

Separate exact branch from the original explicit-receipt WSS attempt. The
installed two-slice C SDK archive, unsigned generic device app link, four exact
simulator cases and both independent WSS peer outcomes are still mandatory.
No production/default-build changes and no change to the prior explicit route.

Apple TN2339 describes scheme-based test-without-building as searching SYMROOT.
This candidate deliberately uses a different mechanism than executing a supplied
xctestrun. Pinned stock Xcode 26.2 and the exact, byte-pinned minimal project and
scheme are the only source of internal loader configuration. Paths and tool
environment are fresh and explicit; no caller-controlled environment, plans,
selectors, plugins, arguments, overrides or script phases are admitted.
Both build and launch use the same target/configuration, precise simulator UUID,
DerivedData and private SYMROOT. The canonical Xcode app must be Apple signed
under its exact identifier and designated identity, and the canonical signed
Developer xcodebuild must be the one resolved by stock xcrun. The original generated v1 xctestrun must name the
exact hosted products and have no selection/host override. It is moved completely
outside the project and DerivedData and fingerprinted as evidence, never provided
to Xcode. Its one observed opaque metadata field / future opaque non-path marker
values are not launch authority and are never copied to a command or plan.
Known values for loader paths remain exact, and additional possible injection
or non-inert values fail the evidence gate.

The App/test bundles and the fallback SYMROOT have a closed exact role
inventory. Optional standard typed dSYMs and byte-identical processing copies
of the installed simulator static archive cannot supply executable alternatives.
Both products are checked for Simulator ARM64 Mach-O, ad-hoc signature validity,
stock dependencies, rpaths and reviewed load command kinds before launch.
Embedded DYLD environment and unreviewed load commands are denied. The WSS XCTest also verifies its actual host/test
bundle identity inside the native ARM64 simulator process. Graph, generated
public CA header, receipt and product closure fingerprints must match before
and after execution. No key or binary artifacts are published. TLS validation
and the two host peer independent checks are unchanged.

This route has not yet been compiled or executed on Apple. In particular it
fails closed if stock Xcode emits a non-reviewed receipt launch shape, requires
the quarantined receipt to execute the scheme, generates another external receipt
in DerivedData, or differs in product/signature layout. Standalone portable
tests do not qualify any native runtime. See [Apple TN2339](https://developer.apple.com/library/archive/technotes/tn2339/_index.html).
