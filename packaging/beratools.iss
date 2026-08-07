#define MyAppVersion GetEnv('APP_VERSION')
#if MyAppVersion == ""
#define MyAppVersion "0.0.0"
#endif

[Setup]
AppName=BERA Tools
WizardImageFile=..\beratools\gui\assets\BERA_WizardImage.png
AppVersion={#MyAppVersion}
VersionInfoVersion={#MyAppVersion}
VersionInfoProductName=BERA Tools
VersionInfoProductVersion={#MyAppVersion}
VersionInfoProductTextVersion={#MyAppVersion}
DefaultDirName={commonpf}\BERA Tools
DefaultGroupName=BERA Tools
OutputDir=dist
OutputBaseFilename=beratools-installer-{#MyAppVersion}
AllowNoIcons=yes
SetupIconFile=..\beratools\gui\assets\BERALogo.ico
UninstallDisplayIcon={app}\BERALogo.ico

[Files]
Source: "..\beratools\gui\assets\BERALogo.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "build\beratools.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "build\python\*"; DestDir: "{app}\python"; Flags: recursesubdirs ignoreversion
Source: "build\beratools\*"; DestDir: "{app}\beratools"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{commondesktop}\BERA Tools"; Filename: "{app}\beratools.exe"; WorkingDir: "{app}"; IconFilename: "{app}\BERALogo.ico"
Name: "{group}\BERA Tools"; Filename: "{app}\beratools.exe"; WorkingDir: "{app}"; IconFilename: "{app}\BERALogo.ico"

[Run]
Filename: "{app}\beratools.exe"; Description: "Launch BERA Tools"; Flags: nowait postinstall skipifsilent
