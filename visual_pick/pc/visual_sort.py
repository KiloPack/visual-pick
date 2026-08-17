import argparse
import sys
from collections import deque

import cv2
import numpy as np
import serial

from serial_test import BAUD_RATE, select_port


# ============================================================
# 参数设置
# ============================================================

CAMERA_ID = 1
DIFF_THRESHOLD = 30
MIN_OBJECT_AREA = 300
APPROX_EPSILON = 0.03

# 检测到零件后先等待曝光和零件稳定，再连续采样。
SETTLE_FRAMES = 8
SAMPLE_FRAMES = 10

# 连续检测到空场达到该帧数后，才允许识别下一件零件。
EMPTY_RESET_FRAMES = 8

COMMANDS = {
    "NUT": b"N",
    "WASHER": b"W",
}


# ============================================================
# 稳定识别状态
# ============================================================

settle_count = 0
empty_count = 0
object_locked = False
locked_object_type = None

vertices_history = deque(maxlen=SAMPLE_FRAMES)
circle_history = deque(maxlen=SAMPLE_FRAMES)
ellipse_error_history = deque(maxlen=SAMPLE_FRAMES)

command_sent_for_object = False
servo_target = "HOLD PREVIOUS"
last_command = "None"
last_reply = "None"
serial_status = "DISCONNECTED"
serial_buffer = bytearray()


def calculate_ellipse_error(contour):
    """计算轮廓相对其最佳拟合椭圆的平均边界误差。"""
    if len(contour) < 5:
        return float("inf")

    (center_x, center_y), (axis_a, axis_b), angle = cv2.fitEllipse(
        contour
    )

    if axis_a <= 0 or axis_b <= 0:
        return float("inf")

    points = contour[:, 0, :].astype(np.float64)
    points[:, 0] -= center_x
    points[:, 1] -= center_y

    theta = np.deg2rad(angle)
    cos_theta = np.cos(theta)
    sin_theta = np.sin(theta)

    rotated_x = (
        points[:, 0] * cos_theta
        + points[:, 1] * sin_theta
    )
    rotated_y = (
        -points[:, 0] * sin_theta
        + points[:, 1] * cos_theta
    )

    normalized_radius = np.sqrt(
        (rotated_x / (axis_a / 2.0)) ** 2
        + (rotated_y / (axis_b / 2.0)) ** 2
    )

    return float(np.mean(np.abs(normalized_radius - 1.0)))


def reset_recognition_state(rearm_command=True):
    """清除上一件零件的识别状态。"""
    global settle_count, empty_count
    global object_locked, locked_object_type
    global command_sent_for_object

    settle_count = 0
    empty_count = 0
    object_locked = False
    locked_object_type = None
    vertices_history.clear()
    circle_history.clear()
    ellipse_error_history.clear()

    if rearm_command:
        command_sent_for_object = False


def classify_vertices(vertices):
    """按最大外轮廓的多边形顶点数给单帧分类。"""
    if 5 <= vertices <= 7:
        return "NUT"
    if vertices >= 8:
        return "WASHER"
    return "UNKNOWN"


def classify_vertex_samples(samples):
    """对10帧单帧类别做严格多数票，未过半则UNKNOWN。"""
    labels = [classify_vertices(value) for value in samples]
    nut_votes = labels.count("NUT")
    washer_votes = labels.count("WASHER")
    unknown_votes = labels.count("UNKNOWN")
    required_votes = len(labels) // 2 + 1

    if nut_votes >= required_votes:
        result = "NUT"
    elif washer_votes >= required_votes:
        result = "WASHER"
    else:
        result = "UNKNOWN"

    return result, nut_votes, washer_votes, unknown_votes


def parse_args():
    """读取可选串口和摄像头参数。"""
    parser = argparse.ArgumentParser(
        description="demo01 视觉算法 + STM32 单舵机分拣"
    )
    parser.add_argument(
        "--port",
        help="串口名称，例如 COM9；省略时自动识别 CH340",
    )
    parser.add_argument(
        "--camera",
        type=int,
        default=CAMERA_ID,
        help=f"摄像头编号，默认 {CAMERA_ID}",
    )
    parser.add_argument(
        "--vision-only",
        action="store_true",
        help="只测试视觉识别，不打开串口、不驱动舵机",
    )
    return parser.parse_args()


def open_sorter_serial(explicit_port):
    """打开指定串口，或自动选择唯一的 CH340。"""
    com_port, ports = select_port(explicit_port)
    print("当前串口：", ", ".join(ports) if ports else "未检测到")
    connection = serial.Serial(
        port=com_port,
        baudrate=BAUD_RATE,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=0,
        write_timeout=1.0,
    )
    connection.reset_input_buffer()
    print(f"已打开 {connection.port}，参数：{BAUD_RATE} 8N1")
    return connection


def send_sort_command(connection, object_type):
    """当前零件确认后只发送一次 N 或 W。"""
    global last_command, servo_target, serial_status

    command = COMMANDS[object_type]
    if connection is None:
        last_command = f"{command.decode('ascii')} (NOT SENT)"
        servo_target = "HOLD PREVIOUS"
        print(f"纯视觉模式：确认 {object_type}，不发送舵机命令。")
        return

    try:
        connection.write(command)
        connection.flush()
    except serial.SerialException as error:
        last_command = f"{command.decode('ascii')} (FAILED)"
        serial_status = f"ERROR: {error}"
        print(f"串口发送失败，不自动重发：{error}", file=sys.stderr)
        return

    last_command = command.decode("ascii")
    if object_type == "NUT":
        servo_target = "LEFT(NUT)"
    else:
        servo_target = "RIGHT(WASHER)"
    print(f"发送一次：{last_command}（{object_type}）")


def poll_serial(connection):
    """非阻塞读取 STM32 文本回复。"""
    global last_reply, serial_status, serial_buffer

    if connection is None:
        return

    try:
        waiting = connection.in_waiting
        if waiting:
            serial_buffer.extend(connection.read(waiting))
            while b"\n" in serial_buffer:
                raw_line, _, remainder = serial_buffer.partition(b"\n")
                serial_buffer = bytearray(remainder)
                reply = raw_line.rstrip(b"\r").decode(
                    "ascii",
                    errors="replace",
                )
                if reply:
                    last_reply = reply
                    print(f"STM32: {reply}")
    except serial.SerialException as error:
        serial_status = f"ERROR: {error}"


# ============================================================
# 打开摄像头
# ============================================================

arguments = parse_args()

if arguments.vision_only:
    serial_connection = None
    serial_status = "VISION ONLY / NO SERIAL"
    print("纯视觉模式：不会打开串口，也不会驱动舵机。")
else:
    try:
        serial_connection = open_sorter_serial(arguments.port)
    except (RuntimeError, serial.SerialException) as error:
        print(f"串口初始化失败：{error}", file=sys.stderr)
        raise SystemExit(1)

    serial_status = f"CONNECTED {serial_connection.port}"

cap = cv2.VideoCapture(arguments.camera, cv2.CAP_DSHOW)

if not cap.isOpened():
    if serial_connection is not None:
        serial_connection.close()
    raise RuntimeError(f"无法打开摄像头 {arguments.camera}")

cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

background = None

print("=" * 50)
print("视觉分拣 V2（稳定识别）")
print("B：保存当前空白检测区作为背景")
print("R：仅重新识别；不会让当前零件重复发送命令")
print("Q：退出")
print("程序启动不回中；识别后保持到下一条 N/W。")
print("=" * 50)


# ============================================================
# 主循环
# ============================================================

try:
    while True:
        ret, frame = cap.read()

        if not ret:
            print("摄像头读取失败")
            break

        # ----------------------------------------------------
        # 1. 设置 ROI
        # ----------------------------------------------------
        height, width = frame.shape[:2]
        x1 = int(width * 0.25)
        y1 = int(height * 0.20)
        x2 = int(width * 0.75)
        y2 = int(height * 0.80)

        roi = frame[y1:y2, x1:x2]
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

        # 每帧的默认值
        object_type = "NO BACKGROUND"
        object_present = False
        contour_area = 0.0
        circularity = 0.0
        vertices = 0
        ellipse_error = float("inf")

        diff = np.zeros_like(gray)
        binary = np.zeros_like(gray)

        # ====================================================
        # 2. 背景差分与特征提取
        # ====================================================
        if background is not None:
            diff = cv2.absdiff(background, gray)
            diff = cv2.GaussianBlur(diff, (5, 5), 0)

            _, binary = cv2.threshold(
                diff,
                DIFF_THRESHOLD,
                255,
                cv2.THRESH_BINARY,
            )

            # 只做开运算，避免闭运算填掉零件中心孔。
            kernel = cv2.getStructuringElement(
                cv2.MORPH_ELLIPSE,
                (3, 3),
            )
            binary = cv2.morphologyEx(
                binary,
                cv2.MORPH_OPEN,
                kernel,
                iterations=1,
            )

            # 只保留最大的白色连通区域。
            num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
                binary,
                connectivity=8,
            )

            if num_labels > 1:
                object_areas = stats[1:, cv2.CC_STAT_AREA]
                largest_label = 1 + int(np.argmax(object_areas))
                largest_area = int(
                    stats[largest_label, cv2.CC_STAT_AREA]
                )

                if largest_area >= MIN_OBJECT_AREA:
                    clean_binary = np.zeros_like(binary)
                    clean_binary[labels == largest_label] = 255
                    binary = clean_binary

                    contours, _ = cv2.findContours(
                        binary,
                        cv2.RETR_EXTERNAL,
                        cv2.CHAIN_APPROX_SIMPLE,
                    )

                    if contours:
                        largest_contour = max(
                            contours,
                            key=cv2.contourArea,
                        )
                        contour_area = cv2.contourArea(largest_contour)
                        perimeter = cv2.arcLength(largest_contour, True)

                        if (
                            contour_area >= MIN_OBJECT_AREA
                            and perimeter > 0
                        ):
                            object_present = True
                            circularity = (
                                4
                                * np.pi
                                * contour_area
                                / (perimeter * perimeter)
                            )

                            # 已验证方案：直接逼近最大外轮廓，不经过凸包。
                            approx = cv2.approxPolyDP(
                                largest_contour,
                                APPROX_EPSILON * perimeter,
                                True,
                            )
                            vertices = len(approx)

                            # 椭圆误差仅保留为调试数据，不参与分类。
                            ellipse_error = calculate_ellipse_error(
                                largest_contour
                            )

                            # 在摄像头原图中框出目标。
                            x, y, w, h = cv2.boundingRect(
                                largest_contour
                            )
                            real_x = x + x1
                            real_y = y + y1

                            approx_on_frame = approx.copy()
                            approx_on_frame[:, 0, 0] += x1
                            approx_on_frame[:, 0, 1] += y1
                            cv2.drawContours(
                                frame,
                                [approx_on_frame],
                                -1,
                                (0, 255, 0),
                                2,
                            )

                            cv2.rectangle(
                                frame,
                                (real_x, real_y),
                                (real_x + w, real_y + h),
                                (0, 255, 255),
                                2,
                            )
                            cv2.putText(
                                frame,
                                f"Area: {int(contour_area)}",
                                (real_x, max(real_y - 15, 25)),
                                cv2.FONT_HERSHEY_SIMPLEX,
                                0.7,
                                (0, 255, 255),
                                2,
                            )
                            cv2.putText(
                                frame,
                                f"Circle: {circularity:.3f}",
                                (real_x, real_y + h + 25),
                                cv2.FONT_HERSHEY_SIMPLEX,
                                0.65,
                                (255, 0, 255),
                                2,
                            )
                            cv2.putText(
                                frame,
                                f"Vertices: {vertices}",
                                (real_x, real_y + h + 50),
                                cv2.FONT_HERSHEY_SIMPLEX,
                                0.65,
                                (255, 0, 255),
                                2,
                            )
                            cv2.putText(
                                frame,
                                f"EllipseErr: {ellipse_error:.3f}",
                                (real_x, real_y + h + 75),
                                cv2.FONT_HERSHEY_SIMPLEX,
                                0.65,
                                (255, 0, 255),
                                2,
                            )
                else:
                    binary[:] = 0

            # =================================================
            # 3. 稳定等待、10 帧中位数分类和单件锁定
            # =================================================
            if object_present:
                empty_count = 0

                if object_locked:
                    # 保持已确认类别，不再用后续抖动帧重复分类。
                    object_type = locked_object_type

                elif settle_count < SETTLE_FRAMES:
                    settle_count += 1
                    object_type = "WAITING"

                else:
                    vertices_history.append(vertices)
                    circle_history.append(circularity)
                    ellipse_error_history.append(ellipse_error)
                    object_type = "SAMPLING"

                    if len(vertices_history) == SAMPLE_FRAMES:
                        median_vertices = float(
                            np.median(vertices_history)
                        )
                        median_circle = float(
                            np.median(circle_history)
                        )
                        median_ellipse_error = float(
                            np.median(ellipse_error_history)
                        )

                        (
                            candidate_object_type,
                            nut_votes,
                            washer_votes,
                            unknown_votes,
                        ) = classify_vertex_samples(
                            list(vertices_history)
                        )

                        object_type = candidate_object_type

                        if candidate_object_type in COMMANDS:
                            locked_object_type = candidate_object_type
                            object_locked = True

                            if not command_sent_for_object:
                                send_sort_command(
                                    serial_connection,
                                    candidate_object_type,
                                )
                                command_sent_for_object = True
                        else:
                            # 首个10帧窗口可能仍包含放置过程中的残影。
                            # UNKNOWN不锁死、不发送命令；保持当前零件在
                            # ROI内时重新等待并采样，直到稳定或被移走。
                            locked_object_type = None
                            object_locked = False
                            print(
                                "UNKNOWN：不发送命令，保持当前舵机位置；"
                                "自动重新采样。"
                            )

                        print(
                            f"确认结果: {object_type}, "
                            f"Vertices中位数={median_vertices:.1f}, "
                            f"Vertices序列={list(vertices_history)}, "
                            f"投票=NUT:{nut_votes}/"
                            f"WASHER:{washer_votes}/"
                            f"UNKNOWN:{unknown_votes}, "
                            f"Circle中位数={median_circle:.3f}, "
                            f"Ellipse误差中位数="
                            f"{median_ellipse_error:.4f}"
                        )

                        if not object_locked:
                            settle_count = 0
                            vertices_history.clear()
                            circle_history.clear()
                            ellipse_error_history.clear()

            else:
                # 大类别会锁定到连续空场 8 帧以后。以前这里从
                # 第一帧就显示 EMPTY，容易让人误以为已经解锁。
                recognition_needs_reset = (
                    object_locked
                    or settle_count > 0
                    or len(vertices_history) > 0
                )
                empty_count += 1

                if empty_count >= EMPTY_RESET_FRAMES:
                    reset_recognition_state()
                    object_type = "EMPTY"
                elif recognition_needs_reset:
                    object_type = "CLEARING"
                else:
                    object_type = "EMPTY"

        poll_serial(serial_connection)

        # ====================================================
        # 4. 画面显示
        # ====================================================
        cv2.rectangle(
            frame,
            (x1, y1),
            (x2, y2),
            (0, 255, 0),
            2,
        )

        status_colors = {
            "NUT": (255, 0, 255),
            "WASHER": (255, 255, 0),
            "EMPTY": (0, 255, 0),
            "UNKNOWN": (0, 0, 255),
            "WAITING": (0, 165, 255),
            "SAMPLING": (0, 165, 255),
            "CLEARING": (0, 165, 255),
            "NO BACKGROUND": (0, 0, 255),
        }
        status_color = status_colors.get(
            object_type,
            (0, 165, 255),
        )

        cv2.putText(
            frame,
            object_type,
            (30, 60),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.5,
            status_color,
            3,
        )

        if object_type == "WAITING":
            progress_text = f"Settle: {settle_count}/{SETTLE_FRAMES}"
        elif object_type == "SAMPLING":
            progress_text = (
                f"Samples: {len(vertices_history)}/{SAMPLE_FRAMES}"
            )
        elif object_type == "CLEARING":
            progress_text = (
                f"Reset: {empty_count}/{EMPTY_RESET_FRAMES}"
            )
        else:
            progress_text = ""

        if progress_text:
            cv2.putText(
                frame,
                progress_text,
                (30, 100),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                status_color,
                2,
            )

        if background is None:
            workflow_state = "WAIT_OBJECT"
        elif object_locked:
            workflow_state = "WAIT_EMPTY"
        elif (
            object_present
            or settle_count > 0
            or len(vertices_history) > 0
        ):
            workflow_state = "CLASSIFYING"
        else:
            workflow_state = "WAIT_OBJECT"

        cv2.putText(
            frame,
            f"State: {workflow_state}",
            (30, 140),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (255, 255, 255),
            2,
        )
        cv2.putText(
            frame,
            f"Servo target: {servo_target}",
            (30, 175),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (255, 255, 255),
            2,
        )
        cv2.putText(
            frame,
            f"Last command: {last_command}",
            (30, 210),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (255, 255, 255),
            2,
        )
        cv2.putText(
            frame,
            f"STM32: {last_reply} / {serial_status}",
            (30, 245),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 255),
            2,
        )

        cv2.imshow("Camera", frame)
        cv2.imshow("Difference", diff)
        cv2.imshow("Binary", binary)

        # ====================================================
        # 5. 键盘控制
        # ====================================================
        key = cv2.waitKey(1) & 0xFF

        if key == ord("b"):
            background = gray.copy()
            reset_recognition_state()
            print("背景已保存。现在可以放入零件。")
        elif key == ord("r"):
            reset_recognition_state(rearm_command=False)
            print("识别锁定已清除；当前零件不会重复发送命令。")
        elif key == ord("q"):
            break

finally:
    cap.release()
    if serial_connection is not None:
        serial_connection.close()
    cv2.destroyAllWindows()
