#include "device_control.h"

unsigned long g_system_tick = 0;
int g_active_device = 0;
DeviceRuntime g_device_table[DEVICE_TABLE_COUNT] = {
    {DEVICE_STATUS_OK, 0, 0},
    {DEVICE_STATUS_OK, 0, 0},
    {DEVICE_STATUS_OK, 0, 0},
    {DEVICE_STATUS_OK, 0, 0}
};
DeviceCalibration g_calibration = {1, 0};

void DeviceRuntime_Tick(void)
{
    g_system_tick++;
}
