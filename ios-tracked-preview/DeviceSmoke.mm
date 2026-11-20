/* Link-only unsigned device probe using the existing App entry point. Not run. */
#import <MadLink/madlink_c.h>
#import <TargetConditionals.h>
#if !TARGET_OS_IOS || TARGET_OS_SIMULATOR || !defined(__arm64__)
#error "The independent link probe requires ARM64 iOS device compilation"
#endif
extern "C" int madlinkSmoke() {
    ml_config_v1 config{};
    ml_host_v1 host{};
    ml_client* client=nullptr;
    volatile ml_status first=ml_create_tracked_v1(&config,&host,1,&client);
    uint64_t id=0;
    volatile ml_status second=ml_send_tracked_v1(client,nullptr,0,100,&id);
    ml_completion_v1 output{};
    output.struct_size=sizeof(output);
    output.abi_version=ML_ABI_V1;
    volatile ml_status third=ml_next_completion_v1(client,&output);
    ml_destroy_v1(client);
    return static_cast<int>(first)+static_cast<int>(second)+static_cast<int>(third);
}
