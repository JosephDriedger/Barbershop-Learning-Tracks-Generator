; Inno Setup script for BLT Music Generator.
;
;   ISCC.exe /DAppVersion=1.0.0 /DSourceDir=<built package folder> /DOutputDir=<folder> packaging\installer.iss
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

; The Microsoft Visual C++ runtime is NOT shipped (Microsoft allows redistributing it only to licensed
; Visual Studio users); Setup requires Microsoft's own redistributable instead. The version is the one in
; src/barbershop_tracks/core/runtime/vcruntime.py (build.ps1 passes it); NumpyMsvcp is the hash-renamed
; name NumPy's wheel imports (packaging/runtime_copies.py), for which Setup copies the PC's own file.
#ifndef VcMajor
  #define VcMajor 14
#endif
#ifndef VcMinor
  #define VcMinor 44
#endif
#ifndef VcBuild
  #define VcBuild 35211
#endif
#ifndef NumpyMsvcp
  #define NumpyMsvcp ""
#endif
; Where the "download" button fetches Microsoft's installer from. Only packaging/installer-gui-test.ps1 builds
; a variant with another address (a local server), to test the download paths without Microsoft's servers.
#ifndef VcRedistUrlOverride
  #define VcRedistUrlOverride "https://aka.ms/vc14/vc_redist.x64.exe"
#endif

[Setup]
; Never change AppId: it is what makes a new version replace the old one in place.
AppId={{7A3B1E52-4C8D-4F6A-9B21-5D0E8C6F3A17}
AppName={#AppName}
AppVersion={#AppVersion}
#ifdef ResearchBuild
AppVerName={#AppName} {#AppVersion} (INTERNAL RESEARCH BUILD, not for distribution)
#else
AppVerName={#AppName} {#AppVersion}
#endif
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
#ifdef ResearchBuild
OutputBaseFilename=BLT-Music-Generator-{#AppVersion}-RESEARCH-ONLY-Setup
#else
OutputBaseFilename=BLT-Music-Generator-{#AppVersion}-Setup
#endif
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
#if NumpyMsvcp != ""
; NumPy imports a hash-renamed MSVCP140; give it a copy of the one this PC already has (the runtime
; Setup has just verified). Nothing from Microsoft travels inside this installer.
Source: "{sys}\msvcp140.dll"; DestDir: "{app}\_internal\numpy.libs"; DestName: "{#NumpyMsvcp}"; Flags: external ignoreversion
#endif

[Dirs]
; BLT's own folder for the user's voicebanks. It is the user's: uninstalling never removes it, and
; upgrading never touches what is in it. No voicebank is shipped.
Name: "{userdocs}\BLT Music Generator\Voices"; Flags: uninsneveruninstall

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Voices folder"; Filename: "{userdocs}\BLT Music Generator\Voices"
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
const
  VcRedistUrl = '{#VcRedistUrlOverride}';
  VcRedistPage = 'https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist';
  VcRedistShort = 'https://aka.ms/vc14/vc_redist.x64.exe';
  VcKey = 'SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64';

{ Is Microsoft's Visual C++ runtime (x64) at the required version or newer installed? The switch
  /VCRUNTIME=missing only lets a test pretend it is not; nothing can pretend it is. }
function VcRuntimeOk(): Boolean;
var
  Installed, Major, Minor, Build: Cardinal;
begin
  Result := False;
  if ExpandConstant('{param:VCRUNTIME|}') = 'missing' then
    Exit;
  if not RegQueryDWordValue(HKLM64, VcKey, 'Installed', Installed) then Exit;
  if Installed <> 1 then Exit;
  if not RegQueryDWordValue(HKLM64, VcKey, 'Major', Major) then Exit;
  if not RegQueryDWordValue(HKLM64, VcKey, 'Minor', Minor) then Exit;
  if not RegQueryDWordValue(HKLM64, VcKey, 'Bld', Build) then Exit;
  Result := (Major > {#VcMajor}) or
    ((Major = {#VcMajor}) and ((Minor > {#VcMinor}) or ((Minor = {#VcMinor}) and (Build >= {#VcBuild}))));
end;

{ A file Microsoft signed? (The download is not pinned by hash because Microsoft updates the
  package under the same address; its signature is what identifies it.) }
function IsMicrosoftSigned(const FileName: String): Boolean;
var
  Escaped, Params: String;
  Code: Integer;
begin
  Escaped := FileName;
  StringChangeEx(Escaped, '''', '''''', True);
  Params := '-NoProfile -ExecutionPolicy Bypass -Command "$s = Get-AuthenticodeSignature -LiteralPath ''' +
    Escaped + '''; if ($s.Status -eq ''Valid'' -and $s.SignerCertificate.Subject -match ''O=Microsoft Corporation'') { exit 0 } else { exit 1 }"';
  Result := Exec('powershell.exe', Params, '', SW_HIDE, ewWaitUntilTerminated, Code) and (Code = 0);
end;

var
  AttemptHandled: Boolean;  { the last attempt has already told the user what happened (or the user backed out) }

function RunMicrosoftInstaller(const FileName: String): Boolean;
var
  Code: Integer;
begin
  Result := False;
  if not IsMicrosoftSigned(FileName) then
  begin
    AttemptHandled := True;
    MsgBox('The file ' + FileName + ' is not signed by Microsoft, so it will not be run.', mbError, MB_OK);
    Exit;
  end;
  { /passive shows Microsoft's own progress window; it asks Windows for administrator rights }
  if not ShellExec('runas', FileName, '/install /passive /norestart', '', SW_SHOWNORMAL, ewWaitUntilTerminated, Code) then
  begin
    AttemptHandled := True;
    MsgBox('Microsoft''s installer could not be started (' + SysErrorMessage(Code) + ').', mbError, MB_OK);
    Exit;
  end;
  { 0 installed, 3010 installed but a restart is advised, 1638 a newer one is already there }
  Result := (Code = 0) or (Code = 3010) or (Code = 1638);
  if not Result then
  begin
    AttemptHandled := True;
    MsgBox('Microsoft''s installer ended with code ' + IntToStr(Code) + '.', mbError, MB_OK);
  end;
end;

function DownloadAndInstallRuntime(): Boolean;
var
  Downloaded: String;
begin
  Result := False;
  try
    DownloadTemporaryFile(VcRedistUrl, 'vc_redist.x64.exe', '', nil);
    Downloaded := ExpandConstant('{tmp}\vc_redist.x64.exe');
  except
    AttemptHandled := True;
    MsgBox('The download from Microsoft did not work:' + #13#10 + GetExceptionMessage + #13#10#13#10 +
      'Check the internet connection and try again, or download the file on another PC from' + #13#10 +
      VcRedistPage + #13#10 + 'and choose "Install from a vc_redist.x64.exe I have".', mbError, MB_OK);
    Exit;
  end;
  Result := RunMicrosoftInstaller(Downloaded);
end;

function InstallRuntimeFromFile(): Boolean;
var
  Chosen: String;
begin
  Result := False;
  Chosen := ExpandConstant('{src}\vc_redist.x64.exe');
  if not FileExists(Chosen) then
  begin
    Chosen := '';
    if not GetOpenFileName('Choose vc_redist.x64.exe', Chosen, '', 'Microsoft installer (vc_redist.x64.exe)|vc_redist.x64.exe|Programs (*.exe)|*.exe', 'exe') then
    begin
      AttemptHandled := True;  { the user backed out: back to the question, no further message }
      Exit;
    end;
  end;
  Result := RunMicrosoftInstaller(Chosen);
end;

{ The GUI path: offer Microsoft's own installer, online or from a copy the user brings. }
function EnsureRuntime(): Boolean;
var
  Answer: Integer;
begin
  Result := VcRuntimeOk();
  while not Result do
  begin
    AttemptHandled := False;
    Answer := TaskDialogMsgBox('Microsoft Visual C++ runtime needed',
      '{#AppName} needs Microsoft''s "Visual C++ Redistributable" (x64, version {#VcMajor}.{#VcMinor}.{#VcBuild} or newer). ' +
      'It is a free Microsoft component that is not part of this installer, and it is not installed on this PC (or is older).' + #13#10#13#10 +
      'Without internet: on another PC download vc_redist.x64.exe from' + #13#10 + VcRedistShort + #13#10 +
      'then either put it next to this installer or choose it here.',
      mbInformation, MB_YESNOCANCEL, ['Download and install it now',
      'Install from a vc_redist.x64.exe I have', 'Go back (BLT is not installed yet)'], 0);
    if Answer = IDYES then
      Result := DownloadAndInstallRuntime() and VcRuntimeOk()
    else if Answer = IDNO then
      Result := InstallRuntimeFromFile() and VcRuntimeOk()
    else
      Exit;
    if (not Result) and (not AttemptHandled) then
      MsgBox('Microsoft''s installer finished, but Setup still cannot find the runtime. ' +
        'Restart Windows if it asks you to, then run this setup again.', mbInformation, MB_OK);
  end;
end;

function InitializeSetup(): Boolean;
begin
  Result := True;
  { A silent install never downloads or installs anything on its own: it stops, and says why }
  if WizardSilent and (not VcRuntimeOk()) then
  begin
    Log('Microsoft Visual C++ runtime {#VcMajor}.{#VcMinor}.{#VcBuild} or newer is required and was not found.');
    Result := False;
  end;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = wpReady then
    Result := EnsureRuntime();
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usDone) and (not UninstallSilent) then
    MsgBox('{#AppName} was removed.' + #13#10#13#10 +
      'Your voicebanks, generated tracks and settings were left in place. ' +
      'They are in %LOCALAPPDATA%\BarbershopLearningTracks and can be deleted by hand.',
      mbInformation, MB_OK);
end;
