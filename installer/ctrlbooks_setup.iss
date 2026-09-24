; =====================================================================
; CtrlBooks - Inno Setup Installer Script (.iss)
; =====================================================================
; Generates production-grade Windows Client Setup Executable (setup.exe)
; - Installs files into C:\Program Files\CtrlBooks
; - Creates Start Menu & Desktop Shortcuts
; - Adds Windows Startup Auto-Launch registry key
; - Bundles app icon, background updater, and safe uninstaller cleanup
; =====================================================================

#define MyAppName "CtrlBooks"
#define MyAppVersion "1.0.2"
#define MyAppPublisher "CtrlBooks"
#define MyAppURL "https://ctrlbooks.com"
#define MyAppExeName "ctrlbooks.exe"

[Setup]
AppId={{8C7A1B6F-E99D-4E46-A013-BF3CF52CF033}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/support
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
LicenseFile=terms_and_conditions.txt
OutputDir=..\dist
OutputBaseFilename=CtrlBooks_Setup_v{#MyAppVersion}
SetupIconFile=..\apps\desktop_app\assets\app_icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "autostart"; Description: "Automatically launch CtrlBooks on Windows startup"; GroupDescription: "System Integration:"

[Dirs]
Name: "{app}\logs"; Permissions: users-modify
Name: "{app}\data"; Permissions: users-modify

[Files]
Source: "..\dist\ctrlbooks\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "CtrlBooks"; ValueData: """{app}\{#MyAppExeName}"" --minimized"; Tasks: autostart; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
Type: filesandordirs; Name: "{userappdata}\CtrlBooks"
Type: filesandordirs; Name: "{localappdata}\CtrlBooks"
