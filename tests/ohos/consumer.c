/* Link-only public C ABI probe. Never executed by this gate. */
#include <madlink_c.h>
_Static_assert(ML_ABI_V1 == 1u, "Expected public ABI v1");
ml_status madlink_ohos_link_probe(void) {
    ml_client *client = 0;
    ml_status result = ml_create_v1(0, 0, &client);
    result += ml_connect_v1(client, "synthetic-unused");
    result += ml_tick_v1(client);
    result += ml_send_v1(client, 0, 0, 0, 0);
    result += ml_cancel_v1(client, 0);
    result += ml_next_event_v1(client, 0);
    result += ml_close_v1(client);
    ml_destroy_v1(client);
    return result;
}
