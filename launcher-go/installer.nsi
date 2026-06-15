!include "MUI2.nsh"

Name "Nickets"
OutFile "NicketsSetup.exe"
InstallDir "$PROGRAMFILES\Nickets"
RequestExecutionLevel admin

!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

Section "Install"
  SetOutPath "$INSTDIR"
  File "nickets.exe"

  CreateDirectory "$SMPROGRAMS\Nickets"
  CreateShortcut "$SMPROGRAMS\Nickets\Nickets.lnk" "$INSTDIR\nickets.exe"
  CreateShortcut "$DESKTOP\Nickets.lnk" "$INSTDIR\nickets.exe"

  WriteUninstaller "$INSTDIR\uninstall.exe"
SectionEnd

Section "Uninstall"
  Delete "$INSTDIR\nickets.exe"
  Delete "$INSTDIR\uninstall.exe"
  Delete "$SMPROGRAMS\Nickets\Nickets.lnk"
  Delete "$DESKTOP\Nickets.lnk"
  RMDir "$SMPROGRAMS\Nickets"
  RMDir "$INSTDIR"
SectionEnd
