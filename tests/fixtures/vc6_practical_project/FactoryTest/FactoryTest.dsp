# Microsoft Developer Studio Project File - Name="FactoryTest" - Package Owner=<4>
# Microsoft Developer Studio Generated Build File, Format Version 6.00

# TARGTYPE "Win32 (x86) Console Application" 0x0103

!IF "$(CFG)" == "FactoryTest - Win32 Debug"

# PROP BASE Use_MFC 0
# ADD BASE CPP /nologo /W3 /Gm /GX /ZI /Od /D "WIN32" /D "_DEBUG" /D "_CONSOLE" /MLd /YX /FD /GZ /c
# ADD CPP /nologo /W3 /Gm /GX /ZI /Od /D "WIN32" /D "_DEBUG" /D "_CONSOLE" /D "FACTORY_TEST=1" /I "..\include" /FI"config_alias.h" /Yu"stdafx.h" /MDd /Fo"Debug/" /Fd"Debug/" /FD /GZ /c

!ELSEIF "$(CFG)" == "FactoryTest - Win32 Release"

# PROP BASE Use_MFC 0
# ADD BASE CPP /nologo /W3 /GX /O2 /D "WIN32" /D "NDEBUG" /D "_CONSOLE" /ML /YX /FD /c
# ADD CPP /nologo /W3 /GX /O2 /D "WIN32" /D "NDEBUG" /D "_CONSOLE" /D "FACTORY_TEST=1" /I "..\include" /FI"config_alias.h" /Yu"stdafx.h" /MD /Fo"Release/" /Fd"Release/" /FD /c

!ENDIF

# Begin Target
# Name "FactoryTest - Win32 Debug"
# Name "FactoryTest - Win32 Release"

# Begin Group "Source Files"

# Begin Source File
SOURCE=..\src\device_control.c
# End Source File

# Begin Source File
SOURCE=..\src\device_runtime.c
# End Source File

# Begin Source File
SOURCE=..\src\platform_io.c
# End Source File

# Begin Source File
SOURCE=..\test\factory_harness.c
# End Source File

# End Group

# Begin Group "Header Files"

# Begin Source File
SOURCE=..\include\config_alias.h
# End Source File

# Begin Source File
SOURCE=..\include\device_control.h
# End Source File

# Begin Source File
SOURCE=..\include\platform_io.h
# End Source File

# Begin Source File
SOURCE=..\include\stdafx.h
# End Source File

# End Group

# End Target
