#define MyAppVersion GetEnv("EARCRAWLER_VERSION")
#ifndef MyAppVersion
  #error EARCRAWLER_VERSION not defined
#endif

[Setup]
AppId={{AF55D4E1-7A0F-4B45-9C36-3890B03A1F47}}
AppName=EarCrawler
AppVersion={#MyAppVersion}
DefaultDirName={pf}\EarCrawler
DefaultGroupName=EarCrawler
OutputDir=..\dist
OutputBaseFilename=earcrawler-setup-{#MyAppVersion}
#ifexist "packaging\\assets\\app.ico"
SetupIconFile=packaging\assets\app.ico
#endif
DisableProgramGroupPage=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "addpath"; Description: "Add EarCrawler to PATH"; GroupDescription: "Additional tasks"; Flags: unchecked

[Files]
Source: "..\dist\earctl-{#MyAppVersion}-win64.exe"; DestDir: "{app}"; DestName: "earctl.exe"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\EarCrawler CLI"; Filename: "{app}\earctl.exe"

[Registry]
Root: HKLM; Subkey: "SYSTEM\CurrentControlSet\Control\Session Manager\Environment"; ValueType: expandsz; ValueName: "Path"; ValueData: "{olddata};{app}"; Tasks: addpath; Flags: preservestringtype

[Run]
Filename: "{app}\README.md"; Description: "Open README"; Flags: postinstall shellexec skipifsilent nowait
