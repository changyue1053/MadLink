#import <XCTest/XCTest.h>
extern "C" int madlinkSmoke();
@interface MadLinkTests : XCTestCase
@end
@implementation MadLinkTests
- (void)testSyntheticLifecycle { XCTAssertEqual(madlinkSmoke(),0); }
@end
