# HDHomeRunWebUI

This is a solid project idea. Providing a lightweight, browser-based alternative to the native Silicon Dust application—especially with a focus on remote access—is something many in the self-hosted community look for.

Based on your project's goals and technical stack, here is a professional and clear description you can use for your GitHub **README.md** or the project **About** section.

---

**HDHomeRun Web UI: Live TV Anywhere**

This project provides a lightweight, Flask-based web interface for HDHomeRun Gateway devices (including Flex 4K, Connect, and Prime). It allows users to stream live OTA or Cable TV directly in a web browser, eliminating the need for the official Windows application and enabling viewing from anywhere in the world.

**Key Features**

* **Browser-Based Viewing:** Watch live TV directly in any modern desktop web browser without extra plugins.
* **Hardware Agnostic:** Works with any HDHomeRun Gateway device (OTA or CableCARD).
* **Remote Access:** Access your home cable or antenna feed from outside your local network (requires port forwarding).
* **Lightweight Backend:** Powered by Python and Flask for minimal resource usage.
* **Simple Setup:** Designed for ease of use—if you can run a Python script, you can host your own TV gateway.

**How It Works**

The application acts as a bridge between your HDHomeRun hardware and a web-based video player. By serving the stream through a Flask backend, it simplifies the handoff to the browser, making it possible to view your content on different networks or even from another country.

**Requirements**

* Python 3.x
* Flask
* An active HDHomeRun device on your network
* A desktop or laptop browser (Mobile support is currently limited due to codec/playback compatibility)

---

**A quick tip for your GitHub repository:**

Since you mentioned that mobile devices aren't playing back the video properly, you might want to add a **Known Limitations** or **Roadmap** section. This lets contributors know that mobile playback is an area where the project is looking to improve, and it prevents users from opening "bug" reports for a feature you're already aware of.

Would you like me to help you draft the specific installation commands for your README?
