; installer.iss  —  Inno Setup script for Truck Dash
; Build with:  ISCC.exe installer.iss

#define AppName    "Truck Dash"
#define AppVersion "1.0"
#define AppExe     "TruckDash.exe"

[Setup]
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Truck Dash
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes
OutputDir=installer_output
OutputBaseFilename=TruckDash_Setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
UninstallDisplayIcon={app}\{#AppExe}
SetupIconFile=TruckDash.ico
WizardImageFile=compiler:WizClassicImage-IS.bmp
WizardSmallImageFile=compiler:WizClassicSmallImage-IS.bmp

; Minimum Windows 10
MinVersion=10.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"; Flags: checkedonce

[Files]
; Main application files (PyInstaller onedir output)
Source: "dist\TruckDash\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Start Menu
Name: "{group}\{#AppName}";              Filename: "{app}\{#AppExe}"
Name: "{group}\Uninstall {#AppName}";   Filename: "{uninstallexe}"
; Desktop (optional)
Name: "{autodesktop}\{#AppName}";       Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; \
  Description: "Launch {#AppName} now"; \
  Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Remove any Qt cache files left behind in the install folder
Type: filesandordirs; Name: "{app}\__pycache__"

[Code]
// Show a friendly "Thank you" message after install
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssDone then
    MsgBox('Truck Dash has been installed!' + #13#10 + #13#10 +
           'Click OK to finish.  Use the desktop shortcut or Start Menu to play.',
           mbInformation, MB_OK);
end;
