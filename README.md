## Getting Started

### Prerequisites
To run this project, your computer needs to interface with an Android environment using the following tools:
* **Android SDK Platform Tools (ADB):** The Android Debug Bridge acts as a command line remote control to automate screenshots and system changes on the test device.
* **UIAutomatorViewer:** A GUI tool included in the Android SDK used to inspect layout bounding boxes and extract XML structural trees from the active mobile screen.

### Local Setup
1. Download and install **Android Studio** to automatically configure the Android SDK and platform tools. **Link**: https://developer.android.com/studio
2. Enable **USB Debugging** on your physical test device, or launch a Virtual Device (Emulator) via the Android Studio Device Manager. **important** for now just use the emulator
3. Verify the connection by opening your terminal and running:
* **For Mac or Linux Terminals:**
  ```bash
  adb devices