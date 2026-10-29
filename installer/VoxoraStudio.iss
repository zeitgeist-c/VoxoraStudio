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
#define AppPublisher "Geeker"
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
OutputBaseFilename=VoxoraStudio-{#AppVersion}
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
; --- 13 dil kurulum arayüzü: English ilk ve varsayılan ---
LanguageDetectionMethod=none
ShowLanguageDialog=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Languages\English.isl"
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "polish"; MessagesFile: "compiler:Languages\Polish.isl"
Name: "dutch"; MessagesFile: "compiler:Languages\Dutch.isl"
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[CustomMessages]
english.StartMenuShortcut=Start Menu shortcut
turkish.StartMenuShortcut=Başlat Menüsü kısayolu
german.StartMenuShortcut=Startmenü-Verknüpfung
spanish.StartMenuShortcut=Acceso directo del menú Inicio
french.StartMenuShortcut=Raccourci du menu Démarrer
italian.StartMenuShortcut=Collegamento al menu Start
brazilianportuguese.StartMenuShortcut=Atalho do Menu Iniciar
russian.StartMenuShortcut=Ярлык меню «Пуск»
polish.StartMenuShortcut=Skrót menu Start
dutch.StartMenuShortcut=Snelkoppeling in Startmenu
chinesesimplified.StartMenuShortcut=「开始」菜单快捷方式
japanese.StartMenuShortcut=スタート メニューのショートカット
korean.StartMenuShortcut=시작 메뉴 바로 가기
english.KeepData=Ayarlarınız, geçmişiniz ve çıktılarınız korundu:
turkish.KeepData=Ayarlarınız, geçmişiniz ve çıktılarınız korundu:
german.KeepData=Ihre Einstellungen, Verlauf und Ausgaben wurden behalten:
spanish.KeepData=Su configuración, historial y salidas se conservaron:
french.KeepData=Vos paramètres, historique et sorties ont été conservés :
italian.KeepData=Impostazioni, cronologia e output conservati:
brazilianportuguese.KeepData=Suas configurações, histórico e saídas foram mantidos:
russian.KeepData=Ваши настройки, история и результаты сохранены:
polish.KeepData=Twoje ustawienia, historia i wyniki zostały zachowane:
dutch.KeepData=Uw instellingen, geschiedenis en uitvoer zijn behouden:
chinesesimplified.KeepData=您的设置、历史记录和输出已保留：
japanese.KeepData=設定、履歴、出力は保持されました:
korean.KeepData=설정, 기록 및 출력이 유지되었습니다:
english.KeepModels=Downloaded voice models are also kept:
turkish.KeepModels=İndirilen ses modelleri de korunur:
german.KeepModels=Heruntergeladene Stimmmodelle bleiben ebenfalls erhalten:
spanish.KeepModels=Los modelos de voz descargados también se conservan:
french.KeepModels=Les modèles vocaux téléchargés sont également conservés :
italian.KeepModels=Anche i modelli vocali scaricati vengono conservati:
brazilianportuguese.KeepModels=Os modelos de voz baixados também são mantidos:
russian.KeepModels=Загруженные голосовые модели также сохранены:
polish.KeepModels=Pobrane modele głosowe również zostają zachowane:
dutch.KeepModels=Gedownloade stemmodellen blijven ook behouden:
chinesesimplified.KeepModels=已下载的语音模型也将保留：
japanese.KeepModels=ダウンロード済み音声モデルも保持されます:
korean.KeepModels=다운로드한 음성 모델도 유지됩니다:
english.CleanHint=You may delete these folders manually.
turkish.CleanHint=Bu klasörleri elle silebilirsiniz.
german.CleanHint=Sie können diese Ordner manuell löschen.
spanish.CleanHint=Puede eliminar estas carpetas manualmente.
french.CleanHint=Vous pouvez supprimer ces dossiers manuellement.
italian.CleanHint=Puoi eliminare queste cartelle manualmente.
brazilianportuguese.CleanHint=Você pode excluir essas pastas manualmente.
russian.CleanHint=Эти папки можно удалить вручную.
polish.CleanHint=Te foldery możesz usunąć ręcznie.
dutch.CleanHint=U kunt deze mappen handmatig verwijderen.
chinesesimplified.CleanHint=您可以手动删除这些文件夹。
japanese.CleanHint=これらのフォルダーは手動で削除できます。
korean.CleanHint=이 폴더를 수동으로 삭제할 수 있습니다.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce
Name: "startmenuicon"; Description: "{cm:StartMenuShortcut}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

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
      MsgBox(ExpandConstant('{cm:KeepData}') + #13#10 +
             DataDir + #13#10#13#10 +
             ExpandConstant('{cm:KeepModels}') + #13#10 +
             ExpandConstant('{%USERPROFILE}\.cache\huggingface') + #13#10#13#10 +
             ExpandConstant('{cm:CleanHint}'),
             mbInformation, MB_OK);
  end;
end;

// Kurulum dili devri: secilen dili kurulum klasorune yaz (13 dil).
// Uygulama kayitli tercihi yoksa bunu okur; guncelleme tercihi ezmez.
procedure CurStepChanged(CurStep: TSetupStep);
var
  LangCode: String;
begin
  if CurStep = ssPostInstall then
  begin
    case ActiveLanguage of
      'english': LangCode := 'en';
      'turkish': LangCode := 'tr';
      'german': LangCode := 'de';
      'spanish': LangCode := 'es';
      'french': LangCode := 'fr';
      'italian': LangCode := 'it';
      'brazilianportuguese': LangCode := 'pt-BR';
      'russian': LangCode := 'ru';
      'polish': LangCode := 'pl';
      'dutch': LangCode := 'nl';
      'chinesesimplified': LangCode := 'zh-CN';
      'japanese': LangCode := 'ja';
      'korean': LangCode := 'ko';
    else
      LangCode := 'en';
    end;
    SaveStringToFile(ExpandConstant('{app}') + '\install-language.txt', LangCode, False);
  end;
end;

// Kaldırma sonrası bilgilendirme yukarıda. Kurulum öncesi çalışan kod yok:
// eski taşınabilir sürüm klasörü silinmez, kullanıcı kendi kararıyla temizler;
// ayarları ilk açılışta uygulama kendisi devralır (app.paths.migrate_legacy_state).

