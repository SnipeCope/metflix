<div align="center">

![Logo](assets/MetflixIcon.png)

![Status](https://img.shields.io/badge/status-active-brightgreen)
![Architecture](https://img.shields.io/badge/architecture-client--server-blue)
![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Stars](https://img.shields.io/github/stars/SnipeCope/metflix?style=social)
![Forks](https://img.shields.io/github/forks/SnipeCope/metflix?style=social)

[![GitHub Release](https://img.shields.io/github/v/release/SnipeCope/metflix)](https://github.com/SnipeCope/metflix/tags)
</div>

Metflix is a self-hosted video streaming project with a separate backend service and web client.

It scans a categorized media library from disk, exposes it through a lightweight Python API, and renders a Netflix-style browser UI for playback, shuffle, continue-watching, history, and library management.



<div align="center">
    
## Showcase

![showcase1](assets/screenshots/showcase(1).gif)

</div>

## Quick Notes

- Metflix does NOT fully replicate Netflix's UI.
- Newest Release: [Click Here](https://github.com/SnipeCope/metflix/tags)
- Setup: [Click Here](https://github.com/SnipeCope/metflix/tree/main#setup)
- Troubleshooting: [Click Here](https://github.com/SnipeCope/metflix/tree/main#troubleshooting)
- [Custom Domain](https://github.com/SnipeCope/metflix/tree/main#development-domain-metflix): Made up domain using a local DNS resolver
- Also, dont use this for a piracy or illegal file sharing website pls

## Overview

The backend is treated as a standard server process and can run on any environment that can run Python and access the internet.
The frontend is a separate web application process that talks to the backend over HTTP.

### Key Features

- Category and subcategory-based library
- Randomized recommendations and shuffle filters
- Continue watching and watch history
- Delete and auto-delete already seen videos
- Fully customisable.
- Custom domain support (optional)
- Local and remote deployment compatibility

## Project Structure

```text
metflix/
├── .gitignore
├── LICENSE
├── README.md
├── config.json <-- configures the web app
├── config.json.example
├── setup.py <-- set ups the configs
├── start.py <-- starts the web app
├── server/
│   ├── config.json <-- configures the server
│   ├── config.json.example
│   └── server.py <-- starts up the server
└── static/
    └── web assets
```

### Default connection endpoints

| Service | Bind Address | Custom Domain Address |
| --- | --- | --- |
| Web client | `127.0.0.1:8000` | `http://met.flix:8000` |
| Backend service | `127.0.0.1:9000` | `http://met.flix:9000` |

## Setup

### 1. Requirements

- Python 3.10 or newer

Check your Python version:

```powershell
python --version
```

if you do not have python install it using these commands:

**Windows:** 
```powershell
winget install Python.Python.3.14
```

**MacOS:** 
```powershell
brew install python
```

**Linux:** 
```powershell
sudo apt install python-is-python3
```

**Termux:** 
```powershell
pkg install python
```
No third-party Python packages are required.

### 2. Download the newest [release](https://github.com/SnipeCope/metflix/tags).

**Git:**
```
git clone https://github.com/SnipeCope/metflix
```

### 3. Configure Metflix

Fastest option:

```powershell
python setup.py
```

This program:

- detects your IP automatically
- Asks for a password.
- creates config files (if they are missing)
- configures both `config.json` and `server/config.json`

Manual option:

Edit `config.json`:

```json
{
  "client": {
    "host": "127.0.0.1",
    "port": 8000,
    "public_host": "met.flix"
  },
  "server": {
    "url": "http://met.flix:9000",
    "device_hint": "Metflix backend service"
  },
  "auth": {
    "password": "CHANGE_ME"
  }
}
```

Edit `server/config.json`:

```json
{
  "server": {
    "host": "127.0.0.1",
    "port": 9000,
    "public_host": "met.flix"
  },
  "library": {
    "videos_root": "./Videos"
  },
  "auth": {
    "password": "CHANGE_ME"
  }
}
```

### 4. Run the server

```powershell
python server\server.py
```

### 5. Run the web app

Open a second terminal:

```powershell
python start.py
```

### 6. Setup a custom domain (optional)

Note: Skip this part if you don't understand or if you are just fine with ip addresses.

Click [Here](https://github.com/SnipeCope/metflix/tree/main#development-domain-metflix)

### 7. Open the App

After the hosts-file mapping is configured, use:

```text
http://met.flix:8000
```

If it doesn't work, you need to setup the custom [domain](https://github.com/SnipeCope/metflix/tree/main#development-domain-metflix) or try the url below (replace "IP" for the url shown when running `start.py`.)

```text
http://IP:8000
```

## Custom Domain

Metflix supports a custom domain so the app can be accessed through it instead of a IP address.

**Note:** You need to manually update every device to be able to access `met.flix`. If you are fine with an ip address, you do not need to use a 'custom domain'.

### Windows

1. Open File Explorer.
2. Type this on the address bar:

```text
C:\Windows\System32\drivers\etc\hosts
```

3. Add    :

```text
127.0.0.1 met.flix
```

4. Save the file.
5. Restart the browser if needed.

### Linux / macOS

Edit:

```bash
sudo nano /etc/hosts
```

Add:

```text
127.0.0.1 met.flix
```

### Using `met.flix` Across Devices

To use `met.flix` across different devices, you need to change the IP address to the server's LAN IP. Run `start.py` to get your server's LAN IP.

Example:

```text
192.168.1.50 met.flix
```

## Video Layout

The backend expects:

```text
Videos/
└── Main Category/
    └── Subcategory/
        ├── video-one.mp4
        └── video-two.mkv
```

The video folder is inside the server folder.

For example:

```text
Videos/
└── Cartoons/
    └── Ben 10/
        ├── ep1.mp4
        └── ep2.mkv
```

## Troubleshooting

### "The web client cannot connect to the backend"

- Make sure `server/server.py` is running
- Verify `server.url` in `config.json`
- Verify the backend host and port in `server/config.json`

### "`met.flix` does not resolve"

- Confirm the hosts file entry exists
- Make sure the browser or terminal is using the updated hosts file
- On Windows, try flushing DNS:

```powershell
ipconfig /flushdns
```

### "Port already in use"

- Change `client.port` or `server.port`
- Keep the web client and backend on different ports
- If you are using Termux, end the session and reinstall Termux.

### "Videos don't appear"

- Confirm `library.videos_root` points to the correct path
- Confirm the media library uses the expected folder structure
