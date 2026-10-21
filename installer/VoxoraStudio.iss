; Voxora Studio — Windows kurulum betiği (Inno Setup 6+)
;
; Derleme (build.bat içinden):
;   ISCC.exe installer\VoxoraStudio.iss /DAppVersion=0.6.0 /DSourceDir=dist\VoxoraStudio-0.6.0
;
; Yerleşim (v0.6.0 ile gelen yapı):
;   Program : {autopf}\VoxoraStudio              (yalnız kod; kurulum siler/yazar)
;   Veri    : {localappdata}\VoxoraStudio        (ayar, geçmiş, çıktı, log)
;   Modeller: {userprofile}\.cache\huggingface   (uygulama yönetir; kurulum dokunmaz)
;
; Yönetici izni: {autopf} = Program Files (tüm kullanıcılar). Bu yüzden her
; güncellemede Windows bir kez onay ister; karşılığında program klasörü tek
; sabit yerdedir ve kısayollar kurulum tarafından yönetilir.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\VoxoraStudio-" + AppVersion
#endif

#define AppName "Voxora Studio"
#define AppExe "VoxoraStudio.exe"
#define AppId "{{8B0F4E4C-5B7E-4C0E-9A3D-1F2C7D6E5A41}"
#define AppPublisher "Voxora"
#define AppUrl "https://github.com/zeitgeist-c/VoxoraStudio"

[Setup]
AppId={#AppId}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppUrl}
AppSupportURL={#AppUrl}
AppUpdatesURL={#AppUrl}/releases
VersionInfoVersion={#AppVersion}
DefaultDirName={autopf}\VoxoraStudio
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
; Program Files'a yazan kurulum: yönetici izni gerekir (tüm kullanıcılar).
PrivilegesRequired=admin
; /CURRENTUSER ile yönetici izni olmadan da kurulabilir (test ve taşınabilir
; doğrulama için); varsayılan yine tüm kullanıcılar.
PrivilegesRequiredOverridesAllowed=commandline dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist\installer
OutputBaseFilename=VoxoraStudio-{#AppVersion}-Setup
SetupIconFile=..\app\assets\voxora.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
LZMAUseSeparateProcess=yes
WizardStyle=modern
WizardSizePercent=110
; Çalışan uygulamayı Restart Manager ile düzgünce kapat; kurulum sonunda geri aç.
CloseApplications=yes
RestartApplications=yes
; Kaldırmada kullanıcı verisine ve model önbelleğine dokunma (bkz. [Code]).
; Uninstall, kurulumun yazdığı dosyaları {app} altında bırakmadan siler.
ChangesAssociations=no
AllowNoIcons=yes
; --- Türkçe arayüz ---
ShowLanguageDialog=no

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce
Name: "startmenuicon"; Description: "Başlat Menüsü kısayolu"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Files]
; Ana program: PyInstaller onedir çıktısı (EXE + _internal).
Source: "{#SourceDir}\VoxoraStudio.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceDir}\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; Güncelleme "temiz kurulum" gibi davranır: eski sürümün dosyaları önce silinir,
; sonra yenisi yazılır. Böylece kaldırılan bir modülün artığı (artık yüklenmeyen
; DLL, silinmiş eklenti) yeni sürümde geride kalmaz.
; `unins000.exe` ve `unins000.dat` BİLİNÇLİ olarak korunur; silinirse kaldırma
; kaydı bozulur. Kullanıcı verisi {app} altında değil, etkilenmez.
Type: filesandordirs; Name: "{app}\_internal"
Type: files; Name: "{app}\VoxoraStudio.exe"
; Eski sürümlü EXE/BAT adları (v0.5.x ve öncesi taşınabilir yerleşiminden kalma).
Type: files; Name: "{app}\VoxoraStudio-*.exe"
Type: files; Name: "{app}\VoxoraStudio-*.bat"
Type: filesandordirs; Name: "{app}\logs"

[Icons]
; Kısayollar her kurulumda yeniden yazılır: bayat yol kalmaz.
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Tasks: startmenuicon
Name: "{group}\{#AppName} kaldır"; Filename: "{uninstallexe}"; Tasks: startmenuicon
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
; Kurulum (güncelleme) sonunda programı aç. `skipifsilent` YOK: uygulama içi
; güncelleme sessiz kurulum kullanır ve programın geri açılması gerekir.
; `runasoriginaluser` ile kurulum yönetici izniyle çalışsa bile program normal
; kullanıcı olarak başlar (Program Files'a yazma izni gerekmez).
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall runasoriginaluser

[UninstallDelete]
; Kurulumun ürettiği artıklar (kullanıcı verisi DEĞİL).
Type: filesandordirs; Name: "{app}\_internal"
Type: filesandordirs; Name: "{app}\logs"

[Code]
// Kaldırma sırasında kullanıcı verisi ve model önbelleği korunur; kullanıcıya
// nerede olduğu söylenir. Kaldırma yalnız {app} altını temizler.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\VoxoraStudio');
    if DirExists(DataDir) then
      MsgBox('Ayarlarınız, geçmişiniz ve çıktılarınız korundu:' + #13#10 +
             DataDir + #13#10#13#10 +
             'İndirilen ses modelleri de korunur:' + #13#10 +
             ExpandConstant('{%USERPROFILE}\.cache\huggingface') + #13#10#13#10 +
             'Bu klasörleri elle silebilirsiniz.',
             mbInformation, MB_OK);
  end;
end;

// Kaldırma sonrası bilgilendirme yukarıda. Kurulum öncesi çalışan kod yok:
// eski taşınabilir sürüm klasörü silinmez, kullanıcı kendi kararıyla temizler;
// ayarları ilk açılışta uygulama kendisi devralır (app.paths.migrate_legacy_state).

