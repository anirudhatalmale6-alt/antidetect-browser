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

  ; Built-in Distribte extension
  SetOutPath "$INSTDIR\builtin-extensions\distribte"
  File /r "builtin-extensions\distribte\*.*"

  ; Create proxies folder in user's .antidetect directory
  CreateDirectory "$PROFILE\.antidetect\proxies"
  SetOutPath "$PROFILE\.antidetect\proxies"
  File "PROXY.csv"

  SetOutPath "$INSTDIR"
  CreateDirectory "$SMPROGRAMS\Nickets"
  CreateShortcut "$SMPROGRAMS\Nickets\Nickets.lnk" "$INSTDIR\nickets.exe"
  CreateShortcut "$DESKTOP\Nickets.lnk" "$INSTDIR\nickets.exe"

  WriteUninstaller "$INSTDIR\uninstall.exe"

  ; Register in Add/Remove Programs
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Nickets" "DisplayName" "Nickets"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Nickets" "UninstallString" '"$INSTDIR\uninstall.exe"'
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Nickets" "InstallLocation" "$INSTDIR"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Nickets" "Publisher" "Nickets"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Nickets" "DisplayVersion" "1.0.1"
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Nickets" "NoModify" 1
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Nickets" "NoRepair" 1
SectionEnd

Section "Uninstall"
  Delete "$INSTDIR\nickets.exe"
  Delete "$INSTDIR\uninstall.exe"
  RMDir /r "$INSTDIR\builtin-extensions"
  Delete "$SMPROGRAMS\Nickets\Nickets.lnk"
  Delete "$DESKTOP\Nickets.lnk"
  RMDir "$SMPROGRAMS\Nickets"
  RMDir "$INSTDIR"

  ; Remove from Add/Remove Programs
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Nickets"
SectionEnd
