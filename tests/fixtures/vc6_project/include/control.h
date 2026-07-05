#ifndef CONTROL_H
#define CONTROL_H

#define SENSOR_MIN 10
#define SENSOR_MAX 100
#define SENSOR_FAIL -1
#define MODE_AUTO 1
#define MODE_MANUAL 2
#define OK 0
#define ERROR -1
#define ERR_LOW 10
#define ERR_HIGH 20

extern int g_error_code;

int ReadSensor(void);
void WriteOutput(int value);
int Control_Update(int mode, int sensor_value);
void Control_Reset(void);

#endif
