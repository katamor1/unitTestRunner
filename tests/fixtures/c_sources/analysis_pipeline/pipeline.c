#define SENSOR_MIN 10
#define SENSOR_MAX 20
#define MODE_AUTO 1
#define MODE_MANUAL 2
#define SENSOR_FAIL -1
#define STATUS_READY 7

static int g_state;
extern int g_error;

static int Helper(int raw)
{
    return raw + 1;
}

int Control_Update(int mode, int sensor, int *out_value, char buffer[16])
{
    int normalized;
    int i;

    normalized = Helper(sensor);
    if (out_value == NULL) {
        return SENSOR_FAIL;
    }
    if (sensor < SENSOR_MIN || CheckLimit(sensor) == 0) {
        g_error = SENSOR_FAIL;
        return SENSOR_FAIL;
    }
    if (sensor >= SENSOR_MIN && sensor <= SENSOR_MAX) {
        *out_value = normalized;
        buffer[0] = 1;
    }
    switch (mode) {
    case MODE_AUTO:
        WritePort(&g_state, normalized);
        break;
    case MODE_MANUAL:
        for (i = 0; i < sensor; i++) {
            g_state += i;
        }
        break;
    default:
        return SENSOR_FAIL;
    }
    return g_state;
}

int __stdcall RegisterCallback(int (*callback)(int code), unsigned long count)
{
    return callback((int)count);
}

int OldStyle(value, out_value)
int value;
int *out_value;
{
    *out_value = value;
    return value;
}
