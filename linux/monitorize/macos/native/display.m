// SPDX-License-Identifier: GPL-3.0-only
// CGVirtualDisplay is a private WindowServer API: availability is checked at runtime.
#import <AppKit/AppKit.h>
#import <CoreGraphics/CoreGraphics.h>
#import <objc/runtime.h>
#import <dispatch/dispatch.h>
#import <signal.h>
#import <unistd.h>
#import <errno.h>
#import <stdlib.h>
#import <string.h>

@interface CGVirtualDisplayMode : NSObject
- (instancetype)initWithWidth:(NSUInteger)width height:(NSUInteger)height refreshRate:(double)rate;
@end
@interface CGVirtualDisplaySettings : NSObject
@property(nonatomic) unsigned int hiDPI;
@property(nonatomic, retain) NSArray *modes;
@end
@interface CGVirtualDisplayDescriptor : NSObject
@property(nonatomic, retain) NSString *name;
@property(nonatomic) unsigned int maxPixelsWide;
@property(nonatomic) unsigned int maxPixelsHigh;
@property(nonatomic) unsigned int vendorID;
@property(nonatomic) unsigned int productID;
@property(nonatomic) unsigned int serialNum;
@property(nonatomic) CGSize sizeInMillimeters;
@property(nonatomic) CGPoint redPrimary;
@property(nonatomic) CGPoint greenPrimary;
@property(nonatomic) CGPoint bluePrimary;
@property(nonatomic) CGPoint whitePoint;
@property(nonatomic, retain) dispatch_queue_t queue;
@end
@interface CGVirtualDisplay : NSObject
- (instancetype)initWithDescriptor:(CGVirtualDisplayDescriptor *)descriptor;
- (BOOL)applySettings:(CGVirtualDisplaySettings *)settings;
@property(nonatomic, readonly) unsigned int displayID;
@end

static void emit(id object) {
    NSData *data = [NSJSONSerialization dataWithJSONObject:object options:0 error:nil];
    fwrite(data.bytes, 1, data.length, stdout);
    fputc('\n', stdout);
    fflush(stdout);
}
static BOOL number(const char *text, long minimum, long maximum, long *value) {
    char *end; errno = 0;
    *value = strtol(text, &end, 10);
    return !errno && end != text && !*end && *value >= minimum && *value <= maximum;
}
int main(int argc, const char *argv[]) {
    @autoreleasepool {
        if (argc == 2 && strcmp(argv[1], "--list") == 0) {
            uint32_t count = 0;
            CGError error = CGGetOnlineDisplayList(0, NULL, &count);
            if (error != kCGErrorSuccess) return 2;
            CGDirectDisplayID *ids = calloc(count ? count : 1, sizeof(*ids));
            error = CGGetOnlineDisplayList(count, ids, &count);
            if (error != kCGErrorSuccess) { free(ids); return 2; }
            NSMutableArray *result = [NSMutableArray array];
            for (uint32_t i = 0; i < count; i++) {
                [result addObject:@{@"id": @(ids[i]), @"width": @(CGDisplayPixelsWide(ids[i])),
                    @"height": @(CGDisplayPixelsHigh(ids[i])), @"main": @(ids[i] == CGMainDisplayID())}];
            }
            free(ids); emit(result); return 0;
        }
        long width, height, rate, slot;
        if (argc != 5 || !number(argv[1], 640, 7680, &width) ||
            !number(argv[2], 480, 4320, &height) || !number(argv[3], 24, 120, &rate) ||
            !number(argv[4], 1, 2, &slot)) {
            fprintf(stderr, "Usage: monitorize-display WIDTH HEIGHT HZ SLOT | --list\n"); return 2;
        }
        Class descriptorClass = NSClassFromString(@"CGVirtualDisplayDescriptor");
        Class displayClass = NSClassFromString(@"CGVirtualDisplay");
        Class settingsClass = NSClassFromString(@"CGVirtualDisplaySettings");
        Class modeClass = NSClassFromString(@"CGVirtualDisplayMode");
        if (!descriptorClass || !displayClass || !settingsClass || !modeClass) {
            fprintf(stderr, "This macOS version does not expose CGVirtualDisplay.\n"); return 3;
        }
        CGVirtualDisplayDescriptor *descriptor = [descriptorClass new];
        descriptor.name = [NSString stringWithFormat:@"Monitorize %ld", slot];
        descriptor.maxPixelsWide = (unsigned int)width;
        descriptor.maxPixelsHigh = (unsigned int)height;
        descriptor.vendorID = 0x4D5A; descriptor.productID = 1;
        descriptor.serialNum = (unsigned int)slot;
        descriptor.sizeInMillimeters = CGSizeMake(width * 25.4 / 96, height * 25.4 / 96);
        descriptor.redPrimary = CGPointMake(0.64, 0.33);
        descriptor.greenPrimary = CGPointMake(0.30, 0.60);
        descriptor.bluePrimary = CGPointMake(0.15, 0.06);
        descriptor.whitePoint = CGPointMake(0.3127, 0.3290);
        descriptor.queue = dispatch_get_main_queue();
        __block CGVirtualDisplay *display = [[displayClass alloc] initWithDescriptor:descriptor];
        CGVirtualDisplaySettings *settings = [settingsClass new];
        settings.hiDPI = 0;
        settings.modes = @[[[modeClass alloc] initWithWidth:width height:height refreshRate:rate]];
        if (!display || ![display applySettings:settings]) {
            fprintf(stderr, "WindowServer rejected the virtual display. Run inside a logged-in desktop session.\n"); return 4;
        }
        // Lifetime follows stdin, so a crashing GUI does not leave orphan displays.
        dispatch_source_t input = dispatch_source_create(DISPATCH_SOURCE_TYPE_READ, STDIN_FILENO, 0, dispatch_get_main_queue());
        dispatch_source_set_event_handler(input, ^{
            char buffer[256];
            if (read(STDIN_FILENO, buffer, sizeof(buffer)) <= 0) { display = nil; exit(0); }
        });
        dispatch_resume(input);
        signal(SIGTERM, SIG_IGN); signal(SIGINT, SIG_IGN);
        dispatch_source_t term = dispatch_source_create(DISPATCH_SOURCE_TYPE_SIGNAL, SIGTERM, 0, dispatch_get_main_queue());
        dispatch_source_t interrupt = dispatch_source_create(DISPATCH_SOURCE_TYPE_SIGNAL, SIGINT, 0, dispatch_get_main_queue());
        dispatch_source_set_event_handler(term, ^{ display = nil; exit(0); });
        dispatch_source_set_event_handler(interrupt, ^{ display = nil; exit(0); });
        dispatch_resume(term); dispatch_resume(interrupt);
        emit(@{@"id": @(display.displayID), @"width": @(width), @"height": @(height)});
        [[NSRunLoop currentRunLoop] run];
    }
    return 0;
}
