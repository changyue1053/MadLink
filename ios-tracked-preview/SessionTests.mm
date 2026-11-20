#import <XCTest/XCTest.h>
#import <TargetConditionals.h>
#if !TARGET_OS_IOS || !TARGET_OS_SIMULATOR || !defined(__arm64__)
#error "This acceptance test must compile for an ARM64 iOS simulator"
#endif
extern "C" int madlinkSessionAcceptance(void);

@interface MadLinkSessionTests : XCTestCase
@end

@implementation MadLinkSessionTests
- (void)testInstalledSessionRecovery32Cycles {
    XCTAssertEqual(madlinkSessionAcceptance(), 0);
}
@end
