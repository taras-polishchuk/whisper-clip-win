#define AppId "{{8C44E6B2-8A1B-4B8C-A1E7-2B0B9EBE0E31}"

#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

#ifndef AppPublisher
  #define AppPublisher "WhisperClip"
#endif

#ifndef AppDisplayName
  #define AppDisplayName "WhisperClip"
#endif

#ifndef AppExeName
  #define AppExeName "WhisperClip"
#endif

#ifndef AppDescription
  #define AppDescription "Tray-based Windows speech-to-text assistant with faster-whisper and DirectML backends."
#endif

#ifndef SourceDir
  #define SourceDir "dist\\WhisperClip"
#endif

#ifndef ReleaseDir
  #define ReleaseDir "release"
#endif

[Setup]
AppId={#AppId}
AppName={#AppDisplayName}
AppVersion={#AppVersion}
AppVerName={#AppDisplayName} {#AppVersion}
AppPublisher={#AppPublisher}
AppComments={#AppDescription}
DefaultDirName={localappdata}\Programs\{#AppDisplayName}
DefaultGroupName={#AppDisplayName}
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#AppExeName}.exe
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
Compression=lzma2
SolidCompression=yes
SetupIconFile=assets\icons\whisperclip.ico
WizardStyle=modern
SetupLogging=yes
CloseApplications=yes
RestartApplications=no
AppMutex=WhisperClipMutex
OutputDir={#ReleaseDir}
OutputBaseFilename={#AppExeName}-Setup-{#AppVersion}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "{#SourceDir}\\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppDisplayName}"; Filename: "{app}\{#AppExeName}.exe"
Name: "{autodesktop}\{#AppDisplayName}"; Filename: "{app}\{#AppExeName}.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}.exe"; Description: "Launch {#AppDisplayName}"; Flags: nowait postinstall skipifsilent