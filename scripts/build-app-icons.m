// Deterministic macOS size/format conversion of the AI-generated master.
// clang -fobjc-arc -framework AppKit scripts/build-app-icons.m -o /tmp/siling-app-icons
// /tmp/siling-app-icons [repository-root]
#import <AppKit/AppKit.h>

int main(int argc, const char **argv) {
    @autoreleasepool {
        NSString *root = argc > 1 ? @(argv[1]) : NSFileManager.defaultManager.currentDirectoryPath;
        NSString *directory = [root stringByAppendingPathComponent:@"static/icons"];
        NSImage *image = [[NSImage alloc] initWithContentsOfFile:[directory stringByAppendingPathComponent:@"orchestrator-1024.png"]];
        if (!image) return 1;
        NSArray *names = @[@"orchestrator-192.png", @"orchestrator-512.png", @"orchestrator-maskable-512.png", @"apple-touch-icon.png"];
        NSArray *sizes = @[@192, @512, @512, @180];
        for (NSUInteger i = 0; i < names.count; i++) {
            NSInteger size = [sizes[i] integerValue];
            NSBitmapImageRep *bitmap = [[NSBitmapImageRep alloc] initWithBitmapDataPlanes:NULL pixelsWide:size pixelsHigh:size bitsPerSample:8 samplesPerPixel:4 hasAlpha:YES isPlanar:NO colorSpaceName:NSDeviceRGBColorSpace bytesPerRow:0 bitsPerPixel:0];
            [NSGraphicsContext saveGraphicsState];
            NSGraphicsContext.currentContext = [NSGraphicsContext graphicsContextWithBitmapImageRep:bitmap];
            NSGraphicsContext.currentContext.imageInterpolation = NSImageInterpolationHigh;
            NSRect rect = NSMakeRect(0, 0, size, size);
            [(i >= 2 ? [NSColor colorWithSRGBRed:13.0/255 green:17.0/255 blue:23.0/255 alpha:1] : NSColor.clearColor) setFill];
            NSRectFillUsingOperation(rect, NSCompositingOperationCopy);
            [image drawInRect:rect fromRect:NSZeroRect operation:NSCompositingOperationSourceOver fraction:1];
            [NSGraphicsContext restoreGraphicsState];
            NSData *png = [bitmap representationUsingType:NSBitmapImageFileTypePNG properties:@{}];
            if (![png writeToFile:[directory stringByAppendingPathComponent:names[i]] atomically:YES]) return 1;
        }
    }
    return 0;
}
