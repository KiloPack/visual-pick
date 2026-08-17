/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : Main program body
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2026 STMicroelectronics.
  * All rights reserved.
  *
  * This software is licensed under terms that can be found in the LICENSE file
  * in the root directory of this software component.
  * If no LICENSE file comes with this software, it is provided AS-IS.
  *
  ******************************************************************************
  */
/* USER CODE END Header */
/* Includes ------------------------------------------------------------------*/
#include "main.h"
#include "tim.h"
#include "usart.h"
#include "gpio.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */

/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */
#define SERVO_NUT_US             1100U
#define SERVO_CENTER_US          1500U
#define SERVO_WASHER_US          1900U
#define SERVO_PULSE_MIN_US       SERVO_NUT_US
#define SERVO_PULSE_MAX_US       SERVO_WASHER_US

/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/

/* USER CODE BEGIN PV */
static uint8_t uart_rx_byte;
static volatile uint8_t uart_command;
static volatile uint8_t uart_command_pending;
static volatile uint8_t uart_rx_restart_required;
static uint8_t servo_pwm_started;
static const uint8_t system_ready_response[] = "SYSTEM READY\r\n";
/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
/* USER CODE BEGIN PFP */
static HAL_StatusTypeDef Servo_SetPulse(uint16_t pulse_us);
static void PWM_Start(void);
static void ProcessCommand(uint8_t command);
static void UART_SendMessage(const uint8_t *message, uint16_t length);
/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */
static HAL_StatusTypeDef Servo_SetPulse(uint16_t pulse_us)
{
  if ((pulse_us < SERVO_PULSE_MIN_US) ||
      (pulse_us > SERVO_PULSE_MAX_US))
  {
    return HAL_ERROR;
  }

  __HAL_TIM_SET_COMPARE(&htim2, TIM_CHANNEL_1, pulse_us);

  if (servo_pwm_started == 0U)
  {
    /* Keep PA0 quiet at startup; enable servo PWM on the first real command. */
    if (HAL_TIM_PWM_Start(&htim2, TIM_CHANNEL_1) != HAL_OK)
    {
      return HAL_ERROR;
    }
    servo_pwm_started = 1U;
  }

  return HAL_OK;
}

static void PWM_Start(void)
{
  /* TIM2_CH1 / PA0 starts lazily on the first command, so boot does not move
     the servo. TIM2_CH2 / PA1 remains disabled in the one-servo design. */
}

static void UART_SendMessage(const uint8_t *message, uint16_t length)
{
  (void)HAL_UART_Transmit(
      &huart1,
      (uint8_t *)message,
      length,
      100U);
}

static void ProcessCommand(uint8_t command)
{
  static const uint8_t center_response[] = "CENTER\r\n";
  static const uint8_t servo_nut_response[] = "SERVO:NUT\r\n";
  static const uint8_t servo_center_response[] = "SERVO:CENTER\r\n";
  static const uint8_t servo_washer_response[] = "SERVO:WASHER\r\n";
  static const uint8_t ch1_min_response[] = "CH1:1100us\r\n";
  static const uint8_t ch1_center_response[] = "CH1:1500us\r\n";
  static const uint8_t ch1_max_response[] = "CH1:1900us\r\n";
  static const uint8_t unknown_response[] = "UNKNOWN\r\n";
  const uint8_t *response = unknown_response;
  uint16_t response_length = (uint16_t)(sizeof(unknown_response) - 1U);

  /* Terminals commonly append CR/LF after a typed command. */
  if ((command == (uint8_t)'\r') || (command == (uint8_t)'\n'))
  {
    return;
  }

  switch (command)
  {
  case (uint8_t)'1':
    (void)Servo_SetPulse(SERVO_NUT_US);
    response = servo_nut_response;
    response_length = (uint16_t)(sizeof(servo_nut_response) - 1U);
    break;

  case (uint8_t)'2':
    (void)Servo_SetPulse(SERVO_CENTER_US);
    response = servo_center_response;
    response_length = (uint16_t)(sizeof(servo_center_response) - 1U);
    break;

  case (uint8_t)'3':
    (void)Servo_SetPulse(SERVO_WASHER_US);
    response = servo_washer_response;
    response_length = (uint16_t)(sizeof(servo_washer_response) - 1U);
    break;

  case (uint8_t)'4':
    (void)Servo_SetPulse(SERVO_NUT_US);
    response = ch1_min_response;
    response_length = (uint16_t)(sizeof(ch1_min_response) - 1U);
    break;

  case (uint8_t)'5':
    (void)Servo_SetPulse(SERVO_CENTER_US);
    response = ch1_center_response;
    response_length = (uint16_t)(sizeof(ch1_center_response) - 1U);
    break;

  case (uint8_t)'6':
    (void)Servo_SetPulse(SERVO_WASHER_US);
    response = ch1_max_response;
    response_length = (uint16_t)(sizeof(ch1_max_response) - 1U);
    break;

  case (uint8_t)'C':
  case (uint8_t)'c':
    (void)Servo_SetPulse(SERVO_CENTER_US);
    response = center_response;
    response_length = (uint16_t)(sizeof(center_response) - 1U);
    break;

  case (uint8_t)'N':
  case (uint8_t)'n':
    (void)Servo_SetPulse(SERVO_NUT_US);
    response = servo_nut_response;
    response_length = (uint16_t)(sizeof(servo_nut_response) - 1U);
    break;

  case (uint8_t)'W':
  case (uint8_t)'w':
    (void)Servo_SetPulse(SERVO_WASHER_US);
    response = servo_washer_response;
    response_length = (uint16_t)(sizeof(servo_washer_response) - 1U);
    break;

  case (uint8_t)'X':
  case (uint8_t)'x':
    (void)Servo_SetPulse(SERVO_CENTER_US);
    response = center_response;
    response_length = (uint16_t)(sizeof(center_response) - 1U);
    break;

  default:
    break;
  }

  UART_SendMessage(response, response_length);
}
/* USER CODE END 0 */

/**
  * @brief  The application entry point.
  * @retval int
  */
int main(void)
{

  /* USER CODE BEGIN 1 */

  /* USER CODE END 1 */

  /* MCU Configuration--------------------------------------------------------*/

  /* Reset of all peripherals, Initializes the Flash interface and the Systick. */
  HAL_Init();

  /* USER CODE BEGIN Init */

  /* USER CODE END Init */

  /* Configure the system clock */
  SystemClock_Config();

  /* USER CODE BEGIN SysInit */

  /* USER CODE END SysInit */

  /* Initialize all configured peripherals */
  MX_GPIO_Init();
  MX_TIM2_Init();
  MX_USART1_UART_Init();
  /* USER CODE BEGIN 2 */
  PWM_Start();

  if (HAL_UART_Receive_IT(&huart1, &uart_rx_byte, 1U) != HAL_OK)
  {
    Error_Handler();
  }

  UART_SendMessage(
      system_ready_response,
      (uint16_t)(sizeof(system_ready_response) - 1U));
/* USER CODE END 2 */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  while (1)
  {
    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */
    if (uart_rx_restart_required != 0U)
    {
      if (HAL_UART_Receive_IT(&huart1, &uart_rx_byte, 1U) == HAL_OK)
      {
        uart_rx_restart_required = 0U;
      }
    }

    if (uart_command_pending != 0U)
    {
      uint8_t command;

      __disable_irq();
      command = uart_command;
      uart_command_pending = 0U;
      __enable_irq();

      ProcessCommand(command);
    }
  }
  /* USER CODE END 3 */
}

/**
  * @brief System Clock Configuration
  * @retval None
  */
void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  /** Initializes the RCC Oscillators according to the specified parameters
  * in the RCC_OscInitTypeDef structure.
  */
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSE;
  RCC_OscInitStruct.HSEState = RCC_HSE_ON;
  RCC_OscInitStruct.HSEPredivValue = RCC_HSE_PREDIV_DIV1;
  RCC_OscInitStruct.HSIState = RCC_HSI_ON;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSE;
  RCC_OscInitStruct.PLL.PLLMUL = RCC_PLL_MUL9;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  /** Initializes the CPU, AHB and APB buses clocks
  */
  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV2;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_2) != HAL_OK)
  {
    Error_Handler();
  }
}

/* USER CODE BEGIN 4 */
void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart)
{
  if (huart->Instance == USART1)
  {
    if (uart_command_pending == 0U)
    {
      uart_command = uart_rx_byte;
      uart_command_pending = 1U;
    }

    if (HAL_UART_Receive_IT(&huart1, &uart_rx_byte, 1U) != HAL_OK)
    {
      uart_rx_restart_required = 1U;
    }
  }
}

void HAL_UART_ErrorCallback(UART_HandleTypeDef *huart)
{
  if (huart->Instance == USART1)
  {
    uart_rx_restart_required = 1U;
  }
}
/* USER CODE END 4 */

/**
  * @brief  This function is executed in case of error occurrence.
  * @retval None
  */
void Error_Handler(void)
{
  /* USER CODE BEGIN Error_Handler_Debug */
  /* User can add his own implementation to report the HAL error return state */
  __disable_irq();
  while (1)
  {
  }
  /* USER CODE END Error_Handler_Debug */
}
#ifdef USE_FULL_ASSERT
/**
  * @brief  Reports the name of the source file and the source line number
  *         where the assert_param error has occurred.
  * @param  file: pointer to the source file name
  * @param  line: assert_param error line source number
  * @retval None
  */
void assert_failed(uint8_t *file, uint32_t line)
{
  /* USER CODE BEGIN 6 */
  /* User can add his own implementation to report the file name and line number,
     ex: printf("Wrong parameters value: file %s on line %d\r\n", file, line) */
  /* USER CODE END 6 */
}
#endif /* USE_FULL_ASSERT */
