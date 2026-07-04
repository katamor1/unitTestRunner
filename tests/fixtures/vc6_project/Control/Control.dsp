# Microsoft Developer Studio Project File - Name="Control" - Package Owner=<4>
# Microsoft Developer Studio Generated Build File, Format Version 6.00

!IF "$(CFG)" == "Control - Win32 Debug"

# PROP BASE Use_MFC 0
# ADD BASE CPP /nologo /W3 /D "WIN32" /D "_DEBUG" /I "..\include" /FI "forced.h" /Yu"stdafx.h" /Fo"Debug/" /Fd"Debug/"
# ADD CPP /nologo /W3 /GX /D "WIN32" /D "_DEBUG" /D "CONTROL_FEATURE=1" /I "..\include" /I "$(LEGACY_SDK)\include" /FI "forced.h" /Yu"stdafx.h" /Fo"Debug/" /Fd"Debug/"

!ELSEIF "$(CFG)" == "Control - Win32 Release"

# ADD CPP /nologo /W3 /O2 /D "WIN32" /D "NDEBUG" /I "..\include" /Yc"stdafx.h" /Fo"Release/" /Fd"Release/"

!ENDIF

# Begin Target
# Name "Control - Win32 Debug"
# Name "Control - Win32 Release"

# Begin Group "Source Files"

# Begin Source File
SOURCE=..\src\control.c
# End Source File

# End Group

# Begin Group "Header Files"

# Begin Source File
SOURCE=..\include\control.h
# End Source File

# End Group

# End Target
