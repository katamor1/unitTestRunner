#include "platform_io.h"

static int s_last_pwm_channel;
static int s_last_pwm_duty;
static int s_last_audit_device;
static int s_last_audit_status;

int Platform_ReadAdc(int channel)
{
    return channel + 10;
}

void Platform_WritePwm(int channel, int duty)
{
    s_last_pwm_channel = channel;
    s_last_pwm_duty = duty;
}

void Audit_Record(int device_index, int status)
{
    s_last_audit_device = device_index;
    s_last_audit_status = status;
}
