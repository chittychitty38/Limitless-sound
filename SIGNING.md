# Signing the apps

Today the downloads aren't signed. So the first time, a Mac asks people to click **Open Anyway**,
and Windows shows SmartScreen's **More info › Run anyway**. Signing proves the apps come from you.
Then the Mac opens them straight away, and Windows shows your name.

The builds are ready for it. You buy the certificates, add them to GitHub as "secrets", and run
the builds again. Nothing in the code needs to change. Until the secrets are there, every build
stays exactly as it is now.

You need:

- **For the Mac:** the Apple Developer Program, $99 a year. Do this part first: it covers the
  whole Mac suite.
- **For Windows:** a code-signing certificate. Read [Windows](#windows) before you buy one.

Keep every password and file from these steps private. Don't email them or put them in the
repository. GitHub keeps secrets hidden, even from people who can see the code.

## Mac

### 1. Join the Apple Developer Program

Already a member? Skip to step 2.

1. Go to [developer.apple.com/programs/enroll](https://developer.apple.com/programs/enroll/).
2. Sign in with your Apple Account. It needs two-factor authentication turned on.
3. Enroll as an **individual**, and pay $99. Apple can take up to two days to confirm it.

### 2. Find your Team ID

1. Go to [developer.apple.com/account](https://developer.apple.com/account) and sign in.
2. Scroll down to **Membership details**.
3. Write down your **Team ID**. It's 10 letters and numbers, like `AB12CD34EF`.

### 3. Make the two certificates

You need two different certificates:

- **Developer ID Application** signs the apps.
- **Developer ID Installer** signs the suite installer (the .pkg). An app certificate can't sign a .pkg.

Only the person who enrolled (Apple calls them the Account Holder) can make these two. If you
enrolled as an individual, that's you.

Make them on your Mac:

1. Open **Keychain Access** (in Applications › Utilities).
2. In the menu bar, choose **Keychain Access › Certificate Assistant › Request a Certificate From
   a Certificate Authority**.
3. Type your email address and your name. Leave "CA Email Address" empty.
4. Choose **Saved to disk**, click **Continue**, and save the file to your Desktop.
5. Go to [developer.apple.com/account/resources/certificates/add](https://developer.apple.com/account/resources/certificates/add).
6. Choose **Developer ID Application** and click **Continue**. If it asks, pick the
   **G2 Sub-CA** option.
7. Upload the file from your Desktop, click **Continue**, then **Download**.
8. Double-click the downloaded file. Keychain Access adds it.
9. Do steps 5 to 8 again, but choose **Developer ID Installer** in step 6. You can use the same
   file from your Desktop.

### 4. Save each certificate as a .p12 file

Do this once for each of the two certificates:

1. In Keychain Access, click **login** on the left, then the **My Certificates** tab at the top.
2. Find **Developer ID Application: Your Name (AB12CD34EF)**. Click the small arrow next to
   it. A key should appear under it. If there's no key, the certificate was made on another Mac:
   make it again on this one.
3. Right-click the certificate and choose **Export**.
4. Choose the format **Personal Information Exchange (.p12)**. Name it
   `DeveloperIDApplication.p12` and save it to your Desktop.
5. Make up a password for the file and write it down. You'll need it in step 6.
6. Your Mac may ask for your Mac's login password. That's normal.

Then do the same for **Developer ID Installer: Your Name (AB12CD34EF)**, and name that file
`DeveloperIDInstaller.p12`.

Write down both names exactly as Keychain Access shows them, for example
`Developer ID Application: Your Name (AB12CD34EF)`. You'll need them in step 6.

### 5. Make an app-specific password

GitHub uses it to send the apps to Apple to be checked ("notarized"). It's not your real password.

1. Go to [account.apple.com](https://account.apple.com) (it used to be appleid.apple.com) and sign in.
2. Open **Sign-In and Security**, then **App-Specific Passwords**.
3. Click the **+** button and name it `GitHub notarization`.
4. Copy the password it shows (it looks like `abcd-efgh-ijkl-mnop`) and keep it for step 6.

### 6. Add the Mac secrets to GitHub

For each line in the table below:

1. Go to [the repository on GitHub](https://github.com/chittychitty38/Limitless-sound).
2. Click **Settings** (at the top), then **Secrets and variables › Actions** (on the left).
3. Click **New repository secret**.
4. Type the **Name** exactly as in the table. Paste the value into **Secret**.
5. Click **Add secret**.

For the two .p12 files, open **Terminal** (in Applications › Utilities) and type this, then
press Return. It copies the file, as text, so you can paste it:

```
base64 -i ~/Desktop/DeveloperIDApplication.p12 | pbcopy
```

For the installer certificate, use `DeveloperIDInstaller.p12` instead.

| Name | What to paste |
| --- | --- |
| `APPLE_CERT_P12` | `DeveloperIDApplication.p12`, copied with the Terminal line above |
| `APPLE_CERT_PASSWORD` | the password you gave that file |
| `APPLE_SIGNING_IDENTITY` | its name, like `Developer ID Application: Your Name (AB12CD34EF)` |
| `APPLE_INSTALLER_CERT_P12` | `DeveloperIDInstaller.p12`, copied the same way |
| `APPLE_INSTALLER_CERT_PASSWORD` | the password you gave that file |
| `APPLE_INSTALLER_IDENTITY` | its name, like `Developer ID Installer: Your Name (AB12CD34EF)` |
| `APPLE_ID` | the email address of your Apple Account |
| `APPLE_TEAM_ID` | your Team ID from step 2 |
| `APPLE_APP_PASSWORD` | the app-specific password from step 5 |

Then delete the two .p12 files and the request file from your Desktop. The certificates stay
safe in Keychain Access.

## Windows

There are two kinds of Windows code-signing certificate:

- **OV** (organization validation). The seller checks who you are. Windows shows your name.
  SmartScreen may still warn for the first weeks, until enough people have downloaded the apps.
- **EV** (extended validation). A stricter check, and it costs more. It used to skip SmartScreen's
  warning period; Microsoft says it no longer does, so OV is enough for these apps.

**Before you buy, know this.** Since June 2023, sellers have to keep the secret part of every new
code-signing certificate, OV or EV, on a USB key or in their own cloud service. You can't download
it as a file. The builds here can sign only with a certificate saved as a **.pfx file**, so a new
certificate from a seller won't work with them as they are.

The usual way around it is a cloud signing service that GitHub can use:

- **Azure Trusted Signing** from Microsoft, about $10 a month. Check it's open to individuals where
  you live.
- **SSL.com eSigner**: an OV or EV certificate kept in SSL.com's cloud.

Choose one, then ask Claude to connect it to the builds. It's a small change to
`.github/scripts/win-sign.ps1` and GazeStage's workflow.

If you do have a certificate as a .pfx file (an older one, say), add it like this:

1. In Terminal on a Mac, type `base64 -i ~/Desktop/certificate.pfx | pbcopy`, then press Return.
   (On Windows, in PowerShell:
   `[Convert]::ToBase64String([IO.File]::ReadAllBytes("$HOME\Desktop\certificate.pfx")) | Set-Clipboard`.)
2. Add two secrets, as in Mac step 6:

| Name | What to paste |
| --- | --- |
| `WINDOWS_CERT_PFX` | the .pfx file, copied with the line above |
| `WINDOWS_CERT_PASSWORD` | the .pfx file's password |

## Make signed builds

The "Run workflow" button only appears once the repository's main branch is `main`. Check
at **Settings › General › Default branch**. If it says something else, click the arrows button
next to it, choose `main`, and confirm.

Or skip the button: ask Claude to release the next suite version. Changing the version in
`packaging/VERSION` builds the suite and publishes it as a new release, signed and notarized the
same way.

Then:

1. On GitHub, click **Actions** (at the top).
2. On the left, click **Limitless Sound Suite**.
3. Click **Run workflow** (on the right), leave the branch as `main`, and click the green
   **Run workflow** button.

This takes up to an hour. It signs every Mac app, signs the Mac installer and has Apple check it,
signs the Windows installer, and puts the new downloads on the newest release page.

To sign each app's own download, and the Windows programs inside the suite, also run each app
once the same way: **Hub and clients**, **Limitless Voice**, **Limitless One-Hand**,
**Limitless Zoom**, **Limitless Color**, **Limitless Control** and **GazeStage**. The suite
rebuilds itself after each one. Each app's own release page gets signed files at its next version.

## Check that it worked

On a Mac:

1. Download `Limitless-Sound-Suite-mac-apple-silicon.pkg` (or the Intel one) from the
   [newest release](https://github.com/chittychitty38/Limitless-sound/releases/latest).
2. In Terminal, type this and press Return:

   ```
   pkgutil --check-signature ~/Downloads/Limitless-Sound-Suite-mac-apple-silicon.pkg
   ```

   It should say `signed by a developer certificate issued by Apple for distribution`, then
   `Notarization: trusted by the Apple notary service`, and show your name.
3. Install it. Then check an app:

   ```
   spctl -a -vv "/Applications/Limitless Voice.app"
   ```

   It should say `accepted` and `source=Notarized Developer ID`, then your name.
4. Open the app. It should open without any **Open Anyway** step.

On Windows: right-click the downloaded `.exe` and choose **Properties**. The **Digital Signatures**
tab shows your name. If SmartScreen still appears in the first weeks, it now names you as the
publisher.

If a build fails, open it in **Actions** and click the red step. The signing scripts say what's
wrong in plain words, for example a certificate name that doesn't match, or a wrong password.

Once it works, ask Claude to take the **Open Anyway** and **Run anyway** steps out of the README
and the release notes.

## Good to know

- **The Apple membership renews every year.** If it lapses, new builds can't be notarized, but
  apps people already have keep working. The certificates last five years.
- **Changing your Apple Account password** cancels app-specific passwords. Make a new one
  (step 5) and update `APPLE_APP_PASSWORD`.
- **Only some secrets?** With the certificates but no `APPLE_ID`, apps are signed but not
  notarized, so a Mac still asks. Without the installer certificate, the apps are signed but the
  suite .pkg isn't.
- **Pull requests from other people's copies of the repository** never get the secrets, so
  their builds stay unsigned. That's on purpose.
- The workflow **Signing check** tests the signing scripts with throwaway certificates whenever
  they change, so they're known to work before the real ones go in.
- How it works, for a developer: `.github/scripts/mac-sign.sh` (Mac signing, notarizing and
  each app's entitlements) and `.github/scripts/win-sign.ps1` (Windows). GazeStage and Limitless
  Color use their build tools' own signing (electron-builder, Tauri), fed the same secrets.
