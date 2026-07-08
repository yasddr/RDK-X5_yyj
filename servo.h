#ifndef __SERVO_H
#define __SERVO_H

#include "main.h"
#include "tim.h"
#include "delay.h"

/* ---------- 舵机类型 ---------- */
#define SERVO_TYPE_180  0
#define SERVO_TYPE_270  1

/* ---------- 脉宽范围（标准 0.5ms ~ 2.5ms） ---------- */
#define SERVO_PULSE_MIN  500
#define SERVO_PULSE_MAX  2500

/* ---------- 根据类型获取最大角度 ---------- */
#define SERVO_ANGLE_MAX(type)  ((type) == SERVO_TYPE_270 ? 270.0f : 180.0f)

/* ---------- 角度 → 脉宽（自动适配类型） ---------- */
#define ANGLE_TO_PULSE(angle, type) \
    ((uint16_t)(SERVO_PULSE_MIN + (angle) * (SERVO_PULSE_MAX - SERVO_PULSE_MIN) / SERVO_ANGLE_MAX(type)))

/*==================== 基础初始化 ====================*/
void Servo_Init(uint8_t Angle1, uint8_t Angle2, uint8_t type1, uint8_t type2);
void Servo_Init_Single(uint8_t Angle, uint8_t channel, uint8_t type);

/*==================== 同步运动（可调速） ====================*/
void Servo_Move_Sync(float Angle1, uint8_t type1,
                     float Angle2, uint8_t type2,
                     uint16_t step_delay_ms);     // ← 步延时，你可以自己调

void Servo_Move_Single(float Angle, uint8_t channel, uint8_t type,
                       uint16_t step_delay_ms);

/*==================== 快捷函数（不需要每次写类型） ====================*/
void Servo_Init_270(uint8_t Angle1, uint8_t Angle2);
void Servo_Init_180(uint8_t Angle1, uint8_t Angle2);
void Servo_180(float Angle1, float Angle2, uint16_t step_delay_ms);
void Servo_270(float Angle1, float Angle2, uint16_t step_delay_ms);

#endif




























