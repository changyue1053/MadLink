#import <XCTest/XCTest.h>
#import <TargetConditionals.h>
#if !TARGET_OS_IOS || !TARGET_OS_SIMULATOR || !defined(__arm64__)
#error "Tracked acceptance requires an ARM64 iOS simulator"
#endif
extern "C" int madlinkTrackedAcceptance(void);

@interface MadLinkTrackedTests : XCTestCase
@end
@implementation MadLinkTrackedTests
- (void)testInstalledTrackedCompletions {
    XCTAssertEqual(madlinkTrackedAcceptance(), 0);
}
@end
