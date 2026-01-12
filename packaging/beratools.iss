#define MyAppVersion GetEnv('APP_VERSION')
#if MyAppVersion == ""
#define MyAppVersion "0.0.0"
#endif

[Setup]
AppName=BERA Tools
AppVersion={#MyAppVersion}
DefaultDirName={pf}\BERA Tools
DefaultGroupName=BERA Tools
OutputDir=dist
OutputBaseFilename=beratools-installer-{#MyAppVersion}
AllowNoIcons=yes
SetupIconFile=beratools\gui\assets\BERALogo.ico

[Files]
Source: "build\beratools.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "build\python\*"; DestDir: "{app}\python"; Flags: recursesubdirs ignoreversion
Source: "build\beratools\*"; DestDir: "{app}\beratools"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{commondesktop}\BERA Tools"; Filename: "{app}\beratools.exe"; WorkingDir: "{app}"
Name: "{group}\BERA Tools"; Filename: "{app}\beratools.exe"; WorkingDir: "{app}"

[Run]
Filename: "{app}\beratools.exe"; Description: "Launch BERA Tools"; Flags: nowait postinstall skipifsilent
