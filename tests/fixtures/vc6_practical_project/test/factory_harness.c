#include "device_control.h"

static int FactoryCallback(int status)
{
    return status;
}

int main(void)
{
    DeviceInput input;
    DeviceOutput output;
    int i;

    input.mode = DEVICE_MODE_AUTO;
    input.sample_count = DEVICE_RAW_SAMPLE_COUNT;
    input.trim = 0;
    for (i = 0; i < DEVICE_RAW_SAMPLE_COUNT; i++) {
        input.raw_samples[i] = i + 1;
    }
    output.status = DEVICE_STATUS_FAULT;
    output.selected_channel = 0;
    output.channels[0] = 0;
    output.channels[1] = 0;

    return DeviceControl_Update(&input, &output, FactoryCallback);
}
