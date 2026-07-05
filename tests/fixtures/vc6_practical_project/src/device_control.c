#include "device_control.h"
#include "platform_io.h"

#define DEVICE_HISTORY_SIZE 8
#define DEVICE_DUTY_MIN 0
#define DEVICE_DUTY_MAX CONFIGURED_PWM_MAX
#define DEVICE_FAULT_LIMIT 3
#define DEVICE_DEFAULT_CHANNEL 0
#define ACTIVE_DEVICE g_active_device
#define RAW_SAMPLE(input, i) ((input)->raw_samples[(i)])
#define LIMIT_DUTY(value) (((value) > DEVICE_DUTY_MAX) ? DEVICE_DUTY_MAX : (((value) < DEVICE_DUTY_MIN) ? DEVICE_DUTY_MIN : (value)))

typedef struct tagControlState {
    int filtered;
    int fault_count;
    int last_status;
} ControlState;

static ControlState s_state = {0, 0, DEVICE_STATUS_OK};
static int s_history[DEVICE_HISTORY_SIZE];
static int s_history_pos;
static DeviceFaultHook s_fault_hook;

extern unsigned long g_system_tick;
extern int g_active_device;
extern DeviceRuntime g_device_table[DEVICE_TABLE_COUNT];
extern DeviceCalibration g_calibration;

static int ValidateInput(DeviceInput *input, DeviceOutput *out)
{
    if (input == 0 || out == 0) {
        return DEVICE_STATUS_FAULT;
    }
    if (input->sample_count <= 0 || input->sample_count > DEVICE_RAW_SAMPLE_COUNT) {
        return DEVICE_STATUS_FAULT;
    }
    if (g_active_device < 0 || g_active_device >= DEVICE_TABLE_COUNT) {
        return DEVICE_STATUS_FAULT;
    }
    return DEVICE_STATUS_OK;
}

static int NormalizeSample(DeviceInput *input)
{
    int i;
    int total;

    total = 0;
    for (i = 0; i < input->sample_count; i++) {
        total += RAW_SAMPLE(input, i);
    }
    if (input->sample_count == 0) {
        return 0;
    }
    return total / input->sample_count;
}

static int ComputeDuty(int normalized, int trim)
{
    int scaled;

    scaled = normalized + g_calibration.offset + trim;
    scaled = scaled * g_calibration.gain;
    return LIMIT_DUTY(scaled);
}

static void ApplyOutput(DeviceOutput *out, int duty)
{
    int channel;

    channel = DEVICE_DEFAULT_CHANNEL;
    out->selected_channel = channel;
    out->channels[channel] = duty;
    g_device_table[ACTIVE_DEVICE].status = DEVICE_STATUS_OK;
    g_device_table[ACTIVE_DEVICE].last_pwm = duty;
}

static void PushHistory(int value)
{
    s_history[s_history_pos] = value;
    s_history_pos++;
    if (s_history_pos >= DEVICE_HISTORY_SIZE) {
        s_history_pos = 0;
    }
}

void DeviceControl_RegisterFaultHook(DeviceFaultHook hook)
{
    s_fault_hook = hook;
}

int DeviceControl_Update(DeviceInput *input, DeviceOutput *out, int (*callback)(int status))
{
    int status;
    int normalized;
    int duty;
    int adc_value;
    int first_sample;

    status = ValidateInput(input, out);
    if (status != DEVICE_STATUS_OK) {
        s_state.fault_count++;
        if (s_fault_hook != 0) {
            s_fault_hook(status);
        }
        Audit_Record(ACTIVE_DEVICE, status);
        return status;
    }

    first_sample = RAW_SAMPLE(input, 0);
    adc_value = Platform_ReadAdc(ACTIVE_DEVICE);
    normalized = NormalizeSample(input);
    duty = ComputeDuty(normalized + adc_value, input->trim);
    duty = LIMIT_DUTY(duty);

    if (first_sample < 0 || duty <= DEVICE_DUTY_MIN) {
        status = DEVICE_STATUS_FAULT;
        s_state.fault_count++;
    } else {
        status = DEVICE_STATUS_OK;
        s_state.fault_count = 0;
    }

    s_state.filtered = normalized;
    s_state.last_status = status;
    s_history[s_history_pos] = s_state.filtered;
    g_device_table[ACTIVE_DEVICE].last_update = g_system_tick;

    if (g_active_device == ACTIVE_DEVICE && status == DEVICE_STATUS_OK) {
        ApplyOutput(out, duty);
        Platform_WritePwm(out->selected_channel, duty);
    }

    PushHistory(duty);
    Audit_Record(ACTIVE_DEVICE, status);

    if (callback != 0) {
        status = callback(status);
    }
    if (s_state.fault_count >= DEVICE_FAULT_LIMIT && s_fault_hook != 0) {
        s_fault_hook(status);
    }

    out->status = status;
    return status;
}

int DeviceControl_RunScheduler(void)
{
    DeviceInput input;
    DeviceOutput output;
    int i;

    input.mode = DEVICE_MODE_AUTO;
    input.sample_count = DEVICE_RAW_SAMPLE_COUNT;
    input.trim = 1;
    for (i = 0; i < DEVICE_RAW_SAMPLE_COUNT; i++) {
        input.raw_samples[i] = Platform_ReadAdc(i);
    }
    output.status = DEVICE_STATUS_FAULT;
    output.selected_channel = DEVICE_DEFAULT_CHANNEL;
    output.channels[0] = 0;
    output.channels[1] = 0;

    return DeviceControl_Update(&input, &output, 0);
}
