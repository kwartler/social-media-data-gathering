# Installing and opening the app

The app is free and runs on your own computer. It isn't signed with a paid Apple or
Microsoft developer certificate, so the first time you open it, your computer will warn you
that it can't verify the app. That's expected. Follow the steps for your computer below; you
only need to do this once per download.

The app only runs on your own machine (at `http://127.0.0.1:8010` in your browser). Nothing
is installed system-wide, and you can delete it like any other file.

- [Mac](#mac)
- [Windows](#windows)
- [After it opens](#after-it-opens)
- [Troubleshooting](#troubleshooting)
- [Removing the app when you're done](#removing-the-app-when-youre-done)

---

## Mac

Requires a Mac with Apple Silicon (M1 or later). To check: Apple menu > **About This Mac**;
the "Chip" line should say Apple M1, M2, M3, M4, or later. Intel Macs are not supported by
the download; see [Run from source](../README.md#run-from-source) instead.

### 1. Download and unzip

1. Go to the [Releases page](https://github.com/kwartler/social-media-data-gathering/releases/latest).
2. Under **Assets**, click `social-media-data-gathering-mac-arm64.zip`.
3. Open your **Downloads** folder and double-click the zip. You'll get
   `social-media-data-gathering.app`.
4. Optional: drag the app into your **Applications** folder.

### 2. Open it the first time

Double-click the app. You will see:

> "social-media-data-gathering" can't be opened because Apple cannot check it for malicious software.

1. Click **Done**. Do **not** click Move to Trash.
2. Open **System Settings** (Apple menu > System Settings).
3. Click **Privacy & Security** in the sidebar.
4. Scroll down to the **Security** section. You'll see a note that
   "social-media-data-gathering" was blocked. Click **Open Anyway**.
5. Enter your Mac password or use Touch ID.
6. In the next dialog, click **Open**.

The **Open Anyway** button only appears for about an hour after you tried to open the app.
If you don't see it, double-click the app again, click **Done**, and go straight back to
Privacy & Security.

From now on, the app opens with a normal double-click.

### Alternative: open it from Terminal

If you're comfortable with Terminal (Applications > Utilities > Terminal), you can skip
System Settings. Paste each command and press Return. No admin password is needed.

First, remove the "downloaded from the internet" flag that triggers the warning (once per
download):

```
xattr -dr com.apple.quarantine ~/Downloads/social-media-data-gathering.app
```

Then open the app (the same as double-clicking it):

```
open ~/Downloads/social-media-data-gathering.app
```

If you moved the app to Applications, use these instead:

```
xattr -dr com.apple.quarantine /Applications/social-media-data-gathering.app
```

```
open /Applications/social-media-data-gathering.app
```

After the first command, double-clicking the app works normally too.

This command is also the fix if macOS ever says the app **"is damaged and can't be opened."**
The app isn't damaged; that's another form of the same warning.

---

## Windows

Requires Windows 10 or 11 (64-bit).

### 1. Download

1. Go to the [Releases page](https://github.com/kwartler/social-media-data-gathering/releases/latest).
2. Under **Assets**, click `social-media-data-gathering-windows.exe`.
3. Your browser may warn that the file "isn't commonly downloaded" or "could harm your device."
   - **Edge:** hover over the download, click the **...** menu, choose **Keep**, then
     **Show more** > **Keep anyway**.
   - **Chrome:** click the download's warning, then **Keep** (you may need to click the
     arrow or **Download suspicious file**).

Optional: move the `.exe` somewhere permanent, such as your Documents folder.

### 2. Open it the first time

Double-click the `.exe`. You will see a blue window:

> Windows protected your PC. Microsoft Defender SmartScreen prevented an unrecognized app from starting.

1. Click **More info** (the small link under the message).
2. Click **Run anyway**.

From now on, it opens with a normal double-click.

### If Windows Security deletes or blocks the file

Occasionally antivirus mistakes apps built with this toolkit for a threat. If the file
disappears or won't run:

1. Open **Windows Security** (Start menu > type "Windows Security").
2. Go to **Virus & threat protection** > **Protection history**.
3. Find the entry for `social-media-data-gathering-windows.exe`, open it, and choose
   **Actions** > **Allow** (or **Restore**).
4. Download the file again if it was removed.

If you are on a school or work computer, your IT department may block unsigned apps
entirely. Use a personal computer, or ask IT to allow it.

### If a firewall prompt appears

Windows may ask whether to allow the app on networks. The app only talks to your own
computer and to the websites you collect from, so you can click **Cancel** or allow it on
**Private networks** only; it works either way.

---

## After it opens

- A small black window (Terminal on Mac, a console window on Windows) opens and stays open.
  **That's the app running. Leave it open** while you work.
- Your web browser opens to `http://127.0.0.1:8010`. If it doesn't, open your browser and
  type that address yourself.
- When you're done, click **Quit** at the top right of the app's page. Then close the
  browser tab. Closing the black window also stops the app.
- Your settings, keys, and exports are saved in a folder in your home directory named
  `.social_media_data_gathering` (hidden by default). See
  [Where data is stored](../README.md#where-data-is-stored).

---

## Troubleshooting

**The browser says "This site can't be reached" at 127.0.0.1:8010.**
The app isn't running. Open it again and wait a few seconds for the black window to appear.

**Double-clicking the app just opens the browser and nothing else happens.**
The app is already running in another window. Use that one, or click **Quit** and reopen.

**Mac: "Open Anyway" never appears in Privacy & Security.**
Use the [Terminal commands](#alternative-open-it-from-terminal) instead.

**Mac: the app opens, then immediately closes.**
Make sure you unzipped it first; don't run it from inside the zip preview. Then try the
Terminal command above.

**Windows: nothing happens when I double-click.**
Check **Protection history** in Windows Security (see above); antivirus may have blocked it.

**Anything else:** note what you clicked and the exact message, and ask your instructor.

---

## Removing the app when you're done

Removing the app takes two parts: the app itself, and the folder where it keeps your
settings, API keys, collected data, and log.

**Before you delete anything:** the data folder holds your exports, including any
`identifiable` folders and `corpus_identified.csv` files with real names. Your IRB protocol
or course policy may say how long to keep research data and how to destroy it. Copy
anything you must keep to its approved location first; then delete the rest.

### Mac

1. **Quit the app** (Quit button on its page, or close its Terminal window).
2. **Delete the app:** drag `social-media-data-gathering.app` (in Downloads or Applications)
   to the Trash. Also delete the downloaded `.zip` if it's still in Downloads.
3. **Delete the data folder.** It's hidden, so either:
   - In Finder, press **Command + Shift + G**, type `~/.social_media_data_gathering`, press
     Return, go up one level, and drag the `.social_media_data_gathering` folder to the
     Trash; or
   - Run this in Terminal (it permanently deletes the folder and everything in it):
     ```
     rm -rf ~/.social_media_data_gathering
     ```
4. **Empty the Trash** (right-click the Trash icon > Empty Trash) so the files are actually
   removed.

### Windows

1. **Quit the app** (Quit button on its page, or close its console window).
2. **Delete the app:** delete `social-media-data-gathering-windows.exe` from wherever you
   saved it (usually Downloads).
3. **Delete the data folder:** press **Windows key + R**, type
   `%USERPROFILE%\.social_media_data_gathering`, and press Enter. In the File Explorer
   window that opens, go up one level and delete the `.social_media_data_gathering` folder.
   Or run this in PowerShell (it permanently deletes the folder and everything in it):
   ```
   Remove-Item -Recurse -Force "$env:USERPROFILE\.social_media_data_gathering"
   ```
4. **Empty the Recycle Bin** so the files are actually removed.

### Also clean up

- **Exports you moved elsewhere:** zip files and `_identified` folders you copied out of the
  app's folder aren't removed by the steps above. Delete them according to your protocol.
- **R model cache:** if you ran `examples/starter_analysis.R`, it downloaded a language model
  for parsing. Remove it by running this in R:
  ```
  unlink(tools::R_user_dir("smdg", "cache"), recursive = TRUE)
  ```
- **Revoke your keys**, so they can't be used if a copy survives somewhere:
  - **OpenRouter:** sign in at [openrouter.ai](https://openrouter.ai), open **Keys**, and
    delete the key you used for class.
  - **Reddit:** at <https://www.reddit.com/prefs/apps>, click **delete app** on the app you
    created.
  - **Bluesky:** in Bluesky, go to **Settings > Privacy and security > App passwords** and
    delete the app password you created.
- **Mac only:** the "Open Anyway" approval you gave in Privacy & Security goes away on its own
  once the app is deleted. Nothing to undo.

