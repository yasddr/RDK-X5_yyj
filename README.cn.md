---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 21aff1279fab7779bfd6becf8d6b0dd7_6c7fb77d7af111f1aac35254006c9bbf
    ReservedCode1: Jj+NOftE0aE4+uGRjbXe6tOYPXl4XporCAnxu6ypoTW1osEmWu4px7VYvjX6StTD4BM38gy4XrGHRcVNGqLribsa8nxnUryYIZcNIH50L2xpJFPURkJSgxXwIY4ZHx6N9f13Y2qmshDw9h2qXbn1vlryOnLcK7dVJqq1MD/0WfirzKzfK8WZbTVLs0g=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 21aff1279fab7779bfd6becf8d6b0dd7_6c7fb77d7af111f1aac35254006c9bbf
    ReservedCode2: Jj+NOftE0aE4+uGRjbXe6tOYPXl4XporCAnxu6ypoTW1osEmWu4px7VYvjX6StTD4BM38gy4XrGHRcVNGqLribsa8nxnUryYIZcNIH50L2xpJFPURkJSgxXwIY4ZHx6N9f13Y2qmshDw9h2qXbn1vlryOnLcK7dVJqq1MD/0WfirzKzfK8WZbTVLs0g=
---

# 基于RDK X5的居家健康边缘服务一体化系统

## 项目简介

本项目以地平线RDK X5为家庭侧边缘计算节点，外接自研STM32协处理器，集成MLX90614红外测温、SGP30气体传感、C100摄像头、二自由度电动云台及USB音频模块，在嵌入式Linux下实现跌倒智能监测、AI语音交互、体温筛查、空气质量检测与云台实时追踪等功能。系统将感知、推理、预警全链路下沉至终端本地，从架构层面切断视频外流路径，兼顾隐私保护与实时性，为智慧居家养老提供了一套可部署、可演示的边缘智能解决方案。

## 项目背景

我国60岁以上人口已超2.9亿，近半数处于独居或空巢状态。跌倒是老年人意外伤害致死的首位原因，而更残酷的是——很多意外发生后，无人知晓。传统云端监控方案将视频流上传至远端处理，存在隐私泄露风险与网络延迟瓶颈，难以在安全性与时效性之间取得平衡。

## 系统架构

系统采用 **"主控—传感器—外设"三层硬件架构**与 **"感知层—推理层—告警层—通信层"四层软件架构**：

```
                        ┌─────────────────────┐
                        │  家属手机 / 社区平台   │
                        └──────────┬──────────┘
                                   │ MQTT / HTTP
┌──────────────────────────────────┴──────────────────────────────┐
│                         RDK X5 主控                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐    │
│  │ 视频采集  │→│ YOLO推理  │→│ 规则引擎  │→│  预警管理     │    │
│  │ (OpenCV) │  │ (BPU加速) │  │ (多帧判定) │  │ (三级状态机)  │    │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────┘    │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────────────────┐  │
│  │ 语音交互  │  │ 云台追踪  │  │  通信管理 (UART/MQTT/HTTP)   │  │
│  │(TTS/ASR) │  │(坐标映射) │  │                              │  │
│  └──────────┘  └──────────┘  └──────────────────────────────┘  │
└────────────────────────┬───────────────────────────────────────┘
                         │ UART (115200bps)
┌────────────────────────┴───────────────────────────────────────┐
│                      STM32F103 协处理器                          │
│  ┌──────────────────┐  ┌──────────────────┐                     │
│  │  传感器采集        │  │  执行控制          │                    │
│  │  MLX90614 / SGP30 │  │  云台PID / 声光告警 │                    │
│  └──────────────────┘  └──────────────────┘                     │
└─────────────────────────────────────────────────────────────────┘
```

## 硬件组成

| 类别 | 器件 | 说明 |
|------|------|------|
| 主控单元 | 地瓜派 RDK X5 | Sunrise 5芯片，八核A55，BPU 10 TOPS，4GB LPDDR4 |
| 协处理器 | STM32F103C6T6 | ARM Cortex-M3，自研扩展板，传感器采集与执行控制 |
| 摄像头 | C100 USB摄像头 | 640×480@30FPS，USB即插即用 |
| 云台 | 双舵机二自由度电动云台 | 水平/俯仰各360°，大扭矩舵机驱动 |
| 测温传感 | MLX90614 | 非接触式红外测温，I2C接口 |
| 气体传感 | SGP30 | TVOC与eCO₂检测，I2C接口 |
| 音频模块 | USB免驱声卡 | TTS语音播报与麦克风拾音 |
| 告警模块 | LED + 蜂鸣器 | GPIO驱动，声光分级告警 |

## 核心功能

- **跌倒智能监测**：BPU加速YOLO人体检测 + 多帧规则引擎（高宽比、纵向位移、静止时长三重判据），≥25FPS实时推理，跌倒识别准确率≥90%
- **三级分级预警**：一级语音询问→二级声光告警→三级MQTT远程推送，平衡即时性与打扰度
- **AI语音交互**：TTS场景化语音播报，引导老人确认状态
- **云台实时追踪**：YOLO检测坐标映射为舵机控制量，PID驱动双舵机360°人体跟随
- **体温筛查**：MLX90614非接触测温，异常自动告警
- **空气质量监测**：SGP30实时检测TVOC与eCO₂
- **日志与存证**：异常事件SQLite存储，支持可选图像片段留存
- **远程推送**：MQTT协议将告警推送至家属手机或社区管理终端

## 技术特点

1. **端侧全闭环隐私保护**：视频数据全程不离开本地，仅向外推送结构化告警信号
2. **BPU-YOLO与规则引擎协同**：深度模型做感知，规则引擎做决策，低算力高鲁棒性
3. **主从异构协同架构**：RDK X5承载AI推理与通信，STM32负责实时采集与执行
4. **视觉伺服云台追踪**：YOLO检测驱动PID闭环控制，消除固定视角盲区
5. **模块化扩展设计**：感知层、推理层、告警层、通信层解耦，预留标准化功能接口

## 创新点

- 提出"终端全闭环"边缘服务范式，将感知、推理、预警全链路下沉至RDK X5家庭节点
- 设计BPU加速YOLO与多帧时序规则引擎协同的轻量级跌倒检测方案
- 构建三级递进预警与本地声光语音多模态交互机制
- 视觉伺服二维云台实时追踪，单路摄像头覆盖大范围活动空间
- 多源感知一体集成（跌倒检测 + 体温 + 空气质量 + 语音 + 追踪）

## 主要性能指标

| 指标 | 数值 |
|------|------|
| 人体检测帧率 | ≥25 FPS（BPU加速） |
| 跌倒识别准确率 | ≥90% |
| 跌倒检测响应延迟 | ≤3秒（含多帧判定） |
| 端侧推理功耗 | ≤10W |
| 本地声光告警响应 | ≤500ms |
| MQTT远程推送延迟 | ≤1秒（局域网） |
| 云台跟踪角度精度 | ≤±1° |
| 有效检测距离 | 1~6米 |
| 运行稳定性 | ≥72小时连续无故障 |

## 快速开始

### 环境要求

- RDK X5开发板（Ubuntu 22.04）
- STM32F103C6T6协处理器扩展板
- Python 3.8+
- 地平线BPU工具链

### 硬件连接

1. C100摄像头通过USB连接RDK X5
2. USB音频模块连接RDK X5 USB口
3. STM32扩展板通过UART连接RDK X5 40PIN接口（TX/RX）
4. MLX90614与SGP30连接至STM32 I2C总线
5. 双舵机云台连接至STM32 PWM输出口
6. LED蜂鸣器连接至STM32 GPIO口

### 部署步骤

```bash
# 1. 克隆项目
git clone <repo-url>
cd elderly-home-edge-service

# 2. 安装Python依赖
pip install -r requirements.txt

# 3. 部署YOLO模型到BPU
python tools/deploy_model.py --model yolov5s --quantize int8

# 4. 烧录STM32固件
# 使用Keil/STM32CubeIDE编译并烧录 stm32_firmware/ 目录下工程

# 5. 启动系统
python main.py --camera 0 --uart /dev/ttyS3
```

### 通信协议

RDK X5与STM32之间采用自定义UART帧协议，波特率115200bps，帧格式：

```
┌────────┬────────┬────────┬────────┬──────────┬────────┐
│ 0xAA   │ 0x55   │ 类型码  │ 数据长度 │  数据负载  │ CRC8   │
│ 帧头1   │ 帧头2   │ 1B     │ 1B     │  nB      │ 1B     │
└────────┴────────┴────────┴────────┴──────────┴────────┘
```

上行帧类型：`0x01`体温 / `0x02`空气质量 / `0x03`批量数据 / `0xFF`心跳
下行命令码：`0x01`云台控制 / `0x02`告警控制 / `0x03`传感器查询

## 可扩展之处

- 感知扩展：接入毫米波雷达、红外热释电等多模态传感器，覆盖卧室等隐私敏感区域
- 检测增强：支持多目标跟踪与多人交叉遮挡处理，扩展多姿态分类（弯腰、徘徊等）
- 通信升级：扩展NB-IoT/4G Cat.1模组，实现无WiFi环境下的远程告警
- 服务叠加：用药提醒定时播报、日常活动量统计与作息规律分析
- 场景泛化：从独居家庭向养老机构多节点组网、医院病房看护等场景迁移

## 项目结构

```
elderly-home-edge-service/
├── main.py                 # 系统主入口
├── config/                 # 配置文件
│   └── settings.yaml
├── modules/
│   ├── camera/             # 视频采集模块
│   ├── detector/           # YOLO推理模块（BPU）
│   ├── rule_engine/        # 多帧规则引擎
│   ├── alert/              # 三级预警管理
│   ├── tracker/            # 云台追踪控制
│   ├── voice/              # 语音交互（TTS/ASR）
│   ├── sensor/             # 传感器数据管理
│   ├── logger/             # 事件日志与存证
│   └── communication/      # UART/MQTT/HTTP通信
├── stm32_firmware/         # STM32协处理器固件
├── models/                 # YOLO模型文件
├── tools/                  # 部署与测试工具
├── docs/                   # 文档
└── requirements.txt
```

## 参考资料

- [地平线RDK X5开发文档](https://developer.d-robotics.cc)
- REDMON J, FARHADI A. YOLOv3: an incremental improvement. arXiv:1804.02767, 2018.
- SHI W, CAO J, ZHANG Q, et al. Edge computing: vision and challenges. IEEE Internet of Things Journal, 2016, 3(5): 637-646.
- CHUTIMAWATTANAKUL P, SAMANPIBOON P. Fall detection for the elderly using YOLOv4 and LSTM. ECTI-CON, 2022.
- Stand-alone M. MQTT Version 3.1.1. OASIS Standard, 2014.

## 许可证

本项目仅用于学术研究与竞赛展示，未经许可不得用于商业用途。
*（内容由AI生成，仅供参考）*
