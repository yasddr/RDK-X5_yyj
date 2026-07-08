#include "servo.h"
#include "math.h"
#include "main.h"
#include "delay.h"

/* 每个通道的当前位置（索引 1~4） */
static float Current_Angle[5] = {0};
static float Target_Angle[5] = {0};

/*==================================================================
 * 初始化两个舵机（可分别指定 180° / 270°）
 *==================================================================*/
void Servo_Init(uint8_t Angle1, uint8_t Angle2, uint8_t type1, uint8_t type2)
{
    Servo_Init_Single(Angle1, 1, type1);
    Servo_Init_Single(Angle2, 2, type2);
}

/*==================================================================
 * 初始化单个通道
 *==================================================================*/
void Servo_Init_Single(uint8_t Angle, uint8_t channel, uint8_t type)
{
    if (Angle <= SERVO_ANGLE_MAX(type))
    {
        uint16_t pulse = ANGLE_TO_PULSE(Angle, type);

        switch (channel)
        {
        case 1:
            __HAL_TIM_SET_COMPARE(&htim1, TIM_CHANNEL_1, pulse);
            HAL_TIM_PWM_Start(&htim1, TIM_CHANNEL_1);   // 只启动一次即可
            break;
        case 2:
            __HAL_TIM_SET_COMPARE(&htim1, TIM_CHANNEL_2, pulse);
            HAL_TIM_PWM_Start(&htim1, TIM_CHANNEL_2);
            break;
        case 3:
            __HAL_TIM_SET_COMPARE(&htim1, TIM_CHANNEL_3, pulse);
            HAL_TIM_PWM_Start(&htim1, TIM_CHANNEL_3);
            break;
        case 4:
            __HAL_TIM_SET_COMPARE(&htim1, TIM_CHANNEL_4, pulse);
            HAL_TIM_PWM_Start(&htim1, TIM_CHANNEL_4);
            break;
        default:
            break;
        }

        Current_Angle[channel] = Angle;
        Target_Angle[channel] = Angle;
    }
}

/*==================================================================
 * 同步平滑移动两个舵机（阻塞式）
 *
 * 参数：
 *   Angle1, type1 : 通道1的目标角度和类型
 *   Angle2, type2 : 通道2的目标角度和类型
 *   step_delay_ms : 每一步的延时（ms）
 *                   ★ 推荐 20 ~ 50 ms ★
 *                   值越小越快，但太小会抽搐
 *==================================================================*/
void Servo_Move_Sync(float Angle1, uint8_t type1,
                     float Angle2, uint8_t type2,
                     uint16_t step_delay_ms)
{
    float start1 = Current_Angle[1];
    float start2 = Current_Angle[2];
    float target1 = Angle1;
    float target2 = Angle2;

    /* 角度限幅 */
    if (target1 < 0) target1 = 0;
    if (target1 > SERVO_ANGLE_MAX(type1)) target1 = SERVO_ANGLE_MAX(type1);
    if (target2 < 0) target2 = 0;
    if (target2 > SERVO_ANGLE_MAX(type2)) target2 = SERVO_ANGLE_MAX(type2);

    float diff1 = fabs(target1 - start1);
    float diff2 = fabs(target2 - start2);

    float max_diff = (diff1 > diff2) ? diff1 : diff2;
    if (max_diff < 0.01f) return;   // 不需要移动

    /* 步进角度（越小越平滑，但步数越多） */
    const float step = 0.5f;
    int steps = (int)(max_diff / step) + 1;

    float inc1 = diff1 / steps;
    float inc2 = diff2 / steps;
    if (target1 < start1) inc1 = -inc1;
    if (target2 < start2) inc2 = -inc2;

    float cur1 = start1;
    float cur2 = start2;

    for (int i = 0; i < steps; i++)
    {
        cur1 += inc1;
        cur2 += inc2;

        /* 防止过冲 */
        if ((inc1 > 0 && cur1 > target1) || (inc1 < 0 && cur1 < target1)) cur1 = target1;
        if ((inc2 > 0 && cur2 > target2) || (inc2 < 0 && cur2 < target2)) cur2 = target2;

        /* 更新两个通道的脉宽（同一个定时器，只需要一次延时） */
        __HAL_TIM_SET_COMPARE(&htim1, TIM_CHANNEL_1, ANGLE_TO_PULSE(cur1, type1));
        __HAL_TIM_SET_COMPARE(&htim1, TIM_CHANNEL_2, ANGLE_TO_PULSE(cur2, type2));

        delay_ms(step_delay_ms);   // ← 你可以调整这个值
    }

    /* 最后精确到位 */
    __HAL_TIM_SET_COMPARE(&htim1, TIM_CHANNEL_1, ANGLE_TO_PULSE(target1, type1));
    __HAL_TIM_SET_COMPARE(&htim1, TIM_CHANNEL_2, ANGLE_TO_PULSE(target2, type2));

    Current_Angle[1] = target1;
    Current_Angle[2] = target2;
    Target_Angle[1] = target1;
    Target_Angle[2] = target2;
}

/*==================================================================
 * 平滑移动单个舵机（阻塞式）
 *==================================================================*/
void Servo_Move_Single(float Angle, uint8_t channel, uint8_t type,
                       uint16_t step_delay_ms)
{
    if (channel < 1 || channel > 4) return;

    float start = Current_Angle[channel];
    float target = Angle;
    if (target < 0) target = 0;
    if (target > SERVO_ANGLE_MAX(type)) target = SERVO_ANGLE_MAX(type);

    float diff = fabs(target - start);
    if (diff < 0.01f) return;

    const float step = 0.5f;
    int steps = (int)(diff / step) + 1;
    float inc = diff / steps;
    if (target < start) inc = -inc;

    float cur = start;
    for (int i = 0; i < steps; i++)
    {
        cur += inc;
        if ((inc > 0 && cur > target) || (inc < 0 && cur < target)) cur = target;

        uint16_t pulse = ANGLE_TO_PULSE(cur, type);
        switch (channel)
        {
        case 1: __HAL_TIM_SET_COMPARE(&htim1, TIM_CHANNEL_1, pulse); break;
        case 2: __HAL_TIM_SET_COMPARE(&htim1, TIM_CHANNEL_2, pulse); break;
        case 3: __HAL_TIM_SET_COMPARE(&htim1, TIM_CHANNEL_3, pulse); break;
        case 4: __HAL_TIM_SET_COMPARE(&htim1, TIM_CHANNEL_4, pulse); break;
        }
        delay_ms(step_delay_ms);
    }

    /* 最后精确到位 */
    uint16_t pulse_f = ANGLE_TO_PULSE(target, type);
    switch (channel)
    {
    case 1: __HAL_TIM_SET_COMPARE(&htim1, TIM_CHANNEL_1, pulse_f); break;
    case 2: __HAL_TIM_SET_COMPARE(&htim1, TIM_CHANNEL_2, pulse_f); break;
    case 3: __HAL_TIM_SET_COMPARE(&htim1, TIM_CHANNEL_3, pulse_f); break;
    case 4: __HAL_TIM_SET_COMPARE(&htim1, TIM_CHANNEL_4, pulse_f); break;
    }

    Current_Angle[channel] = target;
    Target_Angle[channel] = target;
}

/*==================================================================
 * 快捷函数（省去 type 参数）
 *==================================================================*/
void Servo_Init_270(uint8_t Angle1, uint8_t Angle2)
{
    Servo_Init(Angle1, Angle2, SERVO_TYPE_270, SERVO_TYPE_270);
}

void Servo_Init_180(uint8_t Angle1, uint8_t Angle2)
{
    Servo_Init(Angle1, Angle2, SERVO_TYPE_180, SERVO_TYPE_180);
}

void Servo_180(float Angle1, float Angle2, uint16_t step_delay_ms)
{
    Servo_Move_Sync(Angle1, SERVO_TYPE_180, Angle2, SERVO_TYPE_180, step_delay_ms);
}

void Servo_270(float Angle1, float Angle2, uint16_t step_delay_ms)
{
    Servo_Move_Sync(Angle1, SERVO_TYPE_270, Angle2, SERVO_TYPE_270, step_delay_ms);
}