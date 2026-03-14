# pyGround（无人机地面站）

无人机地面站 PyQt 端：通过 **UDP（MAVLink/JSON）** 或 **串口** 接收数据，在地图上显示、入库、日志、报警、3D 轨迹与姿态/状态显示。

## 项目结构

```
pyGround/
├── core/              # 核心功能模块
│   ├── __init__.py
│   ├── database.py    # 数据库操作
│   ├── geo_utils.py   # 地理坐标工具
│   ├── i18n.py        # 国际化支持
│   ├── mavlink_parser.py  # MAVLink协议解析
│   ├── parser.py      # 通用数据解析
│   ├── serial_client.py   # 串口客户端
│   └── udp_client.py      # UDP客户端
├── data/              # 数据目录
│   └── drones.db      # SQLite数据库
├── logs/              # 日志目录
│   ├── screenshots/   # 截图保存目录
│   ├── app.log        # 应用日志
│   └── raw_*.log      # 原始数据日志
├── map/               # 地图相关
│   ├── __init__.py
│   ├── index.html     # 地图HTML
│   └── map_widget.py  # 地图组件
├── scripts/           # 脚本工具
│   └── analyze_raw_log.py  # 日志分析脚本
├── ui/                # UI组件
│   ├── __init__.py
│   ├── attitude_indicator.py  # 姿态指示器
│   ├── main_window.py  # 主窗口
│   └── trajectory_3d_widget.py  # 3D轨迹组件
├── README.md          # 项目说明
├── config.yaml        # 配置文件
├── main.py            # 主入口
└── requirements.txt   # 依赖包
```

## 依赖

```bash
pip install -r requirements.txt
# 即：PyQt6 PyQt6-WebEngine PyYAML pyserial pymavlink matplotlib
```

## 运行

- **UDP（MAVLink）**：先运行 pySimulation（发送 MAVLink），在 pyGround 中点「连接」，填 `127.0.0.1`、端口 `8888`，即可收到连续轨迹与姿态。
- **UDP（JSON）**：若数据源发送以 `{` 开头的 JSON，地面站会按行解析兼容。
- **串口**：选择串口、波特率（通常 115200），点「连接串口」。串口连接真实飞控时，地面站会先发 **GCS HEARTBEAT** 让飞控识别地面站，约 1.5 秒后再发数据流请求；在 `config.yaml` 中可配置：
  - `serial_request_stream: true`（默认）连接后自动发送 REQUEST_DATA_STREAM；
  - `serial_stream_rate_hz: 5` 请求的遥测帧率 (Hz)；
  - `serial_use_set_message_interval: true`（默认）与 `serial_message_interval_us: 200000` 使用 SET_MESSAGE_INTERVAL，真实飞控推荐开启；
  - `serial_format_cmd` 仍可用于上电后发送自定义格式指令。
- **链接统计**：顶部「链接统计」打开对话框，查看下载/上传字节与包数、速率、丢包、质量、包间最大间隔及 Mavlink 2 / Signing 状态，可点击「重置」清零。

## 配置

编辑 `config.yaml`：UDP 地址/端口、默认地图中心（上海）、日志与数据目录、`language: zh|en`（界面语言）、串口 MAVLink 请求与帧率（见上）、各地图 Key 等。

## 功能特性

- **协议支持**：UDP 优先解析 MAVLink 二进制（HEARTBEAT、GLOBAL_POSITION_INT、ATTITUDE、VFR_HUD 等），否则按 JSON 解析。
- **地图显示**：底图切换（OpenStreetMap、Bing、高德、百度、Google）、无人机位置与轨迹、报警圆、弹窗（含姿态与状态）。
- **状态与姿态**：右侧「无人机状态」面板显示飞行模式、解锁状态、电量、Roll/Pitch/Yaw；地图弹窗同。
- **3D 轨迹**：按钮「3D 轨迹」打开子窗口，WGS84 转局部 ENU 后以 matplotlib 绘制高度维轨迹。
- **语言支持**：顶部「语言」下拉可切换 中文 / English，配置持久化。
- **数据存储**：数据写入 SQLite `data/drones.db`，支持检索和轨迹回放。
- **日志系统**：应用日志和原始数据日志，支持查看和分析。
- **链接统计**：实时显示连接状态、数据传输速率、丢包率等。
- **截图功能**：支持地图截图保存。
- **主题切换**：支持深色/浅色主题。
- **姿态显示**：支持经典圆盘和PFD两种姿态显示模式。

## 控制功能

- **解锁/锁定**：控制无人机解锁或锁定。
- **起飞**：发送起飞命令。
- **降落**：发送降落命令。
- **返航**：发送返航命令。

## 技术特点

- **多协议支持**：同时支持 MAVLink 二进制协议和 JSON 协议。
- **多连接方式**：支持 UDP 和串口连接。
- **实时数据处理**：主线程处理 UI 更新，子线程处理数据接收。
- **地理坐标转换**：支持 WGS84 到 ENU 坐标系转换。
- **国际化**：支持中英文界面切换。
- **模块化设计**：核心功能与 UI 分离，便于扩展和维护。

## 使用示例

1. **连接模拟器**：
   - 启动 pySimulation 模拟器
   - 在 pyGround 中点击「连接」按钮
   - 选择 UDP 模式，填写 IP `127.0.0.1` 和端口 `8888`
   - 点击「确定」连接

2. **连接真实飞控**：
   - 通过串口连接飞控
   - 在 pyGround 中点击「连接」按钮
   - 选择串口模式，选择对应的串口和波特率
   - 点击「确定」连接

3. **查看轨迹**：
   - 连接成功后，地图上会显示无人机的实时位置和轨迹
   - 点击「3D 轨迹」按钮查看三维轨迹

4. **查看记录**：
   - 点击「记录检索」按钮查看历史轨迹记录
   - 选择记录后点击「轨迹回放」查看历史轨迹

## 故障排除

- **连接失败**：检查网络连接或串口连接是否正常。
- **无数据**：检查数据源是否正常发送数据，或检查协议是否正确。
- **地图加载失败**：检查网络连接，或在 `config.yaml` 中配置正确的地图 Key。
- **姿态显示异常**：检查数据源是否发送了正确的姿态数据。

## 开发说明

- **核心模块**：`core/` 目录包含所有核心功能，如数据解析、网络通信等。
- **UI 模块**：`ui/` 目录包含所有 UI 组件，如主窗口、姿态指示器等。
- **地图模块**：`map/` 目录包含地图相关功能，如地图显示等。
- **配置文件**：`config.yaml` 包含所有可配置项，如网络设置、地图设置等。

## 许可证

本项目采用 MIT 许可证。

## 贡献

欢迎提交 Issue 和 Pull Request 来改进本项目。