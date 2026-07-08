#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
云台跟踪节点（最终稳定版）
- 适配 C100 摄像头（镜像画面修正）
- 单目标锁定（IoU 关联）
- 基于 FOV 的精确死区与比例控制
- 水平 ±60°、垂直 ±20° 软限幅
- 低通滤波 + 速率限制，运动丝滑
"""
import rclpy
from rclpy.node import Node
from ai_msgs.msg import PerceptionTargets
import serial
import time

# ========================= 硬件/模型参数 =========================
SERIAL_PORT = '/dev/ttyS1'          # 根据实际串口修改
BAUDRATE = 115200

# 模型实际推理尺寸（地平线跌倒模型通常为 960×544，若不是请修改）
IMAGE_WIDTH = 960
IMAGE_HEIGHT = 544

# 相机 FOV（C100 参数）
FOV_H = 112.0          # 水平视场角（度）
FOV_V = 80.0           # 垂直视场角（度）

# 舵机硬件极限（保护）
SERVO1_HW_MIN = 0
SERVO1_HW_MAX = 270
SERVO2_HW_MIN = 0
SERVO2_HW_MAX = 180

# 舵机中位（请根据你的云台实际中位修改！）
SERVO1_CENTER = 135    # 水平舵机中位
SERVO2_CENTER = 90     # 垂直舵机中位

# 运动幅度软限幅（你的要求：水平 ±60°，垂直 ±20°）
SERVO1_LIMIT = 60
SERVO2_LIMIT = 20

# ========================= 控制参数（可微调） =========================
# 像素与角度换算（理论值）
PIX_PER_DEG_H = IMAGE_WIDTH / FOV_H      # ≈ 8.57 像素/度
PIX_PER_DEG_V = IMAGE_HEIGHT / FOV_V     # ≈ 6.8  像素/度

# 死区（以“度”为单位，再换算成像素，建议 0.3°~0.8°）
DEADBAND_ANGLE = 0.5                    # 死区角度（度）
DEADBAND_X = int(PIX_PER_DEG_H * DEADBAND_ANGLE)   # 水平死区像素，当前约 4~5 px
DEADBAND_Y = int(PIX_PER_DEG_V * DEADBAND_ANGLE)   # 垂直死区像素，当前约 3~4 px

# 比例系数（像素误差 → 角度增量，已适配像素/度）
KP_X = 0.05            # 水平：1 像素误差 → 0.05° 转动
KP_Y = 0.06            # 垂直

# 一阶低通滤波系数（0~1，越大越慢但越平稳）
ANGLE_SMOOTH = 0.75    # 0.75 表示新值只占 25% 权重

# 每次发送的最大角度变化（度），防止指令跳变，提高丝滑感
MAX_ANGLE_STEP = 2.0   # 每次最多变化 2°，约等于角速度 30°/秒 @ 15Hz

# 发送频率
SEND_INTERVAL = 0.067  # 约 15 Hz

# 单目标锁定参数
LOCK_MISS_MAX = 25      # 连续丢失帧数（约 1.5 秒）后释放锁
MIN_IOU = 0.25          # 判断两框为同一人的最低 IoU，目标小可降低

# ========================= 串口辅助函数 =========================
def send_servo(ser, angle1, angle2, use_xor=False):
    """发送 4 字节帧到 STM32"""
    # 先硬件限幅
    angle1 = max(SERVO1_HW_MIN, min(SERVO1_HW_MAX, angle1))
    angle2 = max(SERVO2_HW_MIN, min(SERVO2_HW_MAX, angle2))

    low   = angle1 & 0xFF
    high  = (angle1 >> 8) & 0xFF
    byte2 = angle2 & 0xFF
    byte3 = low ^ high ^ byte2 if use_xor else 0x00

    ser.write(bytes([low, high, byte2, byte3]))

def box_center(roi):
    """从 roi 提取中心坐标及宽高"""
    rect = roi.rect
    cx = rect.x_offset + rect.width / 2.0
    cy = rect.y_offset + rect.height / 2.0
    return cx, cy, rect.width, rect.height

def iou(box1, box2):
    """计算两个边界框的交并比（IoU），box = (cx, cy, w, h)"""
    cx1, cy1, w1, h1 = box1
    cx2, cy2, w2, h2 = box2

    x1_min, x1_max = cx1 - w1/2, cx1 + w1/2
    y1_min, y1_max = cy1 - h1/2, cy1 + h1/2
    x2_min, x2_max = cx2 - w2/2, cx2 + w2/2
    y2_min, y2_max = cy2 - h2/2, cy2 + h2/2

    inter_xmin = max(x1_min, x2_min)
    inter_ymin = max(y1_min, y2_min)
    inter_xmax = min(x1_max, x2_max)
    inter_ymax = min(y1_max, y2_max)
    inter_area = max(0, inter_xmax - inter_xmin) * max(0, inter_ymax - inter_ymin)

    area1, area2 = w1 * h1, w2 * h2
    union = area1 + area2 - inter_area
    return inter_area / union if union > 0 else 0.0

# ========================= 主节点 =========================
class PanTiltTracker(Node):
    def __init__(self):
        super().__init__('pan_tilt_tracker')

        # --- 串口 ---
        try:
            self.ser = serial.Serial(port=SERIAL_PORT, baudrate=BAUDRATE,
                                     bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE,
                                     stopbits=serial.STOPBITS_ONE, timeout=0.1)
            self.get_logger().info(f'串口 {SERIAL_PORT} 打开成功')
        except Exception as e:
            self.get_logger().error(f'无法打开串口: {e}')
            raise e

        # --- 订阅 ---
        self.subscription = self.create_subscription(
            PerceptionTargets, '/hobot_falldown_detection', self.callback, 10)

        # --- 控制状态变量 ---
        # 当前滤波后的舵机角度
        self.servo1_angle = float(SERVO1_CENTER)
        self.servo2_angle = float(SERVO2_CENTER)
        self.last_send_time = time.time()
        self.last_sent_angle1 = float(SERVO1_CENTER)
        self.last_sent_angle2 = float(SERVO2_CENTER)

        # 锁定变量
        self.locked_box = None          # 锁定的框 (cx, cy, w, h)
        self.lock_miss_cnt = 0

        # 启动时归中
        send_servo(self.ser, SERVO1_CENTER, SERVO2_CENTER)
        self.get_logger().info(f'云台归中：水平={SERVO1_CENTER}°，垂直={SERVO2_CENTER}°')
        self.get_logger().info('云台跟踪节点启动（锁定 + 丝滑模式）')

    def callback(self, msg: PerceptionTargets):
        now = time.time()

        # -------- 1. 收集当前帧所有人体框 --------
        current_boxes = []   # 元素：(cx, cy, w, h)
        for target in msg.targets:
            if target.type != 'person':
                continue
            for roi in target.rois:
                if roi.type == 'body':
                    cx, cy, w, h = box_center(roi)
                    current_boxes.append((cx, cy, w, h))
                    break

        if not current_boxes:
            # 没检测到人，丢失计数
            self.lock_miss_cnt += 1
            if self.lock_miss_cnt > LOCK_MISS_MAX:
                self.locked_box = None
            return

        # -------- 2. 锁定逻辑（IoU 关联） --------
        target_center = None
        if self.locked_box is not None:
            # 已有锁定目标，在当前帧中找匹配框
            best_iou = MIN_IOU
            best_idx = -1
            for i, box in enumerate(current_boxes):
                iou_val = iou(self.locked_box, box)
                if iou_val > best_iou:
                    best_iou = iou_val
                    best_idx = i
            if best_idx >= 0:
                # 匹配成功，更新锁定框
                self.locked_box = current_boxes[best_idx]
                self.lock_miss_cnt = 0
                target_center = (current_boxes[best_idx][0], current_boxes[best_idx][1])
            else:
                # 匹配失败，丢失计数
                self.lock_miss_cnt += 1
                if self.lock_miss_cnt > LOCK_MISS_MAX:
                    self.get_logger().info('锁定目标丢失超时，释放锁')
                    self.locked_box = None
                # 保持原位，不更新 target_center
                return
        else:
            # 没有锁定目标 → 选择离图像中心最近的人
            img_cx, img_cy = IMAGE_WIDTH / 2.0, IMAGE_HEIGHT / 2.0
            best_dist = float('inf')
            best_box = None
            for box in current_boxes:
                cx, cy = box[0], box[1]
                dist = (cx - img_cx)**2 + (cy - img_cy)**2
                if dist < best_dist:
                    best_dist = dist
                    best_box = box
            if best_box is not None:
                self.locked_box = best_box
                self.lock_miss_cnt = 0
                target_center = (best_box[0], best_box[1])
                self.get_logger().info(f'锁定新目标 中心({best_box[0]:.0f},{best_box[1]:.0f})')

        if target_center is None:
            return

        # -------- 3. 偏移计算（镜像修正） --------
        img_cx = IMAGE_WIDTH / 2.0
        img_cy = IMAGE_HEIGHT / 2.0
        error_x = img_cx - target_center[0]   # C100 镜像，取反恢复真实方向
        error_y = target_center[1] - img_cy

        # 死区判断（实际像素死区）
        if abs(error_x) < DEADBAND_X and abs(error_y) < DEADBAND_Y:
            return

        # -------- 4. 比例控制 + 软限幅 --------
        raw_angle1 = self.servo1_angle + error_x * KP_X
        raw_angle2 = self.servo2_angle - error_y * KP_Y   # 注意符号：图像Y轴下为正，舵机可能相反

        # 软限幅（叠加于硬件保护之上）
        raw_angle1 = max(SERVO1_CENTER - SERVO1_LIMIT,
                         min(SERVO1_CENTER + SERVO1_LIMIT, raw_angle1))
        raw_angle2 = max(SERVO2_CENTER - SERVO2_LIMIT,
                         min(SERVO2_CENTER + SERVO2_LIMIT, raw_angle2))

        # -------- 5. 一阶低通滤波（丝滑关键） --------
        self.servo1_angle = ANGLE_SMOOTH * self.servo1_angle + (1 - ANGLE_SMOOTH) * raw_angle1
        self.servo2_angle = ANGLE_SMOOTH * self.servo2_angle + (1 - ANGLE_SMOOTH) * raw_angle2

        # -------- 6. 速率限制与发送 --------
        if now - self.last_send_time >= SEND_INTERVAL:
            # 限制此次相对上次发送的变化量
            delta1 = self.servo1_angle - self.last_sent_angle1
            delta2 = self.servo2_angle - self.last_sent_angle2

            if abs(delta1) > MAX_ANGLE_STEP:
                self.servo1_angle = self.last_sent_angle1 + MAX_ANGLE_STEP * (1 if delta1 > 0 else -1)
            if abs(delta2) > MAX_ANGLE_STEP:
                self.servo2_angle = self.last_sent_angle2 + MAX_ANGLE_STEP * (1 if delta2 > 0 else -1)

            # 最后的硬件保护
            self.servo1_angle = max(SERVO1_HW_MIN, min(SERVO1_HW_MAX, self.servo1_angle))
            self.servo2_angle = max(SERVO2_HW_MIN, min(SERVO2_HW_MAX, self.servo2_angle))

            try:
                send_servo(self.ser, int(self.servo1_angle), int(self.servo2_angle))
            except serial.SerialException as e:
                self.get_logger().error(f'串口发送失败: {e}')
                return

            # 更新记录
            self.last_sent_angle1 = self.servo1_angle
            self.last_sent_angle2 = self.servo2_angle
            self.last_send_time = now

        # 日志输出（避免刷屏，仅在发送时打印）
        self.get_logger().info(
            f'🎯 中心({target_center[0]:.0f},{target_center[1]:.0f}) '
            f'误差({error_x:.1f},{error_y:.1f}) '
            f'舵机1={self.servo1_angle:.1f}° 舵机2={self.servo2_angle:.1f}°')

    def __del__(self):
        if hasattr(self, 'ser') and self.ser.is_open:
            self.ser.close()
            self.get_logger().info('串口已关闭')

def main():
    rclpy.init()
    node = PanTiltTracker()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node.ser.is_open:
            node.ser.close()
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()