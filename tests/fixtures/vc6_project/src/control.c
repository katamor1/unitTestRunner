#include "control.h"
#include <string.h>

static int g_control_state;
extern int g_error_code;

/* This comment contains fake syntax: int NotAFunction(void) { return 0; } */
static int Helper(int raw)
{
    return raw + 1;
}

int Control_Update(int mode, int sensor_value)
{
    int normalized;
    int i;
    const char *text;

    text = "fake { if (mode) return 1; }";
    normalized = Helper(sensor_value);

    if (sensor_value < SENSOR_MIN) {
        g_error_code = ERR_LOW;
        return ERROR;
    }

    if (sensor_value > SENSOR_MAX || ReadSensor() == SENSOR_FAIL) {
        g_error_code = ERR_HIGH;
        return ERROR;
    }

    switch (mode) {
    case MODE_AUTO:
        WriteOutput(normalized);
        break;
    case MODE_MANUAL:
        for (i = 0; i < 3; i++) {
            g_control_state += i;
        }
        break;
    default:
        return ERROR;
    }

    return OK;
}

void Control_Reset(void)
{
    g_control_state = 0;
}
