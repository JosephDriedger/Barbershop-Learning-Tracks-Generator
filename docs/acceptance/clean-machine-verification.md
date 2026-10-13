# Clean-machine verification (install, run, upgrade, uninstall; with and without the Visual C++ runtime)

Checklist version 1 (M15). Read [README.md](README.md) first. **A result is only valid for the installer whose SHA-256 you write in
section 1.** Everything here is done by a person at the keyboard; nobody needs Python, git or any developer tool.

What this decides: whether the installer works on a PC that has never seen this project, including the common case that the PC does
**not** have Microsoft's Visual C++ runtime (which BLT needs, and which BLT may not ship itself). The automated tests exercised these
paths with stand-ins on the developer's PC; they could not press the Windows administrator prompt (UAC) and they ran on a PC that has
developer tools. That is what you are checking.

## 0. Machine

You need a Windows 10 or 11, **64-bit** PC or virtual machine that has **never had BLT, Python, .NET SDKs or Visual Studio**. Good
choices: a fresh VM (Hyper-V, VirtualBox, VMware) with a snapshot you can go back to; Windows Sandbox (Pro/Enterprise/Education only; it is a
clean machine every time, but has no network unless you enable it); or a spare PC. Take a snapshot **before** you start so you can repeat
part B.

For part B you need a machine that lacks the runtime. Check (PowerShell or Command Prompt):

```
reg query "HKLM\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64" /v Version
```

"The system was unable to find the specified registry key" (or a version below 14.44.35211) means the runtime is missing or too old: part B
applies. A version of 14.44.35211 or higher means it is present. On a **VM only**, you can remove it: Settings > Apps > "Microsoft Visual C++
2015-2022 Redistributable (x64)" > Uninstall; it comes back with the next step. Do not do this on a PC you care about: other programs need it.

You also need, for the offline steps, `vc_redist.x64.exe` from Microsoft: download it on any PC from https://aka.ms/vc14/vc_redist.x64.exe
(check it: right-click the file, Properties, Digital Signatures, signer "Microsoft Corporation") and carry it on a USB stick.

## 1. What you record

| | |
|---|---|
| Your name and role / date | |
| Installer file name and **SHA-256** (must equal the one you were sent) | |
| Machine (physical / VM type), Windows edition and build (`winver`) | |
| Account: administrator or standard user? | |
| Is the Visual C++ runtime present at the start? (output of the `reg query` above) | |
| Network during the test (online / offline) | |
| Antivirus in use | |

## 2. Part A: the PC has the runtime (normal install)

Skip to part B if you are testing a PC without it; do **both** for a complete result (use the snapshot).

| # | Step | Expected | Result | Notes |
|---|---|---|---|---|
| A1 | Double-click the installer. | Windows SmartScreen says "Windows protected your PC" (the installer is unsigned: expected). More info > Run anyway. Record the publisher it shows. | | |
| A2 | Walk through Setup, accepting the defaults. | No administrator prompt; a licence page; install finishes; no message about a missing runtime. | | |
| A3 | Start **BLT Music Generator** from the Start menu. | The window opens. No error about a missing DLL, Python or the Visual C++ runtime. | | |
| A4 | *Help > Copy diagnostics*, paste it into a text file. | "render host" names a folder (no setting needed); "vc runtime ... ok"; FFmpeg "not found" is fine. | | |
| A5 | Command Prompt: `"%LOCALAPPDATA%\Programs\BLT Music Generator\blt.exe" selftest` | Ends with "selftest passed" (first run takes a few seconds longer). | | |
| A6 | Disconnect the network (airplane mode / unplug) and repeat A5. | Still "selftest passed": BLT needs no internet. Reconnect afterwards. | | |
| A7 | Optional but wanted: do the [English voicebank acceptance](english-voicebank-acceptance.md) steps on this machine. | | | |
| A8 | Close BLT and start it again. | Settings and folders are remembered. | | |
| A9 | If you were given a **newer installer**, run it over the installed version. | It upgrades in place; your voices, tracks and settings are still there. (Write "no second build supplied" otherwise.) | | |
| A10 | Settings > Apps > BLT Music Generator > Uninstall. | The program, the Start-menu entry and the Apps entry are gone; **your voicebanks, generated tracks and settings remain.** Note what is left in `%LOCALAPPDATA%\Programs\BLT Music Generator` and `%LOCALAPPDATA%\BarbershopLearningTracks`. | | |
| A11 | Optional: repeat A1-A5 with a Windows account whose user name contains a space and a non-English character (for example `Jörg Müller`). | Installs and runs. | | |

## 3. Part B: the PC does not have the runtime

Go back to the snapshot (or remove the runtime on a VM as described above), confirm with the `reg query` that it is missing, and that BLT is
not installed. Take a screenshot of **every** window Setup shows in this part and keep them with the results.

| # | Step | Expected | Result | Notes |
|---|---|---|---|---|
| B1 | Start the installer, walk to "Ready to Install" and press **Install**. | A dialog "Microsoft Visual C++ runtime needed" explains that BLT needs Microsoft's *Visual C++ Redistributable (x64)*, gives the address `https://aka.ms/vc14/vc_redist.x64.exe`, and offers three buttons: "Download and install it now", "Install from a vc_redist.x64.exe I have", "Go back (BLT is not installed yet)". **Copy the dialog's text into the Notes. Was it clear what to do?** | | |
| B2 | Press **Go back**. | You are back at "Ready to Install"; nothing was installed (check `%LOCALAPPDATA%\Programs` has no BLT folder). Press Cancel to leave Setup. | | |
| B3 | **Online path.** Start the installer again, Install, **Download and install it now**. | Setup downloads the file from Microsoft; Windows asks for permission (UAC) naming **Microsoft Corporation** (a standard user must type an administrator's password). Microsoft's own installer shows a progress window and its licence terms. Afterwards Setup carries on installing BLT without asking again. Record who the UAC prompt names and how long it took. | | |
| B4 | After B3: start BLT, then `blt.exe diagnostics`. | BLT starts; diagnostics shows "vc runtime: ... ok". Run `blt.exe selftest`: "selftest passed". | | |
| B5 | Uninstall BLT; on a VM go back to the snapshot (no runtime) for the next steps. | | | |
| B6 | **Offline path, file beside the installer.** Disconnect the network. Put `vc_redist.x64.exe` (from the USB stick) in the **same folder** as the installer. Start the installer, Install, **Install from a vc_redist.x64.exe I have**. | Setup uses the file **without** opening a file chooser, asks Windows for permission (UAC, Microsoft Corporation), runs Microsoft's installer, and continues installing BLT. | | |
| B7 | Back to the snapshot. **Offline path, choose the file.** Installer alone in its folder; `vc_redist.x64.exe` somewhere else (for example on the USB stick). Install, **Install from a vc_redist.x64.exe I have**. | A window "Choose vc_redist.x64.exe" opens; you pick the file; the rest is as in B6. | | |
| B8 | Back to the snapshot. **You decline the Windows permission.** Take the path of B6, but answer **No** at the UAC prompt. | A message that Microsoft's installer could not be started (the operation was cancelled); the "needed" dialog returns; nothing is installed. Then choose **Go back**. | | |
| B9 | **A wrong file.** Rename any other program to `vc_redist.x64.exe` and put it beside the installer. Install, **Install from a vc_redist.x64.exe I have**. | A message "The file ... is not signed by Microsoft, so it will not be run"; the file is **not** started; the dialog returns. | | |
| B10 | **Download fails.** Disconnect the network, and use **Download and install it now**. | A message says the download did not work, suggests checking the connection or using the second button, and names the Microsoft page; the dialog returns. | | |
| B11 | **Silent install without the runtime.** Command Prompt: `BLT-Music-Generator-<version>-Setup.exe /VERYSILENT /SUPPRESSMSGBOXES`, then check `echo %errorlevel%` and whether BLT was installed. | It does **not** install and does not download anything; a non-zero exit code. | | |
| B12 | **The runtime disappears after BLT was installed** (VM only): with BLT installed, uninstall "Microsoft Visual C++ 2015-2022 Redistributable (x64)" in Apps, then start BLT. | BLT cannot start. **Write down exactly what Windows shows.** The developers could not test this (their PC has the runtime): they expect a message from the program's launcher such as "Failed to load Python DLL", because BLT never gets to run and cannot show its own message. Your observation replaces that guess. Then fix it with B3 or B6 by running the BLT installer again, or Microsoft's installer alone. | | |
| B13 | A standard user (not an administrator), if you have such an account: do B3. | Windows asks for an administrator's password at the UAC step. Without it, B8's message appears. Record what a person who does **not** know the password would do next. | | |

## 4. Observations for everyone

* Did anything look suspicious (unexpected windows, files outside `%LOCALAPPDATA%\Programs\BLT Music Generator` and
  `%LOCALAPPDATA%\BarbershopLearningTracks`, network traffic you did not expect)? Setup should contact the network **only** in step B3.
* Did your antivirus react to the installer or the program? Which one, and what did it say?
* Would a person who is not technical understand each window and message? Quote the ones that were not clear.

## 5. Results block (copy into a text file and send it back)

```
BLT ACCEPTANCE RESULT: clean machine
Checklist version: 1
Tester / role / date:
Installer file and SHA-256:
Machine / Windows build / account type / runtime present at start:
Part A steps A1-A11: PASS / FAIL / COULD NOT RUN / NOT APPLICABLE with a note for each:
Part B steps B1-B13: PASS / FAIL / COULD NOT RUN with a note for each (attach the screenshots):
Text of the "runtime needed" dialog as you saw it, and whether it was clear:
What Windows showed in B12:
Observations (section 4):
Problems found (P1.., with the step number):
VERDICT: accepted / accepted with known issues / rejected / not verified (and which parts were not run)
Reasons:
```

Part A on a PC with the runtime and part B on a PC without it are both needed for *accepted*. If only one could be run, the verdict is
*not verified* and says which.
