; KTRT 安装脚本（Inno Setup 6.3+）
; 用法：
;   ISCC.exe /DKTRT_FLAVOR=full KTRT.iss   完整版（含 GRE 词库）
;   ISCC.exe /DKTRT_FLAVOR=lite KTRT.iss   纯净版（不含词库）

#ifndef KTRT_FLAVOR
  #define KTRT_FLAVOR "full"
#endif

#if KTRT_FLAVOR == "full"
  #define APP_SRC "..\dist\KTRT-full"
  #define APP_EXE "KTRT-full.exe"
  #define OUT_BASE "KTRTSetup"
#else
  #define APP_SRC "..\dist\KTRT-lite"
  #define APP_EXE "KTRT-lite.exe"
  #define OUT_BASE "KTRTSetup-lite"
#endif

#define APP_VERSION "0.1.1"
#define APP_NAME "KillTimeRecitationTool"

[Setup]
AppId={{8F4B9C3E-5A2D-4E7B-9C1A-001122334455}
AppName={#APP_NAME}
AppVersion={#APP_VERSION}
AppPublisher=HoweyYueng
AppPublisherURL=https://github.com/HoweyYang/KTRT
DefaultDirName={autopf}\KTRT
DefaultGroupName=KTRT
UninstallDisplayIcon={app}\{#APP_EXE}
OutputDir=..\release
OutputBaseFilename={#OUT_BASE}-{#APP_VERSION}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
SetupIconFile=..\logo.ico

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务："

[Files]
Source: "{#APP_SRC}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs

[Icons]
Name: "{autodesktop}\KTRT"; Filename: "{app}\{#APP_EXE}"; IconFilename: "{app}\{#APP_EXE}"; Tasks: desktopicon
Name: "{autoprograms}\KTRT"; Filename: "{app}\{#APP_EXE}"

[Run]
Filename: "{app}\{#APP_EXE}"; Description: "立即启动 KTRT"; Flags: nowait postinstall skipifsilent

