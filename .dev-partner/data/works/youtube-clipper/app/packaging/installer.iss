; Inno Setup の設定（clipper-setup.exe）。実行: iscc packaging\installer.iss
; 管理者権限なしで入るユーザー単位のインストール。スタートメニューとデスクトップにショートカットを作る。
#define AppVer GetEnv("CLIPPER_VERSION")
#if AppVer == ""
  #define AppVer "0.2.0"
#endif

[Setup]
AppId={{4BCAA7B2-C133-4C75-8EB6-CD88699FB4F9}
AppName=clipper
AppVersion={#AppVer}
AppPublisher=clipper
DefaultDirName={autopf}\clipper
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=clipper-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\clipper.exe

[Languages]
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"

[Tasks]
Name: "desktopicon"; Description: "デスクトップにアイコンを作る"; GroupDescription: "追加のアイコン:"

[Files]
Source: "..\dist\clipper\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\clipper"; Filename: "{app}\clipper.exe"
Name: "{autodesktop}\clipper"; Filename: "{app}\clipper.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\clipper.exe"; Description: "clipper を起動する"; Flags: nowait postinstall skipifsilent
; アプリ内の更新（/UPDATE=1 で静かに上書き）のときだけ、最後にアプリを起動し直す（B-013）
Filename: "{app}\clipper.exe"; Flags: nowait; Check: IsUpdate

[Code]
function IsUpdate: Boolean;
begin
  Result := ExpandConstant('{param:UPDATE|0}') = '1';
end;
