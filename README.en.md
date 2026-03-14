# pyGround (Drone Ground Station)

A PyQt-based ground station for drones: receives data via **UDP (MAVLink/JSON)** or **serial port**, displays on map, stores in database, logs data, provides alerts, 3D trajectory and attitude/status display.

## Project Structure

```
pyGround/
├── core/              # Core functionality modules
│   ├── __init__.py
│   ├── database.py    # Database operations
│   ├── geo_utils.py   # Geographical coordinate utilities
│   ├── i18n.py        # Internationalization support
│   ├── mavlink_parser.py  # MAVLink protocol parser
│   ├── parser.py      # General data parser
│   ├── serial_client.py   # Serial port client
│   └── udp_client.py      # UDP client
├── data/              # Data directory
│   └── drones.db      # SQLite database
├── logs/              # Log directory
│   ├── screenshots/   # Screenshot directory
│   ├── app.log        # Application log
│   └── raw_*.log      # Raw data logs
├── map/               # Map-related files
│   ├── __init__.py
│   ├── index.html     # Map HTML
│   └── map_widget.py  # Map widget
├── scripts/           # Utility scripts
│   └── analyze_raw_log.py  # Log analysis script
├── ui/                # UI components
│   ├── __init__.py
│   ├── attitude_indicator.py  # Attitude indicator
│   ├── main_window.py  # Main window
│   └── trajectory_3d_widget.py  # 3D trajectory widget
├── README.md          # Project documentation
├── config.yaml        # Configuration file
├── main.py            # Main entry point
└── requirements.txt   # Dependencies
```

## Dependencies

```bash
pip install -r requirements.txt
# Includes: PyQt6 PyQt6-WebEngine PyYAML pyserial pymavlink matplotlib
```

## Running

- **UDP (MAVLink)**：First run pySimulation (sending MAVLink), then in pyGround click "Connect", enter `127.0.0.1` and port `8888` to receive continuous trajectory and attitude data.
- **UDP (JSON)**：If the data source sends JSON starting with `{`, the ground station will parse it line by line.
- **Serial Port**：Select serial port and baud rate (usually 115200), click "Connect Serial". When connecting to a real flight controller, the ground station will first send **GCS HEARTBEAT** for the flight controller to identify the ground station, then send data stream requests after about 1.5 seconds. Configurable in `config.yaml`:
  - `serial_request_stream: true` (default) automatically sends REQUEST_DATA_STREAM after connection;
  - `serial_stream_rate_hz: 5` requested telemetry frame rate (Hz);
  - `serial_use_set_message_interval: true` (default) and `serial_message_interval_us: 200000` use SET_MESSAGE_INTERVAL, recommended for real flight controllers;
  - `serial_format_cmd` can still be used to send custom format commands after power-up.
- **Link Statistics**：Click "Link Statistics" at the top to open a dialog showing download/upload bytes and packets, rate, packet loss, quality, maximum inter-packet interval, and Mavlink 2 / Signing status. Click "Reset" to clear.

## Configuration

Edit `config.yaml`：UDP address/port, default map center (Shanghai), log and data directories, `language: zh|en` (interface language), serial port MAVLink requests and frame rate (see above), various map keys, etc.

## Features

- **Protocol Support**：UDP prioritizes parsing MAVLink binary (HEARTBEAT, GLOBAL_POSITION_INT, ATTITUDE, VFR_HUD, etc.), otherwise parses JSON.
- **Map Display**：Base map switching (OpenStreetMap, Bing, Gaode, Baidu, Google), drone position and trajectory, alert circles, pop-ups (including attitude and status).
- **Status and Attitude**：Right-side "Drone Status" panel displays flight mode, arming status, battery level, Roll/Pitch/Yaw; same in map pop-ups.
- **3D Trajectory**：Click "3D Trajectory" button to open a sub-window, converting WGS84 to local ENU and plotting height-dimensional trajectory with matplotlib.
- **Language Support**：Top "Language" dropdown can switch between Chinese / English, configuration persists.
- **Data Storage**：Data is written to SQLite `data/drones.db`, supporting retrieval and trajectory playback.
- **Logging System**：Application logs and raw data logs, supporting viewing and analysis.
- **Link Statistics**：Real-time display of connection status, data transfer rate, packet loss rate, etc.
- **Screenshot Function**：Supports map screenshot saving.
- **Theme Switching**：Supports dark/light themes.
- **Attitude Display**：Supports both classic dial and PFD attitude display modes.

## Control Functions

- **Arm/Disarm**：Control drone arming or disarming.
- **Takeoff**：Send takeoff command.
- **Land**：Send land command.
- **Return to Launch**：Send return to launch command.

## Technical Features

- **Multi-protocol Support**：Supports both MAVLink binary protocol and JSON protocol.
- **Multi-connection Methods**：Supports UDP and serial port connections.
- **Real-time Data Processing**：Main thread handles UI updates, sub-threads handle data reception.
- **Geographic Coordinate Conversion**：Supports WGS84 to ENU coordinate system conversion.
- **Internationalization**：Supports Chinese and English interface switching.
- **Modular Design**：Core functionality separated from UI, easy to extend and maintain.

## Usage Examples

1. **Connect to Simulator**：
   - Start pySimulation simulator
   - Click "Connect" button in pyGround
   - Select UDP mode, enter IP `127.0.0.1` and port `8888`
   - Click "OK" to connect

2. **Connect to Real Flight Controller**：
   - Connect to flight controller via serial port
   - Click "Connect" button in pyGround
   - Select serial port mode, choose corresponding serial port and baud rate
   - Click "OK" to connect

3. **View Trajectory**：
   - After successful connection, the map will display the drone's real-time position and trajectory
   - Click "3D Trajectory" button to view 3D trajectory

4. **View Records**：
   - Click "Record Search" button to view historical trajectory records
   - Select a record and click "Trajectory Playback" to view historical trajectory

## Troubleshooting

- **Connection Failure**：Check network connection or serial port connection.
- **No Data**：Check if data source is sending data correctly, or check if protocol is correct.
- **Map Loading Failure**：Check network connection, or configure correct map keys in `config.yaml`.
- **Attitude Display Abnormal**：Check if data source is sending correct attitude data.

## Development Notes

- **Core Modules**：`core/` directory contains all core functionality, such as data parsing, network communication, etc.
- **UI Modules**：`ui/` directory contains all UI components, such as main window, attitude indicator, etc.
- **Map Modules**：`map/` directory contains map-related functionality, such as map display, etc.
- **Configuration File**：`config.yaml` contains all configurable items, such as network settings, map settings, etc.

## License

This project is licensed under the MIT License.

## Contribution

Welcome to submit Issues and Pull Requests to improve this project.