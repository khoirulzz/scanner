#define MyAppName "KK Scanner"
#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif
#define MyAppPublisher "Nalaro Dev"
#define MyAppExeName "KK Scanner.exe"
#define MyIconFile "..\assets\scanner.ico"

[Setup]
AppId={{A831864E-53D4-4CC0-8D45-54F68D9BB16C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\KK Scanner
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=output
OutputBaseFilename=KK-Scanner-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupLogging=yes
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
CloseApplications=yes
RestartApplications=no
#if FileExists(MyIconFile)
SetupIconFile={#MyIconFile}
#endif

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Buat shortcut di Desktop"; GroupDescription: "Shortcut:"; Flags: checkedonce

[Files]
Source: "..\dist\KK Scanner\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\KK Scanner"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\KK Scanner"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Jalankan KK Scanner"; Flags: nowait postinstall skipifsilent

[Code]
const
  WebView2ClientGuid = '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';
  WebView2BootstrapperUrl = 'https://go.microsoft.com/fwlink/p/?LinkId=2124703';
  WebView2BootstrapperName = 'MicrosoftEdgeWebview2Setup.exe';

var
  WebView2DownloadPage: TDownloadWizardPage;
  CriticalInstallPhase: Boolean;
  SetupCompleted: Boolean;

function HasUsableVersion(const Version: String): Boolean;
begin
  Result := (Version <> '') and (Version <> '0.0.0.0');
end;

function WebView2RuntimeInstalled(): Boolean;
var
  Version: String;
  MachineKey: String;
  UserKey: String;
begin
  Result := False;
  MachineKey := 'SOFTWARE\Microsoft\EdgeUpdate\Clients\' + WebView2ClientGuid;
  UserKey := 'Software\Microsoft\EdgeUpdate\Clients\' + WebView2ClientGuid;

  { Microsoft documents the 32-bit registry view (WOW6432Node) on x64. }
  if IsWin64 then
  begin
    if RegQueryStringValue(HKLM32, MachineKey, 'pv', Version) and HasUsableVersion(Version) then
    begin
      Result := True;
      Exit;
    end;
    { Extra fallback for machines where an updater wrote to the 64-bit view. }
    if RegQueryStringValue(HKLM64, MachineKey, 'pv', Version) and HasUsableVersion(Version) then
    begin
      Result := True;
      Exit;
    end;
  end
  else if RegQueryStringValue(HKLM, MachineKey, 'pv', Version) and HasUsableVersion(Version) then
  begin
    Result := True;
    Exit;
  end;

  if RegQueryStringValue(HKCU, UserKey, 'pv', Version) and HasUsableVersion(Version) then
    Result := True;
end;

function DownloadProgress(const Url, FileName: String; const Progress, ProgressMax: Int64): Boolean;
begin
  { Critical dependency downloads are intentionally not cancellable halfway. }
  Result := True;
end;

procedure InitializeWizard();
begin
  CriticalInstallPhase := False;
  SetupCompleted := False;
  WebView2DownloadPage := CreateDownloadPage(
    'Menyiapkan komponen aplikasi',
    'Microsoft Edge WebView2 Runtime diperlukan agar jendela KK Scanner dapat ditampilkan.',
    @DownloadProgress
  );
end;

function InstallWebView2IfNeeded(): String;
var
  ResultCode: Integer;
  BootstrapperPath: String;
begin
  Result := '';

  if WebView2RuntimeInstalled() then
  begin
    Log('WebView2 Runtime already installed; dependency step skipped.');
    Exit;
  end;

  CriticalInstallPhase := True;
  BootstrapperPath := ExpandConstant('{tmp}\') + WebView2BootstrapperName;

  WebView2DownloadPage.Clear;
  WebView2DownloadPage.Add(WebView2BootstrapperUrl, WebView2BootstrapperName, '');
  WebView2DownloadPage.Show;
  try
    try
      WebView2DownloadPage.Download;
      Log('WebView2 bootstrapper downloaded to: ' + BootstrapperPath);

      if not Exec(
        BootstrapperPath,
        '/silent /install',
        '',
        SW_HIDE,
        ewWaitUntilTerminated,
        ResultCode
      ) then
      begin
        Result := 'Microsoft Edge WebView2 Runtime tidak dapat dijalankan. Periksa koneksi internet lalu coba instalasi kembali.';
        Exit;
      end;

      if (ResultCode <> 0) and (ResultCode <> 3010) then
      begin
        Result := Format('Instalasi Microsoft Edge WebView2 Runtime gagal (kode %d). Periksa koneksi internet lalu coba kembali.', [ResultCode]);
        Exit;
      end;

      if not WebView2RuntimeInstalled() then
      begin
        Result := 'WebView2 Runtime selesai diproses tetapi belum terdeteksi. Coba ulangi installer atau restart Windows.';
        Exit;
      end;

      Log('WebView2 Runtime installed successfully.');
    except
      Result := 'WebView2 Runtime gagal diunduh atau dipasang. Detail: ' + GetExceptionMessage;
    end;
  finally
    WebView2DownloadPage.Hide;
    CriticalInstallPhase := False;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := InstallWebView2IfNeeded();
end;

function CancelButtonClick(CurPageID: Integer): Boolean;
begin
  if SetupCompleted then
  begin
    Result := True;
    Exit;
  end;

  if CriticalInstallPhase then
  begin
    MsgBox(
      'KK Scanner sedang mengunduh atau memasang komponen yang diperlukan.' + #13#10 + #13#10 +
      'Proses ini tidak dapat ditutup sekarang agar instalasi tidak rusak. Tunggu sampai tahap ini selesai.',
      mbInformation,
      MB_OK
    );
    Result := False;
    Exit;
  end;

  Result := MsgBox(
    'Instalasi KK Scanner belum selesai.' + #13#10 + #13#10 +
    'Jika ditutup sekarang, aplikasi mungkin belum terpasang dengan benar. Tetap batalkan instalasi?',
    mbConfirmation,
    MB_YESNO
  ) = IDYES;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
    CriticalInstallPhase := True
  else if CurStep = ssPostInstall then
  begin
    CriticalInstallPhase := False;
    SetupCompleted := True;
  end;
end;
