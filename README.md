# HDHomeRun Web UI & Unified Media Hub

A lightweight, Flask-based web interface for HDHomeRun Gateway devices (Flex 4K, Connect, and Prime) and local media libraries. This project allows you to stream live OTA/Cable TV and your personal movie/TV collection directly in a web browser, enabling high-quality viewing from anywhere in the world.

## Key Features

* **Unified Dashboard:** Access Live TV, Movies, and TV Shows from a single, dark-themed interface.
* **Hardware Agnostic:** Works with any HDHomeRun device (OTA or CableCARD).
* **Persistent Channel Mapping:** Includes a custom `KNOWN_LABELS` system to identify unencrypted "Ghost" channels that don't provide official guide data.
* **GPU-Powered Upscaling:** Optional real-time 1080p upscaling using NVIDIA CUDA (NVENC) for enhanced picture quality.
* **Remote Access:** Watch your home cable or antenna feed from outside your local network.
* **No Official App Required:** Eliminates the need for the HDHomeRun Windows/Mac desktop applications.

## How It Works

The application acts as a smart bridge between your HDHomeRun hardware, your local storage, and the web browser. By utilizing **FFmpeg** as a backend transcoder, it handles the handoff of raw MPEG-2/AC3 streams into browser-compatible formats, allowing for seamless playback on different networks.

## Requirements

### Software
* **Python 3.x:** Must be installed and added to your System PATH.
* **FFmpeg:** Required for stream transcoding and upscaling.
* **Python Dependencies:** ```bash
    pip install flask requests
    ```

### Hardware & Networking
* **HDHomeRun Device:** Active on your local network.
* **Apache/XAMPP (Optional but Recommended):** To handle Port 80/443 forwarding for a cleaner URL and easier remote access.
* **Port Forwarding:** * Forward **Port 80** (or your chosen Apache port) to the machine running the script.
    * The Python script itself defaults to **Port 5001** internally.

## Setup & Installation

1.  **Configure the Script:**
    Open `app.py` and update the following variables to match your environment:
    * `HDHR_IP`: Set this to your HDHomeRun's local IP address (e.g., `192.168.0.163`).
    * `MEDIA_DIR`: The path to your Movies and TV Shows.

2.  **Run the Server:**
    Navigate to the project folder and run:
    ```bash
    python app.py
    ```

3.  **Access the UI:**
    Open your browser and navigate to:
    * **Local:** `http://localhost:5001`
    * **Remote:** `http://your-public-ip` (Assuming Port 80 is forwarded to 5001 via Apache/XAMPP).

## Usage Instructions

* **Watching Live TV:** Click any channel in the "Live Tuner" sidebar. If a channel is unmapped, it will appear as "Unknown," but can still be streamed.
* **Mapping Channels:** To name "Unknown" channels, identify the content and add the channel number and name to the `KNOWN_LABELS` dictionary inside `app.py`.
* **GPU Upscaling:** For movies and TV shows, check the **"Live Master 1080p Upscaler"** box before clicking a file to trigger hardware-accelerated enhancement (Requires NVIDIA GPU).
* **Search:** Use the top search bar to instantly filter through hundreds of channels or local files.

## Important Notes

* **Mobile Support:** Browser-based playback on mobile devices may vary based on codec support. Desktop Chrome/Edge is recommended for the best experience.
* **CableCARDs:** For Prime users, this UI significantly simplifies navigating unencrypted "Clear QAM" channels that often lack proper labels on standard tuners.

---
*Disclaimer: This project is intended for personal use and private network streaming of content you already have legal access to.*
