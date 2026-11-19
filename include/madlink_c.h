#ifndef MADLINK_C_H
#define MADLINK_C_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* Versioned prototype ABI. No C++ types or allocator ownership cross this boundary. */
#define ML_ABI_V1 1u
typedef struct ml_client ml_client;
typedef int32_t ml_status;
enum { ML_OK=0, ML_INVALID_STATE=1, ML_INVALID_CONFIG=2, ML_QUEUE_FULL=3,
       ML_TIMEOUT=4, ML_TRANSPORT_ERROR=5, ML_CANCELLED=6,
       ML_INVALID_ARGUMENT=100, ML_ABI_MISMATCH=101, ML_OUT_OF_MEMORY=102,
       ML_INTERNAL_ERROR=103, ML_POISONED=104, ML_EMPTY=105, ML_NOT_FOUND=106 };
enum { ML_IDLE=0, ML_CONNECTING=1, ML_CONNECTED=2, ML_BACKOFF=3, ML_CLOSED=4 };
enum { ML_EVENT_STATE=0, ML_EVENT_RECEIVED=1, ML_EVENT_WRITTEN=2, ML_EVENT_FAILED=3 };
enum { ML_WIRE_CONNECTED=0, ML_WIRE_RECEIVED=1, ML_WIRE_DISCONNECTED=2 };
enum { ML_WRITE_ACCEPTED=0, ML_WRITE_BLOCKED=1, ML_WRITE_FAILED=2 };
typedef struct ml_wire_event_v1 {
    uint32_t kind;
    uint64_t generation;
    const uint8_t* data;
    uint64_t data_size;
} ml_wire_event_v1;
typedef struct ml_host_v1 {
    uint32_t struct_size, abi_version;
    void* user;
    void (*connect)(void*, const char*, uint64_t);
    void (*close)(void*);
    /* 1=event, 0=none, -1=transport failure. Data lives until next host call. */
    int32_t (*poll)(void*, ml_wire_event_v1*);
    int32_t (*write)(void*, const uint8_t*, uint64_t);
    uint64_t (*now_ms)(void*);
    uint64_t (*random)(void*);
} ml_host_v1;
typedef struct ml_config_v1 {
    uint32_t struct_size, abi_version;
    uint64_t max_messages, max_bytes, max_events;
    uint64_t connect_timeout_ms, retry_base_ms, retry_cap_ms;
    uint32_t max_retries;
} ml_config_v1;
typedef struct ml_event_v1 {
    uint32_t struct_size, abi_version;
    uint32_t kind, state;
    ml_status error;
    uint64_t operation;
    const uint8_t* data;
    uint64_t data_size;
} ml_event_v1;
/* All calls and host callbacks are synchronous, owner-thread-only, non-reentrant.
 * Host callbacks must not throw. Host/user storage outlives handle destruction.
 * No stale/fabricated handles; destroy(NULL) is safe, double destroy is not.
 * Event bytes are borrowed until next_event or destroy (copy before either).
 * OOM/internal errors poison the handle: destroy it; do not retry operations.
 * A failing tick may already have accepted writes: never infer safe replay. */
ml_status ml_create_v1(const ml_config_v1*, const ml_host_v1*, ml_client**);
ml_status ml_connect_v1(ml_client*, const char* endpoint);
ml_status ml_send_v1(ml_client*, const uint8_t*, uint64_t size, uint64_t deadline_ms, uint64_t* operation);
ml_status ml_tick_v1(ml_client*);
ml_status ml_cancel_v1(ml_client*, uint64_t operation);
ml_status ml_close_v1(ml_client*);
ml_status ml_next_event_v1(ml_client*, ml_event_v1*);
void ml_destroy_v1(ml_client*);
#ifdef __cplusplus
}
#endif
#endif
