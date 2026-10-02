// Isolated test driver: auto-accept updates in fixture bundles only. Never packaged.
#import <Cocoa/Cocoa.h>
#import <Sparkle/Sparkle.h>
@interface TestDriver : NSObject <SPUUserDriver, SPUUpdaterDelegate>
@end
@implementation TestDriver
- (void)showUpdatePermissionRequest:(SPUUpdatePermissionRequest *)request reply:(void (^)(SUUpdatePermissionResponse *))reply {
    reply([[SUUpdatePermissionResponse alloc] initWithAutomaticUpdateChecks:NO sendSystemProfile:NO]);
}
- (void)showUserInitiatedUpdateCheckWithCancellation:(void (^)(void))cancel {}
- (void)showUpdateFoundWithAppcastItem:(SUAppcastItem *)item state:(SPUUserUpdateState *)state reply:(void (^)(SPUUserUpdateChoice))reply { reply(SPUUserUpdateChoiceInstall); }
- (void)showUpdateReleaseNotesWithDownloadData:(SPUDownloadData *)data {}
- (void)showUpdateReleaseNotesFailedToDownloadWithError:(NSError *)error {}
- (void)showUpdateNotFoundWithError:(NSError *)error acknowledgement:(void (^)(void))ack { ack(); exit(3); }
- (void)showUpdaterError:(NSError *)error acknowledgement:(void (^)(void))ack { NSLog(@"Fixture update error: %@", error); ack(); exit(2); }
- (void)showDownloadInitiatedWithCancellation:(void (^)(void))cancel {}
- (void)showDownloadDidReceiveExpectedContentLength:(uint64_t)size {}
- (void)showDownloadDidReceiveDataOfLength:(uint64_t)size {}
- (void)showDownloadDidStartExtractingUpdate {}
- (void)showExtractionReceivedProgress:(double)progress {}
- (void)showReadyToInstallAndRelaunch:(void (^)(SPUUserUpdateChoice))reply { reply(SPUUserUpdateChoiceInstall); }
- (void)showInstallingUpdateWithApplicationTerminated:(BOOL)terminated retryTerminatingApplication:(void (^)(void))retry {}
- (void)showUpdateInstalledAndRelaunched:(BOOL)relaunched acknowledgement:(void (^)(void))ack { puts(relaunched ? "RELAUNCHED" : "INSTALLED"); fflush(stdout); ack(); exit(0); }
- (void)dismissUpdateInstallation {}
- (void)updater:(SPUUpdater *)updater didFinishUpdateCycleForUpdateCheck:(SPUUpdateCheck)check error:(NSError *)error { if (!error) exit(0); }
@end
int main(int argc, const char *argv[]) {
    @autoreleasepool {
        if (argc != 2) return 4;
        NSBundle *host = [NSBundle bundleWithPath:[NSString stringWithUTF8String:argv[1]]];
        if (![[host bundleIdentifier] hasPrefix:@"com.vivo50e.siling.fixture."]) return 4;
        [NSApplication sharedApplication];
        TestDriver *driver = [TestDriver new];
        SPUUpdater *updater = [[SPUUpdater alloc] initWithHostBundle:host applicationBundle:host userDriver:driver delegate:driver];
        NSError *error = nil;
        if (![updater startUpdater:&error]) { NSLog(@"Fixture start failed: %@", error); return 5; }
        [updater checkForUpdates];
        [NSApp run];
    }
}
