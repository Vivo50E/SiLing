#import <Cocoa/Cocoa.h>
#import <Sparkle/Sparkle.h>

// This helper owns Sparkle's UI; the host remains the Electron application.
@interface SiLingUpdateDelegate : NSObject <SPUUpdaterDelegate>
@end
@implementation SiLingUpdateDelegate
- (void)updater:(SPUUpdater *)updater didAbortWithError:(NSError *)error {
    // Do not print feed URLs, credentials or raw network errors.
    puts("{\"event\":\"error\"}"); fflush(stdout);
}
- (void)updater:(SPUUpdater *)updater didFindValidUpdate:(SUAppcastItem *)item {
    puts("{\"event\":\"available\"}"); fflush(stdout);
}
@end

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        if (argc != 3) return 2;
        NSBundle *host = [NSBundle bundleWithPath:[NSString stringWithUTF8String:argv[1]]];
        pid_t parent = (pid_t)strtol(argv[2], NULL, 10);
        if (!host || parent <= 1 || ![host objectForInfoDictionaryKey:@"SUPublicEDKey"]) return 2;
        [NSApplication sharedApplication];
        [NSApp setActivationPolicy:NSApplicationActivationPolicyAccessory];
        SiLingUpdateDelegate *delegate = [SiLingUpdateDelegate new];
        SPUStandardUserDriver *driver = [[SPUStandardUserDriver alloc] initWithHostBundle:host delegate:nil];
        SPUUpdater *updater = [[SPUUpdater alloc] initWithHostBundle:host applicationBundle:host userDriver:driver delegate:delegate];
        NSError *error = nil;
        if (![updater startUpdater:&error]) return 3;
        puts("{\"event\":\"ready\"}"); fflush(stdout);
        // Only fixed commands arrive over the private parent-child pipe. No URLs or paths.
        NSFileHandle *input = [NSFileHandle fileHandleWithStandardInput];
        __block NSMutableData *pending = [NSMutableData data];
        input.readabilityHandler = ^(NSFileHandle *handle) {
            NSData *data = handle.availableData;
            if (!data.length) { dispatch_async(dispatch_get_main_queue(), ^{ [NSApp terminate:nil]; }); return; }
            [pending appendData:data];
            if (pending.length > 1024) { exit(4); }
            const unsigned char *bytes = pending.bytes;
            while (pending.length) {
                NSUInteger index = 0;
                while (index < pending.length && bytes[index] != '\n') index++;
                if (index == pending.length) break;
                NSString *command = [[NSString alloc] initWithBytes:bytes length:index encoding:NSUTF8StringEncoding];
                [pending replaceBytesInRange:NSMakeRange(0, index + 1) withBytes:NULL length:0];
                bytes = pending.bytes;
                dispatch_async(dispatch_get_main_queue(), ^{
                    if ([command isEqualToString:@"check"]) {
                        [NSApp activateIgnoringOtherApps:YES];
                        [updater checkForUpdates];
                    }
                });
            }
        };
        [NSTimer scheduledTimerWithTimeInterval:2 repeats:YES block:^(NSTimer *timer) {
            if (getppid() != parent) [NSApp terminate:nil];
        }];
        [NSApp run];
        input.readabilityHandler = nil;
    }
    return 0;
}
