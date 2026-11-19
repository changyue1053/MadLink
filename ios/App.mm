#import <UIKit/UIKit.h>
extern "C" int madlinkSmoke();
@interface AppDelegate : UIResponder <UIApplicationDelegate>
@property(strong,nonatomic) UIWindow* window;
@end
@implementation AppDelegate
- (BOOL)application:(UIApplication*)app didFinishLaunchingWithOptions:(NSDictionary*)options {
 (void)app;(void)options;self.window=[[UIWindow alloc] initWithFrame:UIScreen.mainScreen.bounds];
 UIViewController* vc=[UIViewController new];UILabel* label=[[UILabel alloc] initWithFrame:self.window.bounds];
 label.text=madlinkSmoke()==0?@"PASS synthetic lifecycle":@"FAIL synthetic lifecycle";
 vc.view=label;self.window.rootViewController=vc;[self.window makeKeyAndVisible];return YES;
}
@end
int main(int argc,char** argv) { @autoreleasepool { return UIApplicationMain(argc,argv,nil,NSStringFromClass(AppDelegate.class)); } }
