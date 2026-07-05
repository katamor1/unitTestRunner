#ifndef DEVICE_CONTROL_H
#define DEVICE_CONTROL_H

#define DEVICE_TABLE_COUNT 4
#define DEVICE_RAW_SAMPLE_COUNT 4
#define DEVICE_CHANNEL_COUNT 2
#define DEVICE_STATUS_OK 0
#define DEVICE_STATUS_FAULT -1
#define DEVICE_MODE_AUTO 1
#define DEVICE_MODE_MANUAL 2

typedef struct tagDeviceInput {
    int mode;
    int sample_count;
    int trim;
    int raw_samples[DEVICE_RAW_SAMPLE_COUNT];
} DeviceInput;

typedef struct tagDeviceOutput {
    int status;
    int selected_channel;
    int channels[DEVICE_CHANNEL_COUNT];
} DeviceOutput;

typedef struct tagDeviceRuntime {
    int status;
    int last_pwm;
    unsigned long last_update;
} DeviceRuntime;

typedef struct tagDeviceCalibration {
    int gain;
    int offset;
} DeviceCalibration;

typedef int (*DeviceStatusCallback)(int status);
typedef void (*DeviceFaultHook)(int status);

extern unsigned long g_system_tick;
extern int g_active_device;
extern DeviceRuntime g_device_table[DEVICE_TABLE_COUNT];
extern DeviceCalibration g_calibration;

int DeviceControl_Update(DeviceInput *input, DeviceOutput *out, int (*callback)(int status));
int DeviceControl_RunScheduler(void);
void DeviceControl_RegisterFaultHook(DeviceFaultHook hook);

#endif
