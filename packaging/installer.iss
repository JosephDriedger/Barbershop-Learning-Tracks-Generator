; Inno Setup script for BLT Music Generator.
;
;   ISCC.exe /DAppVersion=0.1.0 /DSourceDir=<built package folder> /DOutputDir=<folder> packaging\installer.iss
;
; Per-user by default (no administrator rights, installs under %LOCALAPPDATA%\Programs); the user
; can choose "for all users" in the first dialog. The installer never touches the user's voicebanks,
; generated tracks or preferences: those live outside the program folder and are not listed here.
; The installer is NOT code-signed unless a signing tool is configured (see docs/m12-packaging.md),
; so Windows SmartScreen will warn about it.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceDir
  #error SourceDir (the built package folder) must be defined
#endif
#ifndef OutputDir
  #define OutputDir "."
#endif

#define AppName "BLT Music Generator"
#define AppExe "BLT Music Generator.exe"
#define DataDir "{localappdata}\BarbershopLearningTracks"

[Setup]
; Never change AppId: it is what makes a new version replace the old one in place.
AppId={{7A3B1E52-4C8D-4F6A-9B21-5D0E8C6F3A17}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Joseph Driedger
VersionInfoVersion={#AppVersion}
VersionInfoDescription={#AppName} setup
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
SetupIconFile={#SourcePath}\blt.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
LicenseFile={#SourceDir}\LICENSE.txt
OutputDir={#OutputDir}
OutputBaseFilename=BLT-Music-Generator-{#AppVersion}-Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
ChangesAssociations=no
UsePreviousAppDir=yes
#ifdef SignToolName
SignTool={#SignToolName}
SignedUninstaller=yes
#endif

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; Flags: unchecked

[InstallDelete]
; Everything below is program-owned and replaced wholesale on upgrade, so files that a newer version
; no longer ships do not linger. User data is elsewhere and is not touched.
Type: filesandordirs; Name: "{app}\_internal"
Type: filesandordirs; Name: "{app}\host"
Type: filesandordirs; Name: "{app}\licenses"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Third-party notices"; Filename: "{app}\NOTICES.txt"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Start {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Program-owned folders (anything the program wrote into them goes too).
Type: filesandordirs; Name: "{app}\_internal"
Type: filesandordirs; Name: "{app}\host"
Type: filesandordirs; Name: "{app}\licenses"
; Private, reproducible working data of this program. NOT the user's voicebanks ("singers"),
; generated tracks ("outputs") or settings, which stay.
Type: filesandordirs; Name: "{#DataDir}\runtime"
Type: filesandordirs; Name: "{#DataDir}\staging"
Type: filesandordirs; Name: "{#DataDir}\Cache"

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usDone) and (not UninstallSilent) then
    MsgBox('{#AppName} was removed.' + #13#10#13#10 +
      'Your voicebanks, generated tracks and settings were left in place. ' +
      'They are in %LOCALAPPDATA%\BarbershopLearningTracks and can be deleted by hand.',
      mbInformation, MB_OK);
end;
