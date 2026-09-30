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

### Alternative: one Terminal command

If you're comfortable with Terminal (Applications > Utilities > Terminal), this removes the
block in one step. Paste it, press Return, then double-click the app normally:

```
xattr -dr com.apple.quarantine ~/Downloads/social-media-data-gathering.app
```

If you moved the app to Applications, use this instead:

```
xattr -dr com.apple.quarantine /Applications/social-media-data-gathering.app
```

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
Use the [Terminal command](#alternative-one-terminal-command) instead.

**Mac: the app opens, then immediately closes.**
Make sure you unzipped it first; don't run it from inside the zip preview. Then try the
Terminal command above.

**Windows: nothing happens when I double-click.**
Check **Protection history** in Windows Security (see above); antivirus may have blocked it.

**Anything else:** note what you clicked and the exact message, and ask your instructor.
