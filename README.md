# Metflix

![Status](https://img.shields.io/badge/status-active-brightgreen)
![Architecture](https://img.shields.io/badge/architecture-client--server-blue)
![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Stars](https://img.shields.io/github/stars/SnipeCope/metflix?style=social)
![Forks](https://img.shields.io/github/forks/SnipeCope/metflix?style=social)

Metflix is a self-hosted video streaming project with a separate backend service and web client.

It scans a categorized media library from disk, exposes it through a lightweight Python API, and renders a Netflix-style browser UI for playback, shuffle, continue-watching, history, and library management.

## Overview

The backend is treated as a standard server process and can run on:

- a local development machine
- a home server
- a VPS
- a dedicated server
- any other environment that can run Python and access the media library

The frontend is a separate web application process that talks to the backend over HTTP.

### Key Features

- Category and subcategory-based library browsing
- Randomized recommendations and shuffle filters
- Continue-watching and watch-history tracking
- Delete and auto-delete support
- Config-driven client/server setup
- Development domain support via `met.flix`
- Local and remote deployment compatibility

## Folder Structure

```text
metflix/
├── .gitignore
├── LICENSE
├── README.md
├── config.json
├── config.json.example
├── start.py
├── server/
│   ├── config.json
│   ├── config.json.example
│   └── server.py
└── static/
    ├── app.js
    ├── history.html
    ├── home.html
    ├── manage-watched.html
    └── styles.css
```

### Directory Purpose

| Path | Purpose |
| --- | --- |
| `setup.py` | Automatically set up configs |
| `start.py` | Starts the client-facing web app |
| `config.json` | Root configuration for the client/web process |
| `server/server.py` | Starts the backend media API |
| `server/config.json` | Backend configuration |
| `static/` | Browser assets: HTML, CSS, and JavaScript |

## Architecture

Metflix uses a standard client-server model.

### Components

| Component | Responsibility |
| --- | --- |
| Web client (`start.py`) | Serves the UI, handles sessions, and proxies video playback |
| Backend service (`server/server.py`) | Scans the library, streams media files, and handles server-side operations |

### Default Development Endpoints

| Service | Bind Address | Public Development Address |
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

No third-party Python packages are required.

### 2. Configure the Client

Fastest option:

```powershell
python setup.py
```

This utility:

- detects your local LAN IP
- prompts for a shared password
- creates missing config files
- updates both `config.json` and `server/config.json`

Manual option:

Copy or edit `config.json`:

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

### 3. Configure the Backend

Copy or edit `server/config.json`:

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

### 4. Run the Backend

```powershell
python server\server.py
```

### 5. Run the Web Client

Open a second terminal:

```powershell
python start.py
```

### 6. Open the App

After the hosts-file mapping is configured, use:

```text
http://met.flix:8000
```

### Example Local Workflow

```powershell
python server\server.py
python start.py
```

Then open:

```text
http://met.flix:8000
```

## Development Domain: `met.flix`

Metflix supports a custom development domain so the app can be accessed through a stable internal hostname instead of raw IP addresses.

### Windows Hosts File Setup

1. Open Notepad as Administrator.
2. Open:

```text
C:\Windows\System32\drivers\etc\hosts
```

3. Add:

```text
127.0.0.1 met.flix
```

4. Save the file.
5. Restart the browser if needed.

### Linux / macOS Hosts File Setup

Edit:

```bash
sudo nano /etc/hosts
```

Add:

```text
127.0.0.1 met.flix
```

### Using `met.flix` Across Devices

For shared LAN development, map `met.flix` to the server machine's LAN IP on each client machine instead of `127.0.0.1`.

Example:

```text
192.168.1.50 met.flix
```

## Configuration Guide

### Root `config.json`

| Field | Type | Description |
| --- | --- | --- |
| `client.host` | string | Bind address for `start.py` |
| `client.port` | number | Port for the web client |
| `client.public_host` | string | Public hostname shown in generated URLs |
| `server.url` | string | Base URL of the backend service |
| `server.device_hint` | string | Friendly label shown in the UI info panel |
| `auth.password` | string | Unlock password for the UI |

### `server/config.json`

| Field | Type | Description |
| --- | --- | --- |
| `server.host` | string | Bind address for `server/server.py` |
| `server.port` | number | Port for the backend API |
| `server.public_host` | string | Public hostname shown when the backend starts |
| `library.videos_root` | string | Root directory of the media library |

## Media Library Layout

The backend expects:

```text
Videos/
└── Main Category/
    └── Subcategory/
        ├── video-one.mp4
        └── video-two.mkv
```

## Usage

1. Start the backend service
2. Start the web client
3. Open `http://met.flix:8000`
4. Unlock the UI with the configured password
5. Browse the library and play videos

## Deployment Notes

Metflix can be deployed beyond local development.

### Local Machine

- Keep both services on the same host
- Use `127.0.0.1` bind addresses
- Use hosts-file mapping for `met.flix`

### VPS / Dedicated Server / Cloud

- Set backend `server.host` to `0.0.0.0` if it must listen externally
- Set client `client.host` to `0.0.0.0` if the UI should be served externally
- Set `client.public_host` and `server.public_host` to your real hostname or domain
- Set root `server.url` to the actual backend URL

## Troubleshooting

### The web client cannot connect to the backend

- Make sure `server/server.py` is running
- Verify `server.url` in `config.json`
- Verify the backend host and port in `server/config.json`

### `met.flix` does not resolve

- Confirm the hosts file entry exists
- Make sure the browser or terminal is using the updated hosts file
- On Windows, try flushing DNS:

```powershell
ipconfig /flushdns
```

### Port already in use

- Change `client.port` or `server.port`
- Keep the web client and backend on different ports

### Videos do not appear

- Confirm `library.videos_root` points to the correct path
- Confirm the media library uses the expected folder structure

## Publishing Checklist

- [ ] Replace or remove any temporary passwords
- [ ] Verify both config example files are up to date
- [ ] Add screenshots if desired
- [ ] Confirm the GitHub badges render correctly after publishing
