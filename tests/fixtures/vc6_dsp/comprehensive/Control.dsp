# Microsoft Developer Studio Project File - Name="Control" - Package Owner=<4>
# Microsoft Developer Studio Generated Build File, Format Version 6.00

# TARGTYPE "Win32 (x86) Console Application" 0x0103

!IF "$(CFG)" == "Control - Win32 Release"

# ADD BASE CPP /nologo /W3 /GX /O2 /D "WIN32" /D "NDEBUG" /D "_CONSOLE" /ML /YX /FD /c
# ADD CPP /nologo /W4 /GX /O2 /I ".\include" /D "WIN32" /D "NDEBUG" /D "_CONSOLE" /MD /Yc"stdafx.h" /FD /c

!ELSEIF "$(CFG)" == "Control - Win32 Debug"

# ADD BASE CPP /nologo /W3 /Gm /GX /ZI /Od /D "WIN32" /D "_DEBUG" /D "_CONSOLE" /MLd /YX /FD /GZ /c
# ADD CPP /nologo /W3 /Gm /GX /ZI /Od /I ".\include" /I"..\shared include" /I "$(LEGACY_SDK)\include" /D "WIN32" /D "_DEBUG" /D "SIZE=10" /DDEBUG_FLAG /FI"config.h" /Yu"stdafx.h" /MDd /FD /GZ /c

!ENDIF

# Begin Target
# Name "Control - Win32 Release"
# Name "Control - Win32 Debug"

# Begin Group "Source Files"

# Begin Source File
SOURCE=.\src\control.c
# End Source File

# Begin Source File
SOURCE=.\src\helper.cpp
# End Source File

# End Group

# Begin Group "Header Files"

# Begin Source File
SOURCE=.\include\control.h
# End Source File

# End Group

# Begin Group "Resource Files"

# Begin Source File
SOURCE=.\res\control.rc
# End Source File

# End Group

# Begin Source File
SOURCE=.\missing\absent.c
# End Source File

# End Target
