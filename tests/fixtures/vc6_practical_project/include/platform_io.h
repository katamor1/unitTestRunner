#ifndef PLATFORM_IO_H
#define PLATFORM_IO_H

int Platform_ReadAdc(int channel);
void Platform_WritePwm(int channel, int duty);
void Audit_Record(int device_index, int status);

#endif
